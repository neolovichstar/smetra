"""Shared cost-boundary guard for routes capable of spending OpenRouter credits.

Per-user allowance is enforced across legacy drafts, interactive assistant
requests, and durable assistant jobs. Unlike an IP-only WAF it cannot be bypassed
by switching API routes. Handler.throttle uses Redis and fails closed on its
ai: key prefix if that service is unavailable, rather than silently bypassing
a cost-bearing request.
"""

AI_SPEND_PER_MINUTE = 6


def enforce_ai_spend(service):
    """Throttle an authenticated user before starting an external model call."""
    user_id = str(service.user["id"])
    service.h.throttle("ai:spend:" + user_id, AI_SPEND_PER_MINUTE, 60)
