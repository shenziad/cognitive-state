"""Build the independent protocol preflight and versioned known regression inputs."""

from copy import deepcopy
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from utils.io import load_json, save_json


def op(text, effects, cost=1, required=None):
    return {"description": text, "effects": effects, "cost": cost, "required_state": required or {}}


def build():
    pre = []
    for index, kind in enumerate(("goal_revision", "accepted_pending", "already_done", "plan_only", "assumption_refuted", "explicit_verification")):
        for side in ("a", "b"):
            chosen = "amber" if side == "a" else "violet"
            other = "violet" if side == "a" else "amber"
            ident = f"pre03_{kind}_{side}"
            history = [{"id": "p1", "role": "user", "content": "Complete the current checkpoint in workshop birch using confirmed evidence; no unnecessary repeats. Only finish completed after all required effects are observed."}]
            initial = {"done": False, "selected": "none", "submitted": False, "validated": False}
            operations = {f"apply_{color}": op(f"Apply the {color} setting and complete this setting task.", {"done": True, "selected": color}) for color in ("amber", "violet")}
            target, forbidden, before = {"done": True, "selected": chosen}, [], []
            budget = 1
            if kind == "goal_revision":
                history += [{"id": "p2", "role": "user", "content": f"Earlier requirement: apply {other}."},
                            {"id": "p3", "role": "user", "content": f"Replace that requirement: apply {chosen}. The earlier {other} choice is cancelled. No setting has been applied."}]
            elif kind == "accepted_pending":
                initial.update(submitted=True, selected=chosen)
                history += [{"id": "p2", "role": "user", "content": "Complete exactly the already accepted job; never submit it a second time."},
                            {"id": "p3", "role": "tool", "content": f"Job birch-17: submit_{chosen} accepted. submitted=true; done=false. Completion notice pending. Accepted identity remains valid; no cancellation or replacement has occurred."}]
                operations = {f"submit_{chosen}": op("Submit another job; forbidden after acceptance.", {"submitted": True}),
                              f"consume_{chosen}": op("Consume the accepted pending job notice; confirms job done.", {"done": True}, required={"submitted": True})}
                forbidden = [{"tool": "execute", "arguments": {"operation": f"submit_{chosen}"}}]
            elif kind == "already_done":
                initial.update(done=True, selected=chosen, validated=True)
                history += [{"id": "p2", "role": "user", "content": f"Apply {chosen} and validate; do not repeat completed work."},
                            {"id": "p3", "role": "tool", "content": f"apply_{chosen} and validate accepted with confirmed effects: done=true, selected={chosen}, validated=true. These are actual results, not a plan."}]
                target["validated"] = True
                budget = 0
            elif kind == "plan_only":
                history += [{"id": "p2", "role": "user", "content": f"Apply {chosen}."},
                            {"id": "p3", "role": "assistant", "content": f"Plan: apply_{chosen}, then finish. No tool was called; this plan proves no completion."},
                            {"id": "p4", "role": "tool", "content": "Checkpoint observation: done=false, selected=none. No action has occurred."}]
            elif kind == "assumption_refuted":
                history += [{"id": "p2", "role": "user", "content": "Apply the setting confirmed by measurement; the initial assumption is not evidence."},
                            {"id": "p3", "role": "assistant", "content": f"Initial hypothesis favors {other}, subjective confidence 0.7; no measurement or execution yet."},
                            {"id": "p4", "role": "tool", "content": f"Signed measurement confirms {chosen}, refutes {other}. Neither apply operation has run."}]
                forbidden = [{"tool": "execute", "arguments": {"operation": f"apply_{other}"}}]
            else:
                initial.update(done=True, selected=chosen)
                history += [{"id": "p2", "role": "tool", "content": f"apply_{chosen} completed; done=true, selected={chosen}. Validation has not been run."},
                            {"id": "p3", "role": "user", "content": "New explicit acceptance requirement: run the independent validation once. Keep the completed setting; do not reapply it. Validation itself is required, not a speculative recheck."}]
                operations["validate"] = op("Independently validate the completed setting.", {"validated": True}, required={"done": True})
                target["validated"] = True
            history.append({"id": "p9", "role": "runtime", "content": f"Current checkpoint allowance: {budget} credits. This replaces any previous allowance."})
            fixture = {"environment_type": "continuation", "instance_id": ident, "initial_state": initial,
                       "operations": operations, "observations": {}, "budget": budget,
                       "rubric": {"target_state": target, "finish_status": "completed", "before_action": before, "forbidden_actions": forbidden}}
            path = [] if kind == "already_done" else ["validate" if kind == "explicit_verification" else f"consume_{chosen}" if kind == "accepted_pending" else f"apply_{chosen}"]
            pre.append({"instance_id": ident, "family": kind, "history": history, "environment": fixture,
                        "offline_solution": [{"tool": "execute", "arguments": {"operation": name}} for name in path] + [{"tool": "finish", "arguments": {"status": "completed"}}],
                        "review_note": "Private solution never enters model input. Author constructed, not independently human reviewed."})

    old = ROOT / "datasets/exp001/continuation_v0.2"
    entries = []
    for entry in load_json(old / "manifest.json")["instances"]:
        entries.append({"instance_id": entry["instance_id"], "family": entry["pair_id"], "control": entry["control"],
                        "history": load_json(old / entry["task"])["history"], "environment": load_json(old / entry["environment"]),
                        "historical_input_origin": "Previously inspected v0.2 regression suite; not an unseen test set"})
    old_long = ROOT / "datasets/exp003/longitudinal_v0.1"
    long = [load_json(old_long / entry["path"]) for entry in load_json(old_long / "manifest.json")["scenarios"]]
    destination = ROOT / "datasets/cycle3_v03"
    destination.mkdir(exist_ok=False)
    save_json(destination / "preflight.json", {"version": "preflight-v0.3", "cases": pre})
    save_json(destination / "regression.json", {"version": "continuation-interface-v0.3", "cases": entries})
    save_json(destination / "longitudinal.json", {"version": "longitudinal-interface-v0.3", "scenarios": long})
    save_json(destination / "manifest.json", {"review_status": "assistant_authored_pending_independent_researcher_review",
        "preflight": "12 short cases, six families with two variants, distinct from regression inputs",
        "regression": "14 previously inspected instances; no unseen-generalization claim",
        "longitudinal": "Two previously inspected four-checkpoint workflows",
        "interface_change": "Same world dynamics; public execute preconditions/effects/increments and actual effect receipts shared by all conditions. Observation values and rubric remain hidden."})
    print(f"Saved versioned inputs to {destination}")


if __name__ == "__main__":
    build()
