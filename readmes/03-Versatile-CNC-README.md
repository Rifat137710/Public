# Versatile CNC Machine: Pen Plotter, Laser Cutter & Engraver

**Course:** EEE 318 — Control System 1 Laboratory (July 2024)
**Institution:** Department of EEE, Bangladesh University of Engineering and Technology (BUET)
**Section:** C1 | **Group:** 01
**Full report:** [`EEE318_Project_Report_Group_01.pdf`](EEE318_Project_Report_Group_01.pdf)

---

## What this project does

- **Built one CNC machine that does three jobs** — plots with a pen, engraves with a laser, and
  cuts — by swapping the toolhead, instead of buying three separate machines. Aimed at
  hobbyists, small businesses, and schools that need all three capabilities but cannot justify
  three budgets.
- **Started from the hardest case: precision fabric cutting.** Fabric is flexible and delicate,
  its elasticity and thickness vary by type, and clean cuts demand both mechanical rigidity and
  adaptable control — a substantially harder target than pen plotting.
- **Used CoreXY kinematics,** where a single belt drives both axes and the two steppers cooperate
  through a coordinate transform rather than each owning one axis. This keeps moving mass low and
  improves speed and accuracy — the same arrangement common in 3D printers.
- **Ran two different GRBL builds** to cover the toolchange: **v0.9** with its source modified to
  add servo support for the Z-axis pen lift, and **v1.1h** in laser mode for engraving and cutting.
- **Built the full design-to-machine toolchain:** Inkscape for vectorising artwork and generating
  G-code, Universal Gcode Sender for streaming it to the Arduino, and LaserGRBL with line-to-line
  tracing for engraving and centerline conversion for cutting.
- **Result — plotting works well.** The BUET logo was plotted successfully from a traced bitmap.
- **Result — engraving is best on wood.** Solid wooden surfaces yield precise results; paper
  shows minor scorching.
- **Result — cutting works, but fabric falls short.** Cardboard and cloth both cut, yet fabric
  edges come out **less smooth than intended** — the original target application remains the
  weakest result and is still open.
- **Result — integration was the real engineering.** Component alignment demanded painstaking
  work, and the laser module was incompatible with the frame until a **custom laser holder was
  designed and 3D printed**. Driving screws into printed parts, tensioning the timing belt, and a
  power supply wire that would not mate with standard sockets each needed iterative fixes.
- **Result — cost overran by two-thirds.** Budgeted at ৳15,000, the build came in near **৳25,000**
  because several parts had to be ordered internationally and carried shipping charges.

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
