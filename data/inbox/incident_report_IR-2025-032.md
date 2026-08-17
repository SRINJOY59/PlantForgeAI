# Incident Report IR-2025-032

**Date of incident:** 2025-05-29, 21:05 hrs
**Unit:** 100 (Feed Section)
**Classification:** Near miss - no loss of containment, production upset only
**Related work order:** WO-2140

## What happened

During truck unloading into feed tank T-101, the level transmitter LT-104
stuck at 62% while actual level continued rising. The high level alarm came
in late and erratic. The outside operator, cross-checking against the field
gauge glass, stopped unloading manually at an actual level of 88%,
preventing an overfill. Feed pumps P-101A and P-101B were unaffected.

## Timeline

| Time  | Event |
|-------|-------|
| 20:40 | Truck unloading into T-101 started |
| 20:55 | Panel level indication frozen at 62% (not identified at the time) |
| 21:02 | Spurious high level alarm, cleared itself |
| 21:05 | Field operator stops unloading on gauge glass reading 88% |
| 21:30 | LT-104 stub found partially blocked; flushed and reading restored |

## Root cause

Sediment blockage of the LT-104 instrument stub. The stub had no flushing
routine and the transmitter had drifted earlier the same year (WO-2111)
without the stub being inspected.

## Contributing factors

1. No preventive flushing schedule for level instrument stubs on T-101.
2. High level alarm and transmitter share the same stub - no independent
   high level protection on the tank.

## Actions

| # | Action | Owner | Due |
|---|--------|-------|-----|
| 1 | Add LT-104 stub flushing to quarterly PM | Maintenance planning | 2025-07-15 |
| 2 | Evaluate independent high level switch for T-101 | Process engineering | 2025-09-30 |
| 3 | Include gauge glass cross-check in unloading procedure | Operations | 2025-06-30 |
