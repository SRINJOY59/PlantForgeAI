"""Turning an approved work order into something a worker can act on, in the
language they think in.

Two transformations, in this order, and the order is the whole design:

  1. RESHAPE. A work order is written for a planner deciding whether the work
     is justified. A worker needs the opposite document: what to do, in what
     order, and what must be safe first. Doing this in English once means every
     translation starts from a brief that is already the right shape - and it
     means the engineer's console holds an English copy that is directly
     comparable to what each worker was sent.

  2. TRANSLATE. Only then, into each crew member's language.

Doing it the other way round - translating the planner's prose and hoping the
worker extracts the steps - is how a safety instruction ends up as clause four
of a paragraph about seal cavitation history.

Two rules the model is held to, and both exist because this is read at the
equipment rather than at a desk:

  * Identifiers are never translated. SOP-114, P-101B, IS 2062, a torque figure
    in newton-metres - transliterating any of these makes it unfindable in the
    document it points at, and a worker who cannot find the procedure does the
    job from memory. They are carried through verbatim into every language.

  * Nothing is added. The steps come from recommended_fix and the safety lines
    from the order's own hazards and clauses. A model that is allowed to
    helpfully append "isolate before starting" to a job where isolation was
    never specified is a model that will one day omit it and be believed.
"""

from __future__ import annotations

from plantmind_core.llm import Tier, get_llm
from plantmind_core.schemas import WorkerBrief
from plantmind_core.telemetry import get_logger

log = get_logger("agents.usecases.work_order.dispatch")

# What the codes mean, spelled out for the model. A bare "bn" is ambiguous
# enough that a model will occasionally answer in the wrong script, and the
# script matters more than the language name here: a Devanagari rendering of
# Bengali is unreadable to the person it was written for.
LANGUAGE_NAMES = {
    "en": "English",
    "hi": "Hindi (Devanagari script)",
    "bn": "Bengali (Bengali script)",
    "ta": "Tamil (Tamil script)",
    "te": "Telugu (Telugu script)",
    "mr": "Marathi (Devanagari script)",
    "gu": "Gujarati (Gujarati script)",
    "kn": "Kannada (Kannada script)",
    "ml": "Malayalam (Malayalam script)",
    "pa": "Punjabi (Gurmukhi script)",
    "or": "Odia (Odia script)",
    "as": "Assamese (Assamese script)",
    "ur": "Urdu (Arabic script, right-to-left)",
}

RESHAPE_SYSTEM = """You are a maintenance supervisor briefing the technician
who will carry out an approved work order. You are rewriting a planner's work
order into a job card the technician reads while standing at the equipment.

Write:

title: the job in under 10 words. Name the equipment tag.
summary: 1-2 sentences - what is wrong and what they are going to do about it.
steps: the actual work, as short imperative actions in the order they happen.
  One action per step. Start each with a verb. Prefer 4-8 steps.
safety: what must be true BEFORE and DURING the work - isolations, hazards,
  permits. Only what the source material supports.
ppe: protective equipment named or clearly implied by the hazards given.
references: procedure numbers, standards and prior work order ids, copied
  exactly as written.

Hard rules:
- Never invent an isolation point, hazard, procedure number or torque value.
  If the source does not say it, it does not appear.
- Never translate or alter an identifier: equipment tags, document numbers,
  standard names and units stay exactly as given.
- No markdown, no numbering in the text itself - the list is the numbering.
- Plain, direct language. Short sentences. This is read one-handed on a phone."""

TRANSLATE_SYSTEM = """You translate an approved maintenance job card for a
plant technician into {language}.

Translate every field into {language}, naturally - as a supervisor in that
language would actually say it to a technician, not word-for-word from English.

Do NOT translate, transliterate or reformat any of the following; copy them
character for character:
- equipment tags (P-101B, FT-103, E-201)
- document, procedure, permit and work order numbers (SOP-114, WO-2291)
- standard names and codes (IS 2062, API 610, ASME B31.3)
- units and numeric values (bar, rpm, mm, and torque figures)

Keep the same number of steps, in the same order. Do not add advice, warnings
or steps that are not in the source. Do not drop a safety line.

Return the same structure with every field in {language}."""


