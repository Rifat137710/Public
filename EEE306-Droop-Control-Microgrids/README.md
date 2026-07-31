# Droop Control in Decentralized Inverter-Based AC, Islanded & DC Microgrids

**Course:** EEE 306 — Power System I Laboratory (July 2023)
**Institution:** Department of EEE, Bangladesh University of Engineering and Technology (BUET)
**Section:** C1 | **Group:** 05
**Full report:** [`EEE306_Project_Report_Group_05.pdf`](EEE306_Project_Report_Group_05.pdf)
**Demo videos:** [AC](https://youtu.be/Ub8iL2laX48) · [Islanded](https://youtu.be/khQcHFJkYVs) · [DC](https://youtu.be/KE7yp5uuuIQ)

---

## What this project does

Designs, simulates, and evaluates **droop control** across three distinct microgrid
architectures in **MATLAB/Simulink** — inverter-based AC, islanded, and DC — then compares how
each responds to load changes and generation disturbances.

Droop control is the workhorse of decentralized microgrid regulation: each source adjusts its own
output from **local measurements alone**, with no communication link between units. That makes it
simple and robust, and it's why the technique carried over from diesel-generator governors to
modern power-electronic inverters.

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
