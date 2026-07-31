# Versatile CNC Machine: Pen Plotter, Laser Cutter & Engraver

**Course:** EEE 318 — Control System 1 Laboratory (July 2024)
**Institution:** Department of EEE, Bangladesh University of Engineering and Technology (BUET)
**Section:** C1 | **Group:** 01
**Full report:** [`EEE318_Project_Report_Group_01.pdf`](EEE318_Project_Report_Group_01.pdf)
**Demo video:** https://youtu.be/5k_nW82i6Uk

---

## What this project does

One CNC machine that does three jobs — **plots with a pen, engraves with a laser, and cuts** —
by swapping the toolhead. Commercial machines usually do one job well and force you to buy a
separate machine (and a separate budget) for each. This build targets hobbyists, small
businesses, and schools that need all three but can't justify three machines.

The original goal was **precision fabric cutting**, which is harder than pen plotting: fabric is
flexible and delicate, its elasticity and thickness vary by type, and clean cuts demand both
mechanical rigidity and adaptable control.

## How it's built

**CoreXY kinematics** — a single belt drives both axes, so the two motors must work together
through a coordinate transform rather than each owning one axis. The same arrangement is common
in 3D printers; it keeps moving mass low and improves speed and accuracy.

### Electronics

| Component | Role |
| --- | --- |
| Arduino UNO (clone) | Runs the GRBL firmware, interprets G-code |
| CNC Shield V3 | Breakout for drivers and toolhead control |
| 2 × SL42STH34-1334A stepper motors | X/Y motion through the CoreXY belt |
| 2 × Pololu A4988 drivers | Stepper current control and micro-stepping |
| Servo (Z axis) | Lifts and drops the pen |
| Laser module | Engraving and cutting |

### Firmware

Two GRBL builds, swapped depending on the toolhead:

- **Pen plotting** — [GRBL v0.9 with servo support](https://github.com/robottini/grbl-servo);
  the source was modified to add servo control for the Z axis, then GRBL settings retuned.
- **Laser cutting/engraving** — [GRBL v1.1h](https://github.com/gnea/grbl/releases/tag/v1.1h.20190825)
  with laser mode.

### Toolchain

| Task | Software |
| --- | --- |
| Pen plotting | **Inkscape** (Trace Bitmap → vectorize → 4ixDrawer extension → G-code) + **UGS** (Universal Gcode Sender) to stream to the Arduino |
| Engraving | **LaserGRBL** — line-to-line tracing mode |
| Cutting | **LaserGRBL** — centerline conversion, with border speed, laser power, and size configured per job |

## Results

- **Pen plotting** works well — the BUET logo was plotted successfully from a traced bitmap.
- **Laser engraving** performs best on solid wood, yielding precise results. On paper it causes
  minor scorching.
- **Cutting** works on cardboard and cloth. Fabric edges, however, come out **less smooth than
  intended** — the original target application remains the weakest result and needs further work.

## Build challenges

Component alignment demanded painstaking attention. The laser module was **incompatible with the
existing frame**, so the team designed and 3D-printed a **custom laser holder**. Driving screws
into 3D-printed parts, tensioning the timing belt, and a power-supply wire that wouldn't mate
with standard sockets (solved with a custom port) each required iterative fixes.

## Cost

Budgeted at ৳15,000; actual cost came to roughly **৳25,000**, overrun caused by international
shipping charges on parts that had to be ordered from abroad.

## Known limitations

**Steppers** — finite torque (exceed it and you lose steps), a maximum usable speed, a
micro-stepping/torque trade-off, and heat build-up during long runs.
**Pen** — line quality depends on pen pressure; position accuracy is bounded by belts and guide rails.
**Laser** — power output limits material thickness; focus misalignment causes uneven cuts or burns;
fire risk and fumes make ventilation and eye protection mandatory.
**Machine-wide** — workspace size caps part dimensions, frame rigidity limits speed, and the duty
cycle requires cooling breaks. Regular lubrication, cleaning, and belt tensioning are needed.

## Safety

The build includes emergency stop, interlocks, and guards, backed by a hazard risk assessment.
**Wear laser protective eyewear** during engraving and cutting, and do not touch the workpiece
while the laser is running.

## Future work

Wider material support with specialised tooling; better calibration using precision linear
guides, encoders, and sensors; robotic material handling and automatic tool changes; extension
to 5- or 6-axis machining; adaptive machining with real-time feedback and ML-driven predictive
maintenance; IoT remote monitoring; tighter CAD/CAM integration; and cost reduction.

## Team

Sadia Israt Oishi (2006152) — hardware assembly ·
Meharab Hossen Bappy (2006154) — pen plotter setup, laser mounting ·
Chowdhury Blossom Ibn Razzaque (2006156) — hardware assembly, materials ·
Rifat Rahman (2006137) — hardware assembly ·
Nabanita Sarker (2006162) — software control, debugging

**Course instructors:** Dr. Pran Kanai Saha (Professor), Md. Jawad Ul Islam (Lecturer)
