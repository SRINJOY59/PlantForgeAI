from plantmind_core.llm import Tier
from plantmind_core.schemas import Answer, Citation

PROMPT = """You are the plant's knowledge assistant. Answer the question
using ONLY the material below - graph paths from the plant's knowledge
graph and source passages from its documents. Cite sources inline as
[doc:<id>] or [doc:<id> p<page>]. If the material does not contain the
answer, say so plainly instead of guessing. Keep the tone of a senior
engineer: direct, concrete, no filler.

Graph paths are authoritative plant topology: chain them across hops to
answer connectivity questions (A-B plus B-C means C is two steps from A).
Tag convention: the first digit of a tag's number is its unit - P-101A is
Unit 100 equipment, V-210 is Unit 200, T-301 is Unit 300.

{context}

QUESTION: {question}"""


class Answerer:
    def __init__(self, llm):
        self._llm = llm

    async def answer(self, question: str, context: str, evidence: list,
                     mode, graph_version: int) -> Answer:
        # generous budget: reasoning models spend tokens thinking before the
        # visible answer, and a truncated answer reads as a wrong answer
        text = await self._llm.complete(
            [{"role": "user", "content": self._prompt(context, question)}],
            tier=Tier.MID, max_tokens=3000)
        return self._build(text, evidence, mode, graph_version)

    async def stream(self, question: str, context: str):
        """Yields answer text deltas. Retrieval (linking, paths, evidence)
        has already finished before the first token - only generation
        streams, and the citations are known from the evidence, not the
        model output, so the caller can send them at the end."""
        async for delta in self._llm.stream(
                [{"role": "user", "content": self._prompt(context, question)}],
                tier=Tier.MID, max_tokens=3000):
            yield delta

    def build_meta(self, evidence: list, mode, graph_version: int) -> Answer:
        """The structured envelope (citations, mode, confidence) that the
        streaming path emits after the tokens - text left empty."""
        return self._build("", evidence, mode, graph_version)

    @staticmethod
    def _prompt(context, question) -> str:
        return PROMPT.format(context=context, question=question)

    @staticmethod
    def _build(text, evidence, mode, graph_version) -> Answer:
        citations = [Citation(doc_id=e.doc_id, page=e.page,
                              snippet=e.text[:200]) for e in evidence]
        confidence = ("high" if len(evidence) >= 2
                      else "medium" if evidence else "low")
        return Answer(text=text, citations=citations, mode=mode,
                      confidence=confidence, graph_version=graph_version)
