"""Builds the employee's work context before the first question is asked:
their Supabase profile (sent by the frontend) joined with what the knowledge
graph already knows about their unit and projects. The rendered brief is what
makes the interviewer ask 'you logged six seal failures on P-101A - what
never made it into the work orders?' instead of 'so, what did you do here?'"""

import asyncio
import re

from pydantic import BaseModel

from interview.graph_context import InterviewGraphReader

# words in projects/expertise strings that carry no search signal
_STOPWORDS = {"and", "the", "for", "with", "unit", "plant", "system",
              "project", "team", "area", "general", "misc"}

# equipment-tag-shaped tokens, e.g. P-101, P-101A, HX-2043, V-12
_TAG_RE = re.compile(r"\b[A-Z]{1,4}-?\d{1,5}[A-Z]?\b")


class EquipmentContext(BaseModel):
    tag: str
    failures: list = []
    work_orders: list = []
    procedures: list = []
    connected: list = []


class WorkContext(BaseModel):
    profile: dict
    equipment: list[EquipmentContext] = []
    person_docs: list = []
    brief: str = ""


def _search_terms(profile: dict) -> list:
    """Tag-shaped tokens plus meaningful words from projects/expertise/unit."""
    fields = [profile.get("home_unit") or ""]
    fields += list(profile.get("projects") or [])
    fields += list(profile.get("expertise") or [])
    text = " ".join(str(f) for f in fields)

    terms = set(_TAG_RE.findall(text))
    for word in re.split(r"[^A-Za-z0-9-]+", text):
        w = word.strip("-").lower()
        if len(w) > 3 and w not in _STOPWORDS:
            terms.add(w)
    return list(terms)[:40]


def _gather(profile: dict, reader: InterviewGraphReader) -> WorkContext:
    terms = _search_terms(profile)
    tags = [r["tag"] for r in reader.equipment_matching(terms) if r.get("tag")]

    equipment = []
    for tag in tags[:8]:
        equipment.append(EquipmentContext(
            tag=tag,
            failures=reader.equipment_failures(tag),
            work_orders=reader.work_orders_for(tag),
            procedures=reader.procedures_for(tag),
            connected=reader.connected_equipment(tag),
        ))
    # equipment with actual history first - that is where the stories are
    equipment.sort(key=lambda e: len(e.failures) + len(e.work_orders),
                   reverse=True)

    docs = reader.person_docs(profile.get("full_name") or "")
    ctx = WorkContext(profile=profile, equipment=equipment,
                      person_docs=[d.get("doc") for d in docs if d.get("doc")])
    ctx.brief = _render_brief(ctx)
    return ctx


async def build_context(profile: dict,
                        reader: InterviewGraphReader) -> WorkContext:
    # the neo4j driver is sync; keep the event loop free
    return await asyncio.to_thread(_gather, profile, reader)


def _render_brief(ctx: WorkContext) -> str:
    p = ctx.profile
    lines = ["## Employee"]
    lines.append(f"- Name: {p.get('full_name') or 'unknown'}"
                 f" ({p.get('employee_id') or 'no id'})")
    lines.append(f"- Role: {p.get('job_title') or 'unknown'},"
                 f" {p.get('department') or 'unknown department'}")
    lines.append(f"- Plant / unit: {p.get('plant') or 'unknown'}"
                 f" / {p.get('home_unit') or 'unknown'}")
    if p.get("projects"):
        lines.append(f"- Projects: {', '.join(p['projects'])}")
    if p.get("expertise"):
        lines.append(f"- Expertise: {', '.join(p['expertise'])}")

    if ctx.equipment:
        lines.append("\n## Equipment history in the knowledge graph")
        for eq in ctx.equipment:
            lines.append(f"### {eq.tag}")
            for f in eq.failures[:4]:
                causes = ", ".join(f.get("causes") or []) or "causes not recorded"
                lines.append(f"- failure: {f.get('mode')}"
                             f" x{f.get('count', 1)} ({causes})")
            for w in eq.work_orders[:4]:
                action = w.get("action_taken") or "action not recorded"
                lines.append(f"- WO {w.get('wo_id')} ({w.get('date')}):"
                             f" {w.get('description')} -> {action}")
            procs = [x.get("procedure") for x in eq.procedures if x.get("procedure")]
            if procs:
                lines.append(f"- procedures on file: {', '.join(procs[:5])}")
            conn = [c.get("tag") for c in eq.connected if c.get("tag")]
            if conn:
                lines.append(f"- connected to: {', '.join(conn[:6])}")
    else:
        lines.append("\n## Equipment history in the knowledge graph")
        lines.append("- none found for this profile; interview from the"
                     " profile alone and ask them to name their key equipment")

    if ctx.person_docs:
        lines.append("\n## Documents already mentioning them")
        lines += [f"- {d}" for d in ctx.person_docs[:8]]

    return "\n".join(lines)
