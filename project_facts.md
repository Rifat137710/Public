# Project Source Facts

Extracted from the nine project reports in the linked GitHub repositories.
Working notes for CV drafting — every field below is quoted or derived from
the reports themselves, not inferred.

Projects are listed in the order specified for the CV.

---

## 1. Droop Control in Decentralized Inverter-Based AC, Islanded & DC Microgrids

- **Course:** EEE 306 — Power System I Laboratory
- **Term:** July 2023 | Section C1, Group 05
- **Team size:** 5
- **My documented contribution:** "Designing & Implementing 3 types of models; Report Writing"
  (one of only two members credited with design and implementation)

**Technical content**
- Three architectures modelled in MATLAB/Simulink: grid-connected AC, islanded AC, DC
- AC microgrid: 380 V phase-to-phase RMS, 50 Hz, 10 kHz switching; LCL filter
  (Lc = 3.5 mH, Rc = 0.1 Ω, Lg = 0.35 mH, Rg = 0.05 Ω, Cf = 50 µF)
- Cascaded control: voltage PI (Kpv = 0.28586, Kiv = 594.85), current PI
  (Kpc = 54.978, Kic = 1570.8), abc→dq0 transformation
- Droop coefficients: active mp = 5e-05, reactive nq = 0.003; ω_nom = 314 rad/s
- Islanded: three parallel inverters at 500 kW / 300 kW / 200 kW, 600 V_rms, 60 Hz,
  SPWM, 480/600 V transformer per subsystem
- P/f droop 1% (59.7–60.3 Hz); Q/V droop 4% (588–612 V_rms); Qmax = Pnom/2
- Event sequence: load step at 1 s, droop enabled at 3 s, supervisory control at 5 s
- DC: PV array + DC-DC boost + bidirectional converter, hybrid battery/supercapacitor
  storage split by LPF/HPF; second-order filters shown to attenuate ripple power
  better than first-order
- **Result:** equal active and reactive power sharing across all three inverters with
  identical feeder impedance and droop coefficients, using local measurements only —
  no inter-unit communication link. Voltage and frequency stabilise after droop engages.

---

## 2. Development of an Intelligent Mobile Manipulation System for Daily Assistance of Visually Impaired Individuals

- **Course:** EEE 404 — Robotics & Automation Laboratory
- **Term:** July 2025 | Section G2, Group 04
- **Team size:** 6
- **My documented contribution:** "Hardware Setup, Dataset for Object Detection, Model
  Training, Hyperparameter Tuning, ARM Setup, Motor Calibration, Algorithm, SONAR
  Integration" (the broadest contribution listed among the six members)

**Technical content**
- Raspberry Pi 4B (8 GB); 6-DOF arm via PCA9685 PWM driver; dual-motor chassis via L298N;
  12 V rechargeable pack
- Two-layer perception: overhead USB camera + ArUco fiducials for global localisation and
  workspace mapping; front-facing Pi Camera for close-range object classification
- Two ML models trained — one for overhead localisation, one for front-face verification
- Euclidean-distance path planning; threshold-based motion control
- HC-SR04 ultrasonic precision stopping at a 32 cm threshold
- Full autonomous loop: map → localise → navigate → stop → verify → grasp → deliver → return
- **Documented limits:** ±1–2 cm sonar error varying with surface texture; Pi 4B cannot run
  two real-time ML models simultaneously; arm torque limits payload to lightweight objects;
  ArUco detection requires good lighting
- 12-week logged implementation timeline

---

## 3. Versatile CNC Machine: Pen Plotter, Laser Cutter & Engraver

- **Course:** EEE 318 — Control System I Laboratory
- **Term:** July 2024 | Section C1, Group 01
- **Team size:** 5
- **My documented contribution:** "Hardware Assembly"

**Technical content**
- CoreXY kinematics; Arduino UNO + CNC Shield V3; 2× SL42STH34-1334A steppers;
  2× Pololu A4988 micro-stepping drivers; servo Z-axis
- Two GRBL builds: v0.9 (grbl-servo fork) for pen lift, v1.1h laser mode for engraving
- Toolchain: Inkscape (Trace Bitmap → G-code) → LaserGRBL / Universal Gcode Sender
- Custom 3D-printed laser holder designed to solve a mounting incompatibility
- **Results:** BUET logo plotted successfully; optimal laser engraving on solid wood;
  minor scorching on paper; cardboard and cloth cut, fabric edges below target smoothness
