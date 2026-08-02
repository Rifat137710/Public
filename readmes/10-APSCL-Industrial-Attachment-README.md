# Industrial Attachment — Ashuganj Power Station Company Limited (APSCL)

**Programme:** Industrial Attachment, Department of EEE, Bangladesh University of Engineering and Technology (BUET)
**Major group:** Electrical Energy and Power System (EEPS)
**Host:** Ashuganj Power Station Company Limited (APSCL), Brahmanbaria, Bangladesh
**Period:** November 2025
**Full report:** [`Industrial_Attachment_Report_APSCL_NOV_2025.pdf`](Industrial_Attachment_Report_APSCL_NOV_2025.pdf)

---

## What this attachment covers

- **Walked a 1,647 MW combined-cycle generation complex end to end** — four separate plants
  (420 MW East, 450 MW North, 450 MW South, 225 MW), briefed at each stage by APSCL executive
  engineers, and documented the whole facility from gas intake to the 400 kV transmission bus.
- **Traced the complete energy conversion chain** through a combined-cycle plant: natural gas
  intake and conditioning → compressor → combustion → gas turbine → heat recovery steam
  generation → steam turbine → generator → step-up transformer → substation → grid.
- **Studied why combined cycle exists.** A simple-cycle gas turbine runs below 35% efficiency
  and dumps 600 °C exhaust to atmosphere. Routing that exhaust through the HRSG to drive a second
  turbine lifts plant efficiency to **≈58%** — the single most important design decision in the
  facility, and the reason the flue gas finally leaves the chimney at only 86 °C.
- **Mapped the three-pressure HRSG in detail:** the boiler feed pump raises condensate through
  11 stages to **120 bar (HP), 31 bar (IP) and 3 bar (LP)**, with each pressure level running its
  own economiser → evaporator → superheater train, plus IP reheat, all following the Rankine cycle.
- **Learned how a plant is actually operated,** not just how it works — the control room's
  monitoring parameters, fail-proof setpoints, cascaded valve operation, transmitter and actuator
  chains, and the Distributed Control System that ties them together.
- **Studied grid-level control:** droop characteristics for parallel generators, **FGMO**
  (frequency guided master oscillator) isochronous load sharing with a master/slave generator
  pair and a Load Sharing Controller, and the governor instability known as **load hunting**.
- **Compared substation technologies at full scale** — AIS versus GIS, with SF₆ offering roughly
  **3× the dielectric strength of air** and cutting the footprint to 10–30% of an equivalent AIS,
  against 10–40% higher capital cost and strict greenhouse-gas leak management.
- **Examined a Double Bus Double Breaker arrangement** and worked through why it is used at
  400 kV: breaker maintenance, bus faults and breaker failures each resolve with **zero downtime
  to the feeder**, because every circuit is fed through two independent buses.
- **Followed a black start from scheduled shutdown,** the hardest operational sequence in the
  plant — DC auxiliaries from battery storage, the Static Frequency Converter running the
  synchronous machine as a motor at 120 rpm barring speed, burners lit one by one, the machine
  becoming self-sustaining at **60–63% of rated speed**, the generator circuit breaker separating
  from grid, and the diverter damper opened gradually to avoid thermal-shocking the HRSG.
- **Reviewed the protection philosophy** across more than 30 schemes covering generator, stator,
  rotor, transformer, bus and line — differential, restricted earth fault, out-of-step, reverse
  power, under/over-excitation, Buchholz, breaker failure and more.
- **Saw the environmental and social side of the plant,** which is not incidental: cooling and
  steam water is released into irrigation channels in the dry season, supporting roughly
  **40,000 acres** of farmland, and open-cycle cooling water returns to the Meghna within
  **5 °C** of river temperature to protect aquatic life.

## The facility

APSCL became a public limited company in 2003, spun out of the Bangladesh Power Development
Board. It sits beside the Titas Gas Field and the Meghna River — indigenous gas on one side,
cooling water on the other — and converts that gas into bulk power for the national grid.

| Plant | Installed | Present capacity | Generator | Connects to |
| --- | --- | --- | --- | --- |
| **420 MW CCPP (East)** | 400 MW | 393 MW | — | — |
| **450 MW CCPP (North)** | 360 MW | 353.35 MW | 22 kV | 400 kV to Bhulta via GIS; 230 kV bus via 2 × 325 MVA transformers |
| **450 MW CCPP (South)** | 360 MW | up to 318.81 MW | 22 kV | 230 kV bus via GSUT |
| **225 MW CCPP** | 142 MW + 75 MW (split shaft, two generators) | up to 221 MW | 11 kV | 132 kV bus via GSUT |

