"""Per-user rate limits on the endpoints that cost money to serve.

/ask and /moc/assess each fan out to LLM calls; without a ceiling a single
token can run up the bill or starve everyone else. The limit is per user (off
the verified token, never a client-supplied id) and per bucket, so a burst of
questions can't eat into someone's assessments or vice versa.

A dependency, not middleware: only a couple of routes are expensive enough to
meter, and a dependency puts the limit next to the route it guards instead of
in a path-matching block far away.
"""

from fastapi import Depends, HTTPException

from gateway.auth import current_user
from gateway.deps import get_service

# (limit, window_seconds). Assessments are heavier than questions, so they get a
# lower ceiling. Deliberately generous - this is a floor against abuse, not a
# quota a working engineer should ever feel.
LIMITS = {
    "ask": (30, 60),
    "moc": (10, 60),
}


def rate_limit(bucket: str):
    limit, window = LIMITS[bucket]

    def dependency(user: dict = Depends(current_user), svc=Depends(get_service)):
        who = user.get("sub") or user.get("email") or "anon"
        allowed, retry_after = svc.rate_check(f"{bucket}:{who}", limit, window)
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit reached ({limit} per {window}s). "
                       f"Try again in {retry_after}s.",
                headers={"Retry-After": str(retry_after)})

    return dependency
