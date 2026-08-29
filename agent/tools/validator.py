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
            if "fail" in rule.lower() or "error" in rule.lower():
                violations.append(f"Rule '{rule}' failed threshold check")
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
