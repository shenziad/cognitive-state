"""Supplemental descriptive comparisons for a COMPLETE cycle5 mechanism run.

This is a reporting extension, not a replacement for the frozen main analysis.
It does not select successes, modify states, call a model or load credentials.
Executor-input reduction includes all paid executor messages, not just retained
text, and is reported separately from complete strategy provider-token cost.
"""

from collections import Counter
from pathlib import Path
import json
from statistics import mean


CONDITIONS = ("full_context", "full_planner", "summary_s1", "summary_s2", "cs1", "cs_text")
DIMENSIONS = ("entity_phase_confusion", "unsupported_completion", "invented_requirement",
              "missing_pending_job", "unsupported_reopened_question", "missing_decision_dependency")


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _read(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            _require(key not in result, "Duplicate artifact JSON key")
            result[key] = value
        return result

    def finite(value):
        raise ValueError("Nonfinite artifact JSON number")

    return json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=unique, parse_constant=finite)


def _execution_audit(run):
    # Import only when a complete saved run is being reported. This frozen audit
    # checks source review, projection, responses, scores and actual world replay.
    from experiments.exp004_mechanism.runtime_v3 import audit_run
    return audit_run(run)


def _usage(ledger, indices):
    indices = list(indices)
    _require(len(indices) == len(set(indices)), "Usage indices repeat within a strategy")
    input_tokens = output_tokens = 0
    for i in indices:
        _require(type(i) is int and 0 <= i < len(ledger), "Cost index outside ledger")
        metadata = ledger[i].get("metadata", {})
        for key in ("input_tokens", "output_tokens"):
            _require(type(metadata.get(key)) is int and metadata[key] >= 0, "Unknown provider usage")
        input_tokens += metadata["input_tokens"]
        output_tokens += metadata["output_tokens"]
    return {"request_attempts": len(indices), "input_tokens": input_tokens,
            "output_tokens": output_tokens, "total_tokens": input_tokens + output_tokens}


def _reduction(value, baseline):
    return 1 - value / baseline if baseline > 0 else None


def _source_class(assessment):
    values = set(assessment.values())
    if "incorrect" in values:
        return "concrete_error"
    if "ambiguous" in values:
        return "ambiguous_without_concrete_error"
    if values == {"not_observed"}:
        return "not_observed"
    if values == {"correct"}:
        return "correct"
    return "partially_observed"


