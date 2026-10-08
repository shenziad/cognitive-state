"""Build pre-call history diagnostics using public histories and world scoring.

No model, credential, or .env access. Original workflow data remain unchanged.
"""

from copy import deepcopy
from itertools import product
from pathlib import Path
import argparse
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from evaluation.lifecycle import LifecycleEnvironment

SOURCE = ROOT / "datasets/independent_workflows_v01"
DEST = ROOT / "datasets/history_diagnostics_v01"
FINISH = {"tool": "finish", "arguments": {"status": "completed"}}
BLOCK = {"tool": "finish", "arguments": {"status": "blocked"}}
MAX_CALLS = 4

# Select the latest later checkpoint requiring a new parameter/object choice;
# preserving an already-selected parameter is not a new choice. Otherwise h4.
SELECTION = {
    "iw01": (2, "New release-slot choice Friday versus Monday."),
    "iw02": (4, "Fallback: the diagnostic choice is h1, not a later checkpoint."),
    "iw03": (4, "Fallback: later stages collect/validate fixed exports, then deliver."),
    "iw04": (4, "Choose the permitted release asset, landscape versus portrait."),
    "iw05": (4, "Fallback: later stages update or release the fixed review."),
    "iw06": (4, "Fallback: later stages check or release fixed calibration c2."),
    "iw07": (2, "New hotel-location choice station versus venue."),
    "iw08": (3, "New contact-channel choice email versus SMS."),
    "iw09": (4, "Choose the requested production snapshot, s8 versus archived s7."),
    "iw10": (2, "New fit-version choice cohort v2 versus v1."),
    "iw11": (4, "Fallback: later stages switch/revoke/record the fixed rotation."),
    "iw12": (4, "Fallback: later stages reconcile or report the fixed delivery."),
}


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)
                    + "\n", encoding="utf-8", newline="\n")


def execute(name):
    return {"tool": "execute", "arguments": {"operation": name}}


def event(identity, role, content):
    if not isinstance(content, str):
        content = json.dumps(content, ensure_ascii=False, sort_keys=True)
    return {"id": identity, "role": role, "content": content}


def trace_public_events(env, prefix):
    events = []
    for number, item in enumerate(env.trace):
        # state_after and all scoring remain evaluator-only.
        events.append(event(f"{prefix}:action{number}", "assistant", item["action"]))
        events.append(event(f"{prefix}:receipt{number}", "tool", item["observation"]))
    return events


def all_success_routes(fixture):
    """Enumerate finite named actions followed by finish within four calls.

    Unknown-resource/catalog reads and malformed syntax cannot change world or
    recover the missing historical fact. They may pad a path but cannot create a
    new successful finite action sequence; paid precondition failures ARE kept.
    This is sequence solvability, not a theorem about all adaptive policies.
    """
    named = ([execute(name) for name in fixture["operations"]]
             + [{"tool": "observe", "arguments": {"resource": name}}
                for name in fixture["observations"]])
    successful = {}
    attempted = 0
    for count in range(MAX_CALLS):
        for prefix in product(named, repeat=count):
            path = list(prefix) + [deepcopy(FINISH)]
            env = LifecycleEnvironment(fixture)
            for action in path:
                env.apply(action)
            attempted += 1
            if env.evaluate()["task_success"]:
                successful[digest(path)] = {"actions": path, "credits": env.spent}
    return successful, attempted


