"""Build a new, offline continuation dataset; never overwrite a frozen version."""

import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from evaluation.continuation import ContinuationEnvironment
from state.representation import CognitiveState
from utils.io import save_json


def act(tool, **arguments):
    return {"tool": tool, "arguments": arguments}


def execute(name):
    return act("execute", operation=name)


def observe(name):
    return act("observe", resource=name)


FINISH = act("finish", status="completed")


def op(description, effects, cost=2, **extra):
    return {"description": description, "effects": effects, "cost": cost, **extra}


def obs(description, content, effects=None, cost=1, **extra):
    return {"description": description, "observation": {"content": content},
            "effects": effects or {}, "cost": cost, **extra}


def state(objective, criteria, constraints, facts, next_action, *, needs=(), beliefs=(), assumptions=()):
    return {"goal": {"objective": objective, "success_criteria": criteria,
                     "constraints": constraints, "preferences": []},
            "world": {"facts": facts, "beliefs": list(beliefs), "assumptions": list(assumptions)},
            "frontier": {"current_focus": objective, "information_needs": list(needs),
                         "next_action": next_action}}


def public_catalog(operations, observations):
    """Same definitions available before and after interruption, without current answers."""
    rows = [f"execute {name}: {value['description']} Cost={value['cost']}."
            for name, value in operations.items()]
    rows += [f"observe {name}: {value['description']} Cost={value['cost']}."
             for name, value in observations.items()]
    return ("Public tool record: execute accepts an operation name; observe accepts a resource name. "
            "workspace/catalog.json can be observed for free and returns only these definitions. "
            + " ".join(rows))


def distractors(pair, count):
    """Different resolved archival records, identical in both counterfactual members."""
    return [{"id": f"d{i:03d}", "role": "tool", "content":
             f"Closed archive {pair}-{i:03d}, workspace vault, unrelated to current workspace lumen. "
             f"Batch {430+i} used a {'ceramic' if i % 2 else 'glass'} holder; "
             f"its recipient was {'review' if i % 3 else 'retention'} and its encoding was "
             f"{'rune' if i % 2 else 'tile'}. The signed closure lists rack "
             f"{'oak' if i % 2 else 'elm'} as calibrated and broker "
             f"{'jade' if i % 3 else 'pearl'} as acknowledged. The former certificate "
             f"identifiers were Q{80+i} and S{40+i}. These are finished records of other "
             "workspaces, with no live instruction, evidence, or progress for lumen."}
            for i in range(count)]


