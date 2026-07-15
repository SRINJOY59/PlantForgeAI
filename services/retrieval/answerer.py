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
            [{"role": "user",
              "content": PROMPT.format(context=context, question=question)}],
            tier=Tier.MID, max_tokens=3000)

        citations = [Citation(doc_id=e.doc_id, page=e.page,
                              snippet=e.text[:200]) for e in evidence]
        confidence = ("high" if len(evidence) >= 2
                      else "medium" if evidence else "low")
        return Answer(text=text, citations=citations, mode=mode,
                      confidence=confidence, graph_version=graph_version)
