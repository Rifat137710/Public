# Droop Control in Decentralized Inverter-Based AC, Islanded & DC Microgrids

**Course:** EEE 306 — Power System I Laboratory (July 2023)
**Institution:** Department of EEE, Bangladesh University of Engineering and Technology (BUET)
**Section:** C1 | **Group:** 05
**Full report:** [`EEE306_Project_Report_Group_05.pdf`](EEE306_Project_Report_Group_05.pdf)

---

## What this project does

- **Built and compared three complete microgrid models in MATLAB/Simulink** — grid-connected AC,
  islanded AC, and DC — each with droop control implemented from scratch, to test how one
  decentralised control law behaves across fundamentally different architectures.
- **Implemented droop the way real inverters use it:** every source sets its own output from
  local voltage and current measurements only, with **no communication link between units** —
  `ω_ref = ω_nom − m_p·P` and `v_ref = v_nom − n_q·Q` for AC, and voltage-against-load-current
  droop for DC, extended into a frequency-shaped **virtual impedance** so the controller manages
  transient power sharing rather than steady state alone.
- **AC model:** three voltage source converters, each running a cascaded
  droop → outer voltage → inner current stack in the **dq0 rotating frame**, with PI gains tuned
  by pole placement, an LCL filter, a 380 V / 50 Hz bus and 10 kHz switching.
- **Islanded model:** three parallel inverters rated **500 kW, 300 kW and 200 kW** on a
  600 V_rms / 60 Hz bus with a dynamic load and SPWM, driven through a staged event sequence —
  load step at t = 1 s, droop enabled at t = 3 s, supervisory control at t = 5 s.
- **DC model:** PV array and boost converter feeding a bus backed by a **hybrid battery +
  supercapacitor store**, split by a low-pass/high-pass filter pair so the battery covers slow
  demand while the supercapacitor absorbs fast fluctuations.
- **Result — power sharing achieved without communication.** With identical feeder impedances and
  droop coefficients, all three inverters shared active and reactive power **equally**, with
  matching voltage and frequency deviations.
- **Result — regulation held within spec.** P/f droop of 1% kept frequency inside
  **59.7–60.3 Hz**; Q/V droop of 4% kept PCC voltage inside **588–612 V_rms** across the load range.
- **Result — the system recovers from disturbance.** Switching transients appeared during the
  1–2 s load step, then power, frequency, reactive power and voltage all settled back to nominal
  once the controller engaged. Load steps visibly disturbed output current but left output
  voltage steady.
- **Result — the DC bus rode through a generation drop.** Voltage stayed constant through an
  irradiance reduction at t = 1 s because the bidirectional converter and HESS absorbed the
  shortfall. **Second-order** LPF/HPF pairs attenuated ripple power measurably better than
  first-order, visible in the impedance roll-off rate.

## The control law

**AC microgrid** — real power sets frequency, reactive power sets voltage:

```
ω_ref = ω_nominal − m_p · P
v_ref = v_nominal − n_q · Q
```

This mirrors a synchronous generator, where a mechanical/electrical power imbalance changes rotor
speed and hence frequency. The report derives both the **inductive** (θ = 90°) and **resistive**
(θ = 0°) droop forms from the full active/reactive power equations, since the correct pairing
depends on feeder impedance angle.

**DC microgrid** — no natural frequency to regulate, so droop works on voltage against load
current, `v = V_ref − i·R_droop`. The project extends this to a **frequency-coordinating virtual
impedance**: converting `R_droop` into a frequency-shaped `Z_droop` lets the controller manage
transient power sharing, not just steady state.

## Simulation models

### AC microgrid

Three voltage source converters feeding separate loads. Each VSC carries a cascaded control
stack — **droop controller → outer voltage controller → inner current controller** — with all
three-phase quantities transformed into the **dq0 rotating frame**. The current loop is
deliberately tuned faster than the voltage loop to decouple them; both PI controllers are tuned
by pole placement.

