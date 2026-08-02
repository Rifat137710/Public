# Password-Based Gate Locking System

**Course:** Digital Logic Design (DLD) — Final Project
**Institution:** Department of EEE, Bangladesh University of Engineering and Technology (BUET)
**Section:** C1 | **Group:** 03
**Full report:** [`EEE_304_Project_Report_Group_03.pdf`](EEE_304_Project_Report_Group_03.pdf)

> *Note: the report's cover page carries an "EEE 304 / Power Electronics Laboratory" header from
> the department template, but the project itself is a digital logic design build — the filename
> and all content are DLD.*

---

## What this project does

- **Built a working 4-digit password lock entirely from discrete digital logic ICs** — no
  microcontroller, no firmware, no code. Every function is combinational or sequential logic
  wired by hand.
- **Replaces a mechanical lock,** which can be copied, broken or lost, with a digital equivalent
  that demonstrates combinational and sequential logic working together in one practical system.
- **Encodes each of 4 decimal digits to 4 bits,** making a **16-bit** password that is stored
  twice — once as the saved password, once as the attempted entry — and compared digit by digit.
- **Built the keypad encoder by hand** from 10 push buttons and 4 OR gates, forming a
  decimal-to-BCD encoder rather than using an off-the-shelf encoder IC.
- **Used 8 × 74194 shift registers for storage** (4 for the saved password, 4 for the attempt), a
  **4555** demultiplexer to steer each keypress into the correct register, **4013** D flip-flops
  as a counter selecting the active bank, and **8 × 7485** 4-bit magnitude comparators for
  digit-wise matching.
- **Added a brute-force lockout:** a 2-bit counter permits 4 successive retries, after which a
  **555 timer** (R = 10 kΩ, C = 470 µF ⇒ T ≈ 30 s) disables keypad input entirely.
- **Verified in simulation before building.** The design was simulated in **Proteus** first, then
  built on breadboards from the verified schematic.
- **Result — the lock behaves correctly.** After saving a 4-digit password, many wrong and right
  combinations were entered; the gate opened **only on an exact match**, lighting the yellow LED,
  while mismatches lit the red LED and raised the alarm.
- **Result — lockout confirmed.** Pressing reset four times in a row correctly triggered the timed
  lockout, blocking all further keypad input for the full delay period.
- **Result — known limits.** The system needs continuous mains power with no battery backup, a
  static code stays guessable if it is never changed, it is scaled for homes and small offices
  rather than large installations, and there is no remote access or monitoring.

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
