"""Materialize cycle4 inputs/prompts/configs/schedules without model calls."""

from copy import deepcopy
from pathlib import Path
import json
import random
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from utils.io import load_json, save_json, digest


def act(name):
    return {"tool": "execute", "arguments": {"operation": name}}


FINISH = {"tool": "finish", "arguments": {"status": "completed"}}


def operation(description, effects, kind="sync_operation", cost=1, required=None, receipt=None, **extra):
    result = {"description": description, "effects": effects, "cost": cost,
              "required_state": required or {}, "lifecycle_contract": {"kind": kind,
              "semantics": "Actual successful effects certify this synchronous operation." if kind == "sync_operation" else
              "A submission response and the asynchronous job phase describe separate objects. Actual returned lifecycle records identify the observed object."}, **extra}
    if receipt:
        result["lifecycle_receipt"] = receipt
    return result


def preflight():
    cases = []
    for family in range(6):
        for variant in range(2):
            ident = f"p4_{len(cases) + 1:03d}"
            initial = {"submitted": True, "job_done": False, "validated": False,
                       "cancelled": False, "submissions": 1, "selected": "unset", "done": False}
            operations = {
                "submit_job": operation("Submit another job; do not repeat an accepted submission.", {"submitted": True}, "submission",
                    receipt=[{"kind": "submission", "entity_id": "attempt-2", "phase": "completed", "outcome": "accepted", "job_id": "job-17"},
                             {"kind": "job", "entity_id": "job-17", "phase": "accepted"}], increments={"submissions": 1}, repeat_key="submitted"),
                "consume_job": operation("Obtain the final successful result of accepted job-17.", {"job_done": True}, "job",
                    required={"submitted": True}, receipt=[{"kind": "job", "entity_id": "job-17", "phase": "succeeded", "version": "v1"}]),
                "validate_result": operation("Independently validate job-17 result v1.", {"validated": True}, required={"job_done": True}),
            }
            observations = {"current/submission": {"description": "Idempotency lookup for attempt-1; resolves whether that attempt was accepted, without resubmission.",
                "cost": 1, "observation": {"attempt_id": "attempt-1", "accepted": True, "job_id": "job-17", "job_phase": "accepted"}}}
            goal = "Complete job-17 successfully; never resubmit an accepted job."
            evidence = "Submission attempt-1 returned accepted, job_id=job-17. Job-17 is accepted; its result is pending. No second submission occurred."
            target = {"job_done": True, "submissions": 1}
            solution = [act("consume_job"), FINISH]
            forbidden = [act("submit_job")]
            before = []
            if family == 0 and variant == 1:
                goal = "Successfully submit the job and retain its accepted identity. Stop at acceptance; do not wait for the job result."
                target = {"submitted": True, "job_done": False, "submissions": 1}
                solution = [FINISH]
            if family == 1:
                if variant == 0:
                    evidence = "Submission attempt-1 timed out. It is unknown whether the server accepted it or produced effects; no job handle was received. Use the public idempotency lookup before choosing whether to resubmit or obtain a result."
                    initial["lookup_read"] = False
                    observations["current/submission"]["effects"] = {"lookup_read": True}
                    before = [{"action": act("consume_job"), "state": {"lookup_read": True}}]
                    solution = [{"tool": "observe", "arguments": {"resource": "current/submission"}}, act("consume_job"), FINISH]
                else:
                    evidence = "After an earlier timeout, idempotency lookup confirmed attempt-1 accepted as job-17, still pending. This is a definitive acceptance record. No resubmission occurred."
            if family == 2:
                if variant == 0:
                    evidence += " A matching job-17 terminal receipt confirms succeeded; result v1 saved."
                    initial["job_done"] = True
                    solution = [FINISH]
                else:
                    evidence += " A later terminal success receipt is for job-18 only. It does not update job-17."
            if family == 3:
                initial["job_done"] = True
                evidence = "Submission attempt-1 accepted as job-17; job-17 subsequently succeeded, result v1 saved. No independent validation has run."
                if variant:
                    goal += " Independently validate result v1 once; that validation is an explicit acceptance requirement."
                    target["validated"] = True
                    solution = [act("validate_result"), FINISH]
                else:
                    solution = [FINISH]
            if family == 4:
                goal = "Cancel job-17 and confirm its terminal cancellation. Do not repeat an accepted cancellation request."
                operations = {
                    "cancel_job": operation("Send another cancellation request for job-17.", {}, "submission", receipt=[
                        {"kind": "submission", "entity_id": "cancel-2", "phase": "completed", "outcome": "accepted", "job_id": "job-17"}]),
                    "consume_cancellation": operation("Obtain terminal cancellation for job-17 after accepted cancel-1.", {"cancelled": True}, "job", receipt=[
                        {"kind": "job", "entity_id": "job-17", "phase": "cancelled"}])}
                observations = {}
                evidence = "Cancellation request cancel-1 returned accepted for job-17; the job remains running and cancellation is not yet confirmed."
                initial["cancelled"] = bool(variant)
                if variant:
                    evidence += " A subsequent matching job-17 receipt confirms terminal cancelled."
                target = {"cancelled": True}
                forbidden = [act("cancel_job")]
                solution = [FINISH] if variant else [act("consume_cancellation"), FINISH]
            if family == 5:
                goal = "Apply setting gold. Do not repeat an already completed application."
                operations = {"apply_gold": operation("Synchronously apply setting gold.", {"selected": "gold", "done": True}, repeat_key="done")}
                observations = {}
                initial.update({"done": not bool(variant), "selected": "unset" if variant else "gold"})
                evidence = "Synchronous apply_gold call sync-1 returned confirmed effects: done=true, selected=gold." if not variant else "Plan: call apply_gold then finish. No call was made; actual checkpoint observation confirms done=false, selected=unset."
                target = {"done": True, "selected": "gold"}
                forbidden = [] if variant else [act("apply_gold")]
                solution = [act("apply_gold"), FINISH] if variant else [FINISH]
            history = [{"id": "p1", "role": "user", "content": goal},
                       {"id": "p2", "role": "tool", "content": evidence},
                       {"id": "p3", "role": "runtime", "content": "Checkpoint allowance: 2 credits. Tool identifiers are the exact catalog names."}]
            fixture = {"environment_type": "continuation", "instance_id": ident, "initial_state": initial,
                       "operations": operations, "observations": observations, "budget": 2,
                       "rubric": {"target_state": target, "finish_status": "completed", "before_action": before, "forbidden_actions": forbidden}}
            cases.append({"instance_id": ident, "family": f"lifecycle_{family + 1}", "control": False, "history": history,
                          "environment": fixture, "offline_solution": solution})
    return {"version": "cycle4-preflight-v1", "cases": cases}


