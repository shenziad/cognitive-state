"""Extract representations from public pre-cutoff history only."""

import json
from typing import Any

from llm.client import Client
from llm.tokens import RepresentationCounter
from .representation import CognitiveState
from utils.io import parse_json


class StateExtractor:
    def __init__(self, client: Client, counter: RepresentationCounter, budget: int):
        self.client, self.counter, self.budget = client, counter, budget

    def extract(self, history: list[dict[str, Any]], condition: str,
                prompt: str, calls: list[dict[str, Any]]) -> str:
        messages = [{"role": "system", "content": prompt}, {"role": "user", "content": json.dumps({
            "history": history, "representation_budget": self.budget,
            "budget_counter": self.counter.name,
        }, ensure_ascii=False)}]
        completion = self.client.complete(messages, purpose=condition)
        calls.append({"messages": messages, "response": completion.text, "metadata": completion.metadata})
        if completion.metadata.get("finish_reason") != "stop":
            raise ValueError("Extractor completion did not stop normally")
        representation = completion.text.strip()
        if condition == "cognitive_state":
            state = CognitiveState.from_dict(parse_json(representation))
            representation = json.dumps(state.to_dict(), ensure_ascii=False, separators=(",", ":"))
        if not representation:
            raise ValueError("Extractor returned an empty representation")
        if self.counter.count(representation) > self.budget:
            raise ValueError("Representation exceeds the configured budget; no truncation performed")
        return representation