def describe_complete_run(run: Path) -> dict:
    """Return all-assigned 12-task/6-pair cost and source/behavior descriptions.

    The frozen V3 audit must pass and declare the run complete. Encoding and
    behavioral failures remain included. Shared CS preparation is charged to
    both independent deployment strategies and once to the actual ledger.
    A last-response Token-threshold overshoot is allowed; sending any further
    request at/after the threshold is an error. No currency price is inferred.
    """
    run = Path(run).resolve()
    manifest, config = _read(run / "manifest.json"), _read(run / "config.json")
    _require(manifest.get("status") == "completed", "Full comparisons require a completed run")
    _require(config.get("stage") == "mechanism", "Reporting extension requires mechanism stage")
    _require(tuple(config.get("conditions", [])) == CONDITIONS, "Six declared conditions are required")
    task_ids = config.get("task_ids", [])
    _require(len(task_ids) == 12 and len(set(task_ids)) == 12, "Exactly 12 assigned task versions are required")
    rows, ledger, prepared = (_read(run / name) for name in ("results.json", "call_ledger.json", "prepared.json"))
    assignments = {(task, condition) for task in task_ids for condition in CONDITIONS}
    _require(len(rows) == len(assignments) == manifest.get("assigned_cells"), "Saved allocation is incomplete")
    row_map = {(row["task_id"], row["condition"]): row for row in rows}
    preparation = {(p["task_id"], p["condition"]): p for p in prepared}
    _require(len(row_map) == len(rows) and set(row_map) == assignments, "Duplicate/missing result assignment")
    _require(len(preparation) == len(prepared) and set(preparation) == assignments, "Duplicate/missing preparation assignment")
    audit = _execution_audit(run)
    _require(audit.get("complete") is True, "Frozen execution replay did not declare complete")

    actual = _usage(ledger, range(len(ledger)))
    _require(len(ledger) <= config["max_api_calls"], "Actual request cap exceeded")
    ids = []
    prefix_tokens = 0
    threshold = config["token_stop_threshold"]
    _require(type(threshold) is int and threshold > 0, "Invalid Token stop threshold")
    for index, attempt in enumerate(ledger):
        _require(attempt.get("request_index") == index, "Ledger sequence differs")
        _require(attempt.get("status") == "response", "Complete comparison contains nonresponse attempt")
        _require(prefix_tokens < threshold, "Request was sent after Token stopping threshold")
        _require((attempt.get("task_id"), attempt.get("condition")) in assignments, "Ledger owner outside allocation")
        phase, purpose = attempt.get("phase"), attempt.get("purpose", "")
        _require(phase in {"prepare", "execute"}, "Unknown ledger phase")
        _require((phase == "execute") == (purpose == "executor"), "Phase/purpose disagree")
        maximum = config["intermediate_max_output_tokens"] if purpose.endswith((":planner", ":organizer")) else config["max_output_tokens"]
        _require(attempt.get("request_settings", {}).get("max_output_tokens") == maximum, "Recorded output allowance differs")
        response_id = attempt.get("metadata", {}).get("response_id")
        _require(isinstance(response_id, str) and bool(response_id), "Missing unique provider response ID")
        ids.append(response_id)
        prefix_tokens += _usage(ledger, [index])["total_tokens"]
    _require(len(ids) == len(set(ids)), "Provider response ID reused")
    _require(audit.get("usage", {}).get("unknown_usage_attempts") == 0, "Replay contains unknown usage")
    _require(audit["usage"]["request_attempts"] == actual["request_attempts"]
             and audit["usage"]["total_tokens"] == actual["total_tokens"], "Audit/full ledger cost totals differ")

    references, deployed_total = Counter(), {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "request_attempts": 0}
    cells = {}
    pairs = {}
    for task in task_ids:
        base = row_map[(task, "full_context")]
        pair_id, variant = base.get("pair_id"), base.get("variant")
        _require(isinstance(pair_id, str) and bool(pair_id) and isinstance(variant, str), "Missing paired-version identity")
        pairs.setdefault(pair_id, []).append(task)
        for condition in CONDITIONS:
            row, p = row_map[(task, condition)], preparation[(task, condition)]
            _require((row.get("pair_id"), row.get("variant")) == (pair_id, variant), "Pair labels differ between conditions")
            _require(type(row.get("success")) is bool, "Saved success must be Boolean")
            sources, executors = row["source_request_indices"], row["executor_request_indices"]
            _require(row["request_indices"] == sources + executors, "Deployment indices omit/add costs")
            own = p["actual_prepare_request_indices"]
            _require(p["source_request_indices"] == sources, "Saved source attribution differs")
            _require(len(executors) <= config["max_steps"], "Executor request allowance exceeded")
            for i in own:
                _require(ledger[i].get("phase") == "prepare" and ledger[i].get("condition") == condition
                         and ledger[i].get("task_id") == task, "Actual preparation ownership differs")
            for i in executors:
                _require(ledger[i].get("phase") == "execute" and ledger[i].get("condition") == condition
                         and ledger[i].get("task_id") == task, "Executor ownership differs")
            expected_source = preparation[(task, "cs1")]["actual_prepare_request_indices"] if condition == "cs_text" else own
            _require(sources == expected_source, "Shared extraction source indices differ")
            for i in sources:
                _require(ledger[i].get("phase") == "prepare" and ledger[i].get("task_id") == task
                         and ledger[i].get("condition") == ("cs1" if condition == "cs_text" else condition), "Source owner differs")
            _require(not own if condition in {"full_context", "cs_text"} else bool(own), "Actual preparation allocation differs")
            total, preprocessing, execution = (_usage(ledger, x) for x in (row["request_indices"], sources, executors))
            _require(total["total_tokens"] == preprocessing["total_tokens"] + execution["total_tokens"], "Preprocessing/execution totals do not add")
            _require(row["deployment_usage"]["total_tokens"] == total["total_tokens"], "Recorded deployment cost differs")
            references.update(row["request_indices"])
            for key in deployed_total:
                deployed_total[key] += total[key]
            rep = p["preparation"]["representation"]
            _require(rep is None or isinstance(rep, str), "Representation must be string or absent")
            cells[(task, condition)] = {"task_id": task, "condition": condition, "pair_id": pair_id, "variant": variant,
                "success": row["success"], "status": row["status"], "representation_valid": row["representation_valid"],
                "representation_utf8_bytes": len(rep.encode("utf-8")) if rep is not None else None,
                "deployment_preparation_usage": preprocessing, "executor_usage": execution, "deployment_total_usage": total,
                "actual_prepare_usage": _usage(ledger, own),
                "preparation_by_purpose": {suffix: _usage(ledger, [i for i in sources if ledger[i]["purpose"].endswith(":" + suffix)])
                                           for suffix in ("planner", "organizer", "extract", "repair")}}

    _require(len(pairs) == 6 and all(len(members) == 2 for members in pairs.values()), "Exactly six complete pairs are required")
    _require(all(len({row_map[(task, "full_context")]["variant"] for task in members}) == 2
                 for members in pairs.values()), "Pair variants repeat")
    _require(set(references) == set(range(len(ledger))), "Unattributed actual requests remain")
    shared = [i for i, attempt in enumerate(ledger) if attempt["phase"] == "prepare" and attempt["condition"] == "cs1"]
    for i, attempt in enumerate(ledger):
        _require(references[i] == (2 if i in shared else 1), "Actual request duplication exceeds declared CS sharing")
    shared_usage = _usage(ledger, shared)
    for key in deployed_total:
        _require(deployed_total[key] - actual[key] == shared_usage[key], "Deployment/actual shared-cost identity failed")

    review = _read(run / "source_review.json")
    annotation = {(e["task_id"], e["condition"], e["review_scope"]): e for e in review["entries"]}
    expected_annotations = {(task, condition, scope) for task in task_ids for condition, scopes in (
        ("full_planner", ("planner",)), ("summary_s1", ("final",)),
        ("summary_s2", ("organizer", "final")), ("cs1", ("final",))) for scope in scopes}
    _require(len(annotation) == len(review["entries"]) and set(annotation) == expected_annotations, "Source review assignment differs")
    for entry in annotation.values():
        _require(set(entry["assessment"]) == set(DIMENSIONS)
                 and all(v in {"correct", "incorrect", "ambiguous", "not_observed"} for v in entry["assessment"].values()), "Invalid source assessment")

    conditions, source_cross = {}, {}
    for condition in CONDITIONS:
        selected = [cells[(task, condition)] for task in task_ids]
        per_task = []
        for cell in selected:
            base = cells[(cell["task_id"], "full_context")]
            per_task.append({**cell,
                "full_executor_input_tokens": base["executor_usage"]["input_tokens"],
                "executor_input_reduction_vs_full": _reduction(cell["executor_usage"]["input_tokens"], base["executor_usage"]["input_tokens"]),
                "full_deployment_total_tokens": base["deployment_total_usage"]["total_tokens"],
                "deployment_total_token_reduction_vs_full": _reduction(cell["deployment_total_usage"]["total_tokens"], base["deployment_total_usage"]["total_tokens"]),
                "executor_input_reduction_is_not_efficiency_evidence": not cell["success"] or not cell["representation_valid"]})
        source_indices = sorted({i for task in task_ids for i in row_map[(task, condition)]["source_request_indices"]})
        executor_indices = sorted({i for task in task_ids for i in row_map[(task, condition)]["executor_request_indices"]})
        total = _usage(ledger, source_indices + executor_indices)
        ex = _usage(ledger, executor_indices)
        base_ex = sum(cells[(task, "full_context")]["executor_usage"]["input_tokens"] for task in task_ids)
        base_total = sum(cells[(task, "full_context")]["deployment_total_usage"]["total_tokens"] for task in task_ids)
        bytes_observed = [cell["representation_utf8_bytes"] for cell in selected if cell["representation_utf8_bytes"] is not None]
        reductions = [cell["executor_input_reduction_vs_full"] for cell in per_task if cell["executor_input_reduction_vs_full"] is not None]
        conditions[condition] = {"assigned": len(task_ids), "successes": sum(cell["success"] for cell in selected),
            "deployment_preparation_usage": _usage(ledger, source_indices), "executor_usage": ex,
            "deployment_total_usage": total,
            "actual_condition_usage": _usage(ledger, [i for i, a in enumerate(ledger) if a["condition"] == condition]),
            "preparation_by_purpose": {suffix: _usage(ledger, [i for i in source_indices if ledger[i]["purpose"].endswith(":" + suffix)])
                                       for suffix in ("planner", "organizer", "extract", "repair")},
            "executor_input_reduction_vs_full_aggregate": _reduction(ex["input_tokens"], base_ex),
            "executor_input_reduction_vs_full_mean_task": mean(reductions) if reductions else None,
            "executor_input_reduction_observed_tasks": len(reductions),
            "deployment_total_token_reduction_vs_full": _reduction(total["total_tokens"], base_total),
            "representation_bytes": {"observed": len(bytes_observed), "missing": len(task_ids) - len(bytes_observed),
                "sum": sum(bytes_observed), "mean_observed": mean(bytes_observed) if bytes_observed else None,
                "minimum": min(bytes_observed) if bytes_observed else None, "maximum": max(bytes_observed) if bytes_observed else None},
            "paired_joint_success": [{"pair_id": pair, "task_ids": members,
                "member_success": {task: cells[(task, condition)]["success"] for task in members},
                "both_success": all(cells[(task, condition)]["success"] for task in members)} for pair, members in sorted(pairs.items())],
            "per_task": per_task}

        source_condition = "cs1" if condition == "cs_text" else condition
        scopes = ("planner",) if condition == "full_planner" else ("organizer", "final") if condition == "summary_s2" else ("final",) if condition in {"summary_s1", "cs1", "cs_text"} else ()
        by_scope = {}
        for scope in scopes:
            classified = []
            for task in task_ids:
                entry = annotation[(task, source_condition, scope)]
                classified.append({"task_id": task, "source_class": _source_class(entry["assessment"]),
                    "concrete_error": "incorrect" in entry["assessment"].values(),
                    "ambiguous": "ambiguous" in entry["assessment"].values(),
                    "success": cells[(task, condition)]["success"], "assessment": entry["assessment"],
                    "evidence_notes": entry["evidence_notes"], "annotation_condition": source_condition})
            by_scope[scope] = {"annotation_origin": "paired_cs1_shared_source" if condition == "cs_text" else condition,
                "exclusive_classes": {category: {"assigned": sum(row["source_class"] == category for row in classified),
                    "successes": sum(row["source_class"] == category and row["success"] for row in classified),
                    "failures": sum(row["source_class"] == category and not row["success"] for row in classified)}
                    for category in ("correct", "concrete_error", "ambiguous_without_concrete_error", "not_observed", "partially_observed")},
                "concrete_error_success_cross": {"error_and_success": sum(row["concrete_error"] and row["success"] for row in classified),
                    "error_and_failure": sum(row["concrete_error"] and not row["success"] for row in classified),
                    "no_concrete_error_and_success": sum(not row["concrete_error"] and row["success"] for row in classified),
                    "no_concrete_error_and_failure": sum(not row["concrete_error"] and not row["success"] for row in classified)},
                "per_task": classified}
        source_cross[condition] = by_scope

    return {"report_version": "cycle5-descriptive-extension-v1", "source_run": str(run), "complete": True,
        "evidence_type": manifest["evidence_type"], "frozen_main_analysis_unchanged": True,
        "comparison_scope": "All 12 assigned task versions, six correlated workflow pairs; no success filtering.",
        "executor_input_scope": "Actual provider input Tokens across every executor request, including prompts, interface, responses and failed behavior. Not retained representation Tokens or complete system cost.",
        "reduction_scope": "Failed/unexecuted representations can have zero executor input; this is not efficiency evidence. Complete strategy total includes all preprocessing, repair, planning and execution.",
        "conditions": conditions, "source_semantics_behavior_cross": source_cross,
        "full_ledger_validation": {"actual_usage": actual, "deployment_attribution_sum": deployed_total,
            "shared_cs_preparation_usage": shared_usage, "request_reference_multiplicity": dict(sorted(Counter(references.values()).items())),
            "all_actual_requests_covered": True, "only_declared_cs_source_counted_twice": True,
            "deployment_sum_equals_actual_plus_shared_cs": True,
            "request_cap": config["max_api_calls"], "requests_within_cap": True,
            "token_stop_threshold": threshold, "each_request_sent_below_token_threshold": True,
            "final_known_tokens_exceed_threshold": max(0, actual["total_tokens"] - threshold),
            "currency_cost": None, "currency_cost_scope": "Provider currency price/charge was not inferred from Tokens."},
        "frozen_execution_audit": audit}