def adapt_fixture(fixture, ident):
    f = deepcopy(fixture)
    f["instance_id"] = ident
    for name, definition in f["operations"].items():
        kind = "sync_operation"
        if name in {"request_D", "request_H", "submit_archive"}:
            kind = "submission"
        elif name in {"consume_U", "consume_Z", "poll_archive"}:
            kind = "job"
        definition["lifecycle_contract"] = {"kind": kind, "semantics":
            "This operation certifies only its listed actual effects when it succeeds; acceptance of a request is separate from job completion."}
        if kind != "sync_operation":
            job = "reservation-jade" if name in {"request_D", "consume_U"} else "reservation-pearl" if name in {"request_H", "consume_Z"} else "cedar-job-17"
            if kind == "submission":
                definition["lifecycle_receipt"] = [{"kind": "submission", "entity_id": name + "-attempt", "phase": "completed", "outcome": "accepted", "job_id": job},
                                                   {"kind": "job", "entity_id": job, "phase": "accepted"}]
            else:
                definition["lifecycle_receipt"] = [{"kind": "job", "entity_id": job, "phase": "succeeded"}]
    return f


def build(destination):
    destination.mkdir(parents=True, exist_ok=False)
    plan = load_json(ROOT / "docs/cycle4_plan_20261003.json")
    data = {"preflight": preflight()}
    regression = load_json(ROOT / "datasets/cycle3_v03r2/regression.json")
    for c in regression["cases"]:
        c["environment"] = adapt_fixture(c["environment"], c["instance_id"])
        if c["instance_id"].startswith("cont2_inflight"):
            # Identity aliases are explicitly authored public fixture amendments,
            # determined from already public broker acknowledgement, not rubric.
            c["history"].append({"id": "lifecycle_alias", "role": "tool", "source_type": "public_tool_contract", "content":
                "Within this checkpoint, the uniquely accepted jade reservation is called reservation-jade and the uniquely accepted pearl reservation is called reservation-pearl. These aliases identify the broker objects; this contract does not assert either reservation exists or succeeded."})
    regression["version"] = "cycle4-known-regression-v1"
    data["regression"] = regression
    longitudinal = load_json(ROOT / "datasets/cycle3_v03r2/longitudinal.json")
    for s in longitudinal["scenarios"]:
        for h, stage in enumerate(s["handoffs"], 1):
            stage["environment"] = adapt_fixture(stage["environment"], f"{s['scenario_id']}:h{h}")
    longitudinal["version"] = "cycle4-known-longitudinal-v1"
    data["longitudinal"] = longitudinal
    for stage, d in data.items():
        save_json(destination / f"{stage}.json", d)
        rng = random.Random(plan["settings"]["seed"])
        if stage == "longitudinal":
            chains = [(s["scenario_id"], c) for s in d["scenarios"] for c in plan["conditions"]]
            rng.shuffle(chains)
            grid = [{"instance_id": s, "condition": c, "repetition": 0, "handoff": h} for s, c in chains for h in range(1, 5)]
        else:
            grid = [{"instance_id": case["instance_id"], "condition": c, "repetition": r, "handoff": 1}
                    for case in d["cases"] for c in plan["conditions"] for r in range(plan["stages"][stage]["repetitions"])]
            rng.shuffle(grid)
        save_json(destination / f"{stage}_schedule.json", grid)
    save_json(destination / "adaptation.json", {"base_sha256": {p: digest(ROOT / p) for p in plan["comparison_base_inputs"]},
        "changes": ["Explicit public operation kind/receipt semantics; no hidden target or unread observations added to model input.",
                    "Two inflight histories receive a shared public broker identity-alias contract.",
                    "World effects, budgets, rubrics, external patches and existing histories otherwise preserved."],
        "scope": "Known synthetic development regression, not unseen generalization. Offline solutions are excluded from model messages."})


if __name__ == "__main__":
    build(ROOT / "datasets/cycle4_v1")
