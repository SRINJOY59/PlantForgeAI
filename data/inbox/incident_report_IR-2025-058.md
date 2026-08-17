# Incident Report IR-2025-058

**Date of incident:** 2025-09-13, 03:50 hrs
**Unit:** 200 (Vapour Processing)
**Classification:** Process upset - off-spec product for 6 hours
**Related work orders:** WO-3024, WO-3018

## What happened

During a night-shift rate increase, feed to Unit 200 was ramped roughly
25% in under five minutes. Liquid level in KO drum V-210 surged and the
demister could not disengage the carried liquid. Solvent-contaminated
condensate carried over into absorber C-220, initiating foaming. Column
differential pressure rose from 140 to 240 mbar in twenty minutes and
absorption efficiency collapsed. Product went off-spec until rates were
cut and antifoam dosing took effect.

## Timeline

| Time  | Event |
|-------|-------|
| 03:45 | Rate increase started (~25% in <5 min) |
| 03:50 | LT-212 level spike on V-210; carryover begins |
| 04:10 | C-220 DP alarm at 200 mbar |
| 04:25 | Rates cut 30%; antifoam dosing started |
| 09:40 | Product back on spec |

## Root cause

Rate of feed increase far exceeded the 10%-per-15-minutes limit later
codified in SOP-U200-03. The V-210 demister was likely already weakened
by repeated fast ramps (confirmed damaged at the next entry, WO-3052).

## Actions

| # | Action | Owner | Due |
|---|--------|-------|-----|
| 1 | Codify ramp-rate limit in SOP-U200-03 | Operations | 2025-10-31 |
| 2 | Inspect V-210 demister at next opportunity | Maintenance | done (WO-3052) |
| 3 | Add C-220 DP pre-alarm at 180 mbar | Instrumentation | 2025-12-15 |
