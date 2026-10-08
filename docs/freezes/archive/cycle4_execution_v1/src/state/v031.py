"""Cycle4 encoding validation only. Semantic mistakes remain measured outcomes."""

from copy import deepcopy
from pathlib import Path
import json
import math
import re

from state.representation import CognitiveState
from state.v03 import compact, state_delta
from utils.io import parse_json

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT / "docs/schemas/cognitive_state_v0.3.1.schema.json").read_text(encoding="utf-8"))


def shape(value, schema, path="$"):
    """Interpret the finite JSON Schema keyword subset used by the frozen schema.

    No remote refs, network or coercion; unsupported keywords fail closed.
    This is not advertised as a general JSON Schema implementation.
    """
    supported = {"$schema", "title", "description", "type", "properties", "required",
                 "additionalProperties", "items", "minItems", "minimum", "pattern",
                 "enum", "const", "oneOf", "allOf", "if", "then", "else", "not"}
    if set(schema) - supported:
        raise ValueError("Unsupported schema keyword")
    def matches(s):
        try:
            shape(value, s, path)
            return True
        except ValueError:
            return False
    if "oneOf" in schema and sum(matches(s) for s in schema["oneOf"]) != 1:
        raise ValueError(path + ": expected exactly one allowed shape/kind-phase combination")
    for s in schema.get("allOf", []):
        shape(value, s, path)
    if "if" in schema:
        shape(value, schema.get("then" if matches(schema["if"]) else "else", {}), path)
    if "not" in schema and matches(schema["not"]):
        raise ValueError(path + ": disallowed field combination")
    types = {"object": lambda x: isinstance(x, dict), "array": lambda x: isinstance(x, list),
             "string": lambda x: isinstance(x, str), "number": lambda x: type(x) in (int, float) and math.isfinite(x),
             "integer": lambda x: type(x) is int, "boolean": lambda x: type(x) is bool, "null": lambda x: x is None}
    if "type" in schema and not types[schema["type"]](value):
        raise ValueError(path + ": expected " + schema["type"])
    if "const" in schema and value != schema["const"] or "enum" in schema and value not in schema["enum"]:
        raise ValueError(path + ": invalid constant/enum")
    if isinstance(value, dict):
        missing = set(schema.get("required", [])) - value.keys()
        extra = value.keys() - schema.get("properties", {}).keys()
        if missing or schema.get("additionalProperties") is False and extra:
            raise ValueError(f"{path}: missing={sorted(missing)}, extra={sorted(extra)}")
        for key, child in schema.get("properties", {}).items():
            if key in value:
                shape(value[key], child, path + "." + key)
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            raise ValueError(path + ": too few items")
        if "items" in schema:
            for i, child in enumerate(value):
                shape(child, schema["items"], f"{path}[{i}]")
    if isinstance(value, str) and "pattern" in schema and not re.search(schema["pattern"], value):
        raise ValueError(path + ": empty/invalid string")
    if type(value) in (int, float) and "minimum" in schema and value < schema["minimum"]:
        raise ValueError(path + ": below minimum")


def source_authorities(history):
    result = {}
    for event in history:
        inherited = event.get("source_authority", {})
        for ident, authority in inherited.items():
            if ident in result and result[ident] != authority:
                raise ValueError("Conflicting runtime source authority")
            result[ident] = authority
        authority = "contract" if event.get("source_type") == "public_tool_contract" else event["role"]
        if event["id"] in result and result[event["id"]] != authority:
            raise ValueError("Conflicting event identity")
        result[event["id"]] = authority
    return result


def retained_event(representation, condition, history, handoff):
    # Keep only source labels whose IDs were actually retained, for every format.
    # Labels convey authority, never the discarded source content.
    authorities = {k: v for k, v in source_authorities(history).items()
                   if re.search(r"(?<![\w-])" + re.escape(k) + r"(?![\w-])", representation)}
    return {"id": f"retained_h{handoff}", "role": "assistant", "content": representation,
            "retained_schema": condition, "source_authority": authorities}


def validate_state(value, history):
    shape(value, SCHEMA)
    nodes = [n for section in value.values() for group in section.values() if isinstance(group, list)
             for n in group if isinstance(n, dict) and "id" in n]
    ids = {n["id"] for n in nodes}
    if len(ids) != len(nodes):
        raise ValueError("Duplicate active IDs")
    sources = source_authorities(history)
    requirements = {n["id"] for n in value["goal"]["requirements"]}
    obligations = {n["id"] for n in value["frontier"]["obligations"]}
    jobs = {n["id"] for n in value["world"]["operations"] if n["kind"] == "job"}
    for n in nodes + ([value["frontier"]["candidate_action"]] if "candidate_action" in value["frontier"] else []):
        for field, allowed in (("source_refs", sources), ("depends_on", ids), ("requires", ids), ("blocks", obligations)):
            if not set(n.get(field, [])) <= set(allowed):
                raise ValueError(f"Dangling {field}")
        for field, allowed in (("requirement_ref", requirements), ("obligation_ref", obligations),
                               ("job_ref", jobs), ("superseded_by", ids)):
            if field in n and n[field] not in allowed:
                raise ValueError(f"Dangling {field}")
    # No source-class truth judgement, goal-revision/plan feasibility or hidden
    # answer checks. Those are content/behavior diagnostics, not repair triggers.
    return deepcopy(value)


class ExtractorV031:
    def __init__(self, client, budget=6000):
        self.client, self.budget = client, budget

    def extract(self, history, interface, condition, prompt, calls):
        messages = [{"role": "system", "content": prompt}, {"role": "user", "content": compact({
            "history": history, "public_interface": interface,
            "representation_budget": self.budget, "budget_counter": "utf8_bytes"})}]
        diagnostics = []
        for index in range(2):
            completion = self.client.complete(messages, purpose=condition + (":extract" if index == 0 else ":repair"))
            calls.append({"messages": deepcopy(messages), "response": completion.text, "metadata": completion.metadata})
            try:
                if completion.metadata.get("finish_reason") != "stop":
                    raise ValueError("Representation did not stop normally")
                rep = completion.text.strip()
                if condition == "cs_v031":
                    rep = compact(validate_state(parse_json(rep), history))
                elif condition == "cs_v02":
                    rep = compact(CognitiveState.from_dict(parse_json(rep)).to_dict())
                elif condition != "summary":
                    raise ValueError("Unknown condition")
                if not rep or len(rep.encode("utf-8")) > self.budget:
                    raise ValueError("Empty representation or byte budget exceeded")
                diagnostics.append({"attempt": index, "valid": True, "utf8_bytes": len(rep.encode("utf-8"))})
                return rep, diagnostics
            except (ValueError, TypeError, KeyError) as exc:
                diagnostics.append({"attempt": index, "valid": False, "error": str(exc)[:400]})
                messages += [{"role": "assistant", "content": completion.text}, {"role": "user", "content":
                    "Correct only the encoding using the same inputs. Return the complete representation. Error: " + str(exc)[:400]}]
        return None, diagnostics
