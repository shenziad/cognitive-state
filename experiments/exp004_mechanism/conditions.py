"""Cycle5 preparation controls, without transport, credentials or outcome access.

The caller supplies a recording client whose ``complete`` method accepts an
explicit ``max_output_tokens``. API exceptions propagate: the runner records and
stops them rather than disguising an unknown-usage request as an encoding error.
Only shape/reference/phase/size errors permit the single encoding repair.
"""

from copy import deepcopy
from dataclasses import asdict, dataclass, field
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from state.v031 import source_authorities, validate_state
from utils.io import parse_json

ROOT = Path(__file__).resolve().parents[2]
PROMPTS = ROOT / "prompts" / "cycle5"
CONDITIONS = ("full_context", "full_planner", "summary_s1", "summary_s2", "cs1", "cs_text")
PROMPT_NAMES = ("planner", "organizer", "summary", "cs1", "executor")
TEXT_HEADER = "Lossless field-path text v1 (type, JSON path, JSON value; container metadata preserves order)."


def compact(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_prompt(name: str) -> str:
    """Append the exact same semantic instructions to every model stage."""
    if name not in PROMPT_NAMES:
        raise ValueError("Unknown cycle5 prompt")
    return (PROMPTS / (name + ".txt")).read_text(encoding="utf-8").strip() + "\n\n" + (
        PROMPTS / "semantic_common.txt").read_text(encoding="utf-8").strip()


def project_inputs(history: list[dict], public_interface: dict) -> tuple[list[dict], dict]:
    """Allow only public events and catalog contracts; never project fixture data.

    The caller is responsible for choosing the public records. Event metadata
    (family, source_id, fixture, expected actions) is not copied into model input.
    Source authority labels carry source *classes*, never missing source contents.
    Catalog effects are authorized public contracts, not observations of effects.
    """
    allowed_roles = {"user", "assistant", "tool", "runtime"}
    allowed_event = {"id", "role", "content", "source_type", "source_authority", "retained_schema"}
    projected = []
    if not isinstance(history, list):
        raise ValueError("History must be a public event list")
    for event in history:
        if not isinstance(event, dict):
            raise ValueError("Public event must be an object")
        item = {k: deepcopy(v) for k, v in event.items() if k in allowed_event}
        if (not isinstance(item.get("id"), str) or not item["id"].strip()
                or item.get("role") not in allowed_roles or not isinstance(item.get("content"), str)):
            raise ValueError("Public event id/role/content is malformed")
        if "source_type" in item and item["source_type"] != "public_tool_contract":
            raise ValueError("Unsupported source class")
        if "source_authority" in item and (not isinstance(item["source_authority"], dict)
                or any(not isinstance(k, str) or not isinstance(v, str) or v not in allowed_roles | {"contract"}
                       for k, v in item["source_authority"].items())):
            raise ValueError("Malformed source authority labels")
        projected.append(item)
    ids = [e["id"] for e in projected]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate public event IDs")
    allowed_interface = {"version", "catalog", "remaining_credits", "credit_scope", "receipt_contract"}
    if not isinstance(public_interface, dict) or set(public_interface) != allowed_interface:
        raise ValueError("Unexpected public interface keys")
    interface = deepcopy(public_interface)
    catalog = interface["catalog"]
    if not isinstance(catalog, dict) or set(catalog) != {"operations", "resources", "catalog_cost"}:
        raise ValueError("Unexpected public catalog keys")
    operation_keys = {"name", "description", "cost", "preconditions", "successful_effects",
                      "successful_increments", "lifecycle_contract"}
    for category, keys in (("operations", operation_keys), ("resources", {"name", "description", "cost"})):
        if not isinstance(catalog[category], list) or any(not isinstance(item, dict) or set(item) - keys
                                                        for item in catalog[category]):
            raise ValueError("Unexpected catalog item keys")
    # Check serializability (especially NaN) without converting values or order.
    compact(interface)
    for ident, role, content, source_type in (
        ("mechanism:interface_contract", "tool",
         "The supplied public_interface is the authoritative current catalog and receipt contract. "
         "Its effects and preconditions define tools; they are not evidence of past execution.", "public_tool_contract"),
        ("mechanism:runtime_allowance", "runtime", compact({
            "remaining_credits": interface["remaining_credits"], "credit_scope": interface["credit_scope"]}), None),
    ):
        expected = {"id": ident, "role": role, "content": content}
        if source_type:
            expected["source_type"] = source_type
        previous = next((e for e in projected if e["id"] == ident), None)
        if previous is None:
            projected.append(expected)
        elif previous != expected:
            raise ValueError("Reserved public source identity collision")
    source_authorities(projected)  # Conflicts fail before any paid request.
    return projected, interface


@dataclass
class Preparation:
    condition: str
    representation: str | None
    valid: bool
    input_sha256: str
    diagnostics: list[dict] = field(default_factory=list)
    calls: list[dict] = field(default_factory=list)
    intermediate: str | None = None
    shared_source: dict | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict) -> "Preparation":
        if set(value) != set(cls.__dataclass_fields__):
            raise ValueError("Saved preparation fields differ")
        result = cls(**deepcopy(value))
        if result.condition not in CONDITIONS or type(result.valid) is not bool:
            raise ValueError("Malformed saved preparation")
        if result.valid != isinstance(result.representation, str):
            raise ValueError("Saved preparation validity/representation disagree")
        return result

    def deployment_calls(self) -> list[dict]:
        """Costs for an independent deployment; do NOT sum as actual ledger use.

        CS-text has no actual preparation request. It inherits the source CS
        extraction/repair deployment cost. A global actual ledger counts that
        shared request once, while both CS strategies include it independently.
        """
        return deepcopy(self.shared_source["deployment_calls"] if self.condition == "cs_text"
                        and self.shared_source is not None else self.calls)