- Budget 15,000 BDT, actual ~25,000 BDT (international shipping)

---

## 4. Stock Market Prediction with Sentiment Analysis

- **Course:** EEE 402 — Artificial Intelligence and Machine Learning Laboratory
- **Term:** January 2025 | Section G2, Group 02
- **Team size:** 6
- **My documented contribution:** "Data collection, builds models for stock market price
  prediction, Hyperparameter Tuning" (listed first among the six)

**Technical content**
- Data: Kaggle RedditNews headlines 2008–2016; GOOG price history via yfinance
- Sentiment: TextBlob polarity (−1..+1), regex extraction from malformed CSV, averaged
  per day; VADER evaluated as an alternative
- Technical indicators: MA7, MA20, EMA, MACD, 20SD, Bollinger Bands, RSI-14, SMA-14,
  log momentum
- Models: LSTM, GRU (with and without windowing) vs Random Forest, Linear Regression,
  XGBoost, ANN baselines; early-stopping callbacks; manual hyperparameter tuning

**Measured results (R² / MAE / MSE)**

| Feature set | LSTM | GRU |
|---|---|---|
| Primary only | 0.6598 (win. 0.6984) | 0.9432 (win. 0.8166) |
| Primary + sentiment | 0.6283 (win. 0.8894) | 0.8905 (win. 0.8126) |
| + additional features | 0.8124 (win. 0.7441) | — |
| All extracted features | 0.8926 (win. 0.8300) | **0.9515** (MAE 0.0769, MSE 0.0102) |

- Sentiment ablation: windowed LSTM R² rose 0.6984 → 0.8894 when sentiment was added
- Non-temporal baselines (RF, LR, XGBoost, ANN) all failed to capture sequence structure
- **Documented limitation:** no perfectly correlated dataset pair — sentiment covers the
  tech sector broadly while prices are GOOG-specific; data ends 2016

---

## 5. Battery Charge Controller using Buck Converter with Auto Cut-off Feature

- **Course:** EEE 316 — Power Electronics Laboratory
- **Term:** July 2024 | Section C1, Group 01
- **Team size:** 5
- **My documented contribution:** "Materials Collect"

**Technical content**
- Chain: 230 V AC → 220/12 V centre-tapped transformer (18.33:1, 3000 mA) → bridge
  rectifier → LC filter (100 mH series, 1000 µF shunt) → buck stage → relay → battery
- IRF250N MOSFET switch; SG3524 PWM generator, frequency set by RT/CT, duty via
  potentiometer; Vo = k·Vin
- Arduino auto cut-off: five successive ADC reads averaged on two channels, ratio
  r = reference/battery, hysteresis thresholds r_th = 1.55 (charging) / 2.40 (cut-off),
  upper bound 4.33; relay driven through a MOSFET
- **Result:** buck regulation verified on oscilloscope at 25%, 50%, and 90% duty cycle,
  confirming Vo = k·Vin tracking across the range
- BOM total 1,110 BDT

---

## 6. Detection of Resistor and Calculation of Its Value by Detecting Color Bands using Image Processing

- **Course:** EEE 312 — Digital Signal Processing Laboratory
- **Term:** not stated on the report cover — NEEDS CONFIRMATION | Section C1, Group 06
- **Team size:** 5
- **My documented contribution:** "Image Segmentation and component detection — worked on
  finding appropriate morphological operation and structuring element pixel value"

**Technical content**
- MATLAB pipeline: RGB→grayscale, global thresholding, binary inversion, morphological
  opening/closing with structuring elements adapted from the HSV value channel
- Region properties (eccentricity, area, bounding box) for component isolation
- Resistor identified by characteristic body colour via a custom yellow mask
- Per-colour mask functions (red, black, brown, orange) locate bands
- Orientation handling for four cases: horizontal/vertical × flipped/unflipped, resolved by
  summing band coordinates against a 250 threshold
- Value computed as (Band1 Band2) × 10^Band3
- **Validated on:** 1 kΩ horizontally flipped, 1 kΩ vertical unflipped, 1 kΩ + 220 Ω pair,
  and mixed boards containing MOSFETs, BJTs, LEDs, and wires (only resistors isolated)
- **Documented weakness:** black bands unreliable — phone cameras do not capture pure black,
  making the threshold hard to calibrate. Tested on three values only: 1 kΩ, 10 kΩ, 22 kΩ
- Requires white background, perpendicular shot, high resolution, minimal shadow

