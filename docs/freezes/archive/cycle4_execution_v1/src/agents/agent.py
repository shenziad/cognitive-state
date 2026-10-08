"""One JSON action per turn, with shared prompts and tools across conditions."""

import json
from typing import Any

from evaluation.controlled import ControlledEnvironment, TOOL_SPEC
from evaluation.continuation import ContinuationEnvironment
from llm.client import Client
from utils.io import parse_json


class AgentExecutor:
    def __init__(self, client: Client, system_prompt: str, max_steps: int):
        self.client, self.system_prompt, self.max_steps = client, system_prompt, max_steps

    def run(self, context: str, environment: ControlledEnvironment | ContinuationEnvironment,
            calls: list[dict[str, Any]]) -> dict[str, Any]:
        # The fresh continuation instruction deliberately does not restate lost goals/constraints.
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": json.dumps({
                "instruction": "Resume the interrupted task using the supplied context.",
                "context": context, "tools": getattr(environment, "tool_spec", TOOL_SPEC),
            }, ensure_ascii=False)},
        ]
        for _ in range(self.max_steps):
            completion = self.client.complete(messages, purpose="executor")
            calls.append({"messages": [dict(item) for item in messages],
                          "response": completion.text, "metadata": completion.metadata})
            if completion.metadata.get("finish_reason") != "stop":
                raise ValueError("Executor completion did not stop normally")
            messages.append({"role": "assistant", "content": completion.text})
            try:
                action = parse_json(completion.text)
            except (ValueError, TypeError):
                action = {"invalid_output": completion.text}
            observation = environment.apply(action)
            messages.append({"role": "user", "content": json.dumps(
                {"action": action, "observation": observation}, ensure_ascii=False)})
            if environment.finished:
                break
        return {"trace": environment.trace, "final_settings": environment.settings,
                "finished": environment.finished, "metrics": environment.evaluate()}
