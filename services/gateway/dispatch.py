"""Getting an approved work order into the hands of the people who will do it.

This runs the moment Slack says yes, and it is the only place in the codebase
where an artifact leaves the console and becomes an instruction to a person. So
the ordering is deliberate:

    approved -> brief -> translate -> assign -> confirm

The briefs are built by the AGENTS service, not here. Two reasons, and the
second is the real one:

  * The gateway image has no LLM SDK, on purpose. It is the internet-facing
    process; the fewer things it can do, the better.
  * Reshaping a planner's work order into a technician's job card is reasoning
    over plant evidence, which is what the agents service is. Doing it here
    would put a second, quietly diverging copy of that judgement at the edge -
    and the two would disagree about the same work order.

What DOES belong here is everything after the language: who is on this
engineer's crew, whose inbox each brief lands in, and telling Slack it landed.
That is routing, and routing is the gateway's job.

Failure posture: a crew member whose translation fails still gets the job card
in English (the agents service falls back rather than raising), and a Slack
confirmation that fails to post never un-does a dispatch that already reached
the workers. The only hard failure is one that leaves nobody assigned - and
that one is reported back to whoever tapped Approve, while they are still
looking at the screen.
"""

import time

from plantmind_core.config import get_settings
from plantmind_core.notify import SlackNotifier
from plantmind_core.telemetry import get_logger

log = get_logger("gateway.dispatch")

# Building a job card is one structured LLM call plus one per extra language,
# run concurrently upstream. Generous, because the alternative to waiting is a
# crew that was approved and never told.
_BRIEF_TIMEOUT_S = 180


def crew_languages(crew: list) -> list:
    """The distinct languages this crew actually reads.

    Translating into the twelve languages the platform supports when the crew
    speaks two is eleven wasted LLM calls and eleven more chances to produce a
    job card nobody checks. English is always included: it is the source the
    engineer's console keeps, and the fallback when a translation fails.
    """
    langs = {(w.get("lang") or "en").strip() or "en" for w in crew}
    langs.add("en")
    return sorted(langs)


async def fetch_briefs(agents_http, draft: dict, schedule: dict,
                       langs: list) -> dict:
    """{lang: brief} from the agents service."""
    resp = await agents_http.post("/work-order/brief",
                                  json={"draft": draft, "schedule": schedule,
                                        "langs": langs},
                                  timeout=_BRIEF_TIMEOUT_S)
    resp.raise_for_status()
    return (resp.json() or {}).get("briefs") or {}


def worker_key(worker: dict) -> str:
    """The identifier a worker's own JWT will present.

    Their account email, lowercased. It is the only thing that survives both
    ends of this: the engineer types it into the roster, and Supabase puts it
    in the token when that worker signs in. Falling back to the roster id keeps
    a crew member without an account from silently vanishing from the dispatch
    - they just cannot open it until the account exists.
    """
    return (worker.get("email") or worker.get("id") or "").strip().lower()


async def dispatch_to_crew(bus, draft: dict, schedule: dict,
                           agents_http) -> list:
    """Deliver one approved work order to every worker under the engineer.

    Returns what was delivered and to whom, which the caller records against
    the schedule so the console can show it and Slack can confirm it.
    """
    settings = get_settings()
    draft_id = schedule.get("draft_id", "")
    engineer_key = (schedule.get("requested_by") or "").strip().lower()

    crew = bus.crew(engineer_key)
    if not crew:
        # Not an error to swallow quietly: the work is authorised and nobody
        # is going to do it. The caller surfaces this on the card.
        raise ValueError("no crew on this engineer's roster - add workers "
                         "before dispatching")

    wanted = crew_languages(crew)

    # Cache first, and per language rather than per worker: three Hindi-reading
    # fitters on the same order is one translation, not three. The draft is
    # immutable, so a cached brief can never be stale for its draft id.
    briefs = {}
    for lang in wanted:
        cached = bus.cached_brief(draft_id, lang)
        if cached:
            briefs[lang] = cached
    missing = [lang for lang in wanted if lang not in briefs]

    if missing:
        # English is always requested alongside the missing ones: it is the
        # source every translation is made from upstream, and the copy the
        # console shows the engineer.
        fresh = await fetch_briefs(agents_http, draft, schedule,
                                   sorted(set(missing) | {"en"}))
        for lang, brief in fresh.items():
            briefs[lang] = brief
            bus.cache_brief(draft_id, lang, brief,
                            settings.dispatch_brief_ttl_s)

    english = briefs.get("en") or {}
    now = time.time()
    recipients = []
    assignment_ids = []

    for worker in crew:
        lang = (worker.get("lang") or "en").strip() or "en"
        brief = briefs.get(lang) or english
        if not brief:
            log.warning("no brief in any language; skipping worker",
                        draft=draft_id, lang=lang)
            continue

        key = worker_key(worker)
        if not key:
            log.warning("crew member has no email or id; cannot address them",
                        draft=draft_id, name=worker.get("name"))
            continue

        # Deterministic id, so re-dispatching the same order to the same worker
        # updates their copy instead of stacking a second identical job on
        # their phone.
        assignment_id = f"{draft_id}:{key}"
        existing = bus.assignment(key, assignment_id) or {}

        assignment = {
            "id": assignment_id,
            "draft_id": draft_id,
            "equipment": draft.get("equipment", ""),
            "failure_mode": draft.get("failure_mode", ""),
            "order_type": draft.get("order_type", "PM01"),
            "priority": draft.get("priority", "medium"),
            "lang": brief.get("lang", lang),
            "brief": brief,
            # The English source travels with every assignment. When a worker
            # and a supervisor disagree about what the job card said, both can
            # look at the same original instead of arguing through a round
            # trip of re-translation.
            "brief_en": english,
            "window_start": schedule.get("window_start"),
            "window_end": schedule.get("window_end"),
            "notes": schedule.get("notes", ""),
            "assigned_by": schedule.get("requested_by"),
            "approved_by": schedule.get("decided_by"),
            "assigned_at": existing.get("assigned_at") or now,
            # A re-dispatch must not reset a job the worker already picked up.
            "status": existing.get("status") or "assigned",
            "acknowledged_at": existing.get("acknowledged_at"),
            "completed_at": existing.get("completed_at"),
            "worker_note": existing.get("worker_note", ""),
        }
        bus.add_assignment(key, assignment)
        assignment_ids.append(assignment_id)
        recipients.append({"name": worker.get("name") or key,
                           "lang": assignment["lang"],
                           "worker_key": key,
                           "assignment_id": assignment_id})

    if not recipients:
        raise ValueError("no crew member could be addressed - every roster "
                         "entry is missing an email")

    bus.set_order_assignments(draft_id, assignment_ids)

    try:
        SlackNotifier.from_settings().post_work_order_dispatched(
            draft, schedule, recipients)
    except Exception as e:
        # The workers already have it. A missing confirmation message is a
        # cosmetic loss and must never look like a failed dispatch.
        log.warning("dispatch confirmation to slack failed", error=str(e)[:200])

    log.info("dispatch complete", draft=draft_id, workers=len(recipients),
             languages=sorted({r["lang"] for r in recipients}))
    return recipients
