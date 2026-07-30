# Password-Based Gate Locking System

**Course:** Digital Logic Design (DLD) — Final Project
**Institution:** Department of EEE, Bangladesh University of Engineering and Technology (BUET)
**Section:** C1 | **Group:** 03
**Full report:** [`DLD_Project_Report_Group_03.pdf`](DLD_Project_Report_Group_03.pdf)

> *Note: the report's cover page carries an "EEE 304 / Power Electronics Laboratory" header from
> the department template, but the project itself is a digital logic design build — the filename
> and all content are DLD.*

---

## What this project does

A 4-digit password lock built **entirely from discrete digital logic ICs** — no microcontroller,
no firmware. The user sets a 4-digit password, and the circuit compares any later entry against
it bit by bit. A match lights the yellow LED and opens the gate; a mismatch lights the red LED
and raises an alarm. Repeated failed attempts lock the keypad out entirely.

Mechanical locks can be copied, broken, or lost. This is the digital alternative, demonstrating
combinational and sequential logic working together in one practical system.

## How it works

Each of the 4 decimal digits is encoded to 4 bits, so a password is **16 bits** — stored twice
(the saved password and the attempted entry) and compared digit by digit.

| Block | Implementation |
| --- | --- |
| **Keypad / encoder** | 10 push buttons (0–9) with 4 OR gates forming a decimal-to-BCD encoder, built by hand rather than using an encoder IC |
| **Storage** | 8 × **74194** shift registers — 4 hold the saved password, 4 hold the user's attempt |
| **Input routing** | **4555** demultiplexer automatically steers each keypress to the correct register; **4013** D flip-flops act as a counter selecting which register bank is active |
| **Comparison** | 8 × **7485** 4-bit magnitude comparators, one per digit position. All `A = B` outputs high (plus all 4 digits entered) ⇒ final AND gate goes high |
| **Display** | **7447** BCD-to-seven-segment decoders driving 4 common-anode displays, one per digit |
| **Lockout** | A reset button allows 4 successive retries, counted by a 2-bit counter; after that a **555 timer** (R = 10 kΩ, C = 470 µF ⇒ T ≈ 30 s) disables keypad input |
| **Output** | Yellow LED = password matched · Red LED = mismatch + alarm |

The design was first simulated in **Proteus**, then built on breadboards from the verified schematic.

## Testing

The team reset the system, saved a 4-digit password, then entered many wrong and right
combinations. The gate opened only on an exact match. Pressing reset four times in a row
correctly triggered the timed lockout, blocking further input for the delay period.

## Bill of materials (৳)

| Component | Unit | Qty | Total |
| --- | --- | --- | --- |
| AND / OR / NOT gates | 20 | 8 | 160 |
| Resistors (1 K, 2 K, 5 K) | 1 | 30 | 30 |
| Capacitors (10 µ, 100 µ, 470 µ) | 7 | 10 | 70 |
| Push buttons | 15 | 6 | 90 |
| Flip-flops | 36 | 5 | 180 |
| Shift registers | 40 | 8 | 320 |
| Comparators | 36 | 5 | 180 |
| Decoder | 46 | 5 | 230 |
| BCD to 7-segment decoder | 46 | 5 | 230 |
| Common-anode 7-segment display | 18 | 5 | 90 |
| LEDs | 5 | 40 | 200 |
| Jumper wires (box) | 150 | 4 | 600 |
| Breadboards | 150 | 15 | 2,250 |

## Limitations

Needs continuous mains power (no battery backup); a static code stays guessable if never changed;
scaled for homes and small offices rather than large installations; and there is no remote access
or monitoring.

## Future work

IoT remote control, a companion mobile app for entry and notifications, one-time / dynamically
generated passwords instead of a static code, and biometric authentication (fingerprint or facial
recognition) as a second factor.

## Team

Sadia Israt Oishe (2006152) · Meharab Hossen Bappy (2006154) ·
Chowdhury Blossom Ibne Razzaque (2006156) · Md. Rifat Rahman (2006137)

**Course instructors:** Khairul Islam, Md. Meherab Hossain