def original_tasks(public, private, paths):
    result, fixtures, review = [], [], []
    pri = {x["workflow_id"]: x for x in private["workflows"]}
    sol = {x["workflow_id"]: x for x in paths["workflows"]}
    for workflow in public["workflows"]:
        wid = workflow["workflow_id"]
        selected, reason = SELECTION[wid]
        source_private = pri[wid]
        history, blocked_history = [], []
        world = deepcopy(source_private["initial_state"])
        blocked_world = deepcopy(world)
        for index in range(selected - 1):
            checkpoint = workflow["checkpoints"][index]
            handoff = source_private["handoffs"][index]
            world.update(deepcopy(handoff["external_state_patch"]))
            blocked_world.update(deepcopy(handoff["external_state_patch"]))
            fixture = deepcopy(handoff["environment"])
            fixture["initial_state"] = deepcopy(world)
            env = LifecycleEnvironment(fixture)
            alt = deepcopy(fixture)
            alt["initial_state"] = deepcopy(blocked_world)
            blocked_env = LifecycleEnvironment(alt)
            interface_event = event(f"{wid}:h{index + 1}:interface", "runtime",
                                    env.public_interface(handoff["instance_id"]))
            history.extend(deepcopy(checkpoint["new_public_events"]) + [interface_event])
            blocked_history.extend(deepcopy(checkpoint["new_public_events"]) + [deepcopy(interface_event)])
            for action in sol[wid]["handoffs"][index]["actions"]:
                env.apply(action)
            assert env.evaluate()["task_success"]
            blocked_env.apply(BLOCK)
            assert blocked_env.trace[-1]["valid"] and not blocked_env.trace[-1]["policy_violations"]
            history.extend(trace_public_events(env, f"{wid}:h{index + 1}"))
            blocked_history.extend(trace_public_events(blocked_env, f"{wid}:h{index + 1}"))
            world = deepcopy(env.settings)
            blocked_world = deepcopy(blocked_env.settings)
        checkpoint = workflow["checkpoints"][selected - 1]
        handoff = source_private["handoffs"][selected - 1]
        world.update(deepcopy(handoff["external_state_patch"]))
        blocked_world.update(deepcopy(handoff["external_state_patch"]))
        fixture = deepcopy(handoff["environment"])
        assert world == fixture["initial_state"]
        alternative = deepcopy(fixture)
        alternative["initial_state"] = deepcopy(blocked_world)
        task_id = f"original_{wid}_h{selected}"
        task = {"task_id": task_id, "family": "original_candidate",
                "source_workflow_id": wid, "checkpoint": selected,
                "pair_id": None, "variant": None, "historical_context": history,
                "current_public_events": deepcopy(checkpoint["new_public_events"]),
                "public_interface": deepcopy(checkpoint["public_interface"])}
        assert LifecycleEnvironment(fixture).public_interface(handoff["instance_id"]) == task["public_interface"]
        assert LifecycleEnvironment(alternative).public_interface(handoff["instance_id"]) == task["public_interface"]
        canonical = deepcopy(sol[wid]["handoffs"][selected - 1]["actions"])
        canonical_env = LifecycleEnvironment(fixture)
        for action in canonical:
            canonical_env.apply(action)
        assert len(canonical) <= MAX_CALLS and canonical_env.evaluate()["task_success"]
        routes, attempted = all_success_routes(fixture)
        alt_routes, alt_attempted = all_success_routes(alternative)
        overlap = sorted(set(routes) & set(alt_routes))
        # Two distinct, separately solvable worlds with no common successful
        # sequence are a bounded fixed-sequence diagnostic; tool observations can
        # still support adaptive recovery. Do not upgrade this to necessity proof.
        bounded_conflict = bool(routes and alt_routes and not overlap)
        record = {"task_id": task_id, "selection_rule": reason,
                  "history_necessity_status": "not_proven",
                  "interpretation": "Canonical continuation alone does not establish history necessity. Current goals often restate the answer. The alternate allowed failed history is only an offline diagnostic, not a model allocation or a proof about adaptive policies.",
                  "alternate_history_type": "Each preceding checkpoint validly finishes blocked without paid actions; only declared external patches change the world.",
                  "alternate_historical_context": blocked_history,
                  "alternate_initial_state": blocked_world,
                  "current_material_and_interface_equal": True,
                  "canonical_successful_sequence_count": len(routes),
                  "alternative_successful_sequence_count": len(alt_routes),
                  "common_successful_sequence_count": len(overlap),
                  "bounded_fixed_sequence_conflict": bounded_conflict,
                  "enumerated_sequence_count": attempted + alt_attempted,
                  "common_route_example": routes[overlap[0]] if overlap else None,
                  "alternative_route_example": next(iter(alt_routes.values()), None),
                  "canonical_actions": canonical, "canonical_trace": deepcopy(canonical_env.trace),
                  "canonical_score": canonical_env.evaluate()}
        result.append(task)
        fixtures.append({"task_id": task_id, "environment": fixture,
                         "canonical_actions": canonical,
                         "source_reference": {"workflow_id": wid, "instance_id": handoff["instance_id"],
                                              "selection_rule": reason}})
        review.append(record)
    return result, fixtures, review


