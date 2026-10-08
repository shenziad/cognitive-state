"""Explicit authored public lifecycle contracts; no inference from hidden targets."""

from copy import deepcopy
from evaluation.evidence_interface import EvidenceEnvironment


class LifecycleEnvironment(EvidenceEnvironment):
    def catalog(self):
        result = super().catalog()
        for item in result["operations"]:
            definition = self.fixture["operations"][item["name"]]
            item["lifecycle_contract"] = deepcopy(definition["lifecycle_contract"])
        return result

    def public_interface(self, scope):
        interface = super().public_interface(scope)
        interface["version"] = "lifecycle-interface-v1"
        interface["receipt_contract"] = (
            "Catalog effects and lifecycle contracts are definitions, never observations. "
            "Successful execute receipts certify actual listed effects and the returned lifecycle records. "
            "A completed accepted submission is not a succeeded job. Match entity identity and version. "
            "Goal completion depends on current requirements, including any explicit verification. "
            "Observe values remain hidden until read. Paid failed attempts consume credits. "
            "A failed operational precondition or budget check does not certify successful effects.")
        return interface

    def apply(self, action):
        observation = super().apply(action)
        if isinstance(action, dict) and action.get("tool") == "execute" and "error" not in observation:
            definition = self.fixture["operations"][action["arguments"]["operation"]]
            records = deepcopy(definition.get("lifecycle_receipt", []))
            if definition["lifecycle_contract"]["kind"] == "sync_operation":
                records = [{"kind": "sync_operation", "entity_id": f"{self.fixture['instance_id']}:{action['arguments']['operation']}:{len(self.trace)}",
                            "operation": action["arguments"]["operation"], "phase": "succeeded"}]
            observation["lifecycle"] = records
            self.trace[-1]["observation"] = deepcopy(observation)
        return observation
