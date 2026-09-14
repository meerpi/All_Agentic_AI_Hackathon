"""
Multi-Agent Pre-Flight Critic & Debate (Debating Agents / MAAS Architecture).

Implements an adversarial verification agent using Strands Agents SDK InterventionHandler:
- Intercepts proposed tool calls before execution.
- Evaluates actions against strict organizational policies:
  1. Recipient Whitelist & Secret Leak Guard (API keys, private keys, suspicious domains).
  2. Destructive Database Guard (blocks unconstrained DROP, TRUNCATE, DELETE without WHERE).
  3. Computational Quota Guard (timeout caps, infinite loop risk).
  4. Schema & Parameter Integrity Guard (prevents empty/placeholder payloads).
- Emits Strands `Guide(feedback=...)` on violation, forcing the Planner to debate/replan.
- Passes clean actions with an `AuditVerificationBadge` to Human-in-the-Loop (HITL) gates.
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from strands.hooks.events import BeforeToolCallEvent
from strands.interventions.actions import Deny, Guide, Proceed
from strands.interventions.handler import InterventionHandler

logger = logging.getLogger("taskmaster.strands_bridge.auditor")

# Default Policy Constraints
AUTHORIZED_DOMAINS = {
    "taskmaster.ai",
    "google.com",
    "gmail.com",
    "company.internal",
    "devpost.com",
    "github.com",
}

SUSPICIOUS_DOMAINS = {
    "malicious.com",
    "darkweb.org",
    "leaked-data.net",
    "attacker.xyz",
    "phishing.io",
}

SECRET_PATTERNS = [
    (re.compile(r"AIzaSy[A-Za-z0-9_-]{28,45}"), "Google API Key"),
    (re.compile(r"gh[pousr]_[A-Za-z0-9]{28,60}"), "GitHub Token"),
    (re.compile(r"xox[baprs]-[0-9a-zA-Z]{10,48}"), "Slack OAuth Token"),
    (re.compile(r"-----BEGIN (?:RSA )?PRIVATE KEY-----"), "Private Cryptographic Key"),
    (re.compile(r"(?:api[_-]?key|secret|password)\s*[:=]\s*['\"][A-Za-z0-9_\-]{8,}['\"]", re.IGNORECASE), "Plaintext Secret/Password"),
]

DESTRUCTIVE_SQL_PATTERNS = [
    (re.compile(r"\bDROP\s+(?:TABLE|DATABASE|SCHEMA)\b", re.IGNORECASE), "DROP TABLE/DATABASE"),
    (re.compile(r"\bTRUNCATE\s+(?:TABLE)?\b", re.IGNORECASE), "TRUNCATE TABLE"),
    (re.compile(r"\bDELETE\s+FROM\s+\w+\s*(?:;|$)(?!.*\bWHERE\b)", re.IGNORECASE), "Unconstrained DELETE without WHERE"),
]


@dataclass
class AuditRecord:
    """Record of a pre-flight audit evaluation."""
    tool_name: str
    tool_args: Dict[str, Any]
    verdict: str  # "PASS", "CRITIQUE", "DENY"
    reason: Optional[str] = None
    policy_name: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    debate_round: int = 1


class PreFlightAuditor(InterventionHandler):
    """
    Adversarial Auditor / Critic Intervention Handler for Strands Agents SDK.
    Acts as an autonomous auditor intercepting tool calls before execution.
    """

    name = "preflight-auditor"

    def __init__(self, max_debate_rounds: int = 3):
        self.max_debate_rounds = max_debate_rounds
        self.audit_log: List[AuditRecord] = []
        self._tool_debate_counts: Dict[str, int] = {}

    def before_tool_call(self, event: BeforeToolCallEvent, **kwargs: Any) -> Any:
        """
        Intercept proposed tool call and run adversarial pre-flight policy evaluation.
        Returns:
            - Guide(feedback=critique) if policy violation detected (triggers model debate/replan)
            - Deny(reason=...) if maximum debate rounds exceeded
            - Proceed() if tool call satisfies all safety policies
        """
        tool_use = getattr(event, "tool_use", {})
        tool_name = tool_use.get("name") if isinstance(tool_use, dict) else getattr(tool_use, "name", "unknown")
        tool_input = tool_use.get("input", {}) if isinstance(tool_use, dict) else getattr(tool_use, "input", {})
        if not isinstance(tool_input, dict):
            tool_input = {}

        tool_key = f"{tool_name}:{sorted(tool_input.keys())}"
        current_round = self._tool_debate_counts.get(tool_key, 0) + 1
        self._tool_debate_counts[tool_key] = current_round

        # 1. Evaluate safety policies
        violation = self._evaluate_policies(tool_name, tool_input)

        if violation:
            policy_name, critique = violation

            # If agent has debated and failed to resolve within max rounds, deny outright
            if current_round > self.max_debate_rounds:
                record = AuditRecord(
                    tool_name=tool_name,
                    tool_args=tool_input,
                    verdict="DENY",
                    reason=f"Exceeded max debate rounds ({self.max_debate_rounds}). Unresolved policy: {policy_name}",
                    policy_name=policy_name,
                    debate_round=current_round,
                )
                self.audit_log.append(record)
                logger.error(f"[AUDITOR DENIED]: {record.reason}")
                return Deny(reason=record.reason)

            # Issue Guide critique back to the planner model to force an adversarial debate/replanning turn
            feedback_msg = (
                f"[PRE-FLIGHT AUDITOR CRITIQUE - Round {current_round}/{self.max_debate_rounds}]\n"
                f"Policy Flagged: {policy_name}\n"
                f"Critique: {critique}\n"
                f"Action Required: Reconsider your parameters or select an alternative safe tool."
            )
            record = AuditRecord(
                tool_name=tool_name,
                tool_args=tool_input,
                verdict="CRITIQUE",
                reason=critique,
                policy_name=policy_name,
                debate_round=current_round,
            )
            self.audit_log.append(record)
            logger.warning(f"[AUDITOR CRITIQUE]: Tool '{tool_name}' failed policy '{policy_name}': {critique}")
            return Guide(feedback=feedback_msg, reason=critique)

        # Policy passed cleanly
        record = AuditRecord(
            tool_name=tool_name,
            tool_args=tool_input,
            verdict="PASS",
            reason="All pre-flight policies satisfied.",
            policy_name="PASSED_ALL",
            debate_round=current_round,
        )
        self.audit_log.append(record)
        logger.info(f"[AUDITOR PASS]: Tool '{tool_name}' verified clean (Round {current_round}).")
        return Proceed()

    def _evaluate_policies(self, tool_name: str, tool_args: Dict[str, Any]) -> Optional[tuple[str, str]]:
        """
        Run policy validation rules. Returns (policy_name, critique_message) or None if compliant.
        """
        args_str = str(tool_args)

        # ── Policy 1: Secret & Credential Leak Guard ───────────────────
        for pattern, secret_type in SECRET_PATTERNS:
            if pattern.search(args_str):
                return (
                    "CREDENTIAL_LEAK_PREVENTION",
                    f"Tool parameters contain potential plaintext credential ({secret_type}). "
                    f"Never transmit secrets in tool parameters. Mask or reference securely.",
                )

        # ── Policy 2: Email & Messaging Domain Whitelist ──────────────
        if tool_name in ("gmail", "slack"):
            recipient = str(tool_args.get("to") or tool_args.get("recipient") or "")
            if recipient and "@" in recipient:
                domain = recipient.split("@")[-1].strip().lower()
                # Check suspicious domains & keywords first
                if any(sus in domain for sus in SUSPICIOUS_DOMAINS) or any(kw in recipient.lower() for kw in ["attacker", "malicious", "phish", "leaks", "unauthorized"]):
                    return (
                        "UNAUTHORIZED_RECIPIENT_DOMAIN",
                        f"Recipient '{recipient}' belongs to an untrusted domain or triggered security filters. "
                        f"External communications are restricted to authorized domains ({', '.join(sorted(AUTHORIZED_DOMAINS))}).",
                    )
                # Whitelist enforcement: if not in allowed domains
                if not any(domain == allowed or domain.endswith("." + allowed) for allowed in AUTHORIZED_DOMAINS):
                    return (
                        "UNAUTHORIZED_RECIPIENT_DOMAIN",
                        f"Recipient domain '@{domain}' is not in corporate whitelist ({', '.join(sorted(AUTHORIZED_DOMAINS))}). "
                        f"Debate or redirect message to an authorized internal contact (e.g., security@taskmaster.ai).",
                    )

        # ── Policy 3: Destructive Database Query Guard ────────────────
        if tool_name in ("db_manager", "python_sandbox"):
            query_content = str(tool_args.get("code") or tool_args.get("query") or tool_args.get("data") or "")
            for pattern, op_type in DESTRUCTIVE_SQL_PATTERNS:
                if pattern.search(query_content):
                    return (
                        "DESTRUCTIVE_DB_OPERATION",
                        f"Destructive operation detected: '{op_type}'. "
                        f"Unconstrained data deletion or schema destruction is forbidden without explicit archival.",
                    )

        # ── Policy 4: Computational Quota & Infinite Loop Guard ───────
        if tool_name == "python_sandbox":
            timeout = int(tool_args.get("timeout_seconds", 15))
            if timeout > 60:
                return (
                    "COMPUTATIONAL_QUOTA_EXCEEDED",
                    f"Requested sandbox timeout ({timeout}s) exceeds maximum allowed safe limit of 60 seconds.",
                )
            code = str(tool_args.get("code", ""))
            if "while True:" in code and "break" not in code:
                return (
                    "INFINITE_LOOP_RISK",
                    "Code contains unconditional 'while True:' without break statement, posing infinite execution risk.",
                )

        # ── Policy 5: Placeholder & Incomplete Parameter Guard ────────
        for k, v in tool_args.items():
            if isinstance(v, str):
                for placeholder in ["<YOUR_API_KEY>", "<REPLACE_ME>", "TODO: FILL", "<TODO>"]:
                    if placeholder in v:
                        return (
                            "PLACEHOLDER_PARAMETER_DETECTED",
                            f"Parameter '{k}' contains unconfigured template placeholder '{placeholder}'. Provide real parameters.",
                        )

        return None

    def get_audit_summary(self) -> Dict[str, Any]:
        """Return quantitative audit metrics for the current session."""
        total = len(self.audit_log)
        passed = sum(1 for r in self.audit_log if r.verdict == "PASS")
        critiques = sum(1 for r in self.audit_log if r.verdict == "CRITIQUE")
        denials = sum(1 for r in self.audit_log if r.verdict == "DENY")

        return {
            "total_evaluations": total,
            "passed_count": passed,
            "critique_debates_count": critiques,
            "denial_count": denials,
            "pass_rate_percent": round((passed / total) * 100.0, 1) if total > 0 else 100.0,
            "recent_records": [r.__dict__ for r in self.audit_log[-10:]],
        }


# Global instance
preflight_auditor = PreFlightAuditor()