PAIR_SPECS = [
    {"pair_id": "hd01", "source": "iw01", "name": "Research release audience", "choices": ["internal", "public"],
     "fact": "The approved audience for archive release-27 is {value}. The approval applies to this archive only.",
     "fact_role": "user", "key": "audience", "operation_prefix": "publish_",
     "operation_description": "Publish archive release-27 to the {value} audience.",
     "ready_description": "Prepare the redacted, cited archive release-27; preparation does not authorize its audience.",
     "request": "Publish the prepared release-27 archive to its previously approved audience. Keep its redaction and citations."},
    {"pair_id": "hd02", "source": "iw07", "name": "Conference hotel location", "choices": ["station", "venue"],
     "fact": "For reservation hotel-88, the approved location is {value}. Step-free access remains mandatory; do not create another reservation.",
     "fact_role": "user", "key": "hotel_location", "operation_prefix": "confirm_",
     "operation_description": "Confirm the step-free option at {value} for the existing hotel-88 reservation.",
     "ready_description": "Obtain both step-free location options for the existing reservation hotel-88; neither is confirmed.",
     "request": "Confirm the previously approved location for the existing hotel-88 reservation. Step-free access and the one existing reservation remain required."},
    {"pair_id": "hd03", "source": "iw09", "name": "Approved recovery snapshot", "choices": ["s8", "s9"],
     "fact": "The recovery approval authorizes snapshot {value} for production restore restore-52. Both staged candidates have valid hash checks and rehearsals; approval selects only this version.",
     "fact_role": "user", "key": "restored_snapshot", "operation_prefix": "restore_",
     "operation_description": "Restore production from rehearsed and hash-checked snapshot {value}.",
     "ready_description": "Finish the signed checksum and rehearsal records for the two staged candidates s8 and s9; no production restore occurred.",
     "request": "Perform production restore restore-52 using its previously approved snapshot. Preserve the candidate checks and rehearsal records."},
    {"pair_id": "hd04", "source": "iw08", "name": "Customer contact permission", "choices": ["email", "SMS"],
     "fact": "The customer authorizes {value} as the notification channel for corrected invoice i7. This authorization is scoped to this billing notification.",
     "fact_role": "user", "key": "notification_channel", "operation_prefix": "notify_",
     "operation_description": "Send the checked corrected invoice i7 notification via {value}.",
     "ready_description": "Prepare corrected invoice i7 with its existing credit and verified tax; no customer notification was sent.",
     "request": "Notify the customer about checked corrected invoice i7 using the previously authorized channel. Keep the existing credit and service active."},
    {"pair_id": "hd05", "source": "iw12", "name": "Signed carton unit interpretation", "choices": [100, 120],
     "fact": "Signed notice pack-r2 for transfer-19 states {unit} units per carton. The recorded transfer moved 10 cartons once; calculate the report from this notice, without repeating any physical movement.",
     "fact_role": "tool", "key": "reported_units", "operation_prefix": "report_",
     "operation_description": "Commit the stock report with {value} units for the existing 10-carton transfer-19.",
     "ready_description": "Prepare the reconciled 10-carton transfer-19 ledger and original single-transfer receipt; the unit report remains uncommitted.",
     "request": "Commit the unit count for the existing 10-carton transfer-19 using its previously received signed pack-size notice. Do not repeat any movement."},
    {"pair_id": "hd06", "source": "iw11", "name": "Credential rotation record object", "choices": ["k9", "k10"],
     "fact": "Security approval rotation-81 requires the completion record to identify new credential {value}. Both candidates have been tested; this approval selects the active object for this rotation.",
     "fact_role": "user", "key": "recorded_new_credential", "operation_prefix": "record_",
     "operation_description": "Commit the rotation-81 completion record identifying tested new credential {value}.",
     "ready_description": "Prepare the verified test and client-switch evidence for candidate objects k9 and k10; old k8 is disabled and no completion record is committed.",
     "request": "Commit the rotation-81 completion record for its previously approved new-credential object. Retain the test, client-switch and old-k8 revocation evidence."},
]


def operation(description, effects, increments=None):
    return {"description": description, "cost": 1, "required_state": {"ready": True},
            "effects": effects, "increments": increments or {},
            "lifecycle_contract": {"kind": "sync_operation", "semantics": "Success confirms this operation's actual listed effects; it does not certify conformity with the historical authorization. No secret credential value is part of this virtual task."}}