def render_state_text(value: Any) -> str:
    """Lossless preorder field paths: retain all values, containers and ordering."""
    records = []

    def visit(node, path):
        if isinstance(node, dict):
            if any(not isinstance(k, str) for k in node):
                raise ValueError("JSON object keys must be strings")
            kind, encoded = "object", list(node)
        elif isinstance(node, list):
            kind, encoded = "array", len(node)
        elif node is None:
            kind, encoded = "null", None
        elif type(node) is bool:
            kind, encoded = "boolean", node
        elif type(node) is int:
            kind, encoded = "integer", node
        elif type(node) is float and math.isfinite(node):
            kind, encoded = "number", node
        elif isinstance(node, str):
            kind, encoded = "string", node
        else:
            raise ValueError("Non-JSON scalar")
        records.append(kind + "\t" + compact(path) + "\t" + compact(encoded))
        if isinstance(node, dict):
            for key, child in node.items():
                visit(child, path + [key])
        elif isinstance(node, list):
            for i, child in enumerate(node):
                visit(child, path + [i])

    visit(value, [])
    return TEXT_HEADER + "\n" + "\n".join(records)


def restore_state_text(text: str) -> Any:
    """Reject omissions, reordered records, duplicate paths and wrong scalar types."""
    # JSON escapes CR/LF, but may contain literal Unicode line separators.
    # Splitting only the renderer's delimiter preserves those scalar characters.
    lines = text.split("\n")
    if not lines or lines[0] != TEXT_HEADER:
        raise ValueError("Unknown lossless text version")
    records = []
    for line in lines[1:]:
        pieces = line.split("\t", 2)
        if len(pieces) != 3:
            raise ValueError("Malformed field-path record")
        kind, path, value = pieces
        records.append((kind, parse_json(path), parse_json(value)))
    index = 0

    def consume(expected):
        nonlocal index
        if index >= len(records):
            raise ValueError("Missing field-path record")
        kind, path, value = records[index]
        index += 1
        if not isinstance(path, list) or compact(path) != compact(expected):
            raise ValueError("Field paths or ordering differ")
        if kind == "object":
            if not isinstance(value, list) or any(not isinstance(k, str) for k in value) or len(set(value)) != len(value):
                raise ValueError("Malformed object keys")
            return {key: consume(expected + [key]) for key in value}
        if kind == "array":
            if type(value) is not int or value < 0:
                raise ValueError("Malformed array length")
            return [consume(expected + [i]) for i in range(value)]
        types = {"null": lambda x: x is None, "boolean": lambda x: type(x) is bool,
                 "integer": lambda x: type(x) is int,
                 "number": lambda x: type(x) is float and math.isfinite(x), "string": lambda x: isinstance(x, str)}
        if kind not in types or not types[kind](value):
            raise ValueError("Malformed typed scalar")
        return value

    result = consume([])
    if index != len(records):
        raise ValueError("Unexpected trailing field-path records")
    return result


def executor_context(representation: str, public_interface: dict) -> dict:
    """All formats are strings inside the identical executor wrapper."""
    if not isinstance(representation, str):
        raise ValueError("Executor representation must be a string")
    return {"retained_context": representation, "public_interface": deepcopy(public_interface)}


