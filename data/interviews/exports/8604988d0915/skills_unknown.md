# Skills & Knowledge Handover - Gandu

> First-person account by Gandu (n/a), Instrumentation Engineer,
> captured via PlantMind knowledge-capture interview on 2026-07-18.

## Role & Responsibilities
My day‑to‑day goes beyond what’s on the org chart. I’m the one who keeps track of which instruments are actually working and which aren’t – there’s no automated system for that. I also take it on myself to correct instrument memory when the manuals are wrong, because the real behaviour in the plant often doesn’t match what’s written. Managing equipment details properly is a core part of the job, and I believe the person replacing me must know AI properly and use it to manage databases for all our equipment. That’s the only way to stay on top of everything.

## Projects & Current Status
There are no unfinished projects or abandoned modifications that I’m handing over. However, I’ve been pushing for something that hasn’t been built yet: an efficient machinery – a system – that can store specific instrument details and give reminders to a new person. Think of it as a “memory for our plan” that makes it easy to retrieve what you need without digging through outdated manuals. That project hasn’t started, but it’s what I’d want the successor to champion.

## Equipment Know-How

### PSV-204
- **Symptoms to watch for:** Pressure handling issues that are not handled. The exact nature – whether it’s setpoint drift, chatter, or failure to reseat – wasn’t detailed, but the problem is known and unresolved.
- **Fixes that worked:** Manually correcting instrument memory when the manuals are incorrect. If the device’s internal parameters don’t match reality, I go in and fix the memory directly rather than waiting for a global manual update.
- **Fixes that failed:** None captured.
- **Tuning values:** None captured.

## Tribal Knowledge & Gotchas
- The actual operation of some instruments is different from what their manuals say. You’ll find misinformation in the documentation, and the only way to keep things running is to manually correct the instrument memory to match what’s really happening in the plant.
- Updating a manual globally is a painfully slow process: you have to edit the manual yourself, submit it to the authorities, and then wait for them to roll out the change across all plants. In the meantime, you’re stuck with wrong information.
- There’s no central list of which instruments are currently working or not. You have to build that picture in your head or from your own notes.

## Procedures & Workarounds
- **Instrument memory correction:** When you find a discrepancy between the manual and the field, don’t wait for the official update. Go into the instrument and correct its memory directly. As I told the interviewer, “I just had to correct that memory only.”
- **Proposed AI‑based database:** I recommend setting up a “memory for our plan” – a database that holds all the specific instrument details. Use AI to manage it, keep it updated, and set reminders for the successor. This bypasses the slow manual‑update cycle and gives you a single source of truth.

## Key Contacts & Handover Recommendations
- The successor must know AI properly and use it for managing equipment databases. That’s the single most important thing I want them to bring.
- Build that efficient machinery to track equipment details – store instrument‑specific data, flag discrepancies, and provide automatic reminders.
- Prioritise correcting manual misinformation by maintaining a local, plant‑specific memory. Don’t rely on the global manuals until they’ve been verified against what’s actually running.
- No specific vendor or service‑provider contacts were captured during this interview.

## Open Questions
- Unit 300 instrumentation criticality map: which instruments are truly critical and why?
- Vendor and service provider quirks: who to call, response times, reliability, and any unwritten agreements.
- Unfinished projects and abandoned modifications: are there any instrument upgrades that were started and never finished?
- Safety instrumented system (SIS) testing gotchas: specific test procedures, known bypasses, or failure modes.
- Loop tuning parameters held in my head: PID settings, control loop nuances that aren’t documented.
- Interlock and alarm rationalisation gaps: alarms that are frequently ignored, bypassed, or poorly set.
- Spare parts and obsolescence risks: which instruments are hard to source, lead times, and critical spares.
- Startup and shutdown instrument sequence nuances: step‑by‑step checks that aren’t written down.
- Calibration and range‑setting shortcuts: field tricks that save time but aren’t in the procedures.
- DCS and PLC configuration quirks: any non‑standard logic, hidden settings, or configuration traps.
- Detailed nature of PSV‑204 pressure handling issues: root cause, frequency, impact on operations, and any attempted fixes that failed.
- Specific examples of manual misinformation: which other instruments have discrepancies between the manual and actual behaviour?