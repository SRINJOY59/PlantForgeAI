# Incident Report IR-2026-014

**Date of incident:** 2026-03-03, 14:22 hrs
**Unit:** 100 (Feed Section)
**Classification:** Near miss — loss of containment prevented by relief system
**Related work orders:** WO-2245, WO-2251

## What happened

Compressor K-301 tripped on high discharge temperature at 14:22. Loss of
compression caused vapour to back up into separator V-203. Pressure in V-203
rose from 6.2 barg to 9.8 barg over roughly four minutes. Relief valve PSV-204
(set pressure 10.0 barg) lifted at 14:26 and discharged to flare for about
90 seconds. Operators closed the feed from E-204 and pressure normalised by
14:35. No injuries, no release to atmosphere.

## Timeline

| Time  | Event |
|-------|-------|
| 14:22 | K-301 trip, high discharge temperature (142 C against 130 C trip point) |
| 14:24 | High pressure alarm V-203 |
| 14:26 | PSV-204 lifts, flare header active |
| 14:28 | Panel operator closes E-204 outlet, field operator confirms |
| 14:35 | V-203 pressure normal, unit stabilised |

## Root cause

Cooling water flow to the K-301 intercooler had degraded over several weeks
(fouled strainer). Rising discharge temperature was visible in the trend for
at least ten days before the trip but no alarm was configured between the
normal operating point and the trip point. The vibration work in WO-2226
(December) was unrelated.

## Contributing factors

1. No intermediate high-temperature alarm on K-301 discharge.
2. Cooling water strainer not on any preventive maintenance schedule.
3. Trend review not part of daily operator round checklist.

## Actions

| # | Action | Owner | Due |
|---|--------|-------|-----|
| 1 | Add K-301 discharge high-temp pre-alarm at 135 C | Instrumentation | 2026-04-15 |
| 2 | Add intercooler CW strainer to quarterly PM plan | Maintenance planning | 2026-04-30 |
| 3 | Bench test and recertify PSV-204 before reinstallation (WO-2251) | Workshop | 2026-03-20 |
| 4 | Review V-203 relief load case against current K-301 operating envelope | Process engineering | 2026-05-31 |
