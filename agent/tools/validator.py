"""
Validator Tool — Production-Grade Output & Deliverable Validation.
Evaluates structured datasets, deliverables, and payloads against rules, PII safety,
schema constraints, and status criteria.
"""

from typing import Any, Dict, List, Optional
from agent.tools.base import BaseTool


class ValidatorTool(BaseTool):
    name = "validator"
    description = "Validates execution outputs against rules and criteria, returning anomaly flags for self-correction."

    def run(
        self,
        criteria: Optional[List[str]] = None,
        data_to_validate: Optional[Any] = None,
        strict_mode: bool = False,
        **kwargs: Any
    ) -> Dict[str, Any]:
        # Support flexible aliases for input payload
        target_data = (
            data_to_validate
            if data_to_validate is not None
            else kwargs.get("data")
            if kwargs.get("data") is not None
            else kwargs.get("payload")
            if kwargs.get("payload") is not None
            else kwargs.get("input_data")
            if kwargs.get("input_data") is not None
            else kwargs.get("target")
        )

        # Support flexible aliases for rules/criteria
        raw_rules = criteria or kwargs.get("rules") or kwargs.get("validation_rules") or [
            "schema_valid",
            "no_pii_leak",
            "status_ok"
        ]

        if isinstance(raw_rules, str):
            raw_rules = [raw_rules]

        passed_rules: List[str] = []
        violations: List[str] = []

        if target_data is None:
            if strict_mode:
                return {
                    "is_valid": False,
                    "passed_rules_count": 0,
                    "passed_rules": [],
                    "violations": ["Strict validation failed: target data is None or empty."],
                    "recommendation": "RETRY_WITH_CORRECTION"
                }
            target_data = {}

        for rule in raw_rules:
            rule_str = str(rule).strip()
            rule_lower = rule_str.lower().replace("-", "_").replace(" ", "_")

            # 1. PII Detection Criteria
            if any(k in rule_lower for k in ["no_pii", "no_pii_leak", "pii_clean", "pii_safe"]):
                from agent.security import detect_pii
                str_rep = str(target_data)
                if detect_pii(str_rep):
                    violations.append(f"Rule '{rule_str}' failed: Potential PII detected in validated payload.")
                else:
                    passed_rules.append(rule_str)

            # 2. Error / Status OK Criteria
            elif any(k in rule_lower for k in ["no_error", "no_errors", "status_ok", "success"]):
                has_error = False
                err_msg = ""
                if isinstance(target_data, dict):
                    if target_data.get("error"):
                        has_error = True
                        err_msg = str(target_data.get("error"))
                    elif target_data.get("status") in ("FAILED", "ERROR"):
                        has_error = True
                        err_msg = f"Status is {target_data.get('status')}"
                    elif target_data.get("success") is False:
                        has_error = True
                        err_msg = target_data.get("error_message") or "Success flag is False"

                if has_error:
                    violations.append(f"Rule '{rule_str}' failed: Payload indicates failure ({err_msg})")
                else:
                    passed_rules.append(rule_str)

            # 3. Schema & Required Fields Criteria
            elif any(k in rule_lower for k in ["schema_valid", "required_fields", "valid_schema"]):
                required_fields = kwargs.get("required_fields", [])
                if not isinstance(target_data, dict):
                    violations.append(f"Rule '{rule_str}' failed: Target data is not a valid dictionary schema.")
                elif required_fields and not all(f in target_data for f in required_fields):
                    missing = [f for f in required_fields if f not in target_data]
                    violations.append(f"Rule '{rule_str}' failed: Missing required fields: {missing}")
                else:
                    passed_rules.append(rule_str)

            # 4. Custom Declarative / Text-based Rules
            else:
                # Custom descriptive rule (e.g. "Verify all action items exist")
                if isinstance(target_data, dict) and any(
                    isinstance(v, (int, float)) and v == 0 for k, v in target_data.items() if "fail" in k.lower() or "violation" in k.lower()
                ):
                    passed_rules.append(rule_str)
                elif isinstance(target_data, dict) and target_data.get("error"):
                    violations.append(f"Rule '{rule_str}' failed: {target_data.get('error')}")
                else:
                    passed_rules.append(rule_str)

        is_valid = len(violations) == 0

        return {
            "is_valid": is_valid,
            "passed_rules_count": len(passed_rules),
            "passed_rules": passed_rules,
            "violations": violations,
            "recommendation": "PROCEED" if is_valid else "RETRY_WITH_CORRECTION"
        }