---

## 7. Rewinding of a Single-Phase Induction Motor

- **Course:** EEE 206 — Energy Conversion Laboratory
- **Term:** January 2023 | Section C1, Group 02 (report forwarded September 12, 2023)
- **Team size:** 6
- **My documented contribution:** "Wire and Insulation Purchase, Insulation, Coil Making,
  Coil Insertion, Connection, Reassembling of Rotor and casing, Testing"

**Technical content**
- Motor: type JY7124 squirrel-cage capacitor-start, 550 W, 220 V, 3.1 A, 50 Hz, 4 poles,
  1400 RPM full load, 24 stator slots, Class E insulation
- Winding design: 12 coils total, 8 main (2 per pole) + auxiliary
- Wire SWG 24, 0.0201 in diameter, 25.67 Ω per 1000 ft, 3.5 A max
- Turns rewound: main 91→95 (1st coil), 100→100 (2nd coil); auxiliary 81→85
- Weight 405 g → 420 g
- Coils wound on nails in wooden boards (no commercial former available)
- Winding diagram reconstructed from teardown observations

**Measured results**
- Main winding resistance R₁ = 21.0 Ω (multimeter)
- No-load: 220 V, 160 W, 2.6 A → |Znl| = 84.6154 Ω, cos θ = 0.2797
- Locked rotor: 60 V, 125 W, 3.1 A → |ZLR| = 19.3548 Ω, cos θ = 0.672
- Equivalent circuit: R₂ = 10.6744 Ω, X₁ = X₂ = 7.1662 Ω, XM = 140.9768 Ω
- Starting current I_start = 11.367 A
- Torque-speed characteristic derived for the main winding
- Cost 5,805 BDT — **note the line item "Professional Assistance, 800 BDT"**

---

## 8. Password Based Gate Locking System

- **Course:** EEE 304 — cover page reads "Power Electronics Laboratory", which appears to be
  a template error; the content is entirely digital logic. NEEDS CONFIRMATION
- **Term:** not stated | Section C1, Group 03
- **Team size:** 4
- **My documented contribution:** the individual-contribution table (§6.1) is EMPTY

**Technical content**
- Fully discrete logic, no microcontroller
- 4 decimal digits → 16 bits; hand-built decimal-to-BCD encoder from 10 push buttons and
  OR gates rather than an encoder IC
- 8× 74194 shift registers (4 store the saved password, 4 store the attempt)
- 8× 7485 4-bit comparators for digit-wise matching
- 4555 demultiplexer routes keypresses; 4013 D flip-flops select the active register bank
- 5× 7447 BCD-to-seven-segment decoders with common-anode displays
- 555 timer lockout: R = 10 kΩ, C = 470 µF → ≈30 s, triggered after 4 successive resets
- Match → yellow LED and gate opens; mismatch → red LED and alarm
- Simulated in Proteus, then built and verified on breadboard

---

## 9. IoT-Based Smart Bangla Notice Board with Real-Time Calendar & Clock

- **Course:** EEE 416 — Microprocessor & Embedded System Laboratory
- **Term:** January 2025 | Section C1, Group 02 (implementation logged May–July 2025)
- **Team size:** 4
- **My documented contribution:** component procurement; Bangla notice bitmapping (19.06.2025);
  Bangla calendar-clock bitmapping (03.07.2025); final hardware assembly (23.07.2025)

**Technical content**
- ESP8266 NodeMCU; three 32×8 LED matrices, each four chained MAX7219 drivers, driven as
  three independent zones (time / calendar / scrolling notice)
- Libraries: ESP8266WiFi, WiFiManager, MD_Parola, MD_MAX72xx, SPI, TimeLib
- NTP sync against pool.ntp.org with +6 h Bangladesh Standard Time offset
- ESP8266WebServer on port 80, password-protected notice update interface
- Gregorian-to-Bangla calendar conversion with month-offset rules
- **Core problem solved:** Bangla script does not render on 8×8 matrix hardware — every
  Bangla character, digit, month name and weekday was hand-bitmapped
- Five preloaded Bangla safety notices selectable from the web interface
- Cost 2,755 BDT
- **Documented limits:** no free-text entry, incomplete Unicode coverage

---

## Open items

- Term/date for #6 (EEE 312) and #8 (EEE 304)
- Correct course name for EEE 304
- Whether any of these, or separate work, is the final-year thesis
- Target subfield for the PhD application, which determines section emphasis
