"""Minimal v0.3 semantic representation; local checks never read scoring data."""

from copy import deepcopy
import json
import math
from typing import Any

from state.representation import CognitiveState
from utils.io import parse_json


PHASES = {"planned", "issued", "accepted", "completed", "verified", "failed", "cancelled", "unknown"}
BASES = {"observed", "reported", "inferred", "assumed"}


def compact(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def state_delta(previous, current):
    """Audit structural changes only; removed questions are not proven resolved."""
    def items(state):
        return {n["id"]: n for section in state.values() for value in section.values()
                if isinstance(value, list) for n in value if isinstance(n, dict) and "id" in n}
    old = items(previous) if previous else {}
    new = items(current)
    return {"added_ids": sorted(new.keys() - old.keys()), "removed_ids": sorted(old.keys() - new.keys()),
            "changed_ids": sorted(k for k in old.keys() & new.keys() if old[k] != new[k]),
            "goal_revision_changed": previous is not None and previous["goal"]["revision"] != current["goal"]["revision"],
            "candidate_changed": previous is not None and previous["frontier"].get("candidate_action") != current["frontier"].get("candidate_action"),
            "interpretation": "Syntactic item differences, not proof of justified semantic updates"}


def source_permissions(history):
    """Old source handles survive only through the actually retained representation."""
    sources, observed, goals = set(), set(), set()
    for event in history:
        ident = event["id"]
        sources.add(ident)
        if event["role"] in {"tool", "runtime"}:
            observed.add(ident)
        if event["role"] == "user":
            goals.add(ident)
        if event.get("retained_schema") == "v0.3":
            old = parse_json(event["content"])
            # These sets carry provenance labels, not access to discarded content.
            for group in ("requirements", "constraints", "preferences"):
                for node in old["goal"][group]:
                    goals.update(node["source_refs"])
                    sources.update(node["source_refs"])
            for group in ("claims", "operations", "resources"):
                for node in old["world"][group]:
                    sources.update(node["source_refs"])
                    if group != "claims" or node["basis"] == "observed":
                        observed.update(node["source_refs"])
    return sources, observed, goals


def validate_state(value, history, interface):
    """Shape, source-class, reference and declared-budget checks, not a truth oracle."""
    def obj(v, required, optional=()):
        if not isinstance(v, dict) or not set(required) <= set(v) or set(v) - set(required) - set(optional):
            raise ValueError(f"Expected keys {sorted(required)}; optional {sorted(optional)}")

    def text(v):
        if not isinstance(v, str) or not v.strip():
            raise ValueError("Expected nonempty text")

    def texts(v, minimum=0):
        if not isinstance(v, list) or len(v) < minimum:
            raise ValueError("Expected text list")
        for x in v:
            text(x)

    obj(value, {"goal", "world", "frontier"})
    g, w, f = (value[k] for k in ("goal", "world", "frontier"))
    obj(g, {"revision", "objective", "requirements", "constraints", "preferences"})
    obj(w, {"claims", "operations", "resources"})
    obj(f, {"obligations", "open_questions"}, {"candidate_action"})
    text(g["revision"]); text(g["objective"])
    sources, observed_sources, goal_sources = source_permissions(history)
    constraint_sources = goal_sources | {e["id"] for e in history if e["role"] == "runtime"}
    nodes, ids = [], set()

    def node(v, required, optional=(), provenance=None):
        obj(v, required, optional)
        text(v["id"])
        if v["id"] in ids:
            raise ValueError("Duplicate active item ID")
        ids.add(v["id"]); nodes.append(v)
        if "text" in v:
            text(v["text"])
        if "source_refs" in v:
            texts(v["source_refs"], 1)
            if not set(v["source_refs"]) <= sources:
                raise ValueError("Unknown source_refs; use only available source IDs")
            if provenance is not None and not set(v["source_refs"]) <= provenance:
                raise ValueError("Source class does not support this kind of claim")

    for parent, names in ((g, ("requirements", "constraints", "preferences")),
                          (w, ("claims", "operations", "resources")), (f, ("obligations", "open_questions"))):
        for name in names:
            if not isinstance(parent[name], list):
                raise ValueError("Item collections must be arrays")
    if not g["requirements"]:
        raise ValueError("At least one public goal requirement is needed")
    for name in ("requirements", "constraints", "preferences"):
        for n in g[name]:
            node(n, {"id", "text", "source_refs"}, provenance=constraint_sources if name == "constraints" else goal_sources)
    for n in w["claims"]:
        node(n, {"id", "text", "basis", "source_refs"},
             {"depends_on", "standing", "valid_when", "recheck_when", "superseded_by"})
        if n["basis"] not in BASES:
            raise ValueError("Invalid claim basis")
        if n["basis"] == "observed" and not set(n["source_refs"]) <= observed_sources:
            raise ValueError("Observed claims require tool/runtime or inherited observation sources")
        if n["basis"] == "inferred" and not n.get("depends_on"):
            raise ValueError("Inferred claims need depends_on")
        if n.get("standing", "active") not in {"active", "superseded", "refuted", "conflicted"}:
            raise ValueError("Invalid standing")
        for key in ("valid_when", "recheck_when", "superseded_by"):
            if key in n:
                text(n[key])
    for n in w["operations"]:
        node(n, {"id", "operation", "phase", "source_refs"}, {"target", "handle"})
        text(n["operation"])
        if n["phase"] not in PHASES:
            raise ValueError("Invalid operation phase")
        if n["phase"] in {"accepted", "completed", "verified", "failed", "cancelled"} and not set(n["source_refs"]) <= observed_sources:
            raise ValueError("Observed operation phases require observation sources, not a plan")
        if "target" in n and not isinstance(n["target"], dict):
            raise ValueError("Operation target must be an object")
        if "handle" in n:
            text(n["handle"])
    for n in w["resources"]:
        node(n, {"id", "kind", "remaining", "scope", "source_refs"}, provenance=observed_sources)
        text(n["kind"]); text(n["scope"])
        if type(n["remaining"]) not in {int, float} or not math.isfinite(n["remaining"]) or n["remaining"] < 0:
            raise ValueError("Remaining resource must be nonnegative")
        if n["kind"] == "credits" and (n["remaining"] != interface["remaining_credits"] or n["scope"] != interface["credit_scope"]):
            raise ValueError("Current credits must match the supplied runtime interface")
    requirements = {n["id"] for n in g["requirements"]}
    obligations = set()
    for n in f["obligations"]:
        node(n, {"id", "text", "requirement_ref"}, {"depends_on"})
        if n["requirement_ref"] not in requirements:
            raise ValueError("obligation requirement_ref must reference a goal requirement")
        obligations.add(n["id"])
    for n in f["open_questions"]:
        node(n, {"id", "text", "blocks", "decision_relevance"}, {"depends_on"})
        text(n["decision_relevance"]); texts(n["blocks"], 1)
        if not set(n["blocks"]) <= obligations:
            raise ValueError("Questions must block existing obligations")
    for n in nodes:
        if "depends_on" in n:
            texts(n["depends_on"])
            if not set(n["depends_on"]) <= ids or n["id"] in n["depends_on"]:
                raise ValueError("Dangling or self dependency")
        if "superseded_by" in n and (n["superseded_by"] not in ids or n["superseded_by"] == n["id"]):
            raise ValueError("Dangling supersession")
    graph = {n["id"]: n.get("depends_on", []) for n in nodes}
    def visit(ident, path):
        if ident in path:
            raise ValueError("Cyclic dependencies")
        for dep in graph[ident]:
            visit(dep, path | {ident})
    for ident in graph:
        visit(ident, set())
    if "candidate_action" in f:
        a = f["candidate_action"]
        obj(a, {"tool", "arguments", "requires", "obligation_ref", "goal_revision"}, {"known_cost"})
        if a["goal_revision"] != g["revision"] or a["obligation_ref"] not in obligations:
            raise ValueError("Candidate action has stale goal or missing obligation")
        texts(a["requires"])
        if not set(a["requires"]) <= ids:
            raise ValueError("Candidate has dangling requirements")
        definitions = {"execute": ("operation", "operations"), "observe": ("resource", "resources")}
        if a["tool"] not in definitions:
            raise ValueError("Candidate must be execute or observe; omit it for completed tasks")
        arg, group = definitions[a["tool"]]
        obj(a["arguments"], {arg}); text(a["arguments"][arg])
        available = {d["name"]: d for d in interface["catalog"][group]}
        if a["tool"] == "observe":
            available["workspace/catalog.json"] = {"cost": 0}
        name = a["arguments"][arg]
        if name not in available:
            raise ValueError("Unknown candidate tool identifier")
        cost = available[name]["cost"]
        if cost > interface["remaining_credits"] or ("known_cost" in a and (type(a["known_cost"]) not in {int, float} or a["known_cost"] != cost)):
            raise ValueError("Candidate violates known current cost/budget")
        inactive = {n["id"] for n in w["claims"] if n.get("standing", "active") != "active"}
        if set(a["requires"]) & inactive:
            raise ValueError("Candidate relies on an inactive claim")
    return deepcopy(value)


class ExtractorV03:
    """One optional logged repair, identical retry cap for all compressed conditions."""
    def __init__(self, client, budget=6000, repair_attempts=1):
        self.client, self.budget, self.repair_attempts = client, budget, repair_attempts

    def extract(self, history, interface, condition, prompt, calls):
        messages = [{"role": "system", "content": prompt}, {"role": "user", "content": compact({
            "history": history, "public_interface": interface, "representation_budget": self.budget,
            "budget_counter": "utf8_bytes"})}]
        diagnostics = []
        for index in range(self.repair_attempts + 1):
            completion = self.client.complete(messages, purpose=f"{condition}:{'extract' if index == 0 else 'repair'}")
            calls.append({"messages": deepcopy(messages), "response": completion.text, "metadata": completion.metadata})
            try:
                if completion.metadata.get("finish_reason") != "stop":
                    raise ValueError("Representation completion did not stop normally")
                rep = completion.text.strip()
                if condition == "cs_v03":
                    rep = compact(validate_state(parse_json(rep), history, interface))
                elif condition == "cs_v02":
                    rep = compact(CognitiveState.from_dict(parse_json(rep)).to_dict())
                elif condition != "summary":
                    raise ValueError("Unknown extraction condition")
                if not rep or len(rep.encode("utf-8")) > self.budget:
                    raise ValueError("Representation empty or exceeds UTF-8 byte budget")
                diagnostics.append({"attempt": index, "valid": True, "utf8_bytes": len(rep.encode("utf-8"))})
                return rep, diagnostics
            except (ValueError, TypeError, KeyError) as exc:
                diagnostics.append({"attempt": index, "valid": False, "error_type": type(exc).__name__, "error": str(exc)[:400]})
                messages += [{"role": "assistant", "content": completion.text}, {"role": "user", "content":
                    "Repair the representation using exactly the same available information. No new history or answers are available. "
                    "Return only the complete corrected representation. Validation error: " + str(exc)[:400]}]
        return None, diagnostics
