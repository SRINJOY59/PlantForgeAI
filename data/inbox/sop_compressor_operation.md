# SOP-U100-12 Rev 2: Vapour Compressor K-301 - Normal Operation

**Unit:** 100 (Feed Section)
**Applies to:** K-301 (single-stage screw compressor with water-cooled intercooler)
**Revision note:** Rev 2 (May 2026) adds the 135 C discharge pre-alarm response
step following incident IR-2026-014.
**Reference:** OEM manual GD-CM-2210, OISD-STD-179

## 1. Pre-start checks

1. Confirm lube oil level in sight glass between MIN and MAX.
2. Cooling water lined up to the intercooler; return line sight flow visible.
3. Verify intercooler cooling water strainer differential is below 0.3 bar.
   The strainer is on the quarterly PM plan - do not skip this check.
4. Suction from V-203 open; anti-surge recycle valve in AUTO.

## 2. Start sequence

1. Start via DCS; observe discharge pressure rise within 30 seconds.
2. Check discharge temperature on TI-302 stabilises below 118 C at
   normal load.
3. Confirm no abnormal noise at either bearing housing.

## 3. Running checks (per shift)

1. Log TI-302 discharge temperature. Investigate any reading above 125 C.
2. At the 135 C pre-alarm: reduce load, verify cooling water flow, and
   inspect the intercooler strainer. Do not wait for the 142 C trip.
3. Record vibration at NDE bearing weekly; alert limit 4.5 mm/s RMS.

## 4. Shutdown

1. Unload compressor and allow 5 minutes cooldown at minimum load.
2. Stop via DCS; confirm anti-surge valve opens fully.
3. If shutdown exceeds 48 hours, isolate cooling water and drain the
   intercooler shell side.

## 5. Records

Log TI-302 readings, strainer differential, and any pre-alarm events in the
shift log and reference them in work orders raised on K-301.
