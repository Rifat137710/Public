# Academic Project Portfolio — EEE, BUET

Undergraduate course projects from the Department of Electrical and Electronic Engineering,
Bangladesh University of Engineering and Technology (BUET). Each folder holds the **full project
report (PDF)** and a **README** summarising what was built, how it works, and what came out of it.

Nine projects spanning robotics, machine learning, embedded systems, power systems, control,
signal processing, and digital logic.

---

## Projects

### 🤖 [Intelligent Mobile Manipulation System for Visually Impaired Individuals](EEE404-Assistive-Mobile-Manipulator/)
`EEE 404 — Robotics & Automation Laboratory` · Group 04

An autonomous robot that locates an object on a table, drives to it, verifies it, picks it up
with a 6-DOF arm, and delivers it — built as low-cost assistive technology. Uses hybrid
perception: an overhead camera with ArUco markers for global mapping plus a front-facing camera
for close-range classification, all running on a Raspberry Pi 4B.

**Stack:** Raspberry Pi 4B · OpenCV / ArUco · on-device ML classification · 6-DOF arm (PCA9685) · L298N chassis · HC-SR04 sonar

---

### 📈 [Stock Market Prediction with Sentiment Analysis](EEE402-Stock-Market-Prediction-Sentiment-Analysis/)
`EEE 402 — Artificial Intelligence and Machine Learning Laboratory` · Group 02

Forecasts Google's daily closing price by feeding news-headline sentiment scores into recurrent
neural networks alongside price history and technical indicators. GRU reached **R² ≈ 0.95** with
the full feature set; adding sentiment lifted the windowed LSTM from R² 0.63 to 0.89. Regression
and ANN baselines failed because they ignore time.

**Stack:** Python · TextBlob / VADER (NLTK) · LSTM & GRU (Keras) · yfinance · Random Forest, XGBoost, Linear Regression baselines

---

### 🛠️ [Versatile CNC Machine: Pen Plotter, Cutter & Engraver](EEE318-Versatile-CNC-Machine/)
`EEE 318 — Control System 1 Laboratory` · Group 01

One CoreXY machine that plots with a pen, engraves with a laser, and cuts — swap the toolhead
instead of buying three machines. Runs GRBL on an Arduino UNO with a CNC Shield V3, driven by
G-code from Inkscape/UGS for plotting and LaserGRBL for laser work. Engraves cleanly on wood;
fabric cutting, the original target, still leaves rough edges.

**Stack:** Arduino UNO · CNC Shield V3 · GRBL (v0.9 servo fork + v1.1h laser) · A4988 drivers · CoreXY kinematics · Inkscape, UGS, LaserGRBL

---

### ⚙️ [Rewinding of a Single-Phase Induction Motor](EEE206-Single-Phase-Induction-Motor-Rewinding/)
`EEE 206 — Energy Conversion Laboratory` · Group 02

A full teardown and hand-rewind of a 550 W, 4-pole capacitor-start induction motor — 24 slots,
8 main and 4 auxiliary coils wound on a home-made forma of nails and wood. The rebuilt motor was
then characterised through no-load and locked-rotor tests to extract its equivalent circuit
(R₁ = 21.0 Ω, R₂ = 10.67 Ω, X₁ = X₂ = 7.17 Ω, X_M = 140.98 Ω) and torque-speed curve. Total cost ৳5,805.

**Stack:** Squirrel-cage single-phase induction motor · SWG 24 copper · no-load & locked-rotor testing · equivalent circuit modelling

---

### 🔍 [Resistor Detection & Value Calculation via Image Processing](EEE312-Resistor-Detection-Image-Processing/)
`EEE 312 — Digital Signal Processing Laboratory` · Group 06

Finds every resistor in a photo of a mixed component board, reads its colour bands, and computes
its resistance — at any orientation, flipped or not, with multiple resistors in frame. Isolates
resistors by their unique yellowish-brown body colour, then applies per-colour masks to locate
bands. Notably useful for people with colour-vision deficiency.

**Stack:** MATLAB · global thresholding · morphological operations (erosion, dilation, opening, closing) · HSV-adaptive structuring elements · region properties

---

### 📟 [IoT-Based Bangla Smart Notice Board with Clock & Calendar](EEE416-IoT-Bangla-Smart-Notice-Board/)
`EEE 416` · Group 02