def make_case(pair, variant, title, component, original_request, plan, checkpoint, initial,
              operations, observations, budget, target, reference, accepted, recovery,
              *, noise_count, position, progress_terms=(), before=(), forbidden=(), control=False):
    ident = f"cont2_{pair}_{variant}"
    catalog = public_catalog(operations, observations)
    base = [
        {"id": "h01", "role": "user", "content": original_request},
        {"id": "h02", "role": "tool", "content": catalog},
        {"id": "h03", "role": "assistant", "content": plan},
        {"id": "h04", "role": "user" if pair == "goal" else "tool", "content": checkpoint},
        {"id": "h05", "role": "assistant", "content":
         "Interruption occurred here. Continue the current workspace under its active requirements "
         "and remaining budget; planning statements alone are not tool execution evidence."},
    ]
    noise = distractors(pair, noise_count)
    if position == "early":
        history = base[:4] + noise + base[4:]
    elif position == "middle":
        mid = len(noise) // 2
        history = base[:3] + noise[:mid] + base[3:4] + noise[mid:] + base[4:]
    elif position == "late":
        history = base[:3] + noise + base[3:]
    else:
        raise ValueError(position)
    fixture = {"instance_id": ident, "environment_type": "continuation", "initial_state": initial,
               "operations": deepcopy(operations), "observations": deepcopy(observations), "budget": budget,
               "rubric": {"target_state": target, "finish_status": "completed",
                          "before_action": list(before), "forbidden_actions": list(forbidden)}}
    # Recovery keeps the original request and public tool definitions, not later historical updates.
    recovery_context = original_request + "\n" + catalog + "\n" + recovery["public_recovery_note"]
    reference_record = {"instance_id": ident,
                        "review": {"status": "pending", "author": "assistant_generated", "reviewer": None},
                        "source_message_ids": {"goal": ["h01", "h02", "h04"],
                                               "world.facts": ["h02", "h03", "h04"],
                                               "world.beliefs": ["h03", "h04"],
                                               "world.assumptions": ["h03", "h04"],
                                               "frontier": ["h01", "h02", "h04"]},
                        "provenance_notes": {
                            "operation_names": "Every named action/resource in this candidate occurs in h02.",
                            "checkpoint": "h04 is the current evidence or owner update; h03 is tentative.",
                            "future_observations": "Candidate does not insert any as-yet unread resource value."},
                        "state": reference}
    return {"instance_id": ident, "pair_id": None if control else pair, "variant": variant,
            "title": title, "primary_component": component, "control": control,
            "history_distractor_count": noise_count, "critical_evidence_position": position,
            "task": {"instance_id": ident, "history": history, "recovery_context": recovery_context,
                     "ablation_progress_terms": list(progress_terms)},
            "environment": fixture, "reference": reference_record,
            "review": {"instance_id": ident, "accepted_example": accepted + [deepcopy(FINISH)],
                       "no_history_recovery_strategy": recovery["strategy"],
                       "no_history_recovery_example": recovery["actions"] + [deepcopy(FINISH)],
                       "no_history_recovery_expected": recovery["expected"],
                       "candidate_status": "assistant_authored_not_independent_gold"}}


