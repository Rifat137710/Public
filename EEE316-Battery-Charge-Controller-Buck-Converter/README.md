# Battery Charge Controller using a Buck Converter with Auto Cut-off

**Course:** EEE 316 — Power Electronics Laboratory (July 2024)
**Institution:** Department of EEE, Bangladesh University of Engineering and Technology (BUET)
**Section:** C1 | **Group:** 01
**Full report:** [`EEE316_Project_Report_Group_01.pdf`](EEE316_Project_Report_Group_01.pdf)
**Demo videos:** [Buck converter duty-cycle sweep](https://youtu.be/zVfVKqOWoK8) · [Full charger demonstration](https://youtu.be/7cjuLewZ8k8)

---

## What this project does

A mains-powered battery charger with a **variable DC output** and an **automatic cut-off** that
stops charging the moment the battery is full. Because the output voltage is adjustable, one
charger handles many battery chemistries — Li-ion, LiPo, lead-acid — instead of needing a
separate fixed-voltage charger per device.

Two problems it solves at once:

- **Fixed-voltage chargers** only fit one battery type, so users end up owning several.
- **Manual chargers** need someone watching the process; overcharging degrades capacity and can
  be a safety hazard.

## Power stage

The signal path from wall socket to battery:

```
230 V AC → step-down transformer → bridge rectifier → LC filter → buck converter → relay → battery
                                                          ↑
                                       SG3524 PWM (duty cycle set by potentiometer)
```

| Stage | Implementation | Notes |
| --- | --- | --- |
| **Transformer** | 220 V / 12 V centre-tapped, 3000 mA | Turns ratio 18.33 |
| **Rectifier** | Bridge diode, full-wave uncontrolled | Converts AC to pulsating DC |
| **Filter** | 100 mH series inductor + 1000 µF shunt capacitor | Strips high-frequency ripple |
| **Switch** | IRF250N MOSFET | Gate driven between gate and source |
| **PWM generator** | SG3524 IC | Frequency set by R<sub>T</sub> and C<sub>T</sub>; duty cycle trimmed by potentiometer |
| **Output** | Buck converter | V<sub>o</sub> = k · V<sub>in</sub>, where k is the duty cycle |

Stepping the voltage down with a **switching converter rather than a linear regulator** is the
efficiency decision at the heart of the design — a linear regulator burns the excess as heat.

## Auto cut-off

An Arduino continuously compares a reference voltage against the battery voltage and drives a
relay through a MOSFET:

- The **relay coil** is fed from the rectifier output and grounded through the MOSFET.
- With the MOSFET **on**, the SPDT pole moves from NO to NC and charging begins.
- **NC** connects to the battery's positive terminal through a **series diode** (blocks reverse
  current back out of the battery) and a **series power resistor** (limits short-circuit current).
- **NO** connects to a green indicator meaning "not charging".

The firmware averages **5 successive ADC readings** of both the reference (A0) and the battery
(A1) to reject noise, then works with their ratio `r = reference / battery`:

| State | Threshold | Behaviour |
| --- | --- | --- |
| Currently charging | `r_th = 1.55` | Keeps charging while `1.55 ≤ r ≤ 4.33` |
| Currently cut off | `r_th = 2.40` | Stays off until the ratio rises past 2.40 |

The two different thresholds create **hysteresis** — the trip point for stopping differs from the
point for restarting, so a battery hovering near full doesn't chatter the relay on and off. The
upper bound of 4.33 guards against a disconnected or shorted battery. Full source is in §3.5 of
the report.

## Protection features

- **Over-voltage** — regulated buck output prevents spikes reaching the battery
- **Over-current** — series power resistor limits short-circuit current
- **Reverse polarity / back-feed** — series diode blocks current flowing back out of the battery
- **Overcharge** — the auto cut-off itself
- **Status indication** — LM3914-driven battery level indicator plus red/green LEDs

## Results

The buck converter was verified on an oscilloscope at **25%, 50%, and 90% duty cycle**, confirming
the output tracks `V_o = k · V_in` across the range. The cut-off was validated by charging to full
and observing the process halt, with the post-cutoff battery voltage recorded. Power measurements
showed the switching design wasted markedly less energy — and generated less heat — than a linear
regulator equivalent.

## Bill of materials

| Component | Qty | Cost (৳) |
| --- | --- | --- |
| 240/12 V transformer | 1 | 170 |
| Capacitors (1000 µF, 100 µF) | 8 | 50 |
| Resistors | 25 | 25 |
| IRF250N MOSFET | 2 | 200 |
| 10 kΩ potentiometer | 3 | 45 |
| Relay | 2 | 50 |
| Li-ion 18650 battery | 3 | 210 |
| LED | 10 | 10 |
| LM3914 (level indicator) | 2 | 100 |
| Jumper wires | — | 250 |
| **Total** | | **1,110** |

## Usage

1. Connect the power supply to all circuits.
2. Put the charger into charging mode — a **red LED** confirms the state.
3. Set the buck converter output to match your battery, using the potentiometer. It must be set
   **above** the battery's present voltage for current to flow.
4. Connect the battery to the buck converter output.

## Limitations

The report is candid about what constrained the build: specialised components were hard to source
locally and added lead time; buck converter design is non-trivial for anyone new to power
electronics; and the lab lacked high-precision oscilloscopes and power analysers for a fuller
performance characterisation. Notably, **the transformer stage could not be shown during the final
demonstration** due to lab facility limits. Safety certification, a multilingual interface, and
deeper cost reduction were all out of reach at project scale.

## Future work

**Solar panel** input to make the charger self-sufficient and greener; **smart cut-off** that
detects the connected battery and sets its own threshold instead of using fixed constants;
**dual cut-off** that also disconnects the battery from the load at a preset depth of discharge,
protecting against over-discharge as well as overcharge; and **fast charging** via higher input
current.

## Team

Sadia Oishi (2006152) — software and hardware implementation, debugging ·
Meherab Hossain Bappy (2006154) — hardware implementation, lab testing ·
Chowdhury Blossom Ibn Razzaque (2006156) — lab testing, debugging ·
Nabanita Sarker (2006162) — software and hardware implementation, debugging ·
Rifat Rahman (2006137) — materials collection

Work was split three ways — circuit design, circuit build-up, and simulation — coordinated across
online and offline meetings.

**Course instructors:** Swmic Majumder (Part-Time Lecturer), Wasifa Mashiyath (Part-Time Lecturer)
