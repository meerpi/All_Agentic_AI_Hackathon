"""
Guardrails Package — Input/Output/Execution Rails.

Distinct from self-correction (which retries after failure).
Guardrails PREVENT bad inputs from reaching the LLM and
bad outputs from reaching the user/tools.

Three rail types (inspired by NVIDIA NeMo Guardrails):
- Input Rails: Prompt injection detection, topic boundary enforcement
- Output Rails: PII masking, hallucination flagging, schema validation
- Execution Rails: Tool-call parameter validation before execution
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("taskmaster.guardrails")


# ── Input Rails ────────────────────────────────────────────────

# Known prompt injection patterns
INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(a|an)\s+", re.IGNORECASE),
    re.compile(r"disregard\s+(all\s+)?prior", re.IGNORECASE),
    re.compile(r"system\s*prompt\s*:", re.IGNORECASE),
    re.compile(r"new\s+instructions?\s*:", re.IGNORECASE),
    re.compile(r"override\s+(system|safety)", re.IGNORECASE),
    re.compile(r"act\s+as\s+if\s+you", re.IGNORECASE),
    re.compile(r"forget\s+(everything|all)", re.IGNORECASE),
    re.compile(r"do\s+not\s+follow\s+(your|the)\s+(rules|guidelines)", re.IGNORECASE),
    re.compile(r"pretend\s+you\s+(are|have)\s+no\s+(restrictions|rules)", re.IGNORECASE),
]

DANGEROUS_CODE_PATTERNS = [
    re.compile(r"rm\s+-rf\s+/", re.IGNORECASE),
    re.compile(r"DROP\s+(TABLE|DATABASE|SCHEMA)", re.IGNORECASE),
    re.compile(r"DELETE\s+FROM\s+\w+\s*(;|$|WHERE\s+1\s*=\s*1)", re.IGNORECASE),
    re.compile(r"TRUNCATE\s+TABLE", re.IGNORECASE),
    re.compile(r"exec\s*\(", re.IGNORECASE),
    re.compile(r"__import__\s*\(", re.IGNORECASE),
    re.compile(r"subprocess\.(call|run|Popen)", re.IGNORECASE),
]


class InputRailResult:
    """Result of input rail validation."""
    def __init__(self, passed: bool, violations: List[str] = None):
        self.passed = passed
        self.violations = violations or []


def check_input_rails(user_input: str) -> InputRailResult:
    """
    Screen user input for prompt injection and dangerous patterns.
    Returns InputRailResult with pass/fail and violation details.
    """
    violations = []

    # Check prompt injection patterns
    for pattern in INJECTION_PATTERNS:
        if pattern.search(user_input):
            violations.append(f"Potential prompt injection detected: '{pattern.pattern}'")

    # Check for dangerous code
    for pattern in DANGEROUS_CODE_PATTERNS:
        if pattern.search(user_input):
            violations.append(f"Dangerous code pattern detected: '{pattern.pattern}'")

    # Check for excessive length (potential context stuffing)
    if len(user_input) > 50000:
        violations.append(f"Input exceeds maximum length ({len(user_input)} > 50000 chars)")

    return InputRailResult(passed=len(violations) == 0, violations=violations)


# ── Output Rails ───────────────────────────────────────────────

def check_output_rails(output: str, mask_pii: bool = True) -> Tuple[str, List[str]]:
    """
    Validate and sanitize LLM output before returning to user.
    Returns (sanitized_output, warnings).
    """
    warnings = []

    if not output:
        return output, ["Empty output from LLM"]

    sanitized = output

    # PII masking in outputs
    if mask_pii:
        from agent.security import mask_pii as do_mask, detect_pii
        pii_findings = detect_pii(output)
        if pii_findings:
            warnings.append(f"PII detected in output: {len(pii_findings)} items masked")
            sanitized = do_mask(sanitized)

    # Check for leaked system prompt fragments
    system_markers = ["<identity>", "<behavioral_rules>", "Taskmaster Autonomous Agent Engine", "TASKMASTER_SYSTEM_PROMPT"]
    for marker in system_markers:
        if marker in sanitized:
            warnings.append("System prompt leak detected — redacting")
            sanitized = sanitized.replace(marker, "[REDACTED]")

    return sanitized, warnings


# ── Execution Rails ────────────────────────────────────────────

# Validation rules per tool and action
TOOL_VALIDATION_RULES = {
    "gmail": {
        "action_required_fields": {
            "send_email": ["to", "subject"],
            "create_draft": ["to"],
        },
        "field_validators": {
            "to": lambda v: "@" in str(v) or str(v).startswith("$"),
        },
    },
    "google_docs": {
        "action_required_fields": {
            "create_document": ["title"],
        },
    },
    "google_sheets": {
        "action_required_fields": {
            "append_rows": ["rows"],
            "write_range": ["rows"],
        },
    },
    "google_calendar": {
        "action_required_fields": {
            "create_event": ["summary"],
        },
    },
    "jira": {
        "action_required_fields": {
            "create": ["summary"],
            "create_issue": ["summary"],
        },
    },
    "db_manager": {
        "blocked_patterns": [
            re.compile(r"DROP\s+(TABLE|DATABASE)", re.IGNORECASE),
            re.compile(r"TRUNCATE", re.IGNORECASE),
        ],
    },
    "docker_sandbox": {
        "blocked_patterns": [
            re.compile(r"rm\s+-rf\s+/", re.IGNORECASE),
            re.compile(r"--privileged", re.IGNORECASE),
        ],
    },
    "browser_controller": {
        "action_required_fields": {
            "navigate": ["url"],
        },
        "blocked_patterns": [
            re.compile(r"bankofamerica\.com|chase\.com|wellsfargo\.com|paypal\.com\/signin|checkout\.stripe\.com", re.IGNORECASE),
        ],
    },
    "media_controller": {
        "action_required_fields": {
            "youtube_play": [],
            "youtube_search": [],
            "spotify_play": ["query"],
        },
        "action_alternative_fields": {
            "youtube_play": [["query"], ["url"]],
        },
    },
    "os_desktop_tool": {
        "action_required_fields": {
            "mouse_click": ["x", "y"],
        },
    },
}


def screen_page_content_injection(content: str) -> Tuple[bool, List[str]]:
    """
    Screen untrusted webpage content (DOM/ARIA text) for embedded prompt injection attacks.
    Returns (has_injection, detected_patterns).
    """
    detected = []
    for pattern in INJECTION_PATTERNS:
        if pattern.search(content):
            detected.append(pattern.pattern)
    return len(detected) > 0, detected


class ExecutionRailResult:
    """Result of execution rail validation."""
    def __init__(self, passed: bool, violations: List[str] = None,
                 sanitized_args: Optional[Dict] = None):
        self.passed = passed
        self.violations = violations or []
        self.sanitized_args = sanitized_args


def check_execution_rails(tool_name: str, tool_args: Dict[str, Any]) -> ExecutionRailResult:
    """
    Validate tool-call parameters BEFORE execution.
    Prevents dangerous operations and validates required fields based on action.
    """
    violations = []
    rules = TOOL_VALIDATION_RULES.get(tool_name, {})
    action = tool_args.get("action", "").lower()

    # Alias normalization
    if tool_name == "gmail" and "recipient" in tool_args and "to" not in tool_args:
        tool_args["to"] = tool_args["recipient"]
    if tool_name == "google_docs" and "text" in tool_args and "content" not in tool_args:
        tool_args["content"] = tool_args["text"]

    # Check action-specific required fields
    if not action and (("subject" in tool_args or "body" in tool_args or "to" in tool_args) and tool_name == "gmail"):
        action = "send_email"

    # Infer media_controller action from args when LLM omits it
    if not action and tool_name == "media_controller":
        if any(k in tool_args for k in ("query", "url", "video_url", "search_query")):
            action = "youtube_play"
            tool_args["action"] = action
        elif any(k in tool_args for k in ("track", "artist", "album")):
            action = "spotify_play"
            tool_args["action"] = action

    action_reqs = rules.get("action_required_fields", {}).get(action, [])
    for field in action_reqs:
        if field not in tool_args or not tool_args[field]:
            violations.append(f"Missing required field '{field}' for tool '{tool_name}' (action: {action})")

    # Check action_alternative_fields — at least one alternative group must be satisfied
    alt_field_groups = rules.get("action_alternative_fields", {}).get(action)
    if alt_field_groups:
        has_any = any(
            all(f in tool_args and tool_args[f] for f in group)
            for group in alt_field_groups
        )
        if not has_any:
            options = " or ".join(str(g) for g in alt_field_groups)
            violations.append(f"Tool '{tool_name}' action '{action}' requires at least one of: {options}")

    # Run field-level validators
    for field, validator in rules.get("field_validators", {}).items():
        if field in tool_args and tool_args[field]:
            try:
                if not validator(tool_args[field]):
                    violations.append(f"Invalid value for '{field}' in tool '{tool_name}'")
            except Exception:
                pass

    # Check blocked patterns in all string args
    blocked = rules.get("blocked_patterns", [])
    if blocked:
        args_text = json.dumps(tool_args, default=str)
        for pattern in blocked:
            if pattern.search(args_text):
                violations.append(f"Blocked pattern detected in '{tool_name}' args: '{pattern.pattern}'")

    return ExecutionRailResult(
        passed=len(violations) == 0,
        violations=violations,
        sanitized_args=tool_args,
    )
