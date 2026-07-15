# Incident Report IR-2026-007

**Date of incident:** 2025-11-27, 14:05 hrs
**Unit:** 200 (Vapour Processing)
**Classification:** Equipment damage near-miss - loss of standby capability
**Related work order:** WO-3039

## What happened

During a routine changeover from P-201A to P-201B, the outside operator
was called away after starting P-201B but before opening its discharge
valve. The pump ran dead-headed for approximately four minutes until the
motor tripped on thermal overload. Solvent circulation was maintained on
P-201A throughout; no process impact. Had P-201A also been unavailable,
solvent flow to C-220 would have been lost within minutes.

## Root cause

The changeover procedure did not carry a time limit for the dead-head
condition, and the task was interrupted by a radio call treated as more
urgent. Packing-gland friction heat in a dead-headed pump rises far
faster than operators generally assume.

## Contributing factors

1. Single-operator changeover with no second check.
2. No local trip on high casing temperature for P-201A/B.

## Actions

| # | Action | Owner | Due |
|---|--------|-------|-----|
| 1 | Add 60-second dead-head limit to SOP-U200-07 | Operations | done (Rev 2) |
| 2 | Motor inspection and megger test P-201B | Maintenance | done (WO-3039) |
| 3 | Evaluate casing temperature trips for P-201A/B | Process engineering | 2026-03-31 |
