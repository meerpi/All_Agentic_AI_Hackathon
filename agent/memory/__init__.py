"""
Persistent Memory System — Cross-session memory for the Taskmaster agent.

Three-tier architecture following 2025/2026 agent memory best practices:
- Episodic Memory: Time-stamped workflow events and past interactions
- Semantic Memory: User preferences, learned facts, project context
- Procedural Memory: Learned tool-use patterns and prompt refinements

All memory persisted to data/memory/ as JSON files.
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("taskmaster.memory")

MEMORY_DIR = Path(__file__).parent.parent / "data" / "memory"
MEMORY_DIR.mkdir(parents=True, exist_ok=True)


class EpisodicMemory:
    """
    Time-stamped workflow event history.
    Stores what happened, when, and the outcome.
    """
    FILE = MEMORY_DIR / "episodic.json"

    def __init__(self):
        self.episodes: List[Dict[str, Any]] = []
        self._load()

    def _load(self):
        if self.FILE.exists():
            try:
                with open(self.FILE, "r") as f:
                    self.episodes = json.load(f)
            except Exception as e:
                logger.error(f"Failed to load {self.FILE}: {e}, starting fresh")
                self.episodes = []

    def _save(self):
        with open(self.FILE, "w") as f:
            json.dump(self.episodes[-500:], f, indent=2, default=str)  # Keep last 500

    def record(self, event_type: str, workflow_id: str = "", details: Optional[Dict] = None):
        """Record an episodic event."""
        episode = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "workflow_id": workflow_id,
            "details": details or {},
        }
        self.episodes.append(episode)
        self._save()

    def search(self, keyword: str, limit: int = 10) -> List[Dict]:
        """Simple keyword search across episodes."""
        keyword_lower = keyword.lower()
        results = []
        for ep in reversed(self.episodes):
            text = json.dumps(ep).lower()
            if keyword_lower in text:
                results.append(ep)
                if len(results) >= limit:
                    break
        return results

    def get_recent(self, limit: int = 20) -> List[Dict]:
        return self.episodes[-limit:]


class SemanticMemory:
    """
    User preferences, learned facts, and project context.
    Stores structured knowledge that persists across sessions.
    """
    FILE = MEMORY_DIR / "semantic.json"

    def __init__(self):
        self.facts: Dict[str, Any] = {}
        self._load()

    def _load(self):
        if self.FILE.exists():
            try:
                with open(self.FILE, "r") as f:
                    self.facts = json.load(f)
            except Exception as e:
                logger.error(f"Failed to load {self.FILE}: {e}, starting fresh")
                self.facts = {}

    def _save(self):
        with open(self.FILE, "w") as f:
            json.dump(self.facts, f, indent=2, default=str)

    def store(self, key: str, value: Any, category: str = "general"):
        """Store a fact or preference."""
        if category not in self.facts:
            self.facts[category] = {}
        self.facts[category][key] = {
            "value": value,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        self._save()

    def recall(self, key: str, category: str = "general") -> Optional[Any]:
        """Recall a specific fact."""
        cat = self.facts.get(category, {})
        entry = cat.get(key)
        return entry.get("value") if entry else None

    def search(self, keyword: str) -> List[Dict]:
        """Search across all facts."""
        keyword_lower = keyword.lower()
        results = []
        for cat, entries in self.facts.items():
            for key, entry in entries.items():
                if keyword_lower in key.lower() or keyword_lower in str(entry.get("value", "")).lower():
                    results.append({"category": cat, "key": key, **entry})
        return results

    def get_all(self) -> Dict:
        return self.facts


class ProceduralMemory:
    """
    Learned tool-use patterns and prompt refinements.
    Stores what worked and what didn't for specific tool/goal combinations.
    """
    FILE = MEMORY_DIR / "procedural.json"

    def __init__(self):
        self.procedures: List[Dict[str, Any]] = []
        self._load()

    def _load(self):
        if self.FILE.exists():
            try:
                with open(self.FILE, "r") as f:
                    self.procedures = json.load(f)
            except Exception as e:
                logger.error(f"Failed to load {self.FILE}: {e}, starting fresh")
                self.procedures = []

    def _save(self):
        with open(self.FILE, "w") as f:
            json.dump(self.procedures[-200:], f, indent=2, default=str)

    def record_success(self, tool_name: str, tool_args: Dict, goal_context: str):
        """Record a successful tool call pattern."""
        self.procedures.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": "SUCCESS",
            "tool_name": tool_name,
            "tool_args_keys": list(tool_args.keys()),
            "goal_context": goal_context[:200],
        })
        self._save()

    def record_failure(self, tool_name: str, tool_args: Dict, error: str, goal_context: str):
        """Record a failed tool call to avoid repeating mistakes."""
        self.procedures.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": "FAILURE",
            "tool_name": tool_name,
            "tool_args_keys": list(tool_args.keys()),
            "error": error[:200],
            "goal_context": goal_context[:200],
        })
        self._save()

    def get_patterns_for_tool(self, tool_name: str) -> Dict:
        """Get success/failure patterns for a specific tool."""
        successes = [p for p in self.procedures if p["tool_name"] == tool_name and p["type"] == "SUCCESS"]
        failures = [p for p in self.procedures if p["tool_name"] == tool_name and p["type"] == "FAILURE"]
        return {"successes": len(successes), "failures": len(failures), "recent": self.procedures[-5:]}


class MemoryManager:
    """
    Unified memory interface combining all three memory tiers.
    Provides session-start context injection and end-of-session reflection.
    """

    def __init__(self):
        self.episodic = EpisodicMemory()
        self.semantic = SemanticMemory()
        self.procedural = ProceduralMemory()

    def get_session_context(self) -> str:
        """
        Generate a context string to inject into the system prompt
        at the start of each session (prevents cold-start problem).
        """
        parts = []

        # Recent episodes
        recent = self.episodic.get_recent(5)
        if recent:
            parts.append("## Recent Activity")
            for ep in recent:
                parts.append(f"- [{ep['timestamp'][:16]}] {ep['event_type']}: {json.dumps(ep.get('details', {}))[:100]}")

        # User preferences
        prefs = self.semantic.get_all().get("preferences", {})
        if prefs:
            parts.append("\n## User Preferences")
            for key, entry in list(prefs.items())[:10]:
                parts.append(f"- {key}: {entry.get('value', '')}")

        return "\n".join(parts) if parts else ""

    def reflect_on_workflow(self, workflow_id: str, goal: str, steps_summary: str,
                            status: str, tools_used: List[str]):
        """
        End-of-session reflection: extract and store key learnings.
        Called after each workflow completes.
        """
        self.episodic.record(
            event_type=f"WORKFLOW_{status}",
            workflow_id=workflow_id,
            details={"goal": goal[:200], "tools_used": tools_used},
        )

        # Store tools-used patterns
        for tool in tools_used:
            if status == "COMPLETED":
                self.procedural.record_success(tool, {}, goal)

    def search_all(self, query: str) -> Dict[str, List]:
        """Search across all memory tiers."""
        return {
            "episodic": self.episodic.search(query),
            "semantic": self.semantic.search(query),
            "procedural_recent": self.procedural.procedures[-5:],
        }
