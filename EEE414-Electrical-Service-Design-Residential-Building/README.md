# Complete Electrical Service Design of a Multi-Storey Residential Building

**Course:** EEE 414 — Electrical Service Design (January 2026)
**Institution:** Department of EEE, Bangladesh University of Engineering and Technology (BUET)
**Section:** C1 | **Group:** 05
**Full report:** [`EEE414_Project_Report_Group_05.pdf`](EEE414_Project_Report_Group_05.pdf) — 50+ pages of AutoCAD layouts, schedules, and calculations.

---

## What this project does

A complete, code-compliant electrical services design for a residential apartment building —
from the number of bulbs in a bedroom all the way up to the substation transformer. Every layout
is drawn in **AutoCAD**; every rating is calculated against the **Bangladesh National Building
Code (BNBC) 2020**, **PWD** reference tables, and **NFPA 780**.

### Building specification

- 10 residential floors, plus a ground floor and a basement
- 4 flats per floor, **1,550 sq ft** each
- Roof: 60 ft × 80 ft (4,800 sq ft), building height ≈ 120 ft (36 m)

## Scope of the design

| Stage | What was produced |
| --- | --- |
| **Layouts** | Typical unit, ground floor, basement, rooftop floor plans |
| **Fittings & fixtures** | Lux-based light and fan counts per room, placed on plan with a full legend |
| **Conduit** | General, emergency, and power-switch conduit routing (through-ceiling / through-floor) for every level |
| **Switchboards** | SB and ESB schedules and diagrams for units, ground floor, passageways, basement, rooftop |
| **Distribution boards** | SDB / ESDB schedules with circuit breaker and wire ratings |
| **Main boards** | MDB and EMDB phase-balanced connection diagrams |
| **Heavy loads** | Lift and pump sizing, breakers, and cables |
| **Power plant** | Generator, transformer, and PFI plant ratings |
| **Protection** | Lightning protection system (risk assessment + rolling sphere design) |
| **Earthing** | Earth pit construction detail and HT/LT placement |
| **Substation** | Single-line substation layout with HT/LT switchgear and ATS |

## Method: how the numbers were derived

**Lighting** — number of luminaires per room from
`N_L = (E · L · W) / (F · UF · MF)`, with required lux `E` taken from BNBC 2020 Table 8.1.5
(bedroom 70, kitchen 200, dining 150, toilet/stair/lobby 100, dressing 250 …), luminous flux
`F = 2000 lm` at 20 W, maintenance factor `MF = 0.9`, and utilisation factor `UF` interpolated
from the room index against reflectance triplet 0.7/0.5/0.2 for residential spaces.

**Fans** — `N_F = L(ft) · W(ft) / 100`.

**Circuits** — single-phase current `I = P / (V · pf)` at 230 V and pf 0.9; three-phase
`I_L = P / (√3 · V_L · pf)` at 400 V. Breakers and cable cross-sections are then chosen one
standard step above the computed load.

## Headline results

| Item | Value |
| --- | --- |
| Typical-floor SDB (4 units) | 28,520 W → 79.11 A → 125 A TP MCCB |
| EMDB maximum phase current | 145.76 A → 200 A TP MCCB |
| MDB maximum phase current | 341.60 A → 400 A TP MCCB |
| Lift (2 × passenger, 13-person / 1000 kg @ 1.0 m/s) | 5.0 kW each, 20 A TP, fed from EMDB |
| Pump (duty/standby pair, ≈7.5 HP) | 5.5 kW, 8.8 A line, 20 A TP, fed from MDB |
| Generator | 111.75 kVA calculated → **150 kVA** standard |
| Transformer | 261.90 kVA calculated → **400 kVA** standard (13 m² in a 26.1 m² room) |
| PFI plant | 45.93 kVAR calculated → **60 kVAR** standard |

## Lightning protection

Risk assessment per BNBC indices (use of structure, construction type, contents, isolation,
terrain, height, lightning prevalence) totals **49** — above the threshold of 40, so an LPS is
**mandatory**.

Designed with the **rolling sphere method** at Class III (45 m radius), `d = 2√(2rh − h²)`, giving
≈24 ft 3 in spacing for 2 ft rods. Result: arrestors at 25 ft intervals — 4 along the 60 ft length
and 5 along the 80 ft width, **14 arrestors** in total around the roof perimeter, in 12 mm
tin-topped copper rod. **5 down conductors** (first per 80 m², rest per 100 m²) of 19 × 1.8 mm
stranded annealed copper, with earth termination resistance held **below 10 Ω**.

## Earthing & substation

Earth pits use a copper electrode in a GI pipe with alternating charcoal and salt layers to
improve soil conductivity, a copper busbar for distribution, a plastered brick wall, and an RCC
cover slab. **HT and LT pits are kept separate** — HT beside the HT switchgear, LT near the LT
meter board — to limit fault impact.

The substation runs HT supply → HT switchgear → transformer → LT switchgear → MDB, with a
generator tied in through an **Automatic Transfer Switch (ATS)** and an EMDB carrying critical
loads (lifts, emergency lighting, passageways) through an outage.

## Team

Raisa Nusrat (2006132) · Himel Saha (2006135) · Rifat Rahman (2006137) ·
Humayra Binte Monwar (2006159) · Mushfiqur Rahman (2006161) · Nafisa Anjum Promi (2006163)

Work was split across floorplans, fittings, conduit, SB/SDB/MDB diagrams, power calculations,
substation, earthing, and LPS — see the contribution matrix in §3.5 of the report.

**Course instructors:** Tanvir Hossain (Lecturer, EEE), Mohammad Zonayed Hossain (Part-Time Lecturer)

## References

Bangladesh National Building Code (BNBC) 2020 · Public Works Department (PWD) documents ·
NFPA 780 · course lecture material