Roughly **5% of generated power is consumed by the plant itself**, which is why installed and
delivered capacity differ on every unit — North CCPP generates about 410 MW to export 393 MW.

APSCL is also diversifying beyond gas, with land acquired in Patuakhali for LNG-based projects
and solar initiatives in Narshingdi.

## Departments

**Monitoring** — Operators watch valve positions, pneumatic and oil pressures, and temperatures
at key points continuously; no abrupt changes are permitted. Critical readings include HP, CRH,
IP and LP boiler pressure and temperature, close- and open-cycle water temperature, and the
compressor pressure ratio. A set of **fail-proof parameters** is configured once and then
monitored automatically, with the control system energising actuators to hold them.

**Controlling** — Sensors feed transmitters (a sensing probe plus a cable duct back to the
control room), operators decide whether to act, and actuators reposition valves. High-power
valves act on a **cascaded** second stage rather than directly, so a small sensed change
energises an isolated actuator that then drives the main valve. Local control boxes and junction
boxes let operators drive equipment at the machine even while the plant runs automated.

**Maintenance** — Preventive and condition-based work, with transformers as the worked example:
daily oil level, load and OTI/WTI checks; **silica gel breather** colour (blue → pink means
moisture saturation); cooling fan and oil pump operation; bushing cleaning to prevent tracking
and flashover. Oil work covers **dielectric strength (BDV) testing**, filtration and dehydration,
and gasket inspection. Shutdown testing covers terminal tightening, manual **Buchholz relay** and
pressure relief device triggering, and **insulation resistance (Megger)** measurement.

**Instrumentation & Control (I&C)** — Handles pressure, temperature, humidity, flow, pH and
speed through PLC cards, relays, contactors and VSDs. Condenser pressure uses a diaphragm
mechanism with the isolated partition sensing change. Where accuracy is critical, **three
transmitters are installed and majority rule decides** whether a reading is trustworthy.

## Substation

### AIS vs GIS

| | Air Insulated Substation | Gas Insulated Substation |
| --- | --- | --- |
| **Insulation** | Ambient air | SF₆, ~3× the dielectric strength of air |
| **Design** | Open-air breakers, isolators, busbars with large clearances | All active components encapsulated in grounded, pressurised metal chambers |
| **Footprint** | Massive | 10–30% of an equivalent AIS |
| **Best for** | Rural/suburban sites where land is cheap | Urban centres, offshore, underground, harsh industrial |
| **Cost** | Lower capital, easy to expand | 10–40% higher upfront |
| **Maintenance** | Frequent cleaning; vulnerable to pollution, salt, lightning, animals | Nearly maintenance-free; immune to weather |
| **Downside** | Environmental exposure | SF₆ is a potent greenhouse gas; repairs need specialists |

### Double Bus Double Breaker

Two independent buses, every feeder connected to both, each circuit with two dedicated breakers
and four isolators. Both breakers closed in normal operation.

- **Breaker maintenance** — open Breaker A, the feeder stays energised through Breaker B. Zero
  downtime, no transfer switching.
- **Bus fault** — Bus 1 protection trips everything on it; all circuits keep running from Bus 2.
- **Breaker failure** — the protection trips the rest of that bus, but the healthy bus keeps
  feeding every circuit through its second breaker.

## Power plant operation

**Compressor** — Intake air compressed 1 bar → 18 bar. **Inlet Guide Vanes** modulate airflow
with load while the turbine holds constant speed for grid frequency.

**Fuel** — Natural gas from the Bakhrabaad field via the National Gas Transmission Network.
Filtration removes dust, rust and water droplets through a knockout drum; a **Regulation and
Metering System** handles measurement and valve synchronisation. Of three gas boosters, two run
and one stands by, holding **≈33 bar** (never below 25 bar) to prevent incomplete combustion. A
water bath heater brings the gas to ignition temperature.

**Combustion chamber** — 24 burners ignite the air-fuel mixture, driving the turbine at
**3000 rpm**. Extra load is met by raising fuel and air pressure at constant speed to increase
torque; ramp-down is limited to a **13 MW/min** load gradient, adjustable by the operator through
the DCS.

**Gas turbine** — 3000 rpm holds 50 Hz. Blades grow progressively larger from compressor to
exhaust. Exhaust leaves at **600 °C** and feeds the HRSG. Starting takes **18–20 minutes**: grid
power or the emergency diesel generator drives the synchronous machine as a motor, firing begins
early in the ramp, and the machine becomes a generator at 60–63% of nominal speed. On shutdown,
speed cannot drop abruptly — friction would heat and expand the blades — so **turning gear**
holds a 120 rpm barring speed while heat dissipates.

