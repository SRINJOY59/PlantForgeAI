"""Operational endpoints: pipeline metrics and health."""

from fastapi import APIRouter, Depends

from gateway.auth import current_user
from gateway.deps import get_service

router = APIRouter()


# this router is mounted without the blanket auth dependency so /health stays
# reachable for container healthchecks - /metrics protects itself
@router.get("/metrics")
def metrics(svc=Depends(get_service), user=Depends(current_user)):
    return svc.metrics()


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/system/slack/status")
def slack_status():
    from plantmind_core.notify import SlackNotifier
    notifier = SlackNotifier.from_settings()
    return {"enabled": notifier.enabled, "configured": bool(notifier._url)}


@router.post("/system/slack/test")
def slack_test(user=Depends(current_user)):
    from plantmind_core.notify import SlackNotifier
    notifier = SlackNotifier.from_settings()
    if not notifier.enabled:
        return {"success": False, "detail": "Slack webhook is not configured or disabled in .env"}
    name = user.get("full_name") or user.get("email") or "Plant Engineer"
    sent = notifier.post_test(user_name=name)
    return {"success": sent, "detail": "Notification sent" if sent else "Failed to post to Slack webhook"}
