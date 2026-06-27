---
title: Operating Instruction — Cooling Water System Start-up and Shutdown
doc_type: operating_instruction
document_no: OI-OPS-022 Rev 2
---

# Cooling Water Circulation System — Start-up and Shutdown

## Normal Start-up
1. Confirm surge vessel V-201 level (LT-2201) is above 40%. If below the low-low trip of
   15%, line up cooling tower CT-01 make-up water and fill before starting.
2. Confirm the cooling tower CT-01 fans are available and the basin level is normal.
3. Open the heat exchanger HX-12 cooling water inlet and outlet valves.
4. Select P-101A as duty and P-101B as standby on the DCS. Verify interlock I-CW-07 is enabled.
5. Start P-101A. Confirm discharge pressure (PT-2305) rises to about 3.1 barg and flow
   (FT-2301) stabilises above 350 m3/h. Low flow below 180 m3/h will trip the pump.
6. Monitor bearing vibration (VT-2310); normal is below 4 mm/s. Alarm is 7.1 mm/s and trip 11 mm/s.
7. Confirm HX-12 outlet temperature (TT-2330) trends to the normal band of 30–34 °C.

## Normal Shutdown
1. Reduce process heat load on HX-12 first.
2. Stop the duty pump P-101A from the DCS; confirm the standby does not auto-start
   (place P-101B in manual if a full system shutdown is intended).
3. Close HX-12 cooling water valves once flow stops.
4. Maintain V-201 level for freeze/standby protection per site policy.

## Key Setpoints
- FT-2301 low-flow trip: 180 m3/h
- VT-2310 vibration alarm/trip: 7.1 / 11.0 mm/s
- LT-2201 low-low level trip: 15%
- Normal HX-12 outlet temperature: 30–34 °C
