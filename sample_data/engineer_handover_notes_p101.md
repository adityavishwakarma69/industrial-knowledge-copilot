---
title: Engineer Handover Notes — Cooling Water Pumps (tribal knowledge)
doc_type: project_file
author: V. Subramanian (Senior Rotating Equipment Engineer, retiring 2026)
---

# Handover Notes: What You Need to Know About P-101A / P-101B

These are the things that are not written in any manual but matter on the floor. Capturing
them before I retire.

## P-101A nuisance trips
Nine times out of ten, when P-101A "trips for no reason" it is actually the surge vessel
V-201 level dropping because the cooling tower make-up valve sticks. People chase the pump
and replace bearings when the real fix is the make-up valve. Always check LT-2201 trend first.

## The real bearing problem
P-101A had three bearing failures in one year. We finally found it was softfoot on the
baseplate, not the bearings. If vibration VT-2310 keeps coming back after a bearing change,
check baseplate softfoot and coupling alignment before you do anything else. Shim it properly.

## Mechanical seal life
The single mechanical seal on these pumps lasts about 12–15 months on cooling water. Don't
wait for it to leak during monsoon — plan the seal change in the dry season. Seal plan 11
flush line blocks with scale; flush it every seal change.

## Auto-start gotcha
I-CW-07 will auto-start P-101B the moment P-101A trips. Before any work on P-101A you MUST
defeat I-CW-07 at the DCS or the standby will start while your hands are in the coupling.
This has nearly caused an incident twice.

## Spare parts
Keep one mechanical seal cartridge and one set of DE/NDE bearings in stores at all times.
Lead time on the seal is 8 weeks. Do not let stock go to zero.
