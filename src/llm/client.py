"""Non-streaming Chat Completions adapter with explicit usage accounting."""

import json
import os
import time
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


@dataclass
class Completion:
    text: str
    metadata: dict[str, Any]


class Client(Protocol):
    def complete(self, messages: list[dict[str, str]], *, purpose: str) -> Completion: ...


def sdk_error_category(exc: Exception) -> tuple[str, int | None]:
    """Derive an allowlisted diagnosis; never return the server's raw message/body."""
    body = getattr(exc, "body", None)
    if isinstance(body, dict) and isinstance(body.get("error"), dict):
        body = body["error"]
    code, message = None, ""
    if isinstance(body, dict):
        candidate = body.get("code")
        code = candidate if type(candidate) is int else None
        raw_message = body.get("message")
        message = raw_message.lower() if isinstance(raw_message, str) else ""
    if "balance" in message or "余额" in message:
        return "insufficient_balance", code
    if "quota" in message or "配额" in message:
        return "quota_exhausted", code
    if getattr(exc, "status_code", None) == 402:
        return "payment_required", code
    return "provider_request_failed", code


class OpenAISDKClient:
    """OpenAI-compatible SDK transport, with zero implicit retries or fallback models."""

    def __init__(self, config: dict[str, Any]):
        try:
            from openai import OpenAI
        except ImportError:
            raise ValueError("Install the api optional dependencies for the OpenAI SDK") from None
        endpoint = config["endpoint"]
        suffix = "/chat/completions"
        if not endpoint.endswith(suffix):
            raise ValueError("SDK endpoint must end in /chat/completions")
        key = os.environ.get(config["api_key_env"])
        if not key:
            raise ValueError(f"Set environment variable {config['api_key_env']} before running")
        self.config, self.calls = config, 0
        self.client = OpenAI(api_key=key, base_url=endpoint[:-len(suffix)],
                             timeout=config["timeout_seconds"], max_retries=0)

    def complete(self, messages: list[dict[str, str]], *, purpose: str) -> Completion:
        from openai import OpenAIError

        if self.calls >= self.config["max_api_calls"]:
            raise RuntimeError("Configured API call limit reached")
        self.calls += 1
        kwargs: dict[str, Any] = {"model": self.config["model"], "messages": messages, "stream": False}
        if self.config.get("temperature") is not None:
            kwargs["temperature"] = self.config["temperature"]
        kwargs[self.config["output_limit_parameter"]] = self.config["max_output_tokens"]
        if self.config.get("extra_body"):
            kwargs["extra_body"] = self.config["extra_body"]
        started = time.perf_counter()
        try:
            response = self.client.chat.completions.create(**kwargs)
        except OpenAIError as exc:
            # SDK exception text/body can echo the request. Persist only class/status.
            code = getattr(exc, "status_code", None)
            category, provider_code = sdk_error_category(exc)
            raise RuntimeError(f"SDK {type(exc).__name__}; HTTP={code}; category={category}; provider_code={provider_code}; usage unknown") from None
        try:
            choice = response.choices[0]
            content = choice.message.content or ""
            if not isinstance(content, str):
                raise TypeError("Non-text response")
            usage = response.usage.model_dump() if response.usage else {}
            metadata = {
                "purpose": purpose, "source": "api", "transport": "openai_sdk",
                "response_id": response.id, "model": response.model,
                "system_fingerprint": getattr(response, "system_fingerprint", None),
                "finish_reason": choice.finish_reason, "input_tokens": usage.get("prompt_tokens"),
                "output_tokens": usage.get("completion_tokens"), "usage_details": usage,
                "usage_unit": "provider_tokens", "latency_seconds": time.perf_counter() - started,
            }
        except (AttributeError, IndexError, TypeError):
            raise RuntimeError("Unexpected SDK response shape; usage unknown") from None
        return Completion(content, metadata)


class ChatCompletionsClient:
    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.calls = 0
        if urlparse(config["endpoint"]).scheme != "https":
            raise ValueError("API endpoint must use HTTPS")
        self.key = os.environ.get(config["api_key_env"])
        if not self.key:
            raise ValueError(f"Set environment variable {config['api_key_env']} before running")
        if not config.get("model"):
            raise ValueError("Select a model before running")

    def complete(self, messages: list[dict[str, str]], *, purpose: str) -> Completion:
        if self.calls >= self.config["max_api_calls"]:
            raise RuntimeError("Configured API call limit reached")
        self.calls += 1
        payload: dict[str, Any] = {"model": self.config["model"], "messages": messages}
        if self.config.get("temperature") is not None:
            payload["temperature"] = self.config["temperature"]
        payload[self.config["output_limit_parameter"]] = self.config["max_output_tokens"]
        request = Request(self.config["endpoint"], data=json.dumps(payload).encode("utf-8"),
                          headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.key}"},
                          method="POST")
        try:
            with urlopen(request, timeout=self.config["timeout_seconds"]) as response:
                data = json.load(response)
        except HTTPError as exc:
            raise RuntimeError(f"API HTTP error {exc.code}; usage unknown") from None
        except (URLError, TimeoutError, OSError):
            raise RuntimeError("API connection failed; usage unknown") from None
        except (ValueError, TypeError):
            raise RuntimeError("API response was not valid JSON; usage unknown") from None
        try:
            choice = data["choices"][0]
            usage = data.get("usage") or {}
            if not isinstance(usage, dict) or not isinstance(choice, dict):
                raise TypeError("Invalid response metadata")
            content = choice["message"].get("content") or ""
            if not isinstance(content, str):
                raise TypeError("Non-text response")
        except (KeyError, TypeError, IndexError, AttributeError):
            raise RuntimeError("Unexpected API response shape; usage unknown") from None
        return Completion(content, {
            "purpose": purpose, "source": "api", "response_id": data.get("id"),
            "model": data.get("model"), "system_fingerprint": data.get("system_fingerprint"),
            "finish_reason": choice.get("finish_reason"),
            "input_tokens": usage.get("prompt_tokens"), "output_tokens": usage.get("completion_tokens"),
            "usage_unit": "provider_tokens",
        })