| Parameter | Value |
| --- | --- |
| Phase-to-phase RMS voltage | 380 V |
| Grid frequency | 50 Hz |
| Switching frequency | 10 kHz |
| LCL filter | Lc = 3.5 mH, Rc = 0.1 Ω, Lg = 0.35 mH, Rg = 0.05 Ω, Cf = 50 µF |
| Voltage controller | Kpv = 0.28586, Kiv = 594.85 |
| Current controller | Kpc = 54.978, Kic = 1570.8 |
| Active droop coefficients | mp1 = mp2 = mp3 = 5e-05 |
| Reactive droop coefficients | nq1 = nq2 = nq3 = 0.003 |

### Islanded microgrid

Three parallel inverter subsystems rated **500 kW, 300 kW, and 200 kW**, each with a three-phase
two-level converter, LC filter, 480/600 V transformer, ideal DC source (standing in for PV, wind,
or battery storage), control system, and SPWM generator. A dynamic load model varies total
demand. Line voltage 600 Vrms at 60 Hz.

Event sequence: **load increases at t = 1 s → droop control enabled at t = 3 s → supervisory
control enabled at t = 5 s.**

- **P/f droop = 1%** — frequency may swing 60.3 Hz (no active power) to 59.7 Hz (nominal active power)
- **Q/V droop = 4%** — PCC voltage may swing 612 Vrms (full inductive) to 588 Vrms (full capacitive)
- Qmax set to half of nominal active power

### DC microgrid

PV array → DC-DC boost converter → DC bus, with a **hybrid energy storage system (HESS)** of
battery plus supercapacitor on bidirectional converters. The two are split by frequency: a
**low-pass filter** on the battery loop and a **high-pass filter** on the supercapacitor loop, so
their impedances cross at a cut-off frequency ω_c. Below ω_c the battery supplies energy; between
ω_c and the converter frequency the supercapacitor absorbs fast fluctuations — each device does
what it's good at. Second-order filters were shown to attenuate ripple power better than
first-order (visible in the roll-off rate of the impedance-vs-frequency plots).

## Results

| Observation | AC microgrid | DC microgrid | Islanded microgrid |
| --- | --- | --- | --- |
| Active power | Increases at t = 1 s | Decreases as irradiance drops at t = 1 s | Increases at t = 1 s |
| Frequency | Falls as active power rises | Unchanged (no frequency to regulate) | Falls as active power rises |
| Voltage | Falls as active power rises | Unchanged — bidirectional DC-DC converter holds it | Falls as active power rises |
| With droop enabled (t = 3 s) | Voltage and frequency stabilise | Voltage stabilises | Voltage and frequency stabilise |

With **identical feeder impedances and droop coefficients, the three inverters share active and
reactive power equally**, and their voltage/frequency deviations match. Switching transients
appear between 1–2 s; once the controller engages at 2 s, power, frequency, reactive power, and
voltage all settle back to nominal. Load steps show visible current fluctuation but the output
voltage holds steady.

## Limitations of the simulation approach

Simulink is a model, not hardware: complex multi-converter models are computationally heavy and
slow to run; numerical solver error accumulates over long simulations, making solver choice
critical; real-time and hardware-in-the-loop setups face communication overhead and limited
hardware support; interoperability with other tools is imperfect; and validating results against
real-world behaviour is constrained by how faithfully the model captures physical phenomena.

## Future work

Optimise the control algorithms per architecture; add more renewable sources and energy storage;
run cybersecurity analysis for resilience; validate through **Hardware-in-the-Loop (HIL)**
testing; study grid interconnection dynamics; and analyse market dynamics for economic
optimisation alongside reliability.

## Team

Nabanita Sarker (2006162) — designed and implemented all three models, report ·
Saad Sami Shorot (2006150) — implementation support, report ·
Meherab Hossain Bappy (2006154) — design support, report ·
Md. Rifat Rahman (2006137) — report ·
Moshahed Parvez (2006148) — report

**Course instructors:** Shoilie Chakma (Lecturer), Kazi Ishrak Ahmed (Part-Time Lecturer)