def paired_tasks():
    tasks, fixtures, proof = [], [], []
    for spec in PAIR_SPECS:
        pid = spec["pair_id"]
        operations = {spec["operation_prefix"] + str(value): operation(
            spec["operation_description"].format(value=value),
            {spec["key"]: value, "committed": True}, {"commit_count": 1})
            for value in spec["choices"]}
        prepare_fixture = {"environment_type": "continuation", "instance_id": f"{pid}:preparation",
                           "initial_state": {"ready": True, "prepared": False, "preparation_count": 0},
                           "operations": {"prepare_evidence": operation(spec["ready_description"], {"prepared": True}, {"preparation_count": 1})},
                           "observations": {}, "budget": 4,
                           "rubric": {"target_state": {"prepared": True}, "finish_status": "completed"}}
        prepared = LifecycleEnvironment(prepare_fixture)
        prepared.apply(execute("prepare_evidence"))
        prepared.apply(FINISH)
        assert prepared.evaluate()["task_success"]
        current = [event(f"{pid}:current:u", "user", spec["request"] +
                         " Commit once only. Each listed choice is technically executable, but only the historically approved value satisfies the task. A wrong commitment cannot be repaired by sending a second commitment; never send both. The historical authorization or signed notice is unavailable from current resources."),
                   event(f"{pid}:current:runtime", "runtime", "This checkpoint has 4 credits and at most four tool calls including finish. Paid attempts consume credits. Catalog entries are contracts, not evidence of the approved value.")]
        members, success_sets = [], []
        for variant, value in zip(["a", "b"], spec["choices"]):
            tid = f"{pid}_{variant}"
            initial = {"ready": True, "prepared": True, "committed": False,
                       "commit_count": 0, spec["key"]: "unset", "preparation_count": 1}
            fixture = {"environment_type": "continuation", "instance_id": pid,
                       "initial_state": initial, "operations": deepcopy(operations), "observations": {}, "budget": 4,
                       "rubric": {"target_state": {spec["key"]: value, "committed": True,
                                  "commit_count": 1, "prepared": True, "preparation_count": 1},
                                  "finish_status": "completed"}}
            fact = spec["fact"].format(value=value, unit=value // 10 if isinstance(value, int) else value)
            source_fact = event(f"{pid}:approved_fact", spec["fact_role"], fact)
            history = [event(f"{pid}:earlier_goal", "user", "Prepare the task evidence, retain the scoped approval or signed notice, then continue when asked. Approval determines the later committed choice. Do not submit a guessed choice or duplicate commitment."),
                       source_fact]
            for number in range(12):
                history.append(event(f"{pid}:office:{number}", "assistant", f"Completed office note {number + 1}: room booking group {(number % 3) + 1} was updated; this is unrelated to the active business task."))
            history.extend(trace_public_events(prepared, f"{pid}:preparation"))
            task = {"task_id": tid, "family": "historical_counterfactual", "source_workflow_id": spec["source"],
                    "checkpoint": 4, "pair_id": pid, "variant": variant,
                    "historical_context": history, "current_public_events": deepcopy(current),
                    "public_interface": LifecycleEnvironment(fixture).public_interface(pid)}
            canonical = [execute(spec["operation_prefix"] + str(value)), deepcopy(FINISH)]
            env = LifecycleEnvironment(fixture)
            for action in canonical:
                env.apply(action)
            assert env.evaluate()["task_success"] and env.spent == 1 and len(canonical) == 2
            routes, attempted = all_success_routes(fixture)
            success_sets.append(set(routes))
            members.append({"task_id": tid, "variant": variant, "old_fact": fact,
                            "source_event_id": source_fact["id"], "choice": value,
                            "opposite_action": execute(spec["operation_prefix"] + str(spec["choices"][1 if variant == "a" else 0])),
                            "canonical_actions": canonical, "score": env.evaluate(), "trace": deepcopy(env.trace),
                            "successful_sequence_count": len(routes), "enumerated_sequence_count": attempted})
            tasks.append(task)
            fixtures.append({"task_id": tid, "environment": fixture, "canonical_actions": canonical,
                             "source_reference": {"new_counterfactual_extension": True, "source_business_workflow": spec["source"],
                                                  "pair_id": pid, "approval_source_event_id": source_fact["id"]}})
        first, second = tasks[-2:]
        assert first["current_public_events"] == second["current_public_events"]
        assert first["public_interface"] == second["public_interface"]
        first_history, second_history = first["historical_context"], second["historical_context"]
        differing = [i for i, (a, b) in enumerate(zip(first_history, second_history)) if a != b]
        assert differing == [1]
        overlap = success_sets[0] & success_sets[1]
        assert not overlap
        # The same choice yields identical public observations in both worlds;
        # there is no observation-based approved-value oracle before/after commit.
        for name in operations:
            observations = []
            for fixture_record in fixtures[-2:]:
                env = LifecycleEnvironment(fixture_record["environment"])
                observations.append(env.apply(execute(name)))
            assert observations[0] == observations[1]
        both = LifecycleEnvironment(fixtures[-2]["environment"])
        # In member a, commit b incorrectly then a correctly. The restored final
        # value still fails the explicit once-only rule (commit_count=2).
        for name in reversed(list(operations)):
            both.apply(execute(name))
        both.apply(FINISH)
        assert not both.evaluate()["task_success"]
        common_input = {"current_public_events": first["current_public_events"], "public_interface": first["public_interface"]}
        proof.append({"pair_id": pid, "business_name": spec["name"], "source_workflow_id": spec["source"],
                      "history_necessity_status": "proved_for_authored_pair_under_declared_interface",
                      "members": members, "history_differing_event_indices": differing,
                      "common_current_input_sha256": digest(common_input),
                      "common_current_events_sha256": digest(first["current_public_events"]),
                      "common_interface_sha256": digest(first["public_interface"]),
                      "all_successful_sequence_overlap_count": 0,
                      "same_action_public_receipts_equal": True,
                      "wrong_then_right_negative_score": both.evaluate(), "wrong_then_right_trace": deepcopy(both.trace),
                      "interpretation": "No current input or tool observation distinguishes the approval. Each member has a valid two-call route, but no same successful action sequence serves both. A deterministic No History policy has identical information and chooses the same distribution on both; random guesses can still succeed on individual members. This establishes a deliberately authored missing-fact control, not natural long-horizon performance."})
    return tasks, fixtures, proof


README = """# History diagnostics v0.1

Pre-call development diagnostics, authored by an assistant familiar with the
project. This is not an independent benchmark or natural workflow dataset.

## Fixed allocation

- 12 original workflow checkpoints, selected by semantic rule before API calls.
  Histories replay the candidate canonical prior actions. Selected checkpoints:
  iw01 h2, iw02 h4, iw03 h4, iw04 h4, iw05 h4, iw06 h4, iw07 h2,
  iw08 h3, iw09 h4, iw10 h2, iw11 h4, iw12 h4.
- 6 separately authored historical counterfactual pairs (12 members), extending
  six business narratives with genuine two-option commitment operations. They
  do not mutate the original candidate files. Mechanism A is assigned ALL 12
  paired members before calls, never selected by model performance.
- Total: 24 checkpoint tasks; Full/No History diagnostic = 48 assigned cells.
  The paired subset represents 6 correlated workflows, not 12 independent cases.

## Model input boundary

`tasks_public.json` is an authoring container, NOT a whole model message. Send
only one task's historical_context (except No History), current_public_events,
and public_interface. Do not send task_id, family, source_workflow_id, checkpoint,
pair_id, variant, provenance, validation, answers, fixtures, or later events.
All event content values are strings. History action receipts are actual public
observations; private trace state_after and score are never copied to history.
The pair interface scope and event IDs are shared between members, so opaque
variant identifiers cannot leak an approved value. The order of task selection
must be independently randomized by the frozen runner.

`fixtures_private.json` contains evaluator-only world, rubric, and canonical
actions; never expose it to extractors, planners or actors. Canonical actions are
solvability evidence, not exact-match behavior answers. Evaluate final world,
budget, legal finish and user requirements via existing LifecycleEnvironment.

## Necessity evidence and limits

`offline_history_necessity.json` retains source selection, canonical routes,
allowed all-blocked earlier-history counterexamples, and finite route analysis.
Original 12 are marked not_proven: canonical multi-handoff success alone does
not show history is needed; later instructions/catalogs may already give the
answer or required facts. An alternate failed world that cannot finish within
four calls is not accepted as a clean necessity pair. Tool-dependent adaptive
recovery remains a separate question on original tasks.

For each new pair exactly one early fact differs, while current events and
interface are byte-equivalent canonical JSON. Both choices are technically
executable in both worlds; no hidden approved-value precondition, current
resource or receipt discloses the answer. The explicit user rule allows one
commitment; commit_count records duplicates. Wrong followed by correct fails
world/constraint acceptance, rather than matching an exact action string.
All finite named-action routes up to four calls including finish are enumerated.
No sequence succeeds for both members. Each has a two-call, one-credit solution.
Random No History guesses may still succeed; the result is a missing-fact control,
not a claim that No History can never succeed or that CS has an advantage.

All single-checkpoint environments have four credits and at most four actor
calls including finish. The model runner must enforce the call limit; environment
alone records credits. Earlier canonical history is fixed across conditions;
these diagnostics do NOT test actual multi-handoff error propagation or evolving
state. Pending-job distractors are not claimed to prove lifecycle mechanisms.

`provenance.json` locks source hashes, selection, members, and builder/data hashes.
This data version is ready for review, not itself a model-experiment protocol.
The builder refuses overwriting by default. --refresh-unfrozen is allowed only
while provenance status remains reviewable_pre_call_diagnostics; after protocol
freeze, preserve this release and make a new version for corrections.
"""


def build(refresh=False):
    if not __debug__:
        raise SystemExit("Assertions required: do not run Python -O.")
    if DEST.exists():
        old = DEST / "provenance.json"
        if not refresh or not old.exists() or json.loads(old.read_text(encoding="utf-8")).get("status") != "reviewable_pre_call_diagnostics":
            raise SystemExit("Destination exists; refusing to overwrite preserved diagnostics.")
    source_names = ["public_workflows.json", "evaluator_fixtures.json", "offline_trajectories.json", "provenance.json"]
    source_hashes = {name: file_hash(SOURCE / name) for name in source_names}
    public = json.loads((SOURCE / source_names[0]).read_text(encoding="utf-8"))
    private = json.loads((SOURCE / source_names[1]).read_text(encoding="utf-8"))
    paths = json.loads((SOURCE / source_names[2]).read_text(encoding="utf-8"))
    originals, original_fixtures, original_review = original_tasks(public, private, paths)
    paired, pair_fixtures, pair_review = paired_tasks()
    DEST.mkdir(parents=True, exist_ok=True)
    version = "history-diagnostics-development-v01"
    write_json(DEST / "tasks_public.json", {"version": version, "tasks": originals + paired})
    write_json(DEST / "fixtures_private.json", {"version": version, "visibility": "evaluator_only_never_model_input", "tasks": original_fixtures + pair_fixtures})
    write_json(DEST / "offline_history_necessity.json", {"version": version, "model_calls": 0,
        "actor_call_limit_including_finish": MAX_CALLS, "credit_budget": 4,
        "original_task_count": 12, "original_history_necessity_not_proven_count": 12,
        "paired_workflow_count": 6, "paired_member_count": 12,
        "pair_necessity_proofs_passed": 6, "original_tasks": original_review, "counterfactual_pairs": pair_review})
    (DEST / "README.md").write_text(README, encoding="utf-8", newline="\n")
    assert source_hashes == {name: file_hash(SOURCE / name) for name in source_names}, "Original files changed"
    write_json(DEST / "provenance.json", {"version": version, "status": "reviewable_pre_call_diagnostics",
        "created_on": "2026-10-04", "model_calls_during_build": 0,
        "authorship": "Assistant-authored development diagnostics; author knows prior mechanisms and study results, but selects no task using new diagnostic model results.",
        "allocation_selected_before_any_diagnostic_API_calls": True,
        "selection_rule": "Latest later checkpoint requesting a substantive new parameter/object choice; otherwise h4. Existing selected parameters merely preserved at later stages do not create a new choice.",
        "original_selection": {wid: {"checkpoint": h, "reason": reason} for wid, (h, reason) in SELECTION.items()},
        "mechanism_A_allocation": {"selection": "all 12 counterfactual members", "task_ids": [task["task_id"] for task in paired], "independent_business_workflow_count": 6, "member_count": 12, "performance_based_selection": False},
        "source_sha256": source_hashes, "builder_sha256": file_hash(Path(__file__)),
        "public_input_projection": ["historical_context (absent in No History)", "current_public_events", "public_interface"],
        "metadata_never_model_input": ["task_id", "family", "source_workflow_id", "checkpoint", "pair_id", "variant"],
        "sha256": {path.name: file_hash(path) for path in sorted(DEST.iterdir()) if path.is_file() and path.name != "provenance.json"}})
    print(json.dumps({"version": version, "original_tasks": 12, "counterfactual_pairs": 6,
                      "paired_members": 12, "total_tasks": 24, "necessity_pair_proofs": 6,
                      "original_necessity": "not_proven", "model_calls": 0}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh-unfrozen", action="store_true")
    build(parser.parse_args().refresh_unfrozen)
