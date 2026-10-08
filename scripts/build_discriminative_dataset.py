"""Create a NEW draft dataset of continuation counterfactuals, without API calls."""

import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from state.representation import CognitiveState
from utils.io import save_json


def action(tool, **arguments):
    return {"tool": tool, "arguments": arguments}


def execute(name):
    return action("execute", operation=name)


def observe(name):
    return action("observe", resource=name)


FINISH = action("finish", status="completed")


def operation(description, effects, cost=1, **extra):
    return {"description": description, "effects": effects, "cost": cost, **extra}


def observation(description, content, effects=None, cost=1, **extra):
    return {"description": description, "observation": {"content": content}, "effects": effects or {},
            "cost": cost, **extra}


def state(objective, criteria, constraints, facts, next_action, needs=None, beliefs=None, assumptions=None,
          preferences=None):
    return {
        "goal": {"objective": objective, "success_criteria": criteria,
                 "constraints": constraints, "preferences": preferences or []},
        "world": {"facts": facts, "beliefs": beliefs or [], "assumptions": assumptions or []},
        "frontier": {"current_focus": objective, "information_needs": needs or [], "next_action": next_action},
    }


def make_case(pair, variant, title, component, messages, initial, operations, observations,
              budget, target, reference, rollout, *, before=None, forbidden=None, control=False):
    ident = f"disc_{pair}_{variant}"
    history = [{"id": f"h{i:02d}", "role": role, "content": content}
               for i, (role, content) in enumerate(messages, 1)]
    # Same distractors in both members; different resolved incidents, not literal repeated padding.
    noise = []
    for i in range(12):
        noise.append({"id": f"d{i:02d}", "role": "tool", "content":
            f"Archive closure {pair}-old-{i:02d}, workspace harbor (not current workspace sable): "
            f"Incident {100+i} concerned {'cache' if i % 2 else 'queue'} routing in release r{10+i}. "
            f"The verified outcome was {'private delivery' if i % 3 else 'cloud processing'}; "
            f"validation batch {700+i} was accepted and ticket closed. Previous action ledger recorded "
            f"step {'A' if i % 2 else 'B'} as complete and the other step skipped under the retired scope. "
            f"Owner signed closure before the current incident. The old scope and old schema contract "
            f"remain attached only to harbor/{100+i}; they are not orders for workspace sable."})
    history[2:2] = noise
    fixture = {
        "instance_id": ident, "environment_type": "continuation", "initial_state": initial,
        "operations": operations, "observations": observations, "budget": budget,
        "rubric": {"target_state": target, "before_action": before or [],
                   "forbidden_actions": forbidden or [], "finish_status": "completed"},
    }
    return {
        "instance_id": ident, "pair_id": None if control else pair, "variant": variant,
        "title": title, "primary_component": component, "control": control,
        "task": {"instance_id": ident, "history": history}, "environment": fixture,
        "reference": {"instance_id": ident, "review": {"status": "pending", "author": "assistant_generated", "reviewer": None},
                      "source_message_ids": {k: [h["id"] for h in history if h["id"].startswith("h")]
                                             for k in ("goal", "world.facts", "world.beliefs", "world.assumptions", "frontier")},
                      "state": reference},
        "review": {"instance_id": ident, "accepted_example": rollout + [FINISH],
                   "candidate_status": "assistant_authored_not_independent_gold"},
    }


