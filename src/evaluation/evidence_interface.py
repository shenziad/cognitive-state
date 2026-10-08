"""Common public operation contracts and effect receipts; no scoring oracle."""

from copy import deepcopy
from .continuation import ContinuationEnvironment


class EvidenceEnvironment(ContinuationEnvironment):
    def catalog(self):
        result = super().catalog()
        for entry in result["operations"]:
            definition = self.fixture["operations"][entry["name"]]
            entry["preconditions"] = deepcopy(definition.get("required_state", {}))
            entry["successful_effects"] = deepcopy(definition.get("effects", {}))
            entry["successful_increments"] = deepcopy(definition.get("increments", {}))
        # Observe results/evidence are intentionally absent: reading still has a cost.
        return result

    def public_interface(self, scope):
        return {"version": "evidence-interface-v0.3", "catalog": self.catalog(),
                "remaining_credits": max(0, self.budget - self.spent), "credit_scope": scope,
                "receipt_contract": "Successful execute receipts certify listed effects of that operation, not overall task success. "
                "No extra verification is required unless the active user requirements or operation contract demand it. "
                "Accepted/submitted async jobs are not complete until a completion operation reports completion. "
                "Observe values remain unread until observed. Plan descriptions do not certify actions. "
                "Paid attempts consume credits even on precondition failure; budget violations remain failures."}

    def apply(self, action):
        observation = super().apply(action)
        trace = self.trace[-1]
        if isinstance(action, dict) and action.get("tool") == "execute" and "error" not in observation:
            definition = self.fixture["operations"][action["arguments"]["operation"]]
            observation = {"operation_applied": action["arguments"]["operation"],
                           "public_receipt": deepcopy(observation),
                           "confirmed_effects": deepcopy(definition.get("effects", {})),
                           "incremented_values": {k: self.settings[k] for k in definition.get("increments", {})}}
        observation = {**observation, "remaining_credits": max(0, self.budget - self.spent)}
        trace["observation"] = deepcopy(observation)
        return observation
