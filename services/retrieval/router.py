"""Which retrieval mode fits the question. Rules only - the signals
(linked seeds, causal wording) are cheap and reliable; an LLM router can
replace this later without touching anything downstream."""

from plantmind_core.schemas import QueryMode

CAUSAL_WORDS = ("why", "cause", "caused", "lead", "led", "result",
                "because", "affect", "impact", "downstream", "upstream",
                "explain how", "could", "trigger")


class ModeRouter:
    def route(self, question: str, seeds: list) -> QueryMode:
        if not seeds:
            return QueryMode.VECTOR
        q = question.lower()
        if len(seeds) >= 2 or any(w in q for w in CAUSAL_WORDS):
            return QueryMode.PATH
        return QueryMode.LOCAL
