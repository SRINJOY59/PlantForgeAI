# PlantForge.ai — demo script

**Runtime:** ~4:20 · **Narration:** ~650 words at a calm 150 wpm

Record the screen **silent**, generate the voice-over from the NARRATION blocks,
then lay the video under the audio. Cutting video to fit audio is far easier
than the reverse.

---

## Pre-flight

Do these before you hit record — each one is visible on camera if you skip it.

- [ ] **Regenerate the alerts.** The ones on the stream now were written under
      the old prompt: they open with a stray `---` and claim *"the SAP work
      order has been drafted"*, which is false. New investigations produce the
      three-section format ending in a numbered checklist. Clear
      `agents:alerted` and re-trigger so the feed shows the good format.
- [ ] **Decide the standards story.** The watcher is correctly silent — it has
      recorded its baselines, and real standards move a few times a decade. You
      cannot make one fire on cue unless a baseline is tampered first.
- [ ] **Browser at 1920×1080, 100% zoom**, bookmarks bar hidden, one tab.
- [ ] **Log in as an engineer** — operator hides half the nav.
- [ ] **Pre-warm every page once.** First load of Graph Explorer is ~850 ms and
      the answer cache is cold; clicking through once beforehand makes the
      recording feel instant.
- [ ] **Have the Ask question typed and ready** to paste, not typed live.

### For the voice tool

- Feed it the NARRATION text only — no markdown, no headings, no brackets.
- Equipment tags read badly as literals. Write them phonetically in the input:
  `P-101A` → "P one oh one A", `K-301` → "K three oh one",
  `API-510` → "A P I five ten", `PM02` → "P M oh two".
- Put a full stop before every pause you want. TTS ignores line breaks.

---

## Scene 1 — The problem (0:00–0:25)

**SCREEN:** Landing page. Slow scroll to the stats band, then click **Launch**
into the Dashboard. Let the role badge and the KPI row settle.

> **NARRATION**
> A process plant knows almost everything about itself. The problem is that the
> knowledge is scattered across work orders, P and I Ds, inspection records,
> vendor manuals and twenty years of email. So the same pump fails the same way
> for the fourth time, and nobody connects it, because no single person has read
> all four documents. PlantForge reads them all, and keeps the connections.

---

## Scene 2 — Ask, with citations (0:25–1:15)

**SCREEN:** Ask. Paste: *"Why does P-101A keep losing its mechanical seal?"*
Let the answer stream. **Then click a citation chip** and let the document
modal open on the real SOP. Pause two seconds on it. Close.

> **NARRATION**
> Ask it a question and you get an answer built from the plant's own documents.
> Every claim carries a citation, and a citation is not a footnote — it opens
> the source. This is the actual standard operating procedure, pulled from
> storage, at the page the answer leaned on. If the system cannot ground a
> statement in a document you own, it says so rather than sounding confident.
> That distinction is the whole product. An engineer will not act on an answer
> they cannot check.

---

## Scene 3 — It warns you first (1:15–2:05)

**SCREEN:** Alerts. Land on the **P-101A seal-leak** alert. Scroll slowly
through the three sections so the numbered first-checks list is on screen.
Hover the source chips.

> **NARRATION**
> Nobody asked for this one. When a new failure lands in the graph, an agent
> investigates on its own — the equipment's history, its sibling equipment, the
> procedures that fixed it before, and what it is connected to. Here it found
> that P one oh one A is not failing because of a bad seal. It is failing
> because of suction starvation, the same signature its sibling pump shows, and
> a design review recommended a year ago was never actioned. That is a
> connection across four separate documents that no one person had made.

---

## Scene 4 — From warning to action (2:05–2:50)

**SCREEN:** Click **A corrective work order was drafted from this** on the alert
card → Work Orders tab. Point at the priority badge, then the fact chips
(affected equipment, prior work orders, procedures), then the grounded banner.
Click **Approve**. Show the approved state.

> **NARRATION**
> A warning that stops at a warning is just noise, so the same investigation
> drafts the corrective work order. Look at how it is built. The equipment, the
> prior work orders and the procedures are lifted straight out of the graph —
> the model cannot invent into those lists. Only the two written paragraphs come
> from the model, and they are checked against the evidence before you see them.
> The priority is a rule, not an opinion. And nothing here is automatic. It sits
> as a draft until a planner approves it, because committing a technician's
> shift is a person's decision.

---

## Scene 5 — Compliance you can prove (2:50–3:30)

**SCREEN:** Compliance. Let the counts land. Expand an **overdue** item →
**View evidence** (document opens) → close → **Schedule inspection**. Show the
confirmation, then flick back to Work Orders to show the new PM02 draft.

> **NARRATION**
> Statutory obligations come from the same graph. Seven inspections overdue,
> against real standards, on real assets. View evidence opens the document the
> obligation was read from. And scheduling one does not quietly book anything —
> it drafts a preventive work order that lands in the same approval queue as
> everything else. Compliance does not get a side door into the maintenance
> schedule.

---

## Scene 6 — Change impact (3:30–4:05)

**SCREEN:** Change Impact. Use the **V-203** example. Let the evidence steps
tick through live — that streaming is the point. Then the assessment.

> **NARRATION**
> And before a change is made, you can ask what it touches. Watch the left side:
> that is the agent walking the plant's real topology, one query at a time —
> connections, failure history, governing clauses, and every document that would
> have to be revised. What comes back is not an opinion on whether to proceed.
> It is the evidence a competent person needs in order to decide.

---

## Scene 7 — Close (4:05–4:20)

**SCREEN:** Back to Dashboard. Hold still.

> **NARRATION**
> No verdicts. No auto-approvals. Every answer traced to a document, every fact
> harvested rather than asserted, and a human signature on anything that touches
> live plant. That is PlantForge.

---

## If you need a longer cut

Drop these in after Scene 6, 30–40 seconds each:

- **Permits** — draft a permit to work; isolation points and hazards come off
  the graph, not a template.
- **Interview** — capture a retiring engineer's knowledge into the graph. The
  strongest story in the product if the audience is asset-management.
- **Graph Explorer** — one slow pan. Visually impressive, but the heaviest page;
  do not click around on camera.
- **Documents** — drag a file in and show it entering the pipeline.

## Lines worth keeping if you cut for time

- *"No single person has read all four documents."*
- *"A citation is not a footnote — it opens the source."*
- *"The model cannot invent into those lists."*
- *"It sits as a draft until a planner approves it."*