def build_cases():
    cases = []
    operations = {
        "dispatch_K": op("Send digest to the review desk.", {"recipient": "review"}),
        "dispatch_M": op("Send digest to the retention desk.", {"recipient": "retention"}),
    }
    observations = {"current/owner_scope": obs("Re-fetch the current owner scope.", {})}
    request = ("Workspace lumen: send the validated digest to the review desk. The latest owner "
               "scope is authoritative; do not send to any other desk. There are 3 credits at resumption.")
    for variant, recipient in (("a", "retention"), ("b", "review")):
        chosen = "dispatch_M" if recipient == "retention" else "dispatch_K"
        unchosen = "dispatch_K" if chosen == "dispatch_M" else "dispatch_M"
        local_obs = deepcopy(observations)
        local_obs["current/owner_scope"]["observation"]["content"] = {"authorized_recipient": recipient}
        checkpoint = ("Owner scope 6 supersedes scope 1: redirect the digest to the retention desk; "
                      "the review desk is no longer authorized. Nothing has been dispatched." if variant == "a" else
                      "Owner scope 6 supersedes scope 1: retain the review desk as the sole recipient; "
                      "the retention desk is not authorized. Nothing has been dispatched.")
        recovery = {"public_recovery_note": "Current owner scope can be re-fetched; later owner instructions are not retained here.",
                    "strategy": "Always re-fetch the current scope, then dispatch only its authorized recipient.",
                    "actions": [observe("current/owner_scope"), execute(chosen)],
                    "expected": {"task_success": True, "credits": 3, "retained_history_credits": 2}}
        cases.append(make_case("goal", variant, "收件目标的更新与延续", "G", request,
            "The tentative plan under scope 1 is dispatch_K. That plan has not been executed.", checkpoint,
            {"recipient": "none"}, operations, local_obs, 3, {"recipient": recipient},
            state("Dispatch digest under the latest owner scope", ["Only the currently authorized desk receives the digest"],
                  ["Latest owner scope supersedes earlier plans", "3 credits"],
                  [f"Scope 6 authorizes only the {recipient} desk", "Nothing has been dispatched"], f"execute {chosen}"),
            [execute(chosen)], recovery, noise_count=8, position="early",
            progress_terms=["nothing has been dispatched"], forbidden=[execute(unchosen)]))

    operations = {"remedy_N": op("Apply the ion-channel remedy.", {"remedy": "ion"}),
                  "remedy_T": op("Apply the flux-channel remedy.", {"remedy": "flux"})}
    request = ("Workspace lumen: resolve the sensor incident using controlled diagnosis, never a conjecture. "
               "An incorrect irreversible remedy is forbidden. There are 3 credits at resumption.")
    for variant, cause in (("a", "ion"), ("b", "flux")):
        chosen = "remedy_N" if cause == "ion" else "remedy_T"
        unchosen = "remedy_T" if chosen == "remedy_N" else "remedy_N"
        observations = {"current/isolation": obs("Repeat the controlled sensor isolation.",
                        {"confirmed_channel": cause}, {"diagnosis_confirmed": True})}
        recovery = {"public_recovery_note": "A fresh controlled isolation can be obtained after interruption.",
                    "strategy": "Always repeat isolation, then apply the remedy for its confirmed channel.",
                    "actions": [observe("current/isolation"), execute(chosen)],
                    "expected": {"task_success": True, "credits": 3, "retained_history_credits": 2}}
        cases.append(make_case("belief", variant, "控制证据确认或推翻旧信念", "W", request,
            "Before isolation I suspected ion, confidence 0.64. That was a belief, not a measured cause.",
            f"Controlled isolation actually completed: {cause} is confirmed; the other channel is excluded. "
            "No remediation has been applied.", {"remedy": "none", "diagnosis_confirmed": True},
            operations, observations, 3, {"remedy": cause, "diagnosis_confirmed": True},
            state("Resolve incident using controlled evidence", ["Apply only the confirmed channel remedy"],
                  ["No conjectural or incorrect irreversible remedy", "3 credits"],
                  [f"Controlled isolation confirmed {cause} and excluded the other channel", "No remediation has been applied"],
                  f"execute {chosen}"), [execute(chosen)], recovery, noise_count=24, position="late",
            progress_terms=["no remediation has been applied"], forbidden=[execute(unchosen)],
            before=[{"action": execute(name), "state": {"diagnosis_confirmed": True}} for name in operations]))

    operations = {"encode_L": op("Encode packet with the rune contract.", {"encoding": "rune"}),
                  "encode_V": op("Encode packet with the tile contract.", {"encoding": "tile"})}
    request = ("Workspace lumen: encode the packet according to the current receiver negotiation, "
               "not an unverified default. Only one encoding attempt is allowed. 3 credits remain.")
    for variant, encoding in (("a", "tile"), ("b", "rune")):
        chosen = "encode_V" if encoding == "tile" else "encode_L"
        unchosen = "encode_L" if chosen == "encode_V" else "encode_V"
        observations = {"current/negotiation": obs("Repeat receiver negotiation.", {"contract": encoding})}
        recovery = {"public_recovery_note": "The current receiver negotiation can be repeated for its listed cost.",
                    "strategy": "Always negotiate again, then encode under the observed contract.",
                    "actions": [observe("current/negotiation"), execute(chosen)],
                    "expected": {"task_success": True, "credits": 3, "retained_history_credits": 2}}
        cases.append(make_case("assumption", variant, "默认编码被握手证据更新", "W", request,
            "Until negotiation, I assume the old rune contract remains in force. encode_L is tentative, not executed.",
            f"Receiver negotiation completed and certifies the {encoding} contract. It replaces the tentative default. "
            "Packet has not yet been encoded.", {"encoding": "none"}, operations, observations, 3,
            {"encoding": encoding}, state("Encode according to current receiver negotiation", ["Observed contract is used"],
                  ["Only one encoding attempt", "3 credits"],
                  [f"Negotiation certifies {encoding}; old rune default is superseded", "Packet has not yet been encoded"],
                  f"execute {chosen}"), [execute(chosen)], recovery, noise_count=12, position="middle",
            progress_terms=["not yet been encoded"], forbidden=[execute(unchosen)]))

    operations = {"calibrate_J": op("Calibrate oak rack; repeating calibration also costs 2 credits.",
                                    {"oak_calibrated": True}, repeat_key="oak_calibrated"),
                  "calibrate_R": op("Calibrate elm rack; repeating calibration also costs 2 credits.",
                                    {"elm_calibrated": True}, repeat_key="elm_calibrated")}
    request = ("Workspace lumen: ensure both oak and elm racks are calibrated. Do not repeat validated "
               "calibrations, which consume scarce vials. There are 3 credits at resumption.")
    for variant, done in (("a", "oak"), ("b", "elm")):
        remaining = "elm" if done == "oak" else "oak"
        chosen = "calibrate_R" if remaining == "elm" else "calibrate_J"
        unchosen = "calibrate_J" if chosen == "calibrate_R" else "calibrate_R"
        observations = {"current/calibration_ledger": obs("Retrieve the signed rack calibration ledger.",
                        {"validated_rack": done}, cost=2)}
        recovery = {"public_recovery_note": "Calibration progress can be recovered from the signed ledger at its listed cost.",
                    "strategy": "Always retrieve the ledger, then calibrate the rack it reports as still unresolved.",
                    "actions": [observe("current/calibration_ledger"), execute(chosen)],
                    "expected": {"task_success": False, "credits": 4, "retained_history_credits": 2,
                                 "failure": "ledger recovery plus necessary remaining work exceeds 3 credits"}}
        cases.append(make_case("completed", variant, "已验证校准与未完成校准", "F", request,
            "The initial plan was calibrate_J and calibrate_R. Either order is valid; the plan alone proves no calibration.",
            f"Signed checkpoint: {done} calibration completed and validated. {remaining} calibration has not run.",
            {"oak_calibrated": done == "oak", "elm_calibrated": done == "elm"}, operations, observations, 3,
            {"oak_calibrated": True, "elm_calibrated": True},
            state("Complete both rack calibrations without repeating validated work", ["Both racks calibrated"],
                  ["Do not repeat validated calibration", "3 credits"],
                  [f"{done} calibration completed and validated", f"{remaining} calibration has not run"],
                  f"execute {chosen}"), [execute(chosen)], recovery, noise_count=32, position="early",
            progress_terms=["calibration completed", "calibration has not run"], forbidden=[execute(unchosen)]))

    operations = {
        "request_D": op("Submit a reservation to jade broker; creates a new request.",
                        {"pending_jade": True}, increments={"request_count": 1}),
        "request_H": op("Submit a reservation to pearl broker; creates a new request.",
                        {"pending_pearl": True}, increments={"request_count": 1}),
        "consume_U": op("Consume the jade broker notice; requires an accepted jade reservation.",
                        {"fulfilled": True}, required_state={"pending_jade": True}),
        "consume_Z": op("Consume the pearl broker notice; requires an accepted pearl reservation.",
                        {"fulfilled": True}, required_state={"pending_pearl": True}),
    }
    request = ("Workspace lumen: obtain exactly one fulfilled reservation using either broker. "
               "Do not submit another reservation once one has been accepted. 3 credits remain at resumption.")
    for variant, broker in (("a", "pearl"), ("b", "jade")):
        chosen = "consume_Z" if broker == "pearl" else "consume_U"
        observations = {"current/reservation_ledger": obs("Recover accepted reservation identity from the ledger.",
                        {"accepted_broker": broker}, cost=2)}
        recovery = {"public_recovery_note": "Accepted reservation identity can be recovered from the reservation ledger; tool precondition failures also consume operation credits.",
                    "strategy": "Always recover the accepted reservation identity, then consume its notice; never submit a second request.",
                    "actions": [observe("current/reservation_ledger"), execute(chosen)],
                    "expected": {"task_success": False, "credits": 4, "retained_history_credits": 2,
                                 "failure": "identity recovery plus notice consumption exceeds 3 credits"}}
        cases.append(make_case("inflight", variant, "在途预约的真实身份", "F", request,
            "I initially considered request_D, followed by consume_U. This tentative sequence is not an acceptance receipt.",
            f"Broker acknowledgement: exactly one reservation was accepted by {broker}; its notice is pending. "
            "No reservation has been fulfilled yet and no second request was sent.",
            {"pending_jade": broker == "jade", "pending_pearl": broker == "pearl", "request_count": 1, "fulfilled": False},
            operations, observations, 3, {"request_count": 1, "fulfilled": True},
            state("Fulfil exactly one accepted reservation", ["One request total; accepted reservation fulfilled"],
                  ["Do not submit another request after acceptance", "3 credits"],
                  [f"Exactly one pending reservation was accepted by {broker}", "No reservation has been fulfilled yet"],
                  f"execute {chosen}", needs=["Fulfilment notice for the accepted reservation"]),
            [execute(chosen)], recovery, noise_count=16, position="late",
            progress_terms=["pending reservation", "fulfilled yet"], forbidden=[execute("request_D"), execute("request_H")]))

    operations = {f"register_{cargo}_{site}": op(f"Register certificate pair cargo={cargo}, venue={site}.",
                                               {"registered_pair": f"{cargo}_{site}"}, cost=1)
                  for cargo in ("R14", "R29") for site in ("P48", "P63")}
    observations = {
        "current/cargo_certificate": obs("Read the current cargo certificate.", {"cargo_code": "R29"},
                                         {"cargo_verified": True}, cost=2),
        "current/venue_certificate": obs("Read the current venue certificate.", {"venue_code": "P63"},
                                         {"venue_verified": True}, cost=2),
        "current/certificate_index": obs("Recover which certificate was already verified, excluding its value.", {}, cost=2),
    }
    request = ("Workspace lumen: register a pair matching verified cargo and venue certificates. "
               "Never register an unread certificate by guessing. 3 credits remain at resumption.")
    for variant, known in (("a", "cargo"), ("b", "venue")):
        missing = "venue" if known == "cargo" else "cargo"
        code = "R29" if known == "cargo" else "P63"
        local_obs = deepcopy(observations)
        local_obs["current/certificate_index"]["observation"]["content"] = {"already_verified": known}
        recovery = {"public_recovery_note": "Certificate values can each be read again for 2 credits. The optional index identifies prior verification but supplies no certificate values.",
                    "strategy": "Without trusting or guessing lost certificate values, re-read cargo and venue and register their observed pair.",
                    "actions": [observe("current/cargo_certificate"), observe("current/venue_certificate"), execute("register_R29_P63")],
                    "expected": {"task_success": False, "credits": 5, "retained_history_credits": 3,
                                 "failure": "two evidence readings plus registration exceed 3 credits"}}
        cases.append(make_case("information", variant, "已知证书与剩余信息缺口", "F", request,
            "The initial plan was read both certificate resources, then select their matching registration operation. No values can be inferred from that plan.",
            f"Verification receipt: {known} certificate verified with code {code}; {missing} certificate has not been read. No pair registered.",
            {"cargo_verified": known == "cargo", "venue_verified": known == "venue", "registered_pair": "none"},
            operations, local_obs, 3, {"cargo_verified": True, "venue_verified": True, "registered_pair": "R29_P63"},
            state("Register a pair matching both verified certificates", ["Both codes verified; matching pair registered"],
                  ["Do not guess unread certificates", "3 credits"],
                  [f"{known} certificate verified with code {code}", f"{missing} certificate has not been read", "No pair registered"],
                  f"observe current/{missing}_certificate; choose the operation matching the retained and newly observed codes",
                  needs=[f"Value of the {missing} certificate"]),
            [observe(f"current/{missing}_certificate"), execute("register_R29_P63")], recovery,
            noise_count=40, position="middle", progress_terms=["certificate verified", "certificate has not been read", "no pair registered"],
            before=[{"action": execute(name), "state": {"cargo_verified": True, "venue_verified": True}}
                    for name in operations]))

    operations = {"route_B": op("Route the parcel through delta lane.", {"lane": "delta"}),
                  "route_F": op("Route the parcel through sigma lane.", {"lane": "sigma"})}
    observations = {"current/lane_status": obs("Read the current certified open lane.", {"open_lane": "sigma"},
                                              {"lane_checked": True})}
    request = ("Workspace lumen: read current/lane_status and route the parcel through its certified open lane. "
               "All evidence required for routing is publicly available now. 3 credits remain.")
    recovery = {"public_recovery_note": "All required evidence can be obtained from current/lane_status; no historical reading is assumed.",
                "strategy": "Read lane status and route through its observed open lane.",
                "actions": [observe("current/lane_status"), execute("route_F")],
                "expected": {"task_success": True, "credits": 3, "retained_history_credits": 3}}
    cases.append(make_case("control_recoverable", "a", "全部必要证据可重获", "control", request,
        "Plan: obtain current lane evidence before routing.", "No lane has been checked and no parcel routed.",
        {"lane_checked": False, "lane": "none"}, operations, observations, 3,
        {"lane_checked": True, "lane": "sigma"},
        state("Route through the currently certified open lane", ["Current lane evidence read; matching routing done"],
              ["3 credits", "Read evidence before routing"], ["No lane checked", "No parcel routed"],
              "observe current/lane_status; route through its certified lane", needs=["Current open lane"]),
        [observe("current/lane_status"), execute("route_F")], recovery, noise_count=4, position="late",
        progress_terms=["no lane checked", "no parcel routed"],
        before=[{"action": execute(name), "state": {"lane_checked": True}} for name in operations], control=True))

    operations = {"validate_E": op("Run the left fixture validation.", {"left_validated": True}, repeat_key="left_validated"),
                  "validate_W": op("Run the right fixture validation.", {"right_validated": True}, repeat_key="right_validated")}
    request = "Workspace lumen: validate the left and right fixtures, then finish. Do not repeat validated work. 0 credits remain at resumption."
    recovery = {"public_recovery_note": "Only original requirements and public tool definitions are retained; no historical validation receipt is supplied.",
                "strategy": "A finish-only probe is shown for review; it does not establish that a history-free agent can justify completion.",
                "actions": [], "expected": {"task_success": True, "credits": 0, "retained_history_credits": 0,
                                               "limitation": "world is already complete; finish can succeed without retained proof"}}
    cases.append(make_case("control_completed", "a", "实质工作已完成的结束对照", "control", request,
        "Initial plan was to validate both fixtures.", "Signed validation receipt: left and right fixtures both validated. Only finish remains.",
        {"left_validated": True, "right_validated": True}, operations, {}, 0,
        {"left_validated": True, "right_validated": True},
        state("Close the validated fixture task", ["Finish after both fixtures are validated"],
              ["Do not repeat validated work", "0 credits"], ["Left and right fixtures both validated", "Only finish remains"],
              "finish completed"), [], recovery, noise_count=4, position="early",
        progress_terms=["both validated", "only finish remains"], control=True))
    return cases