def _source_material(draft: dict) -> str:
    """The parts of the draft a worker's brief may be built from.

    Root cause is included but the model is told it is background: a technician
    who understands why the seal keeps failing does the job better, but the
    diagnosis is not the instruction, and the planner's grounding caveats,
    citations and priority rules have no business on a job card.
    """
    lines = [
        "Equipment: " + str(draft.get("equipment") or "unknown"),
        "Failure mode: " + str(draft.get("failure_mode") or "not stated"),
        "Order type: " + str(draft.get("order_type") or "PM01"),
        "Priority: " + str(draft.get("priority") or "medium"),
    ]
    for label, key in (("Other equipment affected", "affected_equipment"),
                       ("Procedures", "procedures"),
                       ("Governing standards and clauses", "governing_clauses"),
                       ("Prior work orders on this asset", "prior_work_orders")):
        values = draft.get(key) or []
        if values:
            lines.append(label + ": " + ", ".join(str(v) for v in values))
    if draft.get("root_cause"):
        lines.append("")
        lines.append("Background - why this is happening: " + str(draft["root_cause"]))
    if draft.get("recommended_fix"):
        lines.append("")
        lines.append("The approved fix: " + str(draft["recommended_fix"]))
    return chr(10).join(lines)


def _schedule_note(schedule: dict) -> str:
    if not schedule:
        return ""
    bits = []
    if schedule.get("window_start"):
        bits.append("Scheduled to start: " + str(schedule["window_start"]))
    if schedule.get("window_end"):
        bits.append("Must be complete by: " + str(schedule["window_end"]))
    if schedule.get("notes"):
        bits.append("Note from the engineer: " + str(schedule["notes"]))
    return chr(10).join(bits)


async def build_brief(draft: dict, schedule: dict | None = None,
                      llm=None) -> WorkerBrief:
    """The English job card. One structured call; the shape is the schema."""
    llm = llm or get_llm()
    task = _source_material(draft)
    note = _schedule_note(schedule or {})
    if note:
        task = task + chr(10) + chr(10) + note
    brief = await llm.structured(
        [{"role": "system", "content": RESHAPE_SYSTEM},
         {"role": "user", "content": task}],
        WorkerBrief, tier=Tier.MID, max_tokens=1200)
    brief.lang = "en"
    return _carry_references(brief, draft)


async def translate_brief(brief: WorkerBrief, lang: str, llm=None) -> WorkerBrief:
    """The same job card in one other language.

    English short-circuits rather than round-tripping through the model: a
    translation call that can only degrade the text is a call worth not making.
    A language we have no name for also short-circuits - handing an unlabelled
    code to the model invites a confident answer in the wrong script, and an
    unreadable job card is worse than an English one the worker can show to
    somebody.
    """
    if lang == "en" or lang not in LANGUAGE_NAMES:
        if lang != "en" and lang not in LANGUAGE_NAMES:
            log.warning("no language name for code; leaving brief in English",
                        lang=lang)
        return brief.model_copy(update={"lang": "en"})

    llm = llm or get_llm()
    system = TRANSLATE_SYSTEM.format(language=LANGUAGE_NAMES[lang])
    try:
        out = await llm.structured(
            [{"role": "system", "content": system},
             {"role": "user", "content": brief.model_dump_json()}],
            WorkerBrief, tier=Tier.MID, max_tokens=1600)
    except Exception as e:
        # A worker with an English job card can still do the work and can ask
        # someone. A worker with no job card cannot. Never fail the dispatch on
        # a translation.
        log.warning("brief translation failed; falling back to English",
                    lang=lang, error=str(e))
        return brief.model_copy(update={"lang": "en"})

    out.lang = lang
    # The model is told not to touch identifiers; this is what makes that true
    # rather than requested.
    out.references = list(brief.references)
    if len(out.steps) != len(brief.steps):
        log.warning("translated brief changed step count", lang=lang,
                    source=len(brief.steps), translated=len(out.steps))
    return out


def _carry_references(brief: WorkerBrief, draft: dict) -> WorkerBrief:
    """Procedures and clauses come off the draft, not the model.

    They were harvested out of the graph when the draft was written precisely
    so nothing could invent them; letting the reshape step rewrite them here
    would hand that guarantee straight back.
    """
    refs = [str(v) for v in (draft.get("procedures") or [])]
    refs += [str(v) for v in (draft.get("governing_clauses") or [])]
    brief.references = list(dict.fromkeys(refs))
    return brief
