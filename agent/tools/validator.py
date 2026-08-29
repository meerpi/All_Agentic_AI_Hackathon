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
        rules = criteria or ["schema_valid", "no_pii_leak", "status_ok"]
        passed_rules = []
        violations = []

        for rule in rules:
            rule_lower = rule.lower()
            
            # Simple mock validation: check if rule expects a certain condition in the data
            if data_to_validate:
                data_str = str(data_to_validate).lower()
                # If the rule is "no_errors", ensure "error" isn't in the data
                if rule_lower == "no_errors" and ("error" in data_str or "fail" in data_str):
                    violations.append(f"Rule '{rule}' failed: Found error/fail in data")
                # If the rule requires a specific key
                elif rule_lower == "has_status" and "status" not in data_str:
                    violations.append(f"Rule '{rule}' failed: Missing status in data")
                else:
                    passed_rules.append(rule)
            else:
                # If no data is provided, assume it passes unless strict_mode
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
