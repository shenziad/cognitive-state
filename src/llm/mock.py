"""Scripted protocol exerciser. Its scores are never model performance evidence."""

import json

from .client import Completion


class MockClient:
    def complete(self, messages: list[dict[str, str]], *, purpose: str) -> Completion:
        payload = json.loads(messages[1]["content"])
        if purpose in {"summary", "cognitive_state"}:
            history = payload["history"]
            request = history[0]["content"]
            pending = history[-1]["content"]
            if purpose == "summary":
                text = request + " " + pending
            else:
                text = json.dumps({
                    "goal": {"objective": request, "success_criteria": ["Service checks pass"],
                             "constraints": [], "preferences": []},
                    "world": {"facts": [], "beliefs": [], "assumptions": []},
                    "frontier": {"current_focus": "Service configuration", "information_needs": [pending],
                                 "next_action": "Read docs/runbook.json"},
                }, separators=(",", ":"))
        else:
            trace = [json.loads(message["content"]) for message in messages[2:] if message["role"] == "user"]
            if not trace:
                action = {"tool": "read_file", "arguments": {"path": "docs/runbook.json"}}
            else:
                recommendation = trace[0]["observation"]["content"]["recommended_settings"]
                done = {item["action"]["arguments"].get("key") for item in trace
                        if item["action"]["tool"] == "set_config"}
                todo = [(key, value) for key, value in recommendation.items() if key not in done]
                if todo:
                    key, value = todo[0]
                    action = {"tool": "set_config", "arguments": {"key": key, "value": value}}
                elif trace[-1]["action"]["tool"] != "run_check":
                    action = {"tool": "run_check", "arguments": {}}
                else:
                    action = {"tool": "finish", "arguments": {"status": "completed"}}
            text = json.dumps(action)
        return Completion(text, {
            "purpose": purpose, "source": "mock", "model": "scripted-mock-v1",
            "finish_reason": "stop", "usage_unit": "utf8_bytes",
            "input_tokens": None, "output_tokens": None,
            "input_bytes": len(json.dumps(messages).encode("utf-8")),
            "output_bytes": len(text.encode("utf-8")),
        })
