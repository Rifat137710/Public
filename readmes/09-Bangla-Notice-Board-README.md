# IoT-Based Bangla Smart Notice Board with Real-Time Clock & Calendar

**Course:** EEE 416 (January 2025) — Microprocessor & Embedded System Laboratory
**Institution:** Department of EEE, Bangladesh University of Engineering and Technology (BUET)
**Section:** C1 | **Group:** 02
**Full report:** [`EEE416_Project_Report_Group_02.pdf`](EEE416_Project_Report_Group_02.pdf) — includes complete NodeMCU firmware and website source in the appendices.

---

## What this project does

- **Built a wall-mountable digital notice board that displays time, date and scrolling notices
  entirely in Bangla** across three LED dot-matrix panels, with automatic Wi-Fi time sync and
  remote notice updates from a password-protected web page.
- **Closed a real gap.** English LED notice boards are everywhere and Bangla ones are not —
  because **Bangla script does not render on 8×8 matrix hardware out of the box.**
- **Solved that by hand-bitmapping the entire character set** the system uses: each Bangla digit
  as one 8×8 tile, weekdays as two tiles, month names as three, and full notice sentences stored
  as arrays of `uint64_t` — one 64-bit value per glyph.
- **Drove three independent display zones from a single ESP8266,** each panel four chained
  MAX7219 matrices (32×8) — time on top, Bangla calendar date in the middle, scrolling notice on
  the bottom — sharing data and clock pins with separate chip selects.
- **Eliminated manual clock setting** by calling `configTime()` against `pool.ntp.org` over Wi-Fi
  and applying a +6 h Bangladesh Standard Time offset, then converting the fetched Gregorian date
  into the Bangla calendar month-by-month with the correct year-offset rule.
- **Added remote control** through an `ESP8266WebServer` on port 80 behind a password-gated HTML
  page, exposing `/index?value=<id>` to select one of five preloaded Bangla safety notices or
  clear the display.
- **Result — all three zones run synchronised in one unit,** with `scrollOneFrame()` unpacking the
  bitmap array into a column buffer and sliding it across the notice panel one column per loop
  iteration, while the top two panels keep showing live Bangla time and date.
- **Result — built for under ৳3,000** (৳2,755 total), which makes it genuinely deployable in
  schools and public spaces rather than a lab-only demonstration.
- **Result — the main gap is free-text entry.** Notices must be chosen from preloaded messages,
  because supporting arbitrary Bangla text would require bitmapping every character and conjunct
  in the script — beyond one semester's scope. Full Unicode handling, PCB design and a richer UI
  remain open.

## The three displays

| Panel | Shows | ESP8266 CS pin |
| --- | --- | --- |
| Top | Time in Bangla digits, `HH:MM` (e.g. ১৪:৩৫) | D3 |
| Middle | Bangla calendar date, month (আষাঢ়, শ্রাবণ …) and weekday (বুধ, শনি …), sliding right-to-left | D8 |
| Bottom | Scrolling Bangla notice, selected from the web interface | D6 |

Shared pins: `DATA_PIN = D7`, `CLK_PIN = D5`. Each panel is four chained 8×8 MAX7219 matrices (32×8).

## How it works

1. **Wi-Fi + NTP** — The ESP8266 (NodeMCU) connects to Wi-Fi and calls `configTime()` against
   `pool.ntp.org`, then applies a +6 h offset for Bangladesh Standard Time. No manual clock setting.
2. **Gregorian → Bangla calendar** — `showBanglaDate()` converts the fetched date month-by-month
   into the Bangla calendar (day, month, and year, with the −593/−594 year offset rule).
3. **Custom bitmaps** — Bangla digits are one 8×8 tile each, weekdays two tiles, month names three
   tiles. Full notice sentences are stored as arrays of `uint64_t`, one 64-bit value per 8×8 glyph.
4. **Web control** — An `ESP8266WebServer` on port 80 exposes `/index?value=<id>`. Values `136`–`140`
   select one of five preloaded Bangla safety notices; `135` clears the display.
5. **Scrolling** — `scrollOneFrame()` unpacks the bitmap array into a column buffer and slides it
   across the 32×8 notice panel, one column per loop iteration.

**Libraries:** ESP8266WiFi, WiFiManager, MD_Parola, MD_MAX72xx, SPI, TimeLib, Adafruit_GFX, Max72xxPanel.
Developed in the Arduino IDE.

## Web interface

A single self-contained HTML page (Appendix B of the report) with a client-side password gate,
then six buttons that `fetch()` the ESP's IP to trigger notices:

- লাইন মেনে চলুন · আগে নামতে দিন · যাত্রা শুভ হোক · নিরাপদ দূরত্ব বজায় রাখুন · গাড়ি থামবে · Clear

## Bill of materials

| Component | Cost (৳) |
| --- | --- |
| ESP8266 NodeMCU | 420 |
| LED dot matrix (3 × MAX7219, 8×32) | 2,005 |
| Enclosure / design | 180 |
| Power adapter | 150 |
| **Total** | **2,755** |

## What makes it novel

Custom-bitmapped Bangla fonts on low-cost embedded hardware, three synchronised display zones in
one compact unit, internet-synced time with no manual setting, and web-controlled notice updates —
all at under ৳3,000.

## Limitations & future work

The main gap is **free-text entry**: notices must be chosen from preloaded messages, because
supporting arbitrary Bangla text requires bitmapping every character and conjunct in the script —
too large a task for one semester. Also outstanding: proper Bangla Unicode handling, PCB and
custom enclosure design, a richer UI, tighter date/notice synchronisation, and additional
display effects.

## Usage

1. Plug in the adapter and wait for the panels to stabilise (time and date take a moment to sync).
2. Open the control website and log in.
3. Press a notice button — the bottom panel starts scrolling it; the top two keep showing Bangla
   time and date.
4. To reflash, open the box behind the clock and connect over the Type-B port.

## Team

Group 2, Section C1 — Bashir Shahriyer Rafi (2006136) · Md. Rifat Rahman (2006137) ·
Samia Hossain (2006138) · Sami Hasib Khan (2006139)

Work was shared across bitmapping, firmware, debugging, and hardware assembly, with a joint final
assembly.

**Course instructors:** Sadman Sakib Ahbab (Lecturer), Khairul Islam (Lecturer)
