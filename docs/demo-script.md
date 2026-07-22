# PlantForge.ai — demo script

**Problem Statement 8** · AI for Industrial Knowledge Intelligence: Unified Asset
& Operations Brain
**Runtime:** ~7:15 · **Narration:** ~1,050 words at 150 wpm

Record the screen **silent**, generate the voice-over from the NARRATION blocks,
then cut the video under the audio. Fitting picture to a fixed audio track is far
easier than syncing narration to clips already timed.

---

## Pre-flight

- [ ] **Log in as an admin.** Admin is the only role that reveals the whole
      navigation, including Connectors — the walkthrough depends on it.
- [ ] **Regenerate the alerts.** Those currently on the feed were written under an
      older prompt: they open with a stray rule and claim a work order was
      "drafted in SAP", which is untrue. New investigations produce three clean
      sections ending in a numbered checklist.
- [ ] **Pre-warm every page once** — first load of Graph Explorer is ~850 ms and
      the answer cache starts cold. Clicking through beforehand makes the
      recording feel instant.
- [ ] **Have the Ask question on the clipboard**, not typed live.
- [ ] Browser at 1920×1080, 100% zoom, bookmarks hidden, single tab.

### For the voice tool

Feed it the NARRATION text only — no markdown. Equipment tags read badly as
literals, so spell them phonetically in the input: `P-101A` → "P one oh one A",
`K-301` → "K three oh one", `OISD` → "O I S D", `P&ID` → "P and I D".

---

## Scene 1 — The problem, and the statement (0:00–0:50)

**SCREEN:** Landing page. Slow scroll across the statistics band, hold on it.

> **NARRATION**
> A 2024 McKinsey survey found that professionals in asset-intensive industries
> spend thirty-five percent of their working hours searching for information that
> already exists somewhere in their own organisation. In Indian heavy industry, a
> large plant runs on seven to twelve disconnected document systems — drawings in
> one, work orders in another, procedures in a third, inspection records in a
> fourth, and regulatory correspondence scattered across email. That
> fragmentation drives an estimated eighteen to twenty-two percent of unplanned
> downtime. And within the next decade, a quarter of India's experienced
> engineers retire and take decades of undocumented knowledge with them.
> That is Problem Statement Eight. We chose it because it is not a document
> management problem. It is a safety problem, a compliance problem and a
> reliability problem wearing a filing cabinet as a disguise. This is PlantForge.

---

## Scene 2 — The unified brain (0:50–1:40)

**SCREEN:** Sign in as admin → Dashboard. Let the KPI row and charts settle. Hover
the admin role badge. Then sweep the full left navigation slowly, top to bottom.

> **NARRATION**
> We are signed in as an administrator, so every capability is visible. The
> platform ingests engineering drawings, maintenance records, procedures,
> inspection reports and email archives, and turns them into one connected
> knowledge graph — currently a little over two thousand entities linked across
> forty-two documents. This dashboard is not a mock-up. Every number here is read
> live from that graph and from the running pipeline: alerts the agents raised,
> where the ingestion queue stands, and what the plant is exposed to right now.
> What you see in the sidebar is one brain, addressed by different jobs — asking
> it a question, watching what it warns you about, planning a change, proving
> compliance, and capturing what is still only in someone's head.

---

## Scene 3 — Ask anything, and check the answer (1:40–2:45)

**SCREEN:** Ask → paste *"Why does P-101A keep losing its mechanical seal?"* Let
it stream. **Click a citation chip** — hold on the opened source document for
three full seconds. Close.

> **NARRATION**
> The first job is the one everybody wants: ask the plant a question in plain
> language and get a real answer. This is retrieval over the whole corpus at
> once — work orders, procedures and incident reports that no single search box
> spans today.
> But the answer is not the interesting part. This is. Every claim carries a
> citation, and a citation is not a footnote — it opens the source. That is the
> actual standard operating procedure the answer relied on, retrieved from
> storage, exactly as it was filed. The system also reports its own confidence,
> based on how completely the answer traced back to evidence. If it cannot ground
> a statement in a document you own, it says so instead of sounding certain.
> No engineer signs off on an answer they cannot check, so we made every answer
> checkable.

---

## Scene 4 — The graph underneath (2:45–3:20)

**SCREEN:** Graph Explorer. One slow pan across the network. Hover a node or two
to surface labels. Do not click repeatedly.

> **NARRATION**
> Underneath is why this answers questions a search engine cannot. Documents were
> not just indexed — they were read, and the things inside them extracted as
> entities: equipment tags, failure modes, procedures, work orders, regulatory
> clauses and the people involved. Then they were linked. This pump is connected
> to that vessel, governed by that standard, repaired under that procedure,
> mentioned in those four documents. When a question needs a connection that
> spans three documents and two decades, it is already here, waiting.

