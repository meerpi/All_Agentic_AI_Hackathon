from typing import Any, Dict, List, Optional
from agent.tools.base import BaseTool


class ValidatorTool(BaseTool):
    name = "validator"
    description = "Validates execution outputs against rules and criteria, returning anomaly flags for self-correction."

    def run(
        self,
        criteria: Optional[List[str]] = None,
        data_to_validate: Optional[Dict[str, Any]] = None,
        strict_mode: bool = False,
        **kwargs: Any
    ) -> Dict[str, Any]:
        target_data = data_to_validate or kwargs.get("input_data")
        rules = criteria or ["schema_valid", "no_pii_leak", "status_ok"]
        passed_rules = []
        violations = []

        for rule in rules:
            rule_lower = rule.lower()
            
            if target_data:
                if rule_lower == "no_pii":
                    from agent.security import detect_pii
                    if detect_pii(str(target_data)):
                        violations.append(f"Rule '{rule}' failed: Potential PII detected in data")
                    else:
                        passed_rules.append(rule)
                elif rule_lower == "no_errors":
                    if isinstance(target_data, dict) and target_data.get("error"):
                        violations.append(f"Rule '{rule}' failed: Status indicates an error")
                    else:
                        passed_rules.append(rule)
                elif rule_lower == "schema_valid":
                    required_fields = kwargs.get("required_fields", [])
                    if not isinstance(target_data, dict):
                        violations.append(f"Rule '{rule}' failed: Data is not a valid dictionary schema")
                    elif not all(field in target_data for field in required_fields):
                        missing = [f for f in required_fields if f not in target_data]
                        violations.append(f"Rule '{rule}' failed: Missing required fields: {missing}")
                    else:
                        passed_rules.append(rule)
                else:
                    passed_rules.append(rule)
            else:
                if strict_mode:
                    violations.append(f"Rule '{rule}' failed: No data provided for strict validation")
                else:
                    passed_rules.append(rule)

        is_valid = len(violations) == 0

        return {
            "is_valid": is_valid,
            "passed_rules_count": len(passed_rules),
            "passed_rules": passed_rules,
            "violations": violations,
            "recommendation": "PROCEED" if is_valid else "RETRY_WITH_CORRECTION"
        }