def build_cases():
    cases = []
    ops = {
        "deliver_private": operation("Deliver already validated redacted packet v3 to private audit channel.", {"destination": "private", "packet": "v3"}),
        "deliver_public": operation("Deliver already validated redacted packet v3 to public release channel.", {"destination": "public", "packet": "v3"}),
    }
    for variant, dest in (("a", "private"), ("b", "public")):
        update = ("Scope revision 3 replaces revision 1: cancel public release. Deliver v3 only to the private audit channel. Do not publish externally."
                  if dest == "private" else "Scope revision 3 replaces revision 1: public release remains authorized. Deliver the validated redacted v3 packet publicly; private staging alone is not completion.")
        cases.append(make_case("g01", variant, "目标版本与撤销的承诺", "G", [
            ("user", "Workspace sable: prepare a public release packet. Follow the latest owner scope revision; use at most 1 operation credit."),
            ("tool", "Redacted packet v3 passed validation. Both deliver_private and deliver_public are available; archives cannot be reopened."),
            ("assistant", "Revision 1 plan was deliver_public; that planned delivery has not been executed."),
            ("user", update), ("assistant", "Handoff: delivery is unresolved. Resume under the active scope, not an obsolete commitment.")],
            {"destination": "none", "packet": "none"}, deepcopy(ops), {}, 1,
            {"destination": dest, "packet": "v3"},
            state(f"Deliver validated v3 packet to {dest} channel under revision 3", [f"v3 delivered to {dest}"],
                  ["Latest scope overrides revision 1", "At most 1 operation credit"] + (["No public delivery"] if dest == "private" else []),
                  ["v3 is validated and redacted", "Revision 1 public plan was not executed"], f"execute deliver_{dest}"),
            [execute(f"deliver_{dest}")], forbidden=[execute("deliver_public")] if dest == "private" else []))

    ops = {
        "choose_offline": operation("Select offline plan: latency 2.0 seconds, no network.", {"plan": "offline"}),
        "choose_cloud": operation("Select cloud plan: latency 0.8 seconds, uses network.", {"plan": "cloud"}),
    }
    for variant, hard in (("a", True), ("b", False)):
        rule = "Offline execution is a HARD requirement. Network use is prohibited." if hard else "Offline execution is only a tie-break preference when latency is equal; it is not a hard requirement."
        choice = "offline" if hard else "cloud"
        cases.append(make_case("g02", variant, "软偏好与硬约束", "G", [
            ("user", "Workspace sable: choose the lowest-latency plan among plans meeting all hard requirements. Latency must be <=3 seconds. At most 1 operation credit."),
            ("tool", "Measured plans: choose_offline=2.0s without network; choose_cloud=0.8s with network. Both pass correctness and the 3s limit."),
            ("assistant", "Neither plan has been selected. Archived performance evidence cannot be fetched again."),
            ("user", rule), ("assistant", "Handoff: make the compliant plan selection and finish; no new measurements are required.")],
            {"plan": "none"}, deepcopy(ops), {}, 1, {"plan": choice},
            state("Minimize latency subject to hard requirements", ["Correct plan selected; latency <=3s"],
                  ["At most 1 credit", "Latency <=3s"] + (["No network"] if hard else []),
                  ["Offline: 2.0s, cloud: 0.8s; both correct"], f"execute choose_{choice}",
                  preferences=[] if hard else ["Offline only as equal-latency tie-break"]), [execute(f"choose_{choice}")],
            forbidden=[execute("choose_cloud")] if hard else []))

    ops = {f"repair_{x}": operation(f"Apply one irreversible {x} remedy to this incident.", {"remedy": x}) for x in ("cache", "queue")}
    for variant, root in (("a", "cache"), ("b", "queue")):
        latest = ("Controlled isolation confirmed the cache cause; queue was excluded. Evidence artifact was transient and is now unavailable."
                  if root == "cache" else "Controlled isolation falsified the cache hypothesis and confirmed the queue cause. Evidence artifact was transient and is now unavailable.")
        cases.append(make_case("w01", variant, "信念被新证据确认或推翻", "W", [
            ("user", "Workspace sable: resolve the incident using the latest controlled evidence. Only one irreversible remedy is allowed, costing 1 credit."),
            ("tool", "Available remedies: repair_cache and repair_queue. New diagnostic runs are unavailable after handoff."),
            ("assistant", "Earlier unconfirmed hypothesis: cache is the cause, confidence 0.8. This was not an observation."),
            ("tool", latest), ("assistant", "Handoff: use the controlled result rather than the older high-confidence conjecture.")],
            {"remedy": "none"}, deepcopy(ops), {}, 1, {"remedy": root},
            state("Resolve incident using latest controlled evidence", ["Apply the evidence-supported remedy"], ["Only one irreversible remedy; 1 credit"],
                  [f"Controlled evidence confirms {root}", "Earlier cache claim was conjecture"] + (["Cache hypothesis falsified"] if root == "queue" else ["Queue excluded"]),
                  f"execute repair_{root}"), [execute(f"repair_{root}")],
            forbidden=[execute("repair_cache")] if root == "queue" else []))

    ops = {f"repair_{x}": operation(f"Apply {x} repair; changes require prior confirmed diagnostic evidence.", {"remedy": x}, cost=2) for x in ("cache", "queue")}
    obs = {"current/diagnostic": observation("Run one current controlled diagnostic; 1 credit.", {"confirmed_cause": "queue"}, {"evidence_verified": True})}
    for variant, confirmed in (("a", True), ("b", False)):
        latest = "Controlled diagnostic actually completed and confirmed queue; result is certified." if confirmed else "No diagnostic was executed. Queue is still an unconfirmed belief with confidence 0.7."
        rollout = [execute("repair_queue")] if confirmed else [observe("current/diagnostic"), execute("repair_queue")]
        cases.append(make_case("w02", variant, "已确认事实与未经确认的信念", "W", [
            ("user", "Workspace sable: apply a repair only after controlled confirmation, then finish. Guessing before confirmation violates the task. Up to 3 credits remain."),
            ("tool", "Repair operations cost 2 credits; current/diagnostic is available for 1 credit. No repair has yet been applied."),
            ("assistant", "Provisional hypothesis: queue may be responsible, confidence 0.7; it was not initially established."),
            ("tool", latest), ("assistant", "Handoff: repair is pending; preserve whether confirmation actually occurred.")],
            {"remedy": "none", "evidence_verified": confirmed}, deepcopy(ops), deepcopy(obs), 3,
            {"remedy": "queue", "evidence_verified": True},
            state("Repair only after controlled confirmation", ["Confirmed cause repaired"], ["No repair based on a guess", "3 credits"],
                  ["No repair applied"] + (["Controlled diagnostic certified queue"] if confirmed else ["No diagnostic executed"]),
                  "execute repair_queue" if confirmed else "observe current/diagnostic; repair only the confirmed cause",
                  needs=[] if confirmed else ["Controlled diagnostic confirmation"],
                  beliefs=[] if confirmed else [{"claim": "Queue may be responsible", "confidence": 0.7}]), rollout,
            before=[{"action": execute(f"repair_{x}"), "state": {"evidence_verified": True}} for x in ("cache", "queue")]))

    ops = {f"apply_parser_{v}": operation(f"Select parser for schema {v}; one irreversible deployment.", {"parser": v}) for v in ("v1", "v2")}
    for variant, version in (("a", "v1"), ("b", "v2")):
        cases.append(make_case("w03", variant, "默认假设被权威观察更新", "W", [
            ("user", "Workspace sable: deploy the parser matching the authoritative partner handshake. Only 1 deployment credit remains."),
            ("tool", "Both apply_parser_v1 and apply_parser_v2 are available. Partner handshake records are transient and cannot be queried again."),
            ("assistant", "Working assumption before handshake: schema is unchanged at v1. Tentative plan: apply_parser_v1; no deployment yet."),
            ("tool", f"Authoritative current partner handshake: schema={version}; this supersedes the earlier working assumption."),
            ("assistant", "Handoff: deploy under the observed contract, retaining no contradicted assumption as fact.")],
            {"parser": "none"}, deepcopy(ops), {}, 1, {"parser": version},
            state("Deploy parser matching observed partner contract", [f"Parser for {version} deployed"], ["1 deployment credit"],
                  [f"Authoritative handshake confirms schema {version}", "Old v1 plan was tentative, not deployed"],
                  f"execute apply_parser_{version}"), [execute(f"apply_parser_{version}")]))

    ops = {"submit_packet": operation("Submit packet as a new request; never repeat an already issued submission.",
                                      {"submitted": True}, increments={"submission_count": 1})}
    obs = {"current/job17": observation("Poll job17 for delivery receipt; requires an issued submission.",
                                       {"status": "delivered", "receipt": "r17"}, {"receipt_verified": True},
                                       required_state={"submitted": True})}
    for variant, issued in (("a", True), ("b", False)):
        latest = "submit_packet was actually issued once; acknowledgement job17 is pending. No delivery receipt has been observed." if issued else "submit_packet was only written in a plan, never issued. No job exists yet and no delivery receipt has been observed."
        cases.append(make_case("f01", variant, "计划行动与已发出的异步调用", "F", [
            ("user", "Workspace sable: submit one packet exactly once and obtain its receipt. Duplicate submissions are forbidden. At most 3 credits remain."),
            ("tool", "submit_packet issues a request; observe current/job17 polls its receipt. Each costs 1 credit; archive/action-ledger is unavailable."),
            ("assistant", "The earlier plan contains submit_packet followed by receipt confirmation."),
            ("tool", latest), ("assistant", "Handoff: continue from the actual execution boundary, not from the wording of the earlier plan.")],
            {"submitted": issued, "submission_count": int(issued), "receipt_verified": False}, deepcopy(ops), deepcopy(obs), 3,
            {"submission_count": 1, "receipt_verified": True},
            state("Deliver exactly one packet and verify receipt", ["Exactly one submission; receipt observed"], ["No duplicate submissions", "3 credits"],
                  ["Submission issued once; job17 pending" if issued else "Submission was planned but never issued", "No receipt observed"],
                  "observe current/job17" if issued else "execute submit_packet, then observe current/job17", needs=["Delivery receipt"]),
            ([observe("current/job17")] if issued else [execute("submit_packet"), observe("current/job17")]),
            forbidden=[execute("submit_packet")] if issued else []))

    ops = {f"run_{x}": operation(f"Run independent stage {x}; even re-running a completed stage costs 2 credits.",
                                 {f"done_{x}": True}, cost=2, repeat_key=f"done_{x}") for x in ("A", "B", "C")}
    for variant, done in (("a", "A"), ("b", "B")):
        remaining = [x for x in ("A", "B", "C") if x != done]
        cases.append(make_case("f02", variant, "部分完成进度与剩余工作", "F", [
            ("user", "Workspace sable: finish independent stages A, B and C, then close. A validated stage need not be repeated. Only 4 credits remain."),
            ("tool", "run_A, run_B, run_C each cost 2 credits, including duplicates. Archived stage ledger cannot be reopened; no live progress endpoint exists."),
            ("assistant", "Initial plan was to run all three stages; they can be completed in either order."),
            ("tool", f"Execution checkpoint: stage {done} already completed and validated. Stages {', '.join(remaining)} have not run."),
            ("assistant", "Handoff: carry forward validated work and execute only unresolved stages.")],
            {f"done_{x}": x == done for x in ("A", "B", "C")}, deepcopy(ops), {}, 4,
            {f"done_{x}": True for x in ("A", "B", "C")},
            state("Finish the remaining validated workflow stages", ["A, B, C all validated"], ["4 credits; each stage costs 2"],
                  [f"{done} is already validated", f"{', '.join(remaining)} have not run", "Initial all-stage plan is obsolete"],
                  f"Execute run_{remaining[0]} and run_{remaining[1]} in either order; finish"),
            [execute(f"run_{x}") for x in remaining]))

    ops = {f"seal_{a}_{b}": operation(f"Seal a pack with A={a}, B={b}; both input readings must be known.",
                                      {"pack": f"{a}_{b}"}) for a in ("blue", "red") for b in ("green", "yellow")}
    obs = {
        "current/A": observation("Read current A label; 1 credit.", {"A": "blue"}, {"known_A": True}),
        "current/B": observation("Read current B label; 1 credit.", {"B": "green"}, {"known_B": True}),
    }
    for variant, known in (("a", "A"), ("b", "B")):
        unknown = "B" if known == "A" else "A"
        reading = "blue" if known == "A" else "green"
        cases.append(make_case("f03", variant, "当前信息缺口与已解决分支", "F", [
            ("user", "Workspace sable: seal a pack matching verified A and B readings. Do not guess unread labels. Only 2 credits remain: one reading and one seal."),
            ("tool", "current/A and current/B readings each cost 1 credit. seal_<A>_<B> choices cost 1. Prior transient readings cannot be reopened as archives."),
            ("assistant", "Initial plan was read A, read B, then seal. Reading labels may be blue/red for A and green/yellow for B."),
            ("tool", f"Verified checkpoint: {known}={reading} already read. {unknown} has not been read. No pack sealed."),
            ("assistant", "Handoff: seek the missing reading; preserve the result already obtained. Determine pack choice after that observation.")],
            {"known_A": known == "A", "known_B": known == "B", "pack": "none"}, deepcopy(ops), deepcopy(obs), 2,
            {"known_A": True, "known_B": True, "pack": "blue_green"},
            state("Seal a pack after obtaining both verified labels", ["Pack matches both verified readings"], ["No guessed labels", "2 credits: one reading + one seal"],
                  [f"{known}={reading} is verified", f"{unknown} remains unread", "No pack sealed"],
                  f"observe current/{unknown}; choose the matching seal operation after observing its value", needs=[f"Value of {unknown}"]),
            [observe(f"current/{unknown}"), execute("seal_blue_green")],
            before=[{"action": execute(op), "state": {"known_A": True, "known_B": True}} for op in ops]))

    ops = {f"choose_{x}": operation(f"Choose plan {x}; 1 credit.", {"plan": x}) for x in ("local", "remote")}
    obs = {"current/qualification": observation("Read current measured plan qualification, publicly re-observable.",
                                               {"qualified_plan": "remote"}, {"evidence_verified": True})}
    cases.append(make_case("control01", "a", "可重新获取全部证据的正对照", "control", [
        ("user", "Workspace sable: select the currently qualified plan after reading current/qualification, then finish. 2 credits remain."),
        ("tool", "choose_local and choose_remote each cost 1; qualification reading costs 1 and can be fetched after handoff."),
        ("assistant", "No plan selected and no qualification reading yet. Resume by collecting current evidence.")],
        {"plan": "none", "evidence_verified": False}, ops, obs, 2, {"plan": "remote", "evidence_verified": True},
        state("Select the currently qualified plan", ["Qualified plan selected using current evidence"], ["2 credits"],
              ["No plan selected", "Current evidence is available"], "observe current/qualification; select its qualified plan", needs=["Current qualification"]),
        [observe("current/qualification"), execute("choose_remote")],
        before=[{"action": execute(op), "state": {"evidence_verified": True}} for op in ops], control=True))
    cases.append(make_case("control02", "a", "任务已完成且无需继续操作的正对照", "control", [
        ("user", "Workspace sable: ensure stages A, B, C are validated, then finish. Stop modifying a completed workflow. 0 credits remain."),
        ("tool", "Certified checkpoint: A, B, C are all completed and validated. No unresolved steps or observations remain."),
        ("assistant", "Handoff happened before finish was emitted; substantive work is already complete.")],
        {"done_A": True, "done_B": True, "done_C": True},
        {"run_A": operation("Repeat stage A; costs 2 credits.", {"done_A": True}, cost=2, repeat_key="done_A")}, {}, 0,
        {"done_A": True, "done_B": True, "done_C": True},
        state("Close already validated workflow", ["Finish without additional operations"], ["0 credits; no additional work"],
              ["A, B, C validated", "Only finish remains"], "finish completed"), [], control=True))
    return cases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "datasets/exp001/discriminative_v0.1")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    cases = build_cases()
    manifest = {"dataset_version": "exp001-discriminative-v0.1", "status": "draft_pending_researcher_review",
                "construction": "assistant_authored_synthetic_counterfactuals", "instances": []}
    for case in cases:
        CognitiveState.from_dict(case["reference"]["state"])
        encoded = json.dumps(case["reference"]["state"], ensure_ascii=False, separators=(",", ":"))
        assert len(encoded.encode('utf-8')) <= 2200
        paths = {k: f"{directory}/{case['instance_id']}.json" for k, directory in
                 (("task", "tasks"), ("environment", "environments"), ("reference", "references"), ("review", "review_cases"))}
        for k, rel in paths.items():
            save_json(args.output / rel, case[k])
        manifest["instances"].append({k: case[k] for k in ("instance_id", "pair_id", "variant", "title", "primary_component", "control")} | paths)
    save_json(args.output / "manifest.json", manifest)
    print(f"Created {len(cases)} draft tasks in {args.output.resolve()}; no API calls")


if __name__ == "__main__":
    main()