---

## Scene 5 — Failure intelligence, unprompted (3:20–4:20)

**SCREEN:** Alerts. Open the **P-101A seal-leak** alert. Scroll slowly so the three
sections and the numbered first-checks list are all shown. Hover the source chips.

> **NARRATION**
> Nobody asked for this one. When new failure data lands, an agent investigates on
> its own — the asset's own history, its sibling equipment, the procedures that
> fixed it before, and everything it is physically connected to.
> Here it concluded that P one oh one A is not failing because of a defective
> seal. It is failing from suction starvation — the same signature its sibling
> pump shows — and a design review recommended a year ago was never actioned. It
> then lists the specific checks to make before that pump goes back into service.
> That conclusion required connecting four separate documents filed by four
> different people in four different systems. No individual had read all four.
> This is the lessons-learned problem the statement describes, solved
> continuously instead of during the post-incident review.

---

## Scene 6 — From a warning to scheduled work (4:20–5:05)

**SCREEN:** Click **A corrective work order was drafted from this** → Work Orders.
Point out the priority badge, then the harvested fact chips, then the grounded
banner. Click **Approve**, show the approved state.

> **NARRATION**
> A warning that stops at a warning is just noise, so the same investigation
> drafts the corrective work order. Look at how it is assembled. The affected
> equipment, the prior work orders and the procedures are lifted directly out of
> the graph — the model is not permitted to write into those lists. Only the two
> narrative paragraphs come from the model, and they are checked against the
> evidence before anyone sees them. The priority is calculated from recurrence
> and regulatory exposure, not chosen by an AI.
> And nothing here is automatic. It stays a draft until a planner approves it,
> because committing a technician's shift is a person's decision, not a model's.

---

## Scene 7 — Compliance you can prove (5:05–5:50)

**SCREEN:** Compliance. Let the counts land. Expand an **overdue** item → **View
evidence** (document opens) → close → **Schedule inspection**. Then flick to Work
Orders to show the new preventive draft.

> **NARRATION**
> Regulatory obligations come out of the same graph. Seven statutory inspections
> currently overdue, against real standards — O I S D and pressure-vessel codes —
> mapped onto the specific assets they govern. View evidence opens the document
> the obligation was read from, which is exactly what an auditor asks for.
> Scheduling one does not quietly book anything. It drafts a preventive work
> order into the same approval queue as everything else, because compliance does
> not get a side door into the maintenance schedule.

---

## Scene 8 — Before you change anything (5:50–6:25)

**SCREEN:** Change Impact. Use the **V-203** example. Let the evidence steps tick
through live, then the assessment.

> **NARRATION**
> Before a modification is made, you can ask what it touches. Watch the left
> side — that is the agent walking the plant's real topology, one query at a time:
> connections, failure history, governing clauses, and every document that would
> need revising. What comes back is not a verdict on whether to proceed. It is the
> evidence a competent person needs in order to decide, assembled in seconds
> instead of over a fortnight.

---

## Scene 9 — Catching the knowledge before it walks out (6:25–7:15)

**SCREEN:** Interview. Start a session, ask one or two questions, show the live
transcript. Then show the generated handover document with its structure.

> **NARRATION**
> Which leaves the hardest part of the statement — the quarter of India's
> experienced engineers retiring within the decade.
> You cannot solve that by asking someone to write documentation. So the system
> interviews them. It reads the graph first, so it already knows which assets this
> person worked on and what has historically failed on them, and it asks about
> those specifically — the judgement that never reached a document. Why this pump
> gets a different seal. What the vibration actually means before the alarm.
> What comes out is a structured handover document, and it goes straight back
> through the same ingestion pipeline as any drawing or work order. So the moment
> the conversation ends, that knowledge is answerable in Ask, citable in an
> assessment, and available to whoever replaces them.
> Thirty-five percent of the working week, seven to twelve disconnected systems,
> and a retirement cliff — one graph, one brain, every answer traceable to the
> document it came from. That is PlantForge.

---

## If you need a shorter cut

Drop **Scene 8 (Change Impact)** first, then **Scene 4 (Graph)** — that lands
around 5:30 and keeps the problem statement, the citations, the failure
intelligence, compliance and the retirement cliff.

Do **not** drop Scene 3's citation click or Scene 9. Those are the two moments
that separate this from a chatbot over a document folder.

## Lines worth protecting

- *"A safety problem, a compliance problem and a reliability problem wearing a filing cabinet as a disguise."*
- *"A citation is not a footnote — it opens the source."*
- *"No individual had read all four."*
- *"The model is not permitted to write into those lists."*
- *"You cannot solve that by asking someone to write documentation. So the system interviews them."*
