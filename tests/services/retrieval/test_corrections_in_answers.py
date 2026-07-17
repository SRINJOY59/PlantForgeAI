"""Recording a mistake is only worth anything if the system is reminded of it
at the moment it would repeat it. These pin that an answer built from a
corrected document cannot quote it as though nothing happened."""

from conftest import FakeEmbedder, FakeLLM, FakeReader

from retrieval.service import RetrievalService

CHUNK = {"id": "chunk:sop-1#c1",
         "text": "Repeated seal failures on P-101A have been traced to "
                 "running below minimum suction pressure (cavitation).",
         "context": "From sop_seal_replacement.md: ", "page": 2}

CORRECTION = {
    "doc_id": "sop-1",
    "correction_id": "corr-9",
    "correction": "Only 2 of the 3 were cavitation. The January failure was "
                  "misalignment after the coupling change.",
    "author": "eng@plant.com",
}

# the block's own header. The answerer's standing instructions also talk about
# corrections, so a looser match would pass whether or not one was found.
BLOCK = "CORRECTIONS FROM ENGINEERS AT THIS PLANT"


def reader(corrections=()):
    r = FakeReader()
    r.vector_results = [dict(CHUNK)]
    r.corrections = list(corrections)
    return r


async def ask(r, llm=None, question="why do P-101A seals keep failing?"):
    svc = RetrievalService(r, llm or FakeLLM("answer [doc:sop-1]"),
                           FakeEmbedder())
    return await svc.ask(question)


async def test_a_corrected_source_puts_the_correction_in_the_prompt():
    llm = FakeLLM("answer [doc:sop-1]")
    await ask(reader([CORRECTION]), llm)
    prompt = llm.prompts[0]
    assert BLOCK in prompt
    assert "misalignment after the coupling change" in prompt
    assert "eng@plant.com" in prompt


async def test_the_correction_comes_before_the_material_it_overrules():
    # a model that reads the correction last has already formed the answer the
    # correction exists to prevent
    llm = FakeLLM("answer [doc:sop-1]")
    await ask(reader([CORRECTION]), llm)
    prompt = llm.prompts[0]
    assert prompt.index(BLOCK) < prompt.index(CHUNK["text"])


async def test_the_correction_is_offered_as_a_citable_document():
    llm = FakeLLM("answer [doc:sop-1]")
    await ask(reader([CORRECTION]), llm)
    assert "[doc:corr-9]" in llm.prompts[0]


async def test_the_answer_may_cite_the_correction_and_stay_grounded():
    llm = FakeLLM("The January one was misalignment [doc:corr-9], not "
                  "cavitation [doc:sop-1].")
    r = reader([CORRECTION])
    # the correction document is itself retrievable evidence
    r.vector_results.append({"id": "chunk:corr-9#c1", "text": CORRECTION["correction"],
                             "context": "", "page": None})
    answer = await ask(r, llm)
    assert answer.grounding == "documents"
    assert {c.doc_id for c in answer.citations} == {"sop-1", "corr-9"}


async def test_an_uncorrected_source_adds_nothing_to_the_prompt():
    llm = FakeLLM("answer [doc:sop-1]")
    await ask(reader(), llm)
    assert BLOCK not in llm.prompts[0]


async def test_a_correction_on_a_document_we_did_not_retrieve_is_not_dragged_in():
    # only the evidence in front of us matters; the whole plant's correction
    # history is not context
    llm = FakeLLM("answer [doc:sop-1]")
    await ask(reader([{**CORRECTION, "doc_id": "some-other-doc"}]), llm)
    assert BLOCK not in llm.prompts[0]


async def test_the_reader_is_only_asked_about_documents_in_the_evidence():
    class Spy(FakeReader):
        asked = None

        def corrections_of(self, doc_ids):
            Spy.asked = set(doc_ids)
            return []

    r = Spy()
    r.vector_results = [dict(CHUNK)]
    await ask(r)
    assert Spy.asked == {"sop-1"}


async def test_the_answer_carries_the_correction_so_the_ui_can_show_it():
    # the prose is asked to mention it, but "trust me, I read it" is not
    # something a reader can check - this is the receipt
    answer = await ask(reader([CORRECTION]), FakeLLM("answer [doc:sop-1]"))
    assert len(answer.corrections) == 1
    note = answer.corrections[0]
    assert note.doc_id == "sop-1"
    assert note.correction_id == "corr-9"
    assert note.author == "eng@plant.com"
    assert "misalignment" in note.text


async def test_a_correction_on_a_source_the_answer_ignored_is_not_reported():
    # it was in the prompt, but the answer did not lean on that document, so
    # warning about it is noise
    r = reader([CORRECTION])
    r.vector_results.append({"id": "chunk:other#c1", "text": "unrelated",
                             "context": "", "page": None})
    answer = await ask(r, FakeLLM("answer [doc:other]"))
    assert answer.corrections == []


async def test_an_uncorrected_answer_reports_none():
    answer = await ask(reader(), FakeLLM("answer [doc:sop-1]"))
    assert answer.corrections == []


async def test_the_correction_survives_the_streaming_path():
    from retrieval.service import RetrievalService
    svc = RetrievalService(reader([CORRECTION]), FakeLLM("answer [doc:sop-1]"),
                           FakeEmbedder())
    events = [e async for e in svc.ask_stream("why do P-101A seals fail?")]
    kind, answer = events[-1]
    assert kind == "done"
    assert [c.doc_id for c in answer.corrections] == ["sop-1"]


async def test_two_corrections_on_one_source_both_reach_the_prompt():
    second = {**CORRECTION, "correction_id": "corr-10",
              "correction": "WO-2233 is misfiled against the wrong pump.",
              "author": "senior@plant.com"}
    llm = FakeLLM("answer [doc:sop-1]")
    await ask(reader([CORRECTION, second]), llm)
    prompt = llm.prompts[0]
    assert "coupling change" in prompt and "misfiled" in prompt
