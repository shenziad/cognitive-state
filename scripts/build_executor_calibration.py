"""Independent small executor calibration fixtures; no LLM calls or gold claims."""

import argparse
from copy import deepcopy
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from evaluation.continuation import ContinuationEnvironment
from utils.io import save_json


def action(tool, **args):
    return {"tool": tool, "arguments": args}


def operation(description, effects, cost=1, **extra):
    return {"description": description, "effects": effects, "cost": cost, **extra}


def cases():
    result = []

    def add(ident, request, evidence, initial, operations, observations, budget, target, path, before=None):
        history = [{"id": "h01", "role": "user", "content": request},
                   {"id": "h02", "role": "tool", "content": evidence}]
        fixture = {"instance_id": ident, "environment_type": "continuation", "initial_state": initial,
                   "operations": operations, "observations": observations, "budget": budget,
                   "rubric": {"target_state": target, "before_action": before or [], "finish_status": "completed"}}
        reference = {"instance_id": ident, "review": {"status": "pending", "author": "assistant_generated", "reviewer": None},
                     "source_message_ids": {"goal": ["h01"], "world": ["h02"], "frontier": ["h01", "h02"]},
                     "state": {"goal": {"objective": request, "success_criteria": ["Active requirements satisfied"],
                                       "constraints": [], "preferences": []},
                               "world": {"facts": [evidence], "beliefs": [], "assumptions": []},
                               "frontier": {"current_focus": "Continue from the supplied evidence",
                                            "information_needs": [], "next_action": "Use public tools to satisfy the task"}}}
        rollout = path + [action("finish", status="completed")]
        env = ContinuationEnvironment(fixture)
        for a in rollout:
            env.apply(a)
        assert env.evaluate()["task_success"], ident
        result.append({"instance_id": ident, "task": {"instance_id": ident, "history": history},
                       "environment": fixture, "reference": reference,
                       "review": {"instance_id": ident, "accepted_example": rollout}})

    ops = {"select_amber": operation("Apply amber processing choice.", {"choice": "amber"}),
           "select_violet": operation("Apply violet processing choice.", {"choice": "violet"})}
    add("cal_choose_speed", "Workspace quartz: select and apply the lower-latency option. 1 credit remains.",
        "Measured amber=140ms, violet=80ms. Both eligible. No choice has been applied.",
        {"choice": "none"}, deepcopy(ops), {}, 1, {"choice": "violet"},
        [action("execute", operation="select_violet")])
    add("cal_choose_constraint", "Workspace quartz: apply an eligible option without network access; then finish. 1 credit.",
        "Amber is offline at 140ms; violet uses network at 80ms. No choice applied. Faster is only a preference.",
        {"choice": "none"}, deepcopy(ops), {}, 1, {"choice": "amber"},
        [action("execute", operation="select_amber")])
    ops = {f"accept_{x}": operation(f"Apply eligibility selection {x}.", {"choice": x}) for x in ("kappa", "mu")}
    obs = {"current/eligibility": {"description": "Read eligibility measurement.", "cost": 1,
                                  "effects": {"read": True}, "observation": {"eligible": "mu"}}}
    add("cal_read_then_select", "Workspace quartz: read current/eligibility and apply its eligible option. 2 credits.",
        "No eligibility measurement has been read and no choice applied. Use the catalog for available operations.",
        {"choice": "none", "read": False}, ops, obs, 2, {"choice": "mu", "read": True},
        [action("observe", resource="current/eligibility"), action("execute", operation="accept_mu")],
        [{"action": action("execute", operation=f"accept_{x}"), "state": {"read": True}} for x in ("kappa", "mu")])
    ops = {"run_precheck": operation("Run precheck; repeating validated work costs 1.", {"precheck": True}, repeat_key="precheck"),
           "run_pack": operation("Run packaging.", {"pack": True}, repeat_key="pack")}
    add("cal_remaining_work", "Workspace quartz: ensure precheck and packaging are validated, then finish. 1 credit.",
        "Certified checkpoint: precheck is validated; packaging has never run.",
        {"precheck": True, "pack": False}, deepcopy(ops), {}, 1, {"precheck": True, "pack": True},
        [action("execute", operation="run_pack")])
    add("cal_finish_only", "Workspace quartz: ensure precheck and packaging are validated, then finish. 0 credits.",
        "Certified checkpoint: precheck and packaging already validated. Only finish remains.",
        {"precheck": True, "pack": True}, deepcopy(ops), {}, 0, {"precheck": True, "pack": True}, [])
    ops = {"send_batch": operation("Send a new batch; duplicates consume credit.", {"sent": True}, increments={"count": 1})}
    obs = {"current/q42": {"description": "Read delivery receipt of issued q42.", "cost": 1,
                          "required_state": {"sent": True}, "effects": {"receipt": True},
                          "observation": {"receipt": "delivered"}}}
    add("cal_inflight", "Workspace quartz: send one batch exactly once and verify its receipt. 1 credit remains.",
        "send_batch was already issued once. q42 is pending. No receipt observed yet.",
        {"sent": True, "count": 1, "receipt": False}, ops, obs, 1, {"count": 1, "receipt": True},
        [action("observe", resource="current/q42")])
    ops = {f"deploy_{x}": operation(f"Deploy parser {x}.", {"parser": x}) for x in ("r30", "r32")}
    add("cal_update_assumption", "Workspace quartz: deploy the parser matching the authoritative handshake. 1 credit.",
        "Earlier default r30 was only an assumption. Current verified handshake is r32; no deployment has occurred.",
        {"parser": "none"}, ops, {}, 1, {"parser": "r32"}, [action("execute", operation="deploy_r32")])
    ops = {"stamp_oak": operation("Stamp oak and close the file.", {"stamp": "oak"}),
           "stamp_elm": operation("Stamp elm and close the file.", {"stamp": "elm"})}
    obs = {"current/stamp": {"description": "Read authoritative required stamp.", "cost": 1,
                            "effects": {"read": True}, "observation": {"required_stamp": "oak"}}}
    add("cal_exact_resource", "Workspace quartz: read current/stamp, apply its stamp, then finish. 2 credits.",
        "No stamp read or applied. Resource is current/stamp; quartz is workspace identity, not a resource path prefix.",
        {"stamp": "none", "read": False}, ops, obs, 2, {"stamp": "oak", "read": True},
        [action("observe", resource="current/stamp"), action("execute", operation="stamp_oak")],
        [{"action": action("execute", operation=f"stamp_{x}"), "state": {"read": True}} for x in ("oak", "elm")])
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "datasets/exp001/executor_calibration_v0.1")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    manifest = {"dataset_version": "exp001-executor-calibration-v0.1", "status": "synthetic_calibration_not_research_evidence",
                "instances": []}
    for c in cases():
        paths = {k: f"{d}/{c['instance_id']}.json" for k, d in
                 (("task", "tasks"), ("environment", "environments"), ("reference", "references"), ("review", "review_cases"))}
        for kind, relative in paths.items():
            save_json(args.output / relative, c[kind])
        manifest["instances"].append({"instance_id": c["instance_id"], "pair_id": None, "variant": "a",
                                      "primary_component": "control", "control": True, **paths})
    save_json(args.output / "manifest.json", manifest)
    print(f"Created {len(manifest['instances'])} independently scripted calibration cases; no API calls")


if __name__ == "__main__":
    main()
