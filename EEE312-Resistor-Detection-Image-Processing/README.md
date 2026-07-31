# Resistor Detection & Value Calculation from Colour Bands using Image Processing

**Course:** EEE 312 — Digital Signal Processing Laboratory
**Institution:** Department of EEE, Bangladesh University of Engineering and Technology (BUET)
**Section:** C1 | **Group:** 06
**Full report:** [`EEE312_Project_Report_Group_06.pdf`](EEE312_Project_Report_Group_06.pdf)

> *Note: the running header inside the report reads "EEE306 Project Report Group 3" — a leftover
> from the document template. The cover page and filename (EEE 312, Group 6) are correct.*

---

## What this project does

Point a camera at a board full of components and this **MATLAB** program finds every resistor,
reads its colour bands, and prints its resistance value — regardless of how the resistors are
rotated or flipped, and no matter how many are in the frame.

Reading colour bands by eye is slow, subjective, and error-prone — especially for beginners or
anyone with colour-vision deficiency. This automates it.

## Pipeline

**1. Segmentation** — The RGB image is converted to greyscale, then **global thresholding**
separates foreground from background. The result is binarised and inverted (white objects on
black), and **morphological operations** clean up the black artefacts left inside the white
regions.

**2. Adaptive structuring element** — The image is also converted to **HSV** to extract the value
(brightness) channel. Its average drives the choice of structuring element for the morphological
opening — so the pipeline adapts to how bright or dim the photo is. Region properties
(**eccentricity, area, bounding box**) are computed for the surviving objects.

**3. Resistor identification** — Every component is tested with a `maskedYellow` function. A
resistor's yellowish-brown body colour is unique among components on the board — no MOSFET, BJT,
LED, or wire shares it — so body colour alone separates resistors from everything else.

**4. Cropping** — Bounding boxes crop each confirmed resistor out of the original image, and the
detections are drawn back onto the source photo as red rectangles.

**5. Band detection** — Separate colour mask functions (red, black, brown, orange) run over each
cropped resistor. Each returns the positions of matching pixels; everything outside the position
matrix is zeroed. A structure array collects the detected bands and their coordinates.

**6. Orientation handling** — Band coordinates are summed and compared against an empirically
tuned threshold of **250**. A flipped resistor produces a larger coordinate sum than an
unflipped one, letting the program decide reading direction. All four cases are handled:
horizontal flipped/unflipped, vertical flipped/unflipped.

**7. Value calculation** —

```
Resistance = (Band1 Band2) × 10^Band3   ohms
```

## Morphological operations used

| Operation | What it does | Why it's here |
| --- | --- | --- |
| **Erosion** | Shrinks foreground boundaries (min filter over the structuring element) | Removes small objects, separates touching ones |
| **Dilation** | Expands foreground boundaries (max filter) | Closes gaps, rejoins broken parts |
| **Opening** | Erosion → dilation | Noise removal without shrinking real objects |
| **Closing** | Dilation → erosion | Fills small holes, completes contours |

## Results

Verified on 1 kΩ horizontally flipped, 1 kΩ vertical unflipped, a 1 kΩ and 220 Ω pair, and mixed
boards where only 2 of several components were resistors — in each case the resistors were
isolated, boxed, and valued correctly.

## Usage

- Shoot against a **uniform white background** to minimise noise
- Use a **high-resolution camera**; band printing must be clearly legible
- Shoot **perpendicular** to the board to avoid perspective and contrast issues
- **Avoid shadows**
- Calibrated for a small set of standard resistor values

## Limitations

- **Black bands are the weak point** — a phone photo never captures pure black, so the black
  threshold is hard to calibrate and the band is sometimes missed. Tested with three resistor
  values only (1 kΩ, 10 kΩ, and 22 kΩ — the user-manual section lists 220 kΩ for the third).
- Accuracy depends heavily on lighting, reflections, and image noise; the white background is a
  mitigation, not a fix.
- Non-standard colour codes across manufacturers can be misread.
- Overlapping bands and partial band visibility add algorithm complexity.
- Camera quality directly bounds reliability; periodic recalibration may be needed as conditions change.

## Social impact

The team highlights **accessibility** as the clearest benefit — automating colour reading removes
a real barrier for people with **colour blindness or visual impairment** who want to work in
electronics. Beyond that: faster and less error-prone identification for everyone, a visual
teaching aid for electronics education, and easier reuse of salvaged components, which cuts
electronic waste.

## Future work

More robust colour segmentation across lighting conditions and resistor types (carbon film, metal
film, wire-wound); **CNN-based** band recognition instead of hand-tuned thresholds; image
denoising; a **mobile app** that values a resistor straight from the phone camera; a friendlier
UI; and accessibility features such as voice guidance and screen-reader support.

## Team

| Student ID | Contribution |
| --- | --- |
| 2006142 | Image segmentation and component detection — morphological operation algorithm |
| 2006147 | Image segmentation and component detection — component structuring and isolation |
| 2006158 | Segmentation via thresholding and morphology; orientation handling (horizontal, vertical, flipped); value calculation |
| 2006161 | Resistor identification from components; band finding and bounding-box extraction |
| 2006137 | Selection of appropriate morphological operations and structuring element pixel values |

**Course instructors:** Shahed Ahmed (Lecturer, EEE, BUET), Md. Obaidur Rahman (Part-Time Lecturer, EEE, BUET)
