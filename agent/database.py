"""
SQLite Database & Multi-User Authentication Engine for Taskmaster.

Provides:
- Thread-safe SQLite connection manager with WAL mode
- User registration and authentication with salted PBKDF2-SHA256 password hashing
- Token-based session management
- Segregated per-user chat sessions and message history storage
- Full ACID compliance and automatic schema initialization
"""

import hashlib
import json
import logging
import os
import secrets
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("taskmaster.database")

DB_DIR = Path(__file__).parent.parent / "data"
DB_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DB_DIR / "taskmaster.db"


class DatabaseManager:
    """Thread-safe SQLite database manager for users, sessions, and chat history."""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = str(db_path)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Create and configure a connection with foreign keys and WAL mode."""
        conn = sqlite3.connect(self.db_path, timeout=15.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        return conn

    def _init_db(self):
        """Initialize relational tables and indices."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # 1. Users Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    salt TEXT NOT NULL,
                    full_name TEXT,
                    created_at INTEGER NOT NULL,
                    last_login INTEGER
                );
            """)

            # 2. Auth Tokens Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS auth_tokens (
                    token TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                );
            """)

            # 3. Chat Sessions Table (User-Segregated)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                );
            """)

            # 4. Chat Messages Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    data_json TEXT,
                    timestamp INTEGER NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                );
            """)

            # 5. Operational Tasks Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    user_id TEXT,
                    title TEXT NOT NULL,
                    description TEXT,
                    priority TEXT DEFAULT 'MEDIUM',
                    status TEXT DEFAULT 'PENDING',
                    assigned_to TEXT,
                    due_date TEXT,
                    dependencies_json TEXT,
                    action_payload TEXT,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );
            """)

            # 6. Operational Schedules Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS schedules (
                    id TEXT PRIMARY KEY,
                    user_id TEXT,
                    name TEXT NOT NULL,
                    goal TEXT NOT NULL,
                    interval_minutes INTEGER DEFAULT 60,
                    cron_expression TEXT,
                    status TEXT DEFAULT 'ACTIVE',
                    last_run_at INTEGER,
                    next_run_at INTEGER,
                    created_at INTEGER NOT NULL
                );
            """)

            # 7. Automated Schedule Runs & Anomaly Logs Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS schedule_runs (
                    id TEXT PRIMARY KEY,
                    schedule_id TEXT NOT NULL,
                    schedule_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    summary TEXT,
                    output TEXT,
                    duration_ms INTEGER,
                    is_alert INTEGER DEFAULT 0,
                    created_at INTEGER NOT NULL
                );
            """)

            # Indices for lightning-fast lookups
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_tokens_user ON auth_tokens(user_id);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user ON chat_sessions(user_id, updated_at DESC);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_messages_session ON chat_messages(session_id, timestamp ASC);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_schedules_status ON schedules(status, next_run_at ASC);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_sched_runs ON schedule_runs(schedule_id, created_at DESC);")

            conn.commit()
            logger.info("SQLite database schema initialized successfully with tasks and schedules.")

    # ── Password Hashing Helpers ─────────────────────────────────

    @staticmethod
    def hash_password(password: str, salt: Optional[str] = None) -> Tuple[str, str]:
        """Hash a password with PBKDF2-HMAC-SHA256 and a random salt."""
        if not salt:
            salt = secrets.token_hex(16)
        pwd_hash = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            100_000
        ).hex()
        return pwd_hash, salt

    @staticmethod
    def verify_password(password: str, salt: str, expected_hash: str) -> bool:
        """Verify password against stored hash."""
        calculated_hash, _ = DatabaseManager.hash_password(password, salt)
        return secrets.compare_digest(calculated_hash, expected_hash)

    # ── User & Auth Operations ───────────────────────────────────

    def register_user(self, email: str, password: str, full_name: Optional[str] = None) -> Dict[str, Any]:
        """Register a new user and generate an authentication token."""
        email_clean = email.strip().lower()
        if not email_clean or len(password) < 4:
            raise ValueError("Email and a password of at least 4 characters are required.")

        user_id = str(uuid.uuid4())
        pwd_hash, salt = self.hash_password(password)
        now = int(time.time() * 1000)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    INSERT INTO users (id, email, password_hash, salt, full_name, created_at, last_login)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (user_id, email_clean, pwd_hash, salt, full_name or email_clean.split("@")[0], now, now))
            except sqlite3.IntegrityError:
                raise ValueError("An account with this email address already exists.")

            # Create default first chat session
            default_session_id = str(uuid.uuid4())
            cursor.execute("""
                INSERT INTO chat_sessions (id, user_id, title, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
            """, (default_session_id, user_id, "New Chat", now, now))

            token = secrets.token_urlsafe(32)
            expires_at = now + (30 * 24 * 3600 * 1000)  # 30 days
            cursor.execute("""
                INSERT INTO auth_tokens (token, user_id, created_at, expires_at)
                VALUES (?, ?, ?, ?)
            """, (token, user_id, now, expires_at))

            conn.commit()

        return {
            "token": token,
            "user": {
                "id": user_id,
                "email": email_clean,
                "full_name": full_name or email_clean.split("@")[0],
                "created_at": now
            },
            "default_session_id": default_session_id
        }

    def authenticate_user(self, email: str, password: str) -> Dict[str, Any]:
        """Authenticate user by email and password, returning an auth token."""
        email_clean = email.strip().lower()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE email = ?", (email_clean,))
            user = cursor.fetchone()

            if not user or not self.verify_password(password, user["salt"], user["password_hash"]):
                raise ValueError("Invalid email address or password.")

            user_id = user["id"]
            now = int(time.time() * 1000)
            cursor.execute("UPDATE users SET last_login = ? WHERE id = ?", (now, user_id))

            token = secrets.token_urlsafe(32)
            expires_at = now + (30 * 24 * 3600 * 1000)  # 30 days
            cursor.execute("""
                INSERT INTO auth_tokens (token, user_id, created_at, expires_at)
                VALUES (?, ?, ?, ?)
            """, (token, user_id, now, expires_at))

            conn.commit()

            return {
                "token": token,
                "user": {
                    "id": user_id,
                    "email": user["email"],
                    "full_name": user["full_name"],
                    "created_at": user["created_at"]
                }
            }

    def get_user_by_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Validate token and retrieve user profile."""
        if not token:
            return None

        now = int(time.time() * 1000)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT u.id, u.email, u.full_name, u.created_at, t.expires_at
                FROM auth_tokens t
                JOIN users u ON t.user_id = u.id
                WHERE t.token = ? AND t.expires_at > ?
            """, (token, now))
            row = cursor.fetchone()
            if row:
                return {
                    "id": row["id"],
                    "email": row["email"],
                    "full_name": row["full_name"],
                    "created_at": row["created_at"]
                }
        return None

    def logout_token(self, token: str) -> bool:
        """Revoke an active session token."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM auth_tokens WHERE token = ?", (token,))
            conn.commit()
            return cursor.rowcount > 0

    # ── User Chat Session Operations ─────────────────────────────

    def get_user_sessions(self, user_id: str) -> List[Dict[str, Any]]:
        """Retrieve all chat sessions for a specific user, ordered by most recent."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT s.id, s.title, s.created_at, s.updated_at,
                       (SELECT COUNT(*) FROM chat_messages m WHERE m.session_id = s.id) as message_count
                FROM chat_sessions s
                WHERE s.user_id = ?
                ORDER BY s.updated_at DESC
            """, (user_id,))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def create_session(self, user_id: str, title: str = "New Chat",
                       session_id: Optional[str] = None) -> Dict[str, Any]:
        """Create a new chat session for a user."""
        sid = session_id or str(uuid.uuid4())
        now = int(time.time() * 1000)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR IGNORE INTO chat_sessions (id, user_id, title, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
            """, (sid, user_id, title, now, now))
            conn.commit()

        return {
            "id": sid,
            "user_id": user_id,
            "title": title,
            "created_at": now,
            "updated_at": now,
            "messages": []
        }

    def rename_session(self, session_id: str, user_id: str, new_title: str) -> bool:
        """Rename an existing chat session."""
        now = int(time.time() * 1000)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE chat_sessions
                SET title = ?, updated_at = ?
                WHERE id = ? AND user_id = ?
            """, (new_title.strip(), now, session_id, user_id))
            conn.commit()
            return cursor.rowcount > 0

    def delete_session(self, session_id: str, user_id: str) -> bool:
        """Delete a chat session and all its messages."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM chat_sessions WHERE id = ? AND user_id = ?", (session_id, user_id))
            conn.commit()
            return cursor.rowcount > 0

    # ── Chat Message Operations ──────────────────────────────────

    def get_session_messages(self, session_id: str, user_id: str) -> List[Dict[str, Any]]:
        """Retrieve all messages for a session belonging to a user in chronological order."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Verify session ownership
            cursor.execute("SELECT id FROM chat_sessions WHERE id = ? AND user_id = ?", (session_id, user_id))
            if not cursor.fetchone():
                return []

            cursor.execute("""
                SELECT id, session_id, role, content, data_json, timestamp
                FROM chat_messages
                WHERE session_id = ? AND user_id = ?
                ORDER BY timestamp ASC
            """, (session_id, user_id))
            rows = cursor.fetchall()

            messages = []
            for r in rows:
                data_obj = None
                if r["data_json"]:
                    try:
                        data_obj = json.loads(r["data_json"])
                    except Exception:
                        data_obj = None
                messages.append({
                    "id": r["id"],
                    "session_id": r["session_id"],
                    "role": r["role"],
                    "content": r["content"],
                    "data": data_obj,
                    "timestamp": r["timestamp"]
                })
            return messages

    def add_message(self, session_id: str, user_id: str, role: str,
                    content: str, data: Optional[Dict[str, Any]] = None,
                    timestamp: Optional[int] = None) -> Dict[str, Any]:
        """Save a new chat message and touch the session timestamp."""
        msg_id = str(uuid.uuid4())
        ts = timestamp or int(time.time() * 1000)
        data_str = json.dumps(data) if data else None

        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Auto-create session if not present
            cursor.execute("SELECT id FROM chat_sessions WHERE id = ? AND user_id = ?", (session_id, user_id))
            if not cursor.fetchone():
                title_preview = content[:32] + "..." if len(content) > 32 else content
                cursor.execute("""
                    INSERT INTO chat_sessions (id, user_id, title, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (session_id, user_id, title_preview or "New Chat", ts, ts))
            else:
                cursor.execute("UPDATE chat_sessions SET updated_at = ? WHERE id = ?", (ts, session_id))

            cursor.execute("""
                INSERT INTO chat_messages (id, session_id, user_id, role, content, data_json, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (msg_id, session_id, user_id, role, content, data_str, ts))
            conn.commit()

        return {
            "id": msg_id,
            "session_id": session_id,
            "role": role,
            "content": content,
            "data": data,
            "timestamp": ts
        }

    # ── Task Management Methods ──────────────────────────────────

    def create_task(
        self,
        title: str,
        description: str = "",
        priority: str = "MEDIUM",
        assigned_to: Optional[str] = None,
        due_date: Optional[str] = None,
        dependencies: Optional[List[str]] = None,
        action_payload: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
        task_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        tid = task_id or f"TSK-{secrets.token_hex(3).upper()}"
        ts = int(time.time() * 1000)
        deps_str = json.dumps(dependencies or [])
        payload_str = json.dumps(action_payload or {})

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO tasks (id, user_id, title, description, priority, status, assigned_to, due_date, dependencies_json, action_payload, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 'PENDING', ?, ?, ?, ?, ?, ?)
            """, (tid, user_id, title, description, priority.upper(), assigned_to, due_date, deps_str, payload_str, ts, ts))
            conn.commit()

        return {
            "id": tid,
            "title": title,
            "description": description,
            "priority": priority.upper(),
            "status": "PENDING",
            "assigned_to": assigned_to,
            "due_date": due_date,
            "dependencies": dependencies or [],
            "created_at": ts,
        }

    def list_tasks(self, status: Optional[str] = None, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT * FROM tasks WHERE 1=1"
            params = []
            if status:
                query += " AND status = ?"
                params.append(status.upper())
            if user_id:
                query += " AND user_id = ?"
                params.append(user_id)
            query += " ORDER BY created_at DESC"
            cursor.execute(query, params)
            rows = cursor.fetchall()

        results = []
        for r in rows:
            results.append({
                "id": r["id"],
                "title": r["title"],
                "description": r["description"],
                "priority": r["priority"],
                "status": r["status"],
                "assigned_to": r["assigned_to"],
                "due_date": r["due_date"],
                "dependencies": json.loads(r["dependencies_json"]) if r["dependencies_json"] else [],
                "created_at": r["created_at"],
                "updated_at": r["updated_at"],
            })
        return results

    def update_task_status(self, task_id: str, status: str) -> Optional[Dict[str, Any]]:
        ts = int(time.time() * 1000)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?", (status.upper(), ts, task_id))
            if cursor.rowcount == 0:
                return None
            cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
            r = cursor.fetchone()
            conn.commit()
            if not r:
                return None
            return {
                "id": r["id"],
                "title": r["title"],
                "status": r["status"],
                "priority": r["priority"],
                "updated_at": ts,
            }

    # ── Scheduling Methods ───────────────────────────────────────

    def create_schedule(
        self,
        name: str,
        goal: str,
        interval_minutes: int = 60,
        cron_expression: Optional[str] = None,
        user_id: Optional[str] = None,
        schedule_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        sid = schedule_id or f"SCHED-{secrets.token_hex(3).upper()}"
        ts = int(time.time() * 1000)
        next_run = ts + (interval_minutes * 60 * 1000)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO schedules (id, user_id, name, goal, interval_minutes, cron_expression, status, last_run_at, next_run_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?, 'ACTIVE', NULL, ?, ?)
            """, (sid, user_id, name, goal, interval_minutes, cron_expression, next_run, ts))
            conn.commit()

        return {
            "id": sid,
            "name": name,
            "goal": goal,
            "interval_minutes": interval_minutes,
            "cron_expression": cron_expression,
            "status": "ACTIVE",
            "next_run_at": next_run,
            "created_at": ts,
        }

    def list_schedules(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT * FROM schedules"
            params = []
            if status:
                query += " WHERE status = ?"
                params.append(status.upper())
            query += " ORDER BY next_run_at ASC"
            cursor.execute(query, params)
            rows = cursor.fetchall()

        return [{
            "id": r["id"],
            "name": r["name"],
            "goal": r["goal"],
            "interval_minutes": r["interval_minutes"],
            "cron_expression": r["cron_expression"],
            "status": r["status"],
            "last_run_at": r["last_run_at"],
            "next_run_at": r["next_run_at"],
            "created_at": r["created_at"],
        } for r in rows]

    def get_due_schedules(self, current_time_ms: Optional[int] = None) -> List[Dict[str, Any]]:
        """Retrieve active schedules whose next_run_at timestamp is due."""
        ts = current_time_ms or int(time.time() * 1000)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM schedules 
                WHERE status = 'ACTIVE' AND (next_run_at IS NULL OR next_run_at <= ?)
                ORDER BY next_run_at ASC
            """, (ts,))
            rows = cursor.fetchall()

        return [{
            "id": r["id"],
            "name": r["name"],
            "goal": r["goal"],
            "interval_minutes": r["interval_minutes"],
            "cron_expression": r["cron_expression"],
            "status": r["status"],
            "last_run_at": r["last_run_at"],
            "next_run_at": r["next_run_at"],
            "created_at": r["created_at"],
        } for r in rows]

    def update_schedule_next_run(
        self,
        schedule_id: str,
        last_run_at: int,
        next_run_at: int,
        status: str = "ACTIVE",
    ) -> None:
        """Update last_run and next_run timestamps for a schedule."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE schedules 
                SET last_run_at = ?, next_run_at = ?, status = ?
                WHERE id = ?
            """, (last_run_at, next_run_at, status.upper(), schedule_id))
            conn.commit()

    def record_schedule_run(
        self,
        schedule_id: str,
        schedule_name: str,
        status: str,
        summary: str,
        output: str = "",
        duration_ms: int = 0,
        is_alert: bool = False,
        run_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Record an execution log entry for an autonomous heartbeat schedule run."""
        rid = run_id or f"RUN-{secrets.token_hex(4).upper()}"
        ts = int(time.time() * 1000)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO schedule_runs (id, schedule_id, schedule_name, status, summary, output, duration_ms, is_alert, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (rid, schedule_id, schedule_name, status.upper(), summary, output, duration_ms, 1 if is_alert else 0, ts))
            conn.commit()

        return {
            "id": rid,
            "schedule_id": schedule_id,
            "schedule_name": schedule_name,
            "status": status.upper(),
            "summary": summary,
            "duration_ms": duration_ms,
            "is_alert": bool(is_alert),
            "created_at": ts,
        }

    def list_schedule_runs(self, schedule_id: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieve historical schedule run records."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT * FROM schedule_runs"
            params = []
            if schedule_id:
                query += " WHERE schedule_id = ?"
                params.append(schedule_id)
            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)
            cursor.execute(query, params)
            rows = cursor.fetchall()

        return [{
            "id": r["id"],
            "schedule_id": r["schedule_id"],
            "schedule_name": r["schedule_name"],
            "status": r["status"],
            "summary": r["summary"],
            "output": r["output"],
            "duration_ms": r["duration_ms"],
            "is_alert": bool(r["is_alert"]),
            "created_at": r["created_at"],
        } for r in rows]


# Global singleton instance
db = DatabaseManager()