**HRSG** — The Condensate Extraction Pump moves condensate from the condenser through economiser
and deaerator to the Boiler Feed Pump (two fitted, one standby), which raises it through 11
pressure stages to **120 bar HP / 31 bar IP / 3 bar LP** (the 225 MW plant runs 80 bar HP).

- **HP:** economiser heats to boiling → drum → evaporator adds latent heat → superheater raises
  steam to flue-gas temperature. HP steam enters the turbine at ~120 bar and leaves near 33 bar,
  then goes to the cold reheat boiler.
- **IP:** economiser → drum → evaporator → superheater to **333 °C**. IP superheated steam and
  cold reheat steam pass through two IP reheaters to make hot reheat steam, which drives the IP
  turbine.
- **LP:** condensate through the LP economiser, deaerator strips oxygen and CO₂, LP drum,
  evaporator, superheat, then the LP turbine.

Flue gas leaves the stack at **86 °C**.

**Steam turbine** — HP, IP and LP sections on a **single shaft** shared with the gas turbine and
one generator, coupled by a **Self Shifting Synchronising Clutch (SSSC)** that engages and
disengages the ST as needed. Three startup modes — hot (~2 hours), warm, cold — each with its own
characteristic curve. A **diverter damper** between GT and HRSG evacuates exhaust when running
simple cycle.

**Transformers** — The North CCPP GSUT is **oil natural air forced (ONAF)**, stepping 22 kV to
400 kV into the GIS, with **27 taps and 18 cooling fans**. The **Unit Auxiliary Transformer**
(22 kV / 6.6 kV) supplies the plant's own ~5% draw. The **Grid Auxiliary Transformer** brings
230 kV grid power down to 6.6 kV to start the plant from shutdown. Nameplate codes read as
voltage-type-MVA — `20 BAT 10` is a 20 kV, 10 MVA bus auxiliary transformer. Both UAT and GSUT
carry **RTDs** for fire detection tied to firefighting actuators; the UAT has a breather filtering
the cooling oil.

**Generator** — Mechanical input from GT and ST, electrical output at 22 kV, stepped up by the
GSUT to 400 kV, down by the UAT to 6.6 kV for auxiliaries, and further to 400 V for control and
instrumentation. The compressor is the single largest consumer of gas turbine output.

**Condenser** — Condenses exhaust steam back to water against closed-cycle cooling water, itself
cooled by open-cycle river water. Conductance, pH, temperature and dissolved minerals are
controlled to maintain demineralised quality. Discharge to the river is held **within 5 °C** of
ambient to preserve biodiversity. A vacuum pump maintains negative pressure at the LP terminal to
prevent backflow.

## Modes of generation control

**Droop characteristics** — Speed falls as load is added and rises as it is shed. On a 3000 rpm
machine, **5% droop** means no-load speed sits at 3150 rpm; equivalently a 50 Hz system would
drift to 52.5 Hz if full load were lost. Droop is what lets parallel generators share load
without fighting each other.

**FGMO (Frequency Guided Master Oscillator)** — Isochronous load sharing across parallel GT and
ST generators. One master generator runs isochronous and holds bus frequency exactly constant
regardless of load; slaves follow droop, but their droop is steered by the master. A **Load
Sharing Controller** monitors real power across all machines and, if the master exceeds its
setpoint, raises the slaves' speed references so their governors automatically take on more load.

**Load hunting** — Governor instability where speed, frequency and voltage oscillate
continuously: engine note rises and falls rhythmically, lights pulse. Caused by an
over-compensating governor, worn mechanical linkages, a loose actuator lever, a badly tuned PID
loop, or a fuel injection fault.

## Auxiliary systems

**Cooling**
- **Hydrogen** cools the rotor, stator and windings; seal oil isolates the hydrogen from adjacent
  equipment; an orange duct injects makeup hydrogen through an automated valve if it leaks. The
  hydrogen is produced on site by electrolysis of treated water.
- **Lube oil** cools transformers, turbine and generator bearings, gearbox and turning gear,
  circulated by lube oil pumps.
- **Water** — river water is demineralised for the closed cycle; raw river water serves the open
  cycle in a few specific regions only, since its mineral and particle content would damage
  equipment over time.

**Valves**
- **Pneumatic** — driven by clean, dry instrument air. Three compressors (two on standby) hold
  supply up to 8 bar; roughly **5 bar** actuates a valve.
