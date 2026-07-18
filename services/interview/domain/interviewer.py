"""The interviewer bound to one session: the system prompt it runs on, the
tools it can call, and the handlers behind them.

Both delivery paths drive the same interviewer - voice (voice/bot.py) converts
TOOL_DEFS to Pipecat FunctionSchemas, the text loop (session/service.py) to
OpenAI tool specs - so everything the interviewer 'knows' can be exercised
without a microphone. The handlers only mutate memory; ending the call is the
runner's job (it watches status)."""

from interview.domain.memory import SessionMemory
from interview.prompts import INTERVIEWER_SYSTEM


class Interviewer:
    """Everything the LLM interviewer needs for one session's memory."""

    # provider-agnostic tool definitions, adapted per delivery path
    TOOL_DEFS = [
        {"name": "mark_topic_covered",
         "description": "Mark an agenda topic as fully covered once the "
                        "employee has nothing more to add on it.",
         "parameters": {"type": "object", "properties": {
             "topic_id": {"type": "string",
                          "description": "The topic id from INTERVIEW STATE"},
             "summary": {"type": "string",
                         "description": "One line: the key thing learned"}},
             "required": ["topic_id"]}},
        {"name": "add_topic",
         "description": "Add a new topic the employee raised that is worth "
                        "capturing and is not on the agenda.",
         "parameters": {"type": "object", "properties": {
             "title": {"type": "string"},
             "why": {"type": "string",
                     "description": "Why this is worth capturing"}},
             "required": ["title"]}},
        {"name": "finish_interview",
         "description": "End the interview once every topic is covered or the "
                        "employee wants to stop. Say goodbye BEFORE calling "
                        "this.",
         "parameters": {"type": "object", "properties": {
             "reason": {"type": "string"}},
             "required": []}},
    ]

    def __init__(self, memory: SessionMemory):
        self._memory = memory

    def system_prompt(self) -> str:
        p = self._memory.profile
        return INTERVIEWER_SYSTEM.format(
            name=p.get("full_name") or "there",
            job_title=p.get("job_title") or "engineer",
            home_unit=p.get("home_unit") or "the plant",
            brief=self._memory.context.brief,
            state=self._memory.state_prompt())

    def tool_handlers(self) -> dict:
        """name -> fn(**args) -> json-serialisable result. Mutating memory is
        all they do; ending the call is the runner's job (it watches status)."""
        memory = self._memory

        def mark_topic_covered(topic_id: str, summary: str = ""):
            remaining = memory.mark_covered(topic_id, summary)
            if not remaining:
                return {"ok": True, "remaining": [],
                        "note": "all topics covered - wrap up and call "
                                "finish_interview"}
            return {"ok": True, "remaining": remaining}

        def add_topic(title: str, why: str = ""):
            topic = memory.add_topic(title, why)
            if topic is None:
                return {"ok": False, "note": "duplicate or agenda full"}
            return {"ok": True, "topic_id": topic.id}

        def finish_interview(reason: str = ""):
            memory.status = "ending"
            memory.save()
            return {"ok": True, "note": "interview ending - the farewell you "
                                        "just gave is the last thing said"}

        return {"mark_topic_covered": mark_topic_covered,
                "add_topic": add_topic,
                "finish_interview": finish_interview}
