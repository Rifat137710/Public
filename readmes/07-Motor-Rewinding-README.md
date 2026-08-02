# Rewinding of a Single-Phase Induction Motor

**Course:** EEE 206 — Energy Conversion Laboratory (January 2023)
**Institution:** Department of EEE, Bangladesh University of Engineering and Technology (BUET)
**Section:** C1 | **Group:** 02
**Full report:** [`EEE206_Project_Report_Group_02.pdf`](EEE206_Project_Report_Group_02.pdf)

---

## What this project does

- **Stripped, rewound by hand, rebuilt and then experimentally characterised a 550 W
  capacitor-start, 4-pole squirrel-cage single-phase induction motor** — the kind found in fans,
  pumps, washing machines and small workshop machinery across Bangladesh, where rewinding an old
  motor costs far less than replacing it and keeps a working machine out of the waste stream.
- **Recorded the original design before destroying it.** Turns per coil were counted for both main
  and auxiliary windings during teardown, and the slot-by-slot layout was documented so the
  winding diagram could be reconstructed — this is the data the entire rebuild depends on.
- **Derived the winding design from the slot count:** 24 stator slots and 4 poles give 12 total
  coils — 8 main (2 per pole) and 4 auxiliary (1 per pole) — with a 6-slot coil span and a 3-slot
  phase difference between main and auxiliary windings.
- **Rewound and reassembled end to end** — cut and inserted slot insulation, wound new SWG 24
  copper coils to the recorded turn counts, reinserted them, added a second insulation layer,
  separated and spaced the coil extensions, bound each coil with thread, soldered the terminals,
  varnished the internals for moisture protection, and reassembled rotor and casing.
- **Improvised around missing tools.** With no commercial forma available, coils were wound on
  **nails driven into wooden boards** sized from the original windings — the single biggest
  constraint on winding consistency. A coil insertion tool, proper wire cutter, balancing
  equipment and insulation testers were also unavailable.
- **Result — the rebuilt motor was fully characterised.** Direct multimeter measurement gave main
  winding resistance **R₁ = 21.0 Ω**. A no-load test (220 V, 160 W, 2.6 A) and a locked-rotor test
  (60 V, 125 W, 3.1 A) yielded the complete equivalent circuit:
  **R₁ = 21.0 Ω · R₂ = 10.67 Ω · X₁ = X₂ = 7.17 Ω · X_M = 140.98 Ω.**
- **Result — starting current computed at 11.37 A,** scaled from the locked-rotor test to rated
  voltage.
- **Result — torque-speed characteristic plotted** from the derived parameters. It covers the main
  winding only and therefore shows **no starting torque**, consistent with double-revolving-field
  theory — which is exactly why the capacitor-start auxiliary winding and centrifugal switch are
  necessary.
- **Result — a known source of error, stated openly.** R₂ was derived from the no-load relation
  rather than the locked-rotor `R₁+R₂`, because the auxiliary winding remained connected during
  the locked-rotor test when it should ideally have been open.
- **Result — rewound slightly heavier than original** at identical wire gauge: main winding
  91 → 95 turns, auxiliary 81 → 85, copper weight 405 g → 420 g. Total project cost ৳5,805,
  against a used motor priced at ৳3,500.

## The motor

From the nameplate (type **JY7124**):

| Parameter | Value |
| --- | --- |
| Power | 550 W |
| Voltage | 220 V |
| Current | 3.1 A |
| Frequency | 50 Hz |
| Full-load speed | 1400 RPM |
| Poles | 4 |
| Phase | Single |
| Insulation class | E (120 °C max temperature rise) |

## Winding design

With **24 stator slots** and 4 poles, each slot holding one coil arm:

```
Total coils          = 24 / 2 = 12
Main (running) coils = 12 × 2/3 = 8      → 2 per pole
Auxiliary (starting) = 12 − 8  = 4      → 1 per pole
Coil span            = 24 / 4 = 6
Phase difference     = (90/180) × 6 = 3 slots
```

The full slot-by-slot layout — concentric small/large main coil pairs at 5-8, 4-9, 11-14, 10-15,
17-20, 16-21, 2-23, 3-22 with alternating current direction, and auxiliary coils at 1-6, 7-12,
13-18, 19-24 — is tabulated in the report alongside the winding diagram, which the team
reconstructed by recording the original layout during teardown.

## Process

**Disassembly** — clean the work surface, remove the outer housing, cut the old windings free
with scissors and pliers (**counting turns per coil first** — this is the data the rebuild
depends on), extract the coils, and pull the old slot insulation without damaging the slots.