def prepare(condition: str, history: list[dict], public_interface: dict, config: dict,
            client, *, shared_state: Preparation | dict | None = None) -> Preparation:
    """Prepare one condition, without tools, future events, scores or sematic repair.

    ``config`` accepts representation_budget=6000, intermediate_max_output_tokens
    =1024 and final_max_output_tokens=4096. Public input is projected identically
    for every condition. The runner's ledger handles API/unknown-usage failures.
    """
    if condition not in CONDITIONS:
        raise ValueError("Unknown mechanism condition")
    budget = config.get("representation_budget", 6000)
    intermediate_limit = config.get("intermediate_max_output_tokens", 1024)
    final_limit = config.get("final_max_output_tokens", 4096)
    if any(type(x) is not int or x <= 0 for x in (budget, intermediate_limit, final_limit)):
        raise ValueError("Invalid preparation limits")
    available, interface = project_inputs(history, public_interface)
    public = {"history": available, "public_interface": interface,
              "source_authority": source_authorities(available),
              "representation_budget": budget, "budget_counter": "utf8_bytes"}
    fingerprint = _sha(compact(public))
    result = Preparation(condition, None, False, fingerprint)
    if condition == "full_context":
        result.representation, result.valid = compact(available), True
        return result
    if condition == "cs_text":
        if isinstance(shared_state, dict):
            shared_state = Preparation.from_dict(shared_state)
        if not isinstance(shared_state, Preparation) or shared_state.condition != "cs1":
            raise ValueError("CS-text requires the actual paired CS1 source preparation")
        if shared_state.input_sha256 != fingerprint:
            raise ValueError("CS-text source public inputs differ")
        result.shared_source = {"condition": "cs1", "input_sha256": fingerprint,
            "valid": shared_state.valid, "representation_sha256": _sha(shared_state.representation)
            if shared_state.representation is not None else None,
            "deployment_calls": shared_state.deployment_calls()}
        if not shared_state.valid:
            result.diagnostics = deepcopy(shared_state.diagnostics)
            return result
        value = validate_state(parse_json(shared_state.representation), available)
        text = render_state_text(value)
        if compact(restore_state_text(text)) != compact(value):
            raise ValueError("Lossless text roundtrip differs")
        result.representation, result.valid = text, True
        result.diagnostics = [{"attempt": 0, "valid": True, "deterministic": True,
            "utf8_bytes": len(text.encode("utf-8")), "same_information": True,
            "source_representation_sha256": _sha(shared_state.representation)}]
        # No byte cap or truncation here: this control has the complete source info.
        return result

    def request(messages, purpose, maximum):
        response = client.complete(messages, purpose=purpose, max_output_tokens=maximum)
        result.calls.append({"messages": deepcopy(messages), "response": response.text,
                             "metadata": deepcopy(response.metadata), "max_output_tokens": maximum})
        return response

    if condition in {"full_planner", "summary_s2"}:
        task = "planner" if condition == "full_planner" else "organizer"
        messages = [{"role": "system", "content": load_prompt(task)},
                    {"role": "user", "content": compact(public)}]
        response = request(messages, condition + ":" + task, intermediate_limit)
        if response.metadata.get("finish_reason") != "stop" or not response.text.strip():
            result.diagnostics = [{"stage": task, "valid": False, "error": "Intermediate completion did not stop normally or was empty"}]
            return result
        result.intermediate = response.text.strip()
        if condition == "full_planner":
            result.representation = compact({"history": available, "preexecution_plan": result.intermediate})
            result.valid = True
            result.diagnostics = [{"stage": task, "valid": True}]
            return result
        public["untrusted_information_organizer"] = result.intermediate
    task = "cs1" if condition == "cs1" else "summary"
    messages = [{"role": "system", "content": load_prompt(task)}, {"role": "user", "content": compact(public)}]
    for index in range(2):
        response = request(messages, condition + (":extract" if index == 0 else ":repair"), final_limit)
        try:
            if response.metadata.get("finish_reason") != "stop":
                raise ValueError("Representation did not stop normally")
            rep = response.text.strip()
            if condition == "cs1":
                rep = compact(validate_state(parse_json(rep), available))
            if not rep or len(rep.encode("utf-8")) > budget:
                raise ValueError("Empty representation or byte budget exceeded")
            result.diagnostics.append({"attempt": index, "valid": True, "utf8_bytes": len(rep.encode("utf-8"))})
            result.representation, result.valid = rep, True
            return result
        except (ValueError, TypeError, KeyError) as exc:
            message = str(exc)[:400]
            result.diagnostics.append({"attempt": index, "valid": False, "error": message})
            messages.extend([{"role": "assistant", "content": response.text}, {"role": "user", "content":
                "Correct only encoding, structure, allowed references and length using the SAME original public inputs. "
                "Do not revise semantic content, invent facts, add verification requirements, or use outcomes. "
                "Return the complete representation. Encoding error: " + message}])
    return result
