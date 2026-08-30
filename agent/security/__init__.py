"""
Security Package — Audit logging, PII masking, risk registry, secrets validation.
"""

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("taskmaster.security")

AUDIT_LOG_DIR = Path(__file__).parent.parent.parent / "data" / "audit_logs"
AUDIT_LOG_DIR.mkdir(parents=True, exist_ok=True)


# ── Risk Registry ──────────────────────────────────────────────

# Tools classified by risk level for HITL gating
TOOL_RISK_REGISTRY: Dict[str, str] = {
    # HIGH risk — external side effects, irreversible
    "gmail": "HIGH",
    "google_calendar": "MEDIUM",
    "google_docs": "MEDIUM",
    "google_sheets": "MEDIUM",
    "jira": "HIGH",
    "github": "HIGH",
    "slack": "HIGH",
    "telegram": "MEDIUM",
    "action_dispatcher": "HIGH",
    # LOW risk — read-only or local
    "data_extractor": "LOW",
    "db_manager": "MEDIUM",
    "validator": "LOW",
    "report_generator": "LOW",
    "python_sandbox": "HIGH",
    "docker_sandbox": "CRITICAL",
    # Autonomous Browser & Desktop Automation
    "browser_controller": "HIGH",
    "os_desktop_tool": "HIGH",
    "media_controller": "MEDIUM",
}


def get_tool_risk(tool_name: str) -> str:
    """Get the risk level for a tool."""
    return TOOL_RISK_REGISTRY.get(tool_name, "MEDIUM")


def requires_approval(tool_name: str, approval_mode: bool = False) -> bool:
    """Check if a tool call requires human approval given the current mode."""
    if not approval_mode:
        return False
    risk = get_tool_risk(tool_name)
    return risk in ("HIGH", "CRITICAL")


# ── PII Masking ────────────────────────────────────────────────

PII_PATTERNS = {
    "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),
    "phone": re.compile(r"\b\+?1?\d{9,15}\b"),
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "credit_card": re.compile(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b"),
    "api_key": re.compile(r"\b(sk-[a-zA-Z0-9]{20,}|ATATT[a-zA-Z0-9]{20,}|AIza[a-zA-Z0-9_-]{35})\b"),
}


def mask_pii(text: str, categories: Optional[List[str]] = None) -> str:
    """
    Mask PII in text. If categories is None, mask all known patterns.
    Returns masked text with [REDACTED_<type>] placeholders.
    """
    if not text:
        return text

    patterns_to_check = PII_PATTERNS if categories is None else {
        k: v for k, v in PII_PATTERNS.items() if k in categories
    }

    masked = text
    for pii_type, pattern in patterns_to_check.items():
        masked = pattern.sub(f"[REDACTED_{pii_type.upper()}]", masked)
    return masked


def detect_pii(text: str) -> List[Dict[str, str]]:
    """Detect PII in text without masking. Returns list of findings."""
    findings = []
    for pii_type, pattern in PII_PATTERNS.items():
        matches = pattern.findall(text)
        for match in matches:
            findings.append({"type": pii_type, "value": mask_pii(match)})
    return findings


# ── Audit Logger ───────────────────────────────────────────────

class AuditLogger:
    """Structured audit trail: who called what tool with what args, when."""

    def __init__(self):
        self._log_file = AUDIT_LOG_DIR / f"audit_{datetime.now().strftime('%Y-%m-%d')}.jsonl"

    def log(self, event_type: str, tool_name: str = "",
            tool_args: Optional[Dict] = None, workflow_id: str = "",
            step_number: Optional[int] = None, result_status: str = "",
            details: Optional[Dict] = None):
        """Append an audit entry as a JSON line."""
        # Mask any PII in tool_args before logging
        safe_args = {}
        if tool_args:
            safe_args = json.loads(mask_pii(json.dumps(tool_args, default=str)))

        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "tool_name": tool_name,
            "tool_args": safe_args,
            "workflow_id": workflow_id,
            "step_number": step_number,
            "result_status": result_status,
            "details": details or {},
        }

        try:
            with open(self._log_file, "a") as f:
                f.write(json.dumps(entry, default=str) + "\n")
        except Exception as e:
            logger.error(f"Audit log write failed: {e}")

    def get_entries(self, workflow_id: Optional[str] = None,
                    limit: int = 100) -> List[Dict]:
        """Read audit entries, optionally filtered by workflow_id."""
        entries = []
        try:
            for log_file in sorted(AUDIT_LOG_DIR.glob("audit_*.jsonl"), reverse=True):
                with open(log_file, "r") as f:
                    for line in f:
                        try:
                            entry = json.loads(line.strip())
                            if workflow_id and entry.get("workflow_id") != workflow_id:
                                continue
                            entries.append(entry)
                            if len(entries) >= limit:
                                return entries
                        except json.JSONDecodeError:
                            continue
        except Exception as e:
            logger.error(f"Audit log read failed: {e}")
        return entries


# ── Secrets Validation ─────────────────────────────────────────

def validate_secrets() -> Dict[str, Any]:
    """Check that required secrets are present and not placeholder values."""
    import os
    placeholders = {"mock_key", "your_gemini_api_key_here", "your_key_here", ""}

    checks = {}
    for key in ["GEMINI_API_KEY", "GEMINI_BACKUP_API_KEY", "JIRA_API_TOKEN"]:
        val = os.environ.get(key, "")
        checks[key] = {
            "present": bool(val and val not in placeholders),
            "length": len(val) if val else 0,
        }
    return checks


# Global instances
audit_logger = AuditLogger()