- **Solenoid** — an energised coil moves a plunger magnetically to open or close.
- **Hydraulic** — spool position directs oil flow through the system.

**Blowdown** — Even demineralised condensate carries sludge and dissolved minerals that
precipitate in the HP, IP and LP drums, risking scaling, corrosion and foaming. Blowdown flushes
them out with a small water volume, cools the mixture, and discharges it to the Meghna.

**Firefighting** — Detectors, alarms, sprinklers, hydrants, fire-water pumps, extinguishers and
CO₂ or foam suppression, with the fire-water network held permanently pressurised for immediate
delivery.

Auxiliaries run at **6.6 kV** (GTG starter fuel compressor, GTG SEE, boiler feed pump,
firefighting water pump, CEP, closed-cycle water pump, natural gas booster compressors) or
**400 V** (control, monitoring and operator systems).

## Colour code

| Colour | Carries |
| --- | --- |
| **Orange** | Hydrogen to the generator — keeps rotor and stator in a dry, oxygen-free environment and cools the chamber |
| **Red** | Firefighting water, with actuators distributed across the plant |
| **Dark green** | Demineralised / closed-cycle cooling water (condensate) |
| **Light green** | Open-cycle cooling water, returned to river within 5 °C |
| **Yellow** | Lube oil |
| **Blue** | Instrument air for valve operation |

## Starting generation after a scheduled shutdown

1. **Keep auxiliaries alive.** Instrument air, seal and lube oil pumps must run even in shutdown
   to maintain lubrication, insulation and rust prevention — typically on DC motors fed from
   battery storage or rectified grid power. In a full blackout, battery storage is the only option.
2. **Spin the shaft with the SFC.** A Static Frequency Converter rectifies grid AC and
   regenerates variable-frequency, variable-voltage AC, running the synchronous machine as a
   motor. Frequency is raised gradually from ~2 Hz (120 rpm barring speed) so brushes are not
   damaged by an abrupt start. Some plants, including 400 MW North CCPP, use an **Emergency Diesel
   Generator** instead.
3. **Light the burners.** With the compressor turning on the common shaft, conditioned gas
   arrives through the RMS and natural gas booster, and burners are ignited one at a time. The
   SFC keeps supplying torque, since early combustion cannot yet turn the turbine alone.
4. **Reach self-sustaining speed.** At **60–63% of rated speed (~1800 rpm)** the gas turbine
   becomes self-sustaining. The generator circuit breaker separates from grid and the machine
   becomes a generator.
5. **Accelerate to rated.** The governor admits more gas, raising blade pressure and torque until
   the shaft reaches 3000 rpm. Exhaust bypasses through the GT stack; efficiency at this point is
   **30–35%**.
6. **Bring in the HRSG.** The diverter damper opens *slightly* first, so exhaust heat cannot
   thermally shock the HRSG. Steam flow builds through HP superheat, evaporator and economiser,
   then IP reheat and superheat, then LP, driving the HP, IP and LP turbine sections. Once thermal
   shock risk has passed the damper opens fully and all exhaust routes through the HRSG.
7. **Close the loop.** The condenser condenses exhaust steam, a vacuum pump prevents back
   pressure, and the CEP returns treated condensate to the BFP to sustain the cycle.

## Power plant protection

More than 30 protection schemes are deployed across the plant:

Differential · Restricted Earth Fault · Directional Overcurrent · Directional Ground Fault ·
AC Re-closing Relay with Synchronism Check · Generator Auto-Synchronising · Instantaneous
Overcurrent · AC Time Overcurrent · AC Time Earth Fault · Compound Voltage Block Overcurrent ·
Breaker Failure · Reverse Phase · Transformer Thermal · Over-voltage Earth Fault ·
Over-excitation · Buchholz · Pressure Relief · Oil Level · Oil Temperature · Rotor Earth Fault ·
Stator Earth Fault · Out of Step · Reverse Power · Impedance · Frequency · Under-excitation ·
Under-voltage · Over-voltage · Inadvertent Energisation · Field Breaker · Exciter Trouble Alarm ·
AVR Failure Alarm · Arc Protection

## Team

Hridya Sudeepon Roy (2006032) · Iffat Islam Pinky (2006084) · Md. Woahidur Rahman (2006102) ·
Sabbir Mahmud (2006104) · Md. Rifat Rahman (2006137)

**APSCL instructors:** Md. Masud Parvez (Executive Engineer), Md. Alamgir Kabir (Executive Engineer)