def replay(fixture, actions):
    env = ContinuationEnvironment(fixture)
    for action in actions:
        env.apply(action)
    return env.evaluate()


def audit_cases(cases):
    """Offline construction gates, including costs and counterfactual action swaps."""
    pairs = {}
    results = []
    for case in cases:
        ident = case["instance_id"]
        CognitiveState.from_dict(case["reference"]["state"])
        payload = json.dumps(case["reference"]["state"], ensure_ascii=False, separators=(",", ":"))
        if len(payload.encode("utf-8")) > 2200:
            raise AssertionError(f"Oversized candidate: {ident}")
        correct = replay(case["environment"], case["review"]["accepted_example"])
        if not correct["task_success"]:
            raise AssertionError(f"Invalid accepted path: {ident}")
        recovery = replay(case["environment"], case["review"]["no_history_recovery_example"])
        expected = case["review"]["no_history_recovery_expected"]
        if recovery["task_success"] != expected["task_success"] or recovery["workspace_credits_spent"] != expected["credits"]:
            raise AssertionError(f"Recovery claim mismatch: {ident}")
        # All reference action/resource identifiers must have appeared in the public historical tool record.
        historical_catalog = next(h["content"] for h in case["task"]["history"] if h["id"] == "h02")
        frontier_text = case["reference"]["state"]["frontier"]["next_action"]
        for name in list(case["environment"]["operations"]) + list(case["environment"]["observations"]):
            if name in frontier_text and name not in historical_catalog:
                raise AssertionError(f"Action has no historical source: {ident}/{name}")
        if case["pair_id"]:
            pairs.setdefault(case["pair_id"], []).append(case)
        results.append({"instance_id": ident, "accepted_success": correct["task_success"],
                        "accepted_credits": correct["workspace_credits_spent"],
                        "uniform_recovery_success": recovery["task_success"],
                        "uniform_recovery_credits": recovery["workspace_credits_spent"]})
    swaps = []
    for pair, members in pairs.items():
        if len(members) != 2:
            raise AssertionError(f"Pair cardinality: {pair}")
        first, second = members
        for key in ("operations", "budget"):
            if first["environment"][key] != second["environment"][key]:
                raise AssertionError(f"Unequal public choices/budget: {pair}/{key}")
        # Resource values may differ causally; their definitions and prices cannot.
        definition = lambda case: {k: {"description": v["description"], "cost": v["cost"]}
                                   for k, v in case["environment"]["observations"].items()}
        if definition(first) != definition(second):
            raise AssertionError(f"Unequal resource definitions: {pair}")
        for current, opposite in ((first, second), (second, first)):
            result = replay(current["environment"], opposite["review"]["accepted_example"])
            own = replay(current["environment"], current["review"]["accepted_example"])
            if result["task_success"] and result["workspace_credits_spent"] <= own["workspace_credits_spent"]:
                raise AssertionError(f"Action swap neither fails nor costs more: {current['instance_id']}")
            swaps.append({"instance_id": current["instance_id"], "swapped_success": result["task_success"],
                          "swapped_credits": result["workspace_credits_spent"]})
    return {"dataset_version": "exp001-continuation-v0.2", "tasks": len(cases), "pairs": len(pairs),
            "controls": sum(c["control"] for c in cases), "instances": results, "swaps": swaps,
            "note": "Scripted recovery paths are illustrative policies, not exhaustive bounds on model performance."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "datasets/exp001/continuation_v0.2")
    args = parser.parse_args()
    cases = build_cases()
    report = audit_cases(cases)
    args.output.mkdir(parents=True, exist_ok=False)
    manifest = {"dataset_version": "exp001-continuation-v0.2", "status": "draft_pending_researcher_review",
                "construction": "assistant_authored_synthetic_counterfactuals",
                "reference_role": "source_review_only_not_primary_comparison", "instances": []}
    for case in cases:
        paths = {key: f"{directory}/{case['instance_id']}.json" for key, directory in
                 (("task", "tasks"), ("environment", "environments"), ("reference", "references"), ("review", "review_cases"))}
        for key, relative in paths.items():
            save_json(args.output / relative, case[key])
        metadata = {key: case[key] for key in ("instance_id", "pair_id", "variant", "title", "primary_component",
                                              "control", "history_distractor_count", "critical_evidence_position")}
        manifest["instances"].append(metadata | paths)
    save_json(args.output / "manifest.json", manifest)
    save_json(args.output / "construction_audit.json", report)
    print(f"Created {len(cases)} offline tasks in {args.output.resolve()}; accepted paths and swaps audited")


if __name__ == "__main__":
    main()