**Rewinding** — cut insulation paper to slot width and insert it, wind new coils to the recorded
turn counts, reinsert them into the slots, add a second insulation layer over each winding,
separate and space the coil extensions, insert insulation between main and auxiliary windings,
bind each coil with thread, solder the terminals, and bring out the supply leads.

**Finishing** — varnish the internals for moisture protection, reassemble rotor and casing, then
spray-repaint the housing with the internals masked off.

### Wire data — before vs after

| Parameter | Original | New |
| --- | --- | --- |
| Wire type | Copper | Copper |
| SWG | 24 | 24 |
| Weight | 405 g | 420 g |
| Main winding turns | 91 / 100 | 95 / 100 |
| Auxiliary winding turns | 81 | 85 |
| Max current | 3.5 A | 3.5 A |
| Diameter | 0.0201 in | 0.0201 in |
| Resistance per 1000 ft | 25.67 Ω | 25.67 Ω |

## Testing & equivalent circuit

Main winding resistance measured directly with a multimeter: **R₁ = 21.0 Ω**.

| No-load test | | Locked-rotor test | |
| --- | --- | --- | --- |
| V_nl | 220 V | V_LR | 60 V |
| W_nl | 160 W | W_LR | 125 W |
| I_nl | 2.6 A | I_LR | 3.1 A |
| \|Z_nl\| | 84.62 Ω | \|Z_LR\| | 19.35 Ω |
| cos θ | 0.2797 | cos θ | 0.672 |

Working through `|Z_nl|cos θ = R₁ + R₂/4` and `|Z_LR|sin θ = X₁ + X₂` (assuming X₁ = X₂):

**R₁ = 21.0 Ω · R₂ = 10.67 Ω · X₁ = X₂ = 7.17 Ω · X_M = 140.98 Ω**

Starting current, scaled from the locked-rotor test: **I_start = 11.37 A**

R₂ was derived from the *no-load* relation rather than the locked-rotor `R₁+R₂`, because the
auxiliary winding stayed connected during the locked-rotor test — the team flags this as a known
source of error, since the test should ideally be run with that winding open.

The torque-speed characteristic plotted from these parameters covers the **main winding only**,
so it shows **no starting torque** — consistent with double-revolving-field theory, which is why
a single-phase induction motor isn't self-starting and needs the capacitor-start auxiliary
winding plus a centrifugal switch (which disconnects at 75–80% of synchronous speed).

## Tool limitations

The team worked without several standard tools, and improvised:

- **No commercial forma** — coils were wound on **nails driven into wooden boards**, sized from
  the original windings. This was the single biggest constraint on winding consistency.
- **No coil insertion tool** — reinserting high-turn-count coils by hand was slow and difficult.
- Also missing: a proper wire cutter, balancing equipment, and insulation testers/ohmmeters for
  verification. A hammer was used for rotor bar work, which risks damaging the core.

## Cost

| Item | ৳ |
| --- | --- |
| Single-phase induction motor (used) | 3,500 |
| Wire, insulation, varnish | 1,275 |
| Professional assistance | 800 |
| Paint | 100 |
| Other | 130 |
| **Total** | **5,805** |

Sourcing a structurally sound used motor needing only a rewind was the main cost-saving decision;
prices were cross-checked against manufacturer sites and local market rates before purchase.

## Why it matters

In a country where generation capacity is constrained and largely fossil-fuelled, a poorly wound
motor wastes energy every hour it runs — and single-phase motors are everywhere, from
agriculture and small manufacturing to household appliances. Rewinding well extends motor life,
conserves the raw materials a replacement would consume, and cuts electronic waste. The report is
candid about the other side: insulation materials can contain hazardous substances requiring
careful handling and disposal, the process itself consumes energy, and it generates waste that
needs managing.

## Future work

Changing the pole number to retune performance for specific applications; more efficient winding
configurations and materials; experimenting with alternative rotor types (wound, hysteresis);
and better speed regulation and starting behaviour through VFDs or soft starters.

## Team

Md. Rifat Rahman (2006137) · Samia Hossain (2006138) · Sami Hasib Khan (2006139) ·
Alif Mahmud (2006140) · Asikul Islam Asik (2006141) · Rajin Abdullah Zeeshan (2006142)

All six members took part in insulation, coil making, coil insertion, connections, reassembly,
and testing, with individual leads on purchasing, disassembly, varnishing, and painting — the
per-member breakdown is in §6 of the report.

**Course instructors:** Ashikur Rahman Jowel (Lecturer), Shafin Bin Hamid (Lecturer)
