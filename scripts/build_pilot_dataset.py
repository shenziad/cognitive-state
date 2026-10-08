"""Rebuild the versioned synthetic pilot fixtures; no LLM or private data needed."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "datasets" / "exp001" / "v0.1"

# Different service scenarios share a deliberately small tool environment.
# Target settings live in post-cutoff evidence and the evaluator, never in the extraction input.
CASES = [
    ("jwt_units", "修复 JWT 时间单位", "Restore JWT expiration validation",
     {"expiry_unit": "seconds", "clock_skew": 30, "schema_version": 1}, {"expiry_unit": "milliseconds"},
     ["schema_version", "clock_skew"], "JWT validation fails for fresh tokens; a restart did not help.",
     "Timezone conversion may be wrong", {"key": "expiry_unit", "value": "seconds"},
     "The current token issuer documents millisecond timestamps; verifier must use the same unit."),
    ("api_endpoint", "更新 API 地址", "Restore invoice API requests",
     {"api_base": "/v1/invoices", "api_version": "v1", "region": "eu", "schema_version": 1},
     {"api_base": "/v2/invoices", "api_version": "v2"}, ["region", "schema_version"],
     "The service receives HTTP 404; credentials were already checked.", "The API may require a different version header",
     {"key": "api_base", "value": "/v1/invoices"}, "Both endpoint path and version header must match v2."),
    ("request_timeout", "调整请求超时", "Restore report export requests",
     {"timeout_ms": 1000, "retry_count": 2, "schema_version": 1}, {"timeout_ms": 5000},
     ["retry_count", "schema_version"], "Exports time out after one second; increasing retries previously failed.",
     "The upstream export may have slower-than-usual latency", {"key": "retry_count", "value": 5},
     "Measured normal export latency is four seconds; use a five-second timeout."),
    ("cache_namespace", "修复缓存命名空间", "Restore tenant-specific cache reads",
     {"namespace": "shared", "tenant_id": "tenant-b", "ttl_seconds": 600, "schema_version": 1},
     {"namespace": "tenant-b"}, ["tenant_id", "ttl_seconds", "schema_version"],
     "Cache misses occur for tenant-b; clearing the cache previously did not help.",
     "Requests may be using an unexpected namespace", {"key": "ttl_seconds", "value": 60},
     "The namespace must equal tenant-b; freshness is not the cause of this incident."),
    ("csv_format", "修复 CSV 格式", "Restore partner CSV imports",
     {"delimiter": ",", "encoding": "latin-1", "skip_errors": False, "schema_version": 1},
     {"delimiter": ";", "encoding": "utf-8"}, ["skip_errors", "schema_version"],
     "Imported columns are merged and accented names are corrupted.", "Input encoding may also differ from local settings",
     {"key": "delimiter", "value": ","}, "The partner format is semicolon-separated UTF-8; reject malformed rows."),
    ("tls_bundle", "修复 TLS 信任链", "Restore verified TLS connections",
     {"ca_bundle": "legacy.pem", "verify_tls": True, "schema_version": 1},
     {"ca_bundle": "partner-ca.pem"}, ["verify_tls", "schema_version"],
     "Certificate verification fails after partner certificate rotation.", "The configured CA bundle may be outdated",
     {"key": "ca_bundle", "value": "legacy.pem"}, "The rotated certificate chains to partner-ca.pem."),
    ("staging_route", "纠正测试环境路由", "Restore the staging inference route",
     {"route": "production", "model_revision": "r1", "production_route": "stable", "schema_version": 1},
     {"route": "staging", "model_revision": "r2"}, ["production_route", "schema_version"],
     "Staging requests hit the production service; previous DNS flush had no effect.",
     "Route configuration may still point at the wrong environment", {"key": "route", "value": "production"},
     "Staging uses route=staging and model_revision=r2. Production routing is outside this task."),
    ("pagination", "修复分页兼容性", "Restore complete inventory pagination",
     {"page_size": 500, "cursor_mode": "offset", "include_archived": False, "schema_version": 1},
     {"page_size": 100, "cursor_mode": "token"}, ["include_archived", "schema_version"],
     "Inventory requests fail on the second page; the proxy is reachable.", "A proxy issue may truncate results",
     {"key": "page_size", "value": 500}, "The current API allows 100 items and requires token cursors."),
    ("scheduler", "纠正定时任务时区", "Restore the daily billing schedule",
     {"timezone": "UTC", "hour": 9, "duplicate_guard": True, "schema_version": 1},
     {"timezone": "Asia/Hong_Kong"}, ["hour", "duplicate_guard", "schema_version"],
     "Billing runs eight hours late; the configured hour is already correct.",
     "Timezone handling may be wrong", {"key": "hour", "value": 1},
     "Use Asia/Hong_Kong with the existing hour=9; preserve the duplicate guard."),
    ("feature_flag", "恢复灰度开关", "Restore checkout for the pilot cohort",
     {"pilot_enabled": False, "cohort": "internal", "global_enabled": False, "schema_version": 1},
     {"pilot_enabled": True, "cohort": "pilot-a"}, ["global_enabled", "schema_version"],
     "Pilot users cannot reach checkout; global rollout is explicitly out of scope.",
     "The cohort selector may be stale", {"key": "cohort", "value": "internal"},
     "Enable only pilot-a using pilot_enabled=true; keep global_enabled=false."),
    ("log_redaction", "恢复日志脱敏", "Restore useful redacted audit logs",
     {"redact_pii": False, "log_level": "debug", "audit_enabled": True, "schema_version": 1},
     {"redact_pii": True, "log_level": "info"}, ["audit_enabled", "schema_version"],
     "Audit output contains personal fields and excessive debug records.",
     "The logger may be using pre-redaction settings", {"key": "log_level", "value": "debug"},
     "Redact personal fields and use info level while preserving audit output."),
    ("queue_batch", "修复队列批量限制", "Restore successful queue consumption",
     {"batch_size": 100, "ack_mode": "automatic", "delete_on_failure": False, "schema_version": 1},
     {"batch_size": 50, "ack_mode": "manual"}, ["delete_on_failure", "schema_version"],
     "Batches are rejected; failed items must remain recoverable.", "Consumer acknowledgement mode may have changed",
     {"key": "batch_size", "value": 100}, "Consumer supports batches of 50 and manual acknowledgement."),
]


def save(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    manifest = {"dataset_version": "exp001-pilot-v0.1", "synthetic": True,
                "split": "pilot", "reference_review_status": "pending", "instances": []}
    for index, case in enumerate(CASES, 1):
        slug, title, objective, initial, target, protected, fact, belief, failed, evidence = case
        instance_id = f"pilot{index:02d}_{slug}"
        constraints = [f"Preserve {key}={json.dumps(initial[key])}; do not change it." for key in protected]
        constraints += ["No database migration; modify virtual service configuration only."]
        history = [
            {"id": "h01", "role": "user", "content": objective + ". Success means all service checks pass. " + " ".join(constraints)},
            {"id": "h02", "role": "assistant", "content": "I will investigate the virtual service configuration. Working assumption: the virtual fixture represents the interrupted service; this has not independently been checked."},
            {"id": "h03", "role": "tool", "content": fact + " Current config/service.json: " + json.dumps(initial)},
            {"id": "h04", "role": "assistant", "content": "Unconfirmed belief: " + belief + ". Confidence: 0.6. This is not established."},
            {"id": "h05", "role": "tool", "content": "Earlier unsuccessful change: " + json.dumps(failed) + ". It did not solve the incident and was reverted."},
            {"id": "h06", "role": "user", "content": "Continue the original repair. " + " ".join(constraints) + " Prefer a small, evidence-based change."},
            {"id": "h07", "role": "tool", "content": "docs/legacy_runbook.json is explicitly deprecated; it recommends the old configuration. Use docs/runbook.json for current guidance; its contents have not been read yet."},
        ]
        # Vary distractor volume. These are synthetic history lengths, not genuine long-horizon traces.
        for j in range(2 + index % 4):
            history.append({"id": f"d{j:02d}", "role": "user", "content":
                "Unrelated archived meeting note: the dashboard theme, weekly demo agenda, "
                "team lunch and documentation spelling were discussed. No service configuration "
                "or task constraint changed. This note belongs to an older completed activity. " * 2})
        history.append({"id": "h08", "role": "assistant", "content":
                        "Current focus: " + objective + ". Need the current settings guidance. "
                        "Next action: read docs/runbook.json before editing; then test and report completion."})
        public = {"instance_id": instance_id, "title": title, "cutoff": "after:h08", "history": history}
        fixture = {"instance_id": instance_id, "files": {
            "config/service.json": initial,
            "docs/runbook.json": {"status": "current", "explanation": evidence, "recommended_settings": target},
            "docs/legacy_runbook.json": {"status": "deprecated", "recommended_settings": initial},
            "logs/runtime.log": fact,
        }, "rubric": {"target_settings": target, "protected_keys": protected,
                       "known_failed_changes": [failed], "evidence_path": "docs/runbook.json"}}
        state = {
            "goal": {"objective": objective, "success_criteria": ["All service checks pass"],
                     "constraints": constraints, "preferences": ["Prefer a small, evidence-based change"]},
            "world": {"facts": [fact, "Earlier change " + json.dumps(failed) + " failed and was reverted",
                                  "Legacy runbook is deprecated; current runbook has not been read"],
                      "beliefs": [{"claim": belief, "confidence": 0.6}],
                      "assumptions": ["The virtual fixture represents the interrupted service"]},
            "frontier": {"current_focus": objective, "information_needs": ["Current settings guidance"],
                         "next_action": "Read docs/runbook.json, then edit based on evidence and run checks"},
        }
        reference = {"instance_id": instance_id, "review": {"status": "pending", "author": "assistant_generated", "reviewer": None},
                     "source_message_ids": {"goal": ["h01", "h06"], "world.facts": ["h03", "h05", "h07"],
                                            "world.beliefs": ["h04"], "world.assumptions": ["h02"], "frontier": ["h08"]},
                     "state": state}
        paths = {"task": f"tasks/{instance_id}.json", "environment": f"environments/{instance_id}.json",
                 "reference": f"references/{instance_id}.json"}
        for key, value in (("task", public), ("environment", fixture), ("reference", reference)):
            save(DATA / paths[key], value)
        manifest["instances"].append({"instance_id": instance_id, "title": title, **paths})
    save(DATA / "manifest.json", manifest)
    print(f"Wrote {len(CASES)} pilot tasks to {DATA}")


if __name__ == "__main__":
    main()
