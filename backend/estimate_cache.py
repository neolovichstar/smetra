"""Workspace-isolated, exact-input cache. Similarity never authorizes a financial result."""
import json

from backend import redis_infra


def read(workspace_id, payload):
    try:
        client = redis_infra.provider()
        if client is None:
            return None
        value = client.get(redis_infra.key("estimateparse", workspace_id, payload))
        if value is None:
            return None
        parsed = json.loads(value) if isinstance(value, str) else value
        if not isinstance(parsed, dict) or not isinstance(parsed.get("choices"), list):
            return None
        # Never reuse provider usage or a previous request's provenance capability.
        return {"choices": parsed["choices"], "usage": {"prompt_tokens": 0, "completion_tokens": 0}}
    except Exception:
        # Cache availability must not decide whether the user can work.
        return None


def write(workspace_id, payload, result):
    try:
        client = redis_infra.provider()
        if client is not None:
            value = json.dumps({"choices": result["choices"]}, ensure_ascii=False, allow_nan=False)
            if len(value.encode()) <= 150_000:
                client.set(redis_infra.key("estimateparse", workspace_id, payload), value, ttl=900)
    except Exception:
        pass
