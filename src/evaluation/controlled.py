"""A deterministic, in-memory repair environment; never modifies real systems."""

from copy import deepcopy
from typing import Any


TOOL_SPEC = [
    {"tool": "read_file", "arguments": {"path": "string"}, "description": "Read a virtual file."},
    {"tool": "set_config", "arguments": {"key": "string", "value": "JSON scalar"},
     "description": "Change one existing key in config/service.json."},
    {"tool": "run_check", "arguments": {}, "description": "Test the current service configuration."},
    {"tool": "finish", "arguments": {"status": "completed or blocked"}, "description": "End the run."},
]


def equal(value: Any, expected: Any) -> bool:
    return type(value) is type(expected) and value == expected


class ControlledEnvironment:
    def __init__(self, fixture: dict[str, Any]):
        self.files = deepcopy(fixture["files"])
        self.settings = self.files["config/service.json"]
        self.initial = deepcopy(self.settings)
        self.rubric = fixture["rubric"]
        self.trace: list[dict[str, Any]] = []
        self.finished = False
        self.verified = False
        self.evidence_read = False

    def apply(self, action: Any) -> dict[str, Any]:
        observation: dict[str, Any] = {}
        valid, constraint_ok, informed = True, True, True
        tool, args = None, {}
        if not isinstance(action, dict) or set(action) != {"tool", "arguments"}:
            valid = False
        else:
            tool, args = action["tool"], action["arguments"]
            valid = isinstance(tool, str) and isinstance(args, dict)
        if self.finished:
            valid = False
        if valid and tool == "read_file":
            valid = set(args) == {"path"} and isinstance(args["path"], str) and args["path"] in self.files
            if valid:
                observation = {"content": deepcopy(self.files[args["path"]])}
                if args["path"] == self.rubric["evidence_path"]:
                    self.evidence_read = True
        elif valid and tool == "set_config":
            valid = (set(args) == {"key", "value"} and isinstance(args["key"], str)
                     and args["key"] in self.settings and type(args["value"]) in (str, int, float, bool))
            if valid:
                informed = self.evidence_read
                constraint_ok = args["key"] not in self.rubric["protected_keys"]
                self.settings[args["key"]] = args["value"]
                self.verified = False
                observation = {"updated": args["key"]}
        elif valid and tool == "run_check":
            valid = not args
            if valid:
                self.verified = all(self.goal_checks().values())
                observation = {"checks_passed": self.verified}
        elif valid and tool == "finish":
            valid = set(args) == {"status"} and args["status"] in ("completed", "blocked")
            if valid:
                self.finished = True
                observation = {"finished": args["status"]}
        elif valid:
            valid = False
        if not valid:
            observation = {"error": "Invalid tool name, arguments, path, or action after finish"}
        self.trace.append({"action": deepcopy(action), "observation": observation, "valid": valid,
                           "constraint_ok": constraint_ok, "evidence_before_change": informed,
                           "verified_after": self.verified})
        return observation

    def goal_checks(self) -> dict[str, bool]:
        checks = {f"target:{key}": equal(self.settings.get(key), value)
                  for key, value in self.rubric["target_settings"].items()}
        checks.update({f"preserved:{key}": equal(self.settings[key], self.initial[key])
                       for key in self.rubric["protected_keys"]})
        return checks

    def evaluate(self) -> dict[str, Any]:
        checks = self.goal_checks()
        writes = [item for item in self.trace if isinstance(item["action"], dict)
                  and item["action"].get("tool") == "set_config"]
        finishes = [item for item in self.trace if isinstance(item["action"], dict)
                    and item["action"].get("tool") == "finish"]
        rules = {
            "evidence_before_changes": bool(writes) and all(item["evidence_before_change"] for item in writes),
            "constraints_respected": bool(self.trace) and all(item["constraint_ok"] for item in self.trace),
            "known_failed_change_not_repeated": bool(writes) and not any(
                isinstance(item["action"].get("arguments"), dict)
                and item["action"]["arguments"] == failed
                for item in writes for failed in self.rubric["known_failed_changes"]),
            "completion_verified": bool(finishes) and finishes[-1]["valid"]
                and finishes[-1]["action"]["arguments"]["status"] == "completed"
                and finishes[-1]["verified_after"],
        }
        valid_tools = sum(item["valid"] and item["constraint_ok"] for item in self.trace)
        return {
            "task_success": all(checks.values()) and rules["completion_verified"] and rules["constraints_respected"],
            "final_goal_completion": sum(checks.values()) / len(checks),
            "tool_usage_correctness": valid_tools / len(self.trace) if self.trace else 0.0,
            "decision_consistency": sum(rules.values()) / len(rules),
            "goal_checks": checks, "decision_checks": rules,
        }
