import sqlite3
import json
from typing import Any, Dict, Optional
from agent.tools.base import BaseTool

# Local SQLite store to simulate Cloud SQL / Firestore persistent memory bank
DB_PATH = "taskmaster.db"


class DBManagerTool(BaseTool):
    name = "db_manager"
    description = "Queries, updates, and persists agent state, records, and task metrics to central storage."

    def __init__(self):
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS agent_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                collection TEXT,
                record_data TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        conn.close()

    def run(
        self,
        action: str = "upsert",
        collection: str = "task_records",
        data: Optional[Dict[str, Any]] = None,
        query_filter: Optional[Dict[str, Any]] = None,
        **kwargs: Any
    ) -> Dict[str, Any]:
        data_to_store = data or {"status": "ACTIVE", "processed_by": "TaskmasterAgent"}

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        if action in ("upsert", "write", "create"):
            cursor.execute(
                "INSERT INTO agent_records (collection, record_data) VALUES (?, ?)",
                (collection, json.dumps(data_to_store))
            )
            conn.commit()
            record_id = cursor.lastrowid
            conn.close()
            return {
                "action": action,
                "collection": collection,
                "record_id": record_id,
                "stored_data": data_to_store,
                "status": "SUCCESS"
            }
        
        elif action in ("query", "read"):
            cursor.execute("SELECT id, record_data, timestamp FROM agent_records WHERE collection = ?", (collection,))
            rows = cursor.fetchall()
            conn.close()
            records = [{"id": r[0], "data": json.loads(r[1]), "timestamp": r[2]} for r in rows]
            return {
                "action": action,
                "collection": collection,
                "result_count": len(records),
                "records": records[:10]
            }

        conn.close()
        return {"action": action, "status": "COMPLETED", "details": "Default operation executed"}
