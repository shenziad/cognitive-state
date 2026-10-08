"""Small in-memory continuation tasks; scoring rules are never tool observations."""

from copy import deepcopy
from typing import Any

from .controlled import equal


TOOL_SPEC = [
    {"tool": "observe", "arguments": {"resource": "string"},
     "description": "Observe an available virtual resource. workspace/catalog.json lists operations and resources."},
    {"tool": "execute", "arguments": {"operation": "string"},
     "description": "Execute one named virtual operation from the workspace catalog."},
    {"tool": "finish", "arguments": {"status": "completed or blocked"},
     "description": "End the continuation; completion must follow the original task requirements."},
]


class ContinuationEnvironment:
    tool_spec = TOOL_SPEC

    def __init__(self, fixture: dict[str, Any]):
        self.fixture = deepcopy(fixture)
        self.settings = deepcopy(fixture["initial_state"])
        self.budget = fixture["budget"]
        self.spent = 0
        self.trace: list[dict[str, Any]] = []
        self.finished = False
        self.finish_status: str | None = None

    def catalog(self) -> dict[str, Any]:
        # Definitions and prices only: no task target, history, rubric or hidden state.
        return {
            "operations": [{"name": k, "description": v["description"], "cost": v["cost"]}
                           for k, v in self.fixture["operations"].items()],
            "resources": [{"name": k, "description": v["description"], "cost": v["cost"]}
                          for k, v in self.fixture["observations"].items()],
            "catalog_cost": 0,
        }

    def apply(self, action: Any) -> dict[str, Any]:
        before = deepcopy(self.settings)
        valid, cost, violations, repeated = True, 0, [], False
        observation: dict[str, Any]
        tool, args, definition = None, {}, None
        if not isinstance(action, dict) or set(action) != {"tool", "arguments"}:
            valid = False
        else:
            tool, args = action["tool"], action["arguments"]
            valid = isinstance(tool, str) and isinstance(args, dict) and not self.finished
        if valid and tool == "observe":
            valid = set(args) == {"resource"} and isinstance(args["resource"], str)
            if valid and args["resource"] == "workspace/catalog.json":
                observation = {"content": self.catalog()}
            elif valid and args["resource"] in self.fixture["observations"]:
                definition = self.fixture["observations"][args["resource"]]
            elif valid:
                # Archived resources cannot disclose the removed historical evidence.
                observation = {"error": "Resource unavailable in this continuation"}
        elif valid and tool == "execute":
            valid = (set(args) == {"operation"} and isinstance(args["operation"], str)
                     and args["operation"] in self.fixture["operations"])
            if valid:
                definition = self.fixture["operations"][args["operation"]]
        elif valid and tool == "finish":
            valid = (set(args) == {"status"} and isinstance(args["status"], str)
                     and args["status"] in {"completed", "blocked"})
            if valid:
                self.finished, self.finish_status = True, args["status"]
                observation = {"finished": args["status"]}
        elif valid:
            valid = False
        if not valid:
            observation = {"error": "Invalid tool or arguments"}
        elif definition is not None:
            cost = definition["cost"]
            self.spent += cost
            required = definition.get("required_state", {})
            ready = all(equal(before.get(k), v) for k, v in required.items())
            if self.spent > self.budget:
                violations.append("budget_exceeded")
                observation = {"error": "Workspace credit budget exhausted"}
            elif not ready:
                observation = {"error": "Operational precondition not met"}
                valid = False
            else:
                for forbidden in self.fixture["rubric"].get("forbidden_actions", []):
                    if action == forbidden:
                        violations.append("forbidden_action")
                for rule in self.fixture["rubric"].get("before_action", []):
                    if action == rule["action"] and not all(
                            equal(before.get(k), v) for k, v in rule["state"].items()):
                        violations.append("action_without_required_evidence")
                repeated = bool(definition.get("repeat_key") and before.get(definition["repeat_key"]) is True)
                self.settings.update(deepcopy(definition.get("effects", {})))
                for k, increment in definition.get("increments", {}).items():
                    self.settings[k] += increment
                observation = deepcopy(definition.get("observation", {"applied": args.get("operation")}))
        self.trace.append({"action": deepcopy(action), "observation": observation, "valid": valid,
                           "constraint_ok": not violations, "policy_violations": violations,
                           "cost": cost, "repeated_work": repeated, "state_after": deepcopy(self.settings)})
        return observation

    def evaluate(self) -> dict[str, Any]:
        rubric = self.fixture["rubric"]
        checks = {k: equal(self.settings.get(k), v) for k, v in rubric["target_state"].items()}
        violations = [v for t in self.trace for v in t["policy_violations"]]
        completion = self.finished and self.finish_status == rubric.get("finish_status", "completed")
        constraints = not violations and self.spent <= self.budget
        decisions = {"final_requirements_met": all(checks.values()), "constraints_respected": constraints,
                     "completion_status_correct": completion}
        return {
            "task_success": all(checks.values()) and completion and constraints,
            "final_goal_completion": sum(checks.values()) / len(checks),
            "tool_usage_correctness": sum(t["valid"] for t in self.trace) / len(self.trace) if self.trace else 0.0,
            "decision_consistency": sum(decisions.values()) / len(decisions),
            "goal_checks": checks, "decision_checks": decisions,
            "workspace_credits_spent": self.spent,
            "workspace_credit_budget": self.budget,
            "policy_violation_count": len(violations),
            "repeated_work_count": sum(t["repeated_work"] for t in self.trace),
            "unavailable_observation_count": sum(t["observation"].get("error") == "Resource unavailable in this continuation"
                                                 for t in self.trace),
        }