A wall-mountable board showing time, the Bangla calendar date, and scrolling notices — **all in
Bangla script** on three 8×32 LED matrices. Bangla glyphs don't exist for dot-matrix hardware, so
every character, digit, month, and weekday was bitmapped by hand. Time syncs over NTP; notices are
pushed from a password-protected web page. Total build cost: **৳2,755**.

**Stack:** ESP8266 NodeMCU · MAX7219 LED matrices · Arduino IDE · NTP · ESP8266WebServer · custom HTML control page

---

### 🔌 [Droop Control in Decentralized AC, Islanded & DC Microgrids](EEE306-Droop-Control-Microgrids/)
`EEE 306 — Power System I Laboratory` · Group 05

Models and compares droop control — decentralized regulation using only local measurements —
across three microgrid architectures in Simulink. The AC model runs cascaded droop → voltage →
current control in the dq0 frame; the islanded model shares load across 500/300/200 kW inverters;
the DC model splits a battery-supercapacitor HESS by frequency using LPF/HPF virtual impedance.

**Stack:** MATLAB/Simulink · dq0 transform · PI control by pole placement · LCL filters · PV + battery + supercapacitor HESS

---

### ⚡ [Complete Electrical Service Design of a Residential Building](EEE414-Electrical-Service-Design-Residential-Building/)
`EEE 414 — Electrical Service Design` · Group 05

Full electrical design of a 10-floor apartment building (4 flats/floor, 1,550 sq ft each) — from
lux-based fixture counts and conduit routing up through switchboards, distribution boards, and the
substation. Includes a 400 kVA transformer, 150 kVA generator, 60 kVAR PFI plant, lift and pump
sizing, a 14-arrestor lightning protection system, and earth pit design.

**Stack:** AutoCAD · BNBC 2020 · PWD reference tables · NFPA 780 (rolling sphere method)

---

### 🔐 [Password-Based Gate Locking System](DLD-Password-Based-Gate-Locking-System/)
`Digital Logic Design (DLD)` · Group 03

A 4-digit password lock built entirely from discrete logic ICs — no microcontroller. Shift
registers store the saved password and the attempt, comparators check them digit by digit, seven
segment displays echo the entry, and a 555-timer lockout disables the keypad for 30 seconds after
four failed retries. Simulated in Proteus, then built on breadboard.

**Stack:** 74194 shift registers · 7485 comparators · 7447 decoders · 4555 demux · 4013 flip-flops · 555 timer · Proteus

---

## Repository layout

```
.
├── EEE206-Single-Phase-Induction-Motor-Rewinding/
├── EEE306-Droop-Control-Microgrids/
├── EEE312-Resistor-Detection-Image-Processing/
├── EEE318-Versatile-CNC-Machine/
├── EEE402-Stock-Market-Prediction-Sentiment-Analysis/
├── EEE404-Assistive-Mobile-Manipulator/
├── EEE414-Electrical-Service-Design-Residential-Building/
├── EEE416-IoT-Bangla-Smart-Notice-Board/
└── DLD-Password-Based-Gate-Locking-System/
```

Every folder contains `README.md` (the summary) and the original project report PDF.

## At a glance

| Project | Course | Domain | Key outcome |
| --- | --- | --- | --- |
| Assistive Mobile Manipulator | EEE 404 | Robotics, computer vision, embedded | Autonomous pick-and-place for visually impaired users |
| Stock Market Prediction | EEE 402 | Machine learning, NLP | GRU model at R² ≈ 0.95 with sentiment features |
| Versatile CNC Machine | EEE 318 | Control systems, mechatronics | One machine plotting, engraving, and cutting |
| Induction Motor Rewinding | EEE 206 | Energy conversion, machines | Motor rewound by hand and fully characterised |
| Resistor Detection | EEE 312 | Digital signal & image processing | Automated colour-band reading at any orientation |
| Bangla Smart Notice Board | EEE 416 | IoT, embedded systems | Bangla-script LED display, NTP-synced, web-controlled |
| Droop Control in Microgrids | EEE 306 | Power systems, control | Equal power sharing across AC, islanded, and DC models |
| Electrical Service Design | EEE 414 | Power systems, building services | BNBC-compliant design for a 10-floor building |
| Password Gate Lock | DLD | Digital logic | 4-digit lock from discrete ICs with timed lockout |

---

*Reports are the original submitted documents; each README is a condensed summary of the work.*
