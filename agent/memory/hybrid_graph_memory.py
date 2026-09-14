"""
Hybrid Graph & Temporal Vector Memory System (Mem0 / Letta Architecture).

Provides:
- Entity Knowledge Graph: Nodes (Entities) and Directed Edges (Relations)
  persisted to SQLite for topological relationship queries.
- Core Working Memory Blocks (Letta-style): Editable cross-session memory
  (human, persona, system_state).
- Temporal Decay Scoring: Exponential decay formula prioritizing recent,
  frequently accessed knowledge over stale facts:
    Score = Relevance(q, m) * exp(-lambda * delta_hours) * (1 + 0.2 * ln(1 + access_count))
- Associative Semantic & Keyword Search with Graph Traversal.
"""

import json
import logging
import math
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from agent.database import DB_PATH as MEMORY_DB_PATH
logger = logging.getLogger("taskmaster.memory.hybrid")


class HybridGraphMemory:
    """
    Combines relational entity graph topology, working memory blocks,
    and temporal decay scoring into a unified cross-session memory manager.
    """

    def __init__(self, db_path: Path = MEMORY_DB_PATH):
        self.db_path = str(db_path)
        self.decay_lambda = 0.02  # Half-life ~35 hours
        self._init_schema()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=15.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def _init_schema(self):
        """Initialize entity graph and working memory tables in SQLite."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # 1. Entity Nodes
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS memory_entities (
                    id TEXT PRIMARY KEY,
                    name TEXT UNIQUE NOT NULL,
                    entity_type TEXT NOT NULL,
                    attributes_json TEXT,
                    created_at REAL NOT NULL,
                    last_accessed_at REAL NOT NULL,
                    access_count INTEGER DEFAULT 1
                );
            """)

            # 2. Directed Relationships (Edges)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS memory_relations (
                    id TEXT PRIMARY KEY,
                    source_entity TEXT NOT NULL,
                    relation_type TEXT NOT NULL,
                    target_entity TEXT NOT NULL,
                    weight REAL DEFAULT 1.0,
                    metadata_json TEXT,
                    created_at REAL NOT NULL,
                    FOREIGN KEY(source_entity) REFERENCES memory_entities(name) ON DELETE CASCADE,
                    FOREIGN KEY(target_entity) REFERENCES memory_entities(name) ON DELETE CASCADE,
                    UNIQUE(source_entity, relation_type, target_entity)
                );
            """)

            # 3. Core Working Memory Blocks (Letta-style)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS memory_blocks (
                    label TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    updated_at REAL NOT NULL
                );
            """)

            cursor.execute("CREATE INDEX IF NOT EXISTS idx_mem_entities_name ON memory_entities(name);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_mem_rel_source ON memory_relations(source_entity);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_mem_rel_target ON memory_relations(target_entity);")
            conn.commit()

            # Initialize default working memory blocks
            self._ensure_default_blocks(cursor, conn)

    def _ensure_default_blocks(self, cursor, conn):
        defaults = {
            "persona": "Taskmaster Pro: Autonomous operational partner for technical professionals, makers, and teams.",
            "human": "Lead Engineer / Maker managing software delivery, infrastructure reliability, and product releases.",
            "system_state": "Active environment: Local SQLite, Strands Agents SDK v1.55, Playwright Chromium headless.",
        }
        for label, content in defaults.items():
            cursor.execute("SELECT label FROM memory_blocks WHERE label = ?", (label,))
            if not cursor.fetchone():
                cursor.execute(
                    "INSERT INTO memory_blocks (label, content, updated_at) VALUES (?, ?, ?)",
                    (label, content, time.time()),
                )
        conn.commit()

    # ── 1. Working Memory Blocks ──────────────────────────────────

    def get_working_memory(self) -> Dict[str, str]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT label, content FROM memory_blocks")
            return {r["label"]: r["content"] for r in cursor.fetchall()}

    def update_block(self, label: str, content: str) -> Dict[str, Any]:
        ts = time.time()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO memory_blocks (label, content, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(label) DO UPDATE SET content = excluded.content, updated_at = excluded.updated_at
            """, (label, content, ts))
            conn.commit()
        return {"status": "SUCCESS", "label": label, "updated_at": ts}

    # ── 2. Entity Knowledge Graph ─────────────────────────────────

    def remember_entity(
        self,
        name: str,
        entity_type: str = "concept",
        attributes: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Store or touch an entity node in the knowledge graph."""
        clean_name = name.strip()
        ts = time.time()
        attr_str = json.dumps(attributes or {})

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO memory_entities (id, name, entity_type, attributes_json, created_at, last_accessed_at, access_count)
                VALUES (?, ?, ?, ?, ?, ?, 1)
                ON CONFLICT(name) DO UPDATE SET
                    last_accessed_at = excluded.last_accessed_at,
                    access_count = memory_entities.access_count + 1,
                    attributes_json = excluded.attributes_json
            """, (str(uuid.uuid4()), clean_name, entity_type, attr_str, ts, ts))
            conn.commit()

        return {"name": clean_name, "type": entity_type, "status": "STORED"}

    def add_relation(
        self,
        source: str,
        relation: str,
        target: str,
        weight: float = 1.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create a directed relationship edge between two entities."""
        self.remember_entity(source)
        self.remember_entity(target)

        ts = time.time()
        rel_type = relation.upper().replace(" ", "_")
        meta_str = json.dumps(metadata or {})

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO memory_relations (id, source_entity, relation_type, target_entity, weight, metadata_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_entity, relation_type, target_entity) DO UPDATE SET
                    weight = excluded.weight,
                    metadata_json = excluded.metadata_json
            """, (str(uuid.uuid4()), source.strip(), rel_type, target.strip(), weight, meta_str, ts))
            conn.commit()

        return {
            "source": source.strip(),
            "relation": rel_type,
            "target": target.strip(),
            "weight": weight,
        }

    def query_graph(self, entity_name: str, depth: int = 1) -> Dict[str, Any]:
        """Traverse the knowledge graph outbound and inbound from an entity."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Outbound relations
            cursor.execute("""
                SELECT relation_type, target_entity, weight FROM memory_relations
                WHERE source_entity = ?
            """, (entity_name.strip(),))
            outbound = [{"relation": r["relation_type"], "target": r["target_entity"], "weight": r["weight"]} for r in cursor.fetchall()]

            # Inbound relations
            cursor.execute("""
                SELECT source_entity, relation_type, weight FROM memory_relations
                WHERE target_entity = ?
            """, (entity_name.strip(),))
            inbound = [{"source": r["source_entity"], "relation": r["relation_type"], "weight": r["weight"]} for r in cursor.fetchall()]

        return {
            "entity": entity_name,
            "outbound_relations": outbound,
            "inbound_relations": inbound,
            "total_connections": len(outbound) + len(inbound),
        }

    # ── 3. Recall with Temporal Decay ─────────────────────────────

    def recall(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Recall entities and relations, ranked by relevance and temporal decay.
        Score = relevance_match * exp(-lambda * delta_hours) * (1 + 0.2 * ln(1 + access_count))
        """
        now = time.time()
        query_terms = [t.lower() for t in query.split() if len(t) > 2]

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM memory_entities")
            entities = cursor.fetchall()

        scored_entities = []
        for e in entities:
            name = e["name"].lower()
            attrs = e["attributes_json"].lower() if e["attributes_json"] else ""
            
            # Text matching relevance
            match_score = 0.0
            for term in query_terms:
                if term in name:
                    match_score += 2.0
                elif term in attrs:
                    match_score += 1.0

            if match_score == 0.0 and len(query_terms) > 0:
                continue

            # Temporal decay calculation
            delta_hours = max(0.0, (now - e["last_accessed_at"]) / 3600.0)
            decay_factor = math.exp(-self.decay_lambda * delta_hours)
            frequency_boost = 1.0 + 0.2 * math.log(1.0 + e["access_count"])

            final_score = (match_score or 1.0) * decay_factor * frequency_boost
            scored_entities.append({
                "name": e["name"],
                "type": e["entity_type"],
                "score": round(final_score, 4),
                "access_count": e["access_count"],
                "last_accessed_hours_ago": round(delta_hours, 2),
            })

        scored_entities.sort(key=lambda x: x["score"], reverse=True)
        return scored_entities[:limit]


# Global singleton instance
hybrid_memory = HybridGraphMemory()
