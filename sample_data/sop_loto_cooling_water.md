---
title: SOP — Lockout/Tagout for Cooling Water Pumps P-101A/B
doc_type: safety_procedure
document_no: SOP-SAF-014 Rev 3
owner: Plant Safety Department
review_due: 2026-09-30
---

# Standard Operating Procedure: Lockout/Tagout (LOTO) for Cooling Water Circulation Pumps

## 1. Purpose and Scope
This procedure defines the energy isolation (lockout/tagout) steps required before any
maintenance, mechanical seal replacement, or bearing work on cooling water circulation
pumps P-101A and P-101B. It applies to all maintenance technicians and contractors.

## 2. Hazards
- Stored electrical energy in the 75 kW motor circuit.
- Rotating equipment start-up via auto-start interlock I-CW-07 (standby pump can start automatically).
- Residual cooling water pressure on lines CW-6-101 and CW-8-110 up to discharge pressure (PT-2305).
- Hot surfaces near HX-12.

## 3. Required PPE
Safety helmet, safety shoes, chemical-resistant gloves, and face shield when breaking
flanges. A valid Permit to Work must be raised before starting.

## 4. Isolation Procedure
1. Notify the panel operator and obtain a Permit to Work referencing the pump tag.
2. Stop the pump locally and confirm zero flow on FT-2301.
3. **Defeat the auto-start interlock I-CW-07** at the DCS before isolating, so the standby
   pump P-101B cannot start automatically while you work on P-101A.
4. Open the motor circuit breaker at MCC-1, apply a personal lock and danger tag.
5. Close suction valve on CW-6-101 and discharge valve on CW-8-110; lock both valves.
6. Open the casing drain to relieve residual pressure; verify pressure on PT-2305 reads zero.
7. Attempt a start to verify de-energisation (try-out), then return the control to off.

## 5. Re-energisation
Reverse the isolation steps, remove all locks/tags personally, re-enable interlock I-CW-07,
and confirm with the panel operator before returning the pump to auto.

## 6. Records
Attach the completed permit and LOTO checklist to the work order in the CMMS.
