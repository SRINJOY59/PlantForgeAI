"""The condenser is what makes a follow-up answerable, and what stops the
answer cache from serving one thread's answer to another. Both are worth
pinning."""

import pytest

from plantmind_core.schemas import Turn

from retrieval.condenser import QuestionCondenser, Standalone


class FakeLLM:
    """Returns a canned rewrite and records what it was asked."""

    def __init__(self, rewrite="", fail=False, is_follow_up=True):
        self.rewrite = rewrite
        self.fail = fail
        self.is_follow_up = is_follow_up
        self.prompts = []

    async def structured(self, messages, schema, tier=None, max_tokens=None):
        self.prompts.append(messages[0]["content"])
        if self.fail:
            raise RuntimeError("provider exploded")
        return Standalone(is_follow_up=self.is_follow_up, question=self.rewrite)

    @property
    def prompt(self):
        return self.prompts[-1]


async def test_a_first_question_is_never_condensed():
    # nothing to resolve, and an llm call per opening question is pure waste
    llm = FakeLLM(rewrite="should not be used")
    condenser = QuestionCondenser(llm)
    out = await condenser.condense("How many seal failures has P-101A had?", [])
    assert out == "How many seal failures has P-101A had?"
    assert llm.prompts == []


async def test_a_follow_up_is_rewritten_to_stand_alone():
    llm = FakeLLM(rewrite="What failures has P-101B, the sibling of P-101A, had?")
    condenser = QuestionCondenser(llm)
    out = await condenser.condense(
        "what about its sibling?",
        [Turn(question="How many seal failures has P-101A had?",
              answer="P-101A has had 3 seal failures.")])
    assert out == "What failures has P-101B, the sibling of P-101A, had?"


async def test_the_conversation_reaches_the_model():
    llm = FakeLLM(rewrite="x")
    await QuestionCondenser(llm).condense(
        "what about its sibling?",
        [Turn(question="seal failures on P-101A?", answer="Three.")])
    assert "P-101A" in llm.prompt
    assert "Three." in llm.prompt
    assert "what about its sibling?" in llm.prompt


async def test_only_the_last_few_turns_are_sent():
    # older turns drag stale tags into a question that has moved on
    llm = FakeLLM(rewrite="x")
    history = [Turn(question=f"question about K-{i}00?", answer=f"answer {i}")
               for i in range(1, 7)]
    await QuestionCondenser(llm, max_turns=4).condense("and that one?", history)
    assert "K-100" not in llm.prompt
    assert "K-200" not in llm.prompt
    assert "K-600" in llm.prompt


async def test_a_long_answer_is_clipped():
    llm = FakeLLM(rewrite="x")
    await QuestionCondenser(llm).condense(
        "why?", [Turn(question="q", answer="P-101A " + "z" * 5000)])
    assert len(llm.prompt) < 2000
    assert "P-101A" in llm.prompt, "the clip must keep the start, where tags are"


async def test_a_question_that_is_not_a_follow_up_is_left_exactly_alone():
    # the real failure: "what is actually barg" asked during a thread about
    # V-203 came back rewritten as a question about V-203's pressure, linked a
    # seed, routed to LOCAL, and answered something nobody asked. The model has
    # to declare the question referential before we accept its rewrite.
    llm = FakeLLM(rewrite="what is the operating pressure of V-203?",
                  is_follow_up=False)
    out = await QuestionCondenser(llm).condense(
        "what is actually barg",
        [Turn(question="why did PSV-204 lift?",
              answer="V-203 rose from 6.2 barg to 9.8 barg.")])
    assert out == "what is actually barg"


async def test_the_instructions_tell_the_model_a_definition_is_not_a_follow_up():
    llm = FakeLLM(rewrite="x")
    await QuestionCondenser(llm).condense("what is barg",
                                          [Turn(question="q", answer="a")])
    assert "what is barg" in llm.prompt.lower()
    assert "never a follow-up" in llm.prompt.lower()


async def test_a_condense_failure_falls_back_to_the_question_as_asked():
    # a bad rewrite should cost accuracy on one follow-up, never the answer
    condenser = QuestionCondenser(FakeLLM(fail=True))
    out = await condenser.condense("what about its sibling?",
                                   [Turn(question="q", answer="a")])
    assert out == "what about its sibling?"


async def test_an_empty_rewrite_falls_back_too():
    condenser = QuestionCondenser(FakeLLM(rewrite="   "))
    out = await condenser.condense("what about it?", [Turn(question="q", answer="a")])
    assert out == "what about it?"


async def test_history_may_arrive_as_plain_dicts():
    # the eval runner and tests pass dicts; http passes Turn models
    llm = FakeLLM(rewrite="x")
    await QuestionCondenser(llm).condense(
        "and?", [{"question": "seal failures on P-101A?", "answer": "Three."}])
    assert "P-101A" in llm.prompt


async def test_a_turn_with_no_answer_still_contributes_its_question():
    llm = FakeLLM(rewrite="x")
    await QuestionCondenser(llm).condense(
        "and?", [Turn(question="what about P-101A?")])
    assert "P-101A" in llm.prompt
