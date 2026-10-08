"""One isolated connectivity probe; never retries or prints provider error bodies."""

from pathlib import Path
import argparse
import json
import os
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from llm.client import sdk_error_category
from utils.io import load_json, save_json, digest


def main(output):
    if output.exists():
        raise ValueError("Refuse to overwrite a service probe")
    from dotenv import load_dotenv
    from openai import OpenAI, OpenAIError

    config_path = ROOT / "configs/cycle4_preflight_v1.json"
    config = load_json(config_path)
    load_dotenv(ROOT / ".env")
    key = os.environ.get(config["api_key_env"])
    if not key:
        raise ValueError("Configured API credential is missing")
    messages = [{"role": "user", "content": "Reply with OK."}]
    client = OpenAI(api_key=key, base_url=config["endpoint"].removesuffix("/chat/completions"),
                    timeout=config["timeout_seconds"], max_retries=0)
    record = {"purpose": "service_probe_not_experimental_cell", "model": config["model"],
              "config_sha256": digest(config_path), "request_attempts": 1,
              "messages": messages, "max_tokens": 8, "temperature": 0,
              "extra_body": config["extra_body"], "total_tokens": None,
              "unknown_usage_attempts": 1}
    started = time.perf_counter()
    try:
        response = client.chat.completions.create(model=config["model"], messages=messages,
            max_tokens=8, temperature=0, stream=False, extra_body=config["extra_body"])
        usage = response.usage.model_dump() if response.usage else {}
        known = type(usage.get("total_tokens")) is int
        record.update(status="response_received" if known else "response_usage_unknown",
                      response_id=response.id, usage=usage,
                      total_tokens=usage.get("total_tokens"), unknown_usage_attempts=0 if known else 1)
    except OpenAIError as exc:
        category, provider_code = sdk_error_category(exc)
        record.update(status="api_error", error={"class": type(exc).__name__,
            "http_status": getattr(exc, "status_code", None), "category": category,
            "provider_code": provider_code})
    finally:
        record["latency_seconds"] = time.perf_counter() - started
        save_json(output, record)
        client.close()
    print(json.dumps({k: record.get(k) for k in
        ("status", "error", "total_tokens", "unknown_usage_attempts")}, ensure_ascii=True))
    return 0 if record["status"] == "response_received" else 1


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    sys.exit(main(p.parse_args().output))
