# ClearSAR Track-1 — session handoff

Paste this whole file into a new chat as the first message. It carries every
measurement made so far, every dead end (so they are not repeated), and the
prioritised next actions.

---

## 1. The problem

ESA Φ-lab **ClearSAR Track-1**. Detect radio-frequency interference (RFI) as
bounding boxes in Sentinel-1 quicklook RGB PNGs.

- 3,154 training images + 786 test, 9,288 boxes, single class `RFI`
- Images ~520 × 341 px, COCO annotations, metric **mAP@[0.50:0.95]**
- Dataset ships **only** the PNGs, `instances_train.json`, a README, a starter
  notebook, and a STAC file manifest. The manifest has no acquisition metadata —
  every geographic bbox is `0,0,0,0`, `datetime` is the upload time. There is no
  orbit, polarisation, geolocation or product ID anywhere.

**Original question:** many boxes are labelled RFI but are invisible to the eye
and undetected by YOLO. Are they labelling mistakes, and how can they be found?

---

## 2. Current pipeline and scores

YOLO11-L (ultralytics, anchor-free), `imgsz=1024`, `batch=8`, 100 epochs,
`single_cls=True`, deterministic stratified split seed 42 → **2523 train / 631
val** (reproduced and verified). Inference `conf=0.001, iou=0.6, max_det=300`.

| run | mAP | AP50 | AP75 | AP_s | AP_m | AP_l | AR100 | AR_s | AR_m | AR_l |
|---|---|---|---|---|---|---|---|---|---|---|
| E01 RGB plain | 0.3940 | 0.6782 | 0.4079 | 0.3540 | 0.4591 | 0.2707 | 0.6310 | 0.5907 | 0.6646 | 0.7007 |
| E01 RGB TTA | 0.4014 | 0.6820 | 0.4129 | 0.3571 | 0.4652 | 0.3000 | 0.6444 | 0.5971 | 0.6803 | 0.7457 |
| E04 composite plain | 0.3837 | 0.6663 | 0.3889 | 0.3411 | 0.4481 | 0.2899 | 0.6168 | 0.5719 | 0.6517 | 0.7079 |
| E04 composite TTA | 0.3887 | 0.6709 | 0.3993 | 0.3406 | 0.4589 | 0.3049 | 0.6299 | 0.5718 | 0.6797 | 0.7225 |

E04 replaced RGB with `[cyan_excess, horizontal_structure(gray), luminance]`.
**It is worse: −0.0149.**

---

## 3. THE KEY DIAGNOSIS — read this first

**The model is localisation-limited, not detection-limited.**

```
AP75 / AP50 = 0.601          well-localised COCO detectors run 0.75-0.80
=> effective vertical error ~1.4 px on a median 10 px-tall box

reaching e = 1.0 px  ->  mAP ~0.443
reaching e = 0.5 px  ->  mAP ~0.569
integer-quantised labels alone cap mAP at ~0.57
currently at 0.394  =>  ~0.17 of headroom, NOT blocked by label precision
```

Second, the largest single inefficiency:

```
         AP      AR100     gap
small  0.354     0.591    0.237
medium 0.459     0.665    0.205
large  0.271     0.701    0.430   <- highest recall, lowest precision
```

Large boxes are **found reliably and scored terribly**. The likely cause is
fragmentation: one tall RFI event emits several partial boxes that do not
overlap each other enough for NMS at `iou=0.6` to merge, giving 1 TP + several
FP. That is a post-processing problem, not a model problem.

`AR_small = 0.591` means the "invisible" boxes are already being recovered
somewhere in the top-100 detections. **Detection was never the bottleneck.**

---

## 4. Are the invisible boxes labelling mistakes? — No

Three independent tests against **size-matched** background cutouts that avoid
every annotation:

| test | AUC | note |
|---|---|---|
| peak response inside box vs size-matched random box | **0.720 ± 0.055** | z = 4.0 vs the no-information value 0.50 |
| response at box centre, at the box's own scale | 0.733 | 44 boxes, 264 controls |
| best of luminance / polarisation, per box | 0.72–0.76 | 81 boxes, 972 controls |

- 78% of boxes beat the majority of their controls; 43% beat >90%.
- **11% beat <10% of their controls** — the genuine error candidates.
- A double dissociation exists (`step` works on block RFI, `period` on pulsed
  RFI) that random labels cannot produce.

**But "not a mistake" ≠ "visible".** Likely reasons a correct box shows nothing:
ESA detects RFI from SLC/GRD noise-measurement metadata rather than from the
quicklook; box geometry is quantised to sub-swaths so a small event gets a large
box that is mostly clean; IPF ≥ 3.40 may have mitigated the interference before
the quicklook was rendered. None of these is verifiable with the released files.

### No local appearance feature finds them

Split boxes by how visible they are in luminance:

```
group                              n    luminance   polarisation
INVISIBLE in luminance (low 3rd)  22        0.242          0.479   <- chance = 0.500
middle third                      24        0.697          0.847
clearly visible (top 3rd)         35        0.977          0.931
correlation(luminance, polarisation) = +0.658
```

The polarisation channel scores **at chance** on exactly the boxes luminance
cannot see, and correlates 0.66 with luminance overall — it finds the *same*
boxes, just more crisply. Eight features tested (luminance, polarisation
contrast, dB ratio, periodicity, edge step, chroma, multi-scale top-hat,
cyan-excess); all fail on the invisible subset.

### The only remaining cue: azimuth context

RFI is an event in time, and time maps to image rows.

```
distance to nearest sibling box in azimuth (8,124 boxes, 1,956 images)
  real annotations : median 0.0379 of image height
  random placement : median 0.0856              -> 2.3x tighter than chance
  sibling within 2% of height: real 38%  vs chance 18%
  sibling within 5% of height: real 56%  vs chance 35%     (~1.6x lift)
  sibling at SAME azimuth in a DIFFERENT sub-swath: 25%

50% of invisible boxes have a clearly-visible sibling within 5% azimuth
(visible boxes: 48% — the cue is equally available to both)
```

This is the only signal that does not depend on the box's own pixels.

---

## 5. Dataset geometry (all 9,288 boxes — solid, full-dataset stats)

```
height   q05 4   q25 7   median 10   q75 13   q95 155 px
width    bimodal: 33% under 10% of image width; 46% exactly one sub-swath (~165 px)
aspect   median 8.4:1, 45% exceed 10:1, max 88 (safely under ultralytics ar_thr=100)
COCO size classes: small 48.8%, medium 43.0%, large 8.2%
boxes/image: median 2, mean 2.97, q90 6, max 28;  34 images have ZERO boxes
all box coordinates are integers
IW sub-swath seams at 0.338 and 0.688 of width
31.3% of boxes have BOTH x-edges within 2% of a seam
```

## 6. SAR physics measured on real quicklooks

**The background is terrain-clutter-limited, not speckle-limited.**

```
sigma(h,w) ~ sigma_pixel * (h*w)^(-alpha/2),  fitted alpha = 0.426
                                  (alpha_azimuth 0.588, alpha_range 0.306)
independent pixels would give alpha = 1.0
a 4x12 window averages 48 px and reduces noise by 1.07x  -- essentially nothing
a median 10x138 box is worth ~24 independent samples, not 1380
```

**The clutter is violently non-Gaussian and its tail depends on scale.** For the
magnitude of the azimuth top-hat, `q99.9 / MAD-sigma` runs 33 at h=4 px down to
13 at h=43 px, against 5.5 for a half-normal. A MAD z-score is therefore *not*
comparable across window sizes — the smallest scale wins every argmax.

**Feature ablation** (81 boxes, 972 size-matched controls, AUC):

```
h-struct( (g-r)/(g+r+1) )    0.762   <- best
h-struct( cyan_excess )      0.735
h-struct( g-r )              0.733
E04 ch0  cyan_excess         0.718   <- currently used
E04 ch1  h-struct(gray)      0.680   <- currently used
(g-r)/(g+r+1)                0.607
dB ratio R-G                 0.603
g - r                        0.553
h-struct( dB ratio )         0.387   <- worse than chance
```

**The blue channel is not the mean of the two polarisations.** Regressing per
image gives `B ≈ -1.086*R + 0.988*G + const`, R² = 0.62 — it already carries
polarisation-difference information, contrary to the Sentinel-1 spec wording.

---

## 7. Dead ends — do NOT repeat these

| tried | result |
|---|---|
| Hand-built classical detector | 4 versions. Best: P 20.9% / R 20.5% at IoU 0.25, 7% at IoU 0.5, on a 7-image blind test. Rebuilding it for correct object granularity made it **5× worse** (P 4.2%). Abandon. |
| Dropping the invisible boxes | They are real (AUC 0.72) and the official test GT contains them. Dropping caps recall at ~0.77 and mAP near 0.31. |
| dB / log domain | `h-struct(dB ratio)` = 0.387, worse than chance, vs 0.762 for normalised linear contrast. RFI is *additive* power; dB is matched to *multiplicative* terrain, and the log amplifies quantisation noise (G is quantised at 3 DN). |
| Anchor refitting | Irrelevant — YOLO11 is anchor-free. (Would have applied to the starter pack's Faster R-CNN, where only 4.9% of GT can reach IoU 0.7 with default anchors.) |
| Snapping predicted x-edges to sub-swath seams | Only 31% of boxes have both edges on a seam, and a 3 px x-error costs ~4% IoU where the same y-error costs ~46%. Not worth it. |
| E04 physics composite | Measured −0.0149. The channel is r=0.66 redundant with luminance. |
| Larger `imgsz`, ensembling | User tried repeatedly; no gain. Explanation: upsampling a 520 px source adds no information. |
| 5-channel RGB+physics | Predicted near-neutral for the same redundancy reason. Low priority. |

### Config bug found

`mosaic=1.0` with `scale=0.5` silently discards **6.5% of boxes** (ultralytics
`box_candidates`, `wh_thr=2`) and crushes the median box to 4.9 px at
`imgsz=1024`.

---

## 8. Next actions, in priority order

**Free, no retraining — do these first:**

1. **NMS / Weighted Box Fusion sweep** on the existing val predictions. Try
   `iou` from 0.4 to 0.75 and WBF instead of NMS. Directly targets the
   0.43 AP_large gap. Highest expected movement of anything on this list.
2. **Azimuth-consistency re-ranking** — boost low-confidence detections that
   share azimuth with a high-confidence one. mAP integrates precision over
   recall, so promoting a true positive raises AP directly. This is the only
   untested mechanism that addresses invisible boxes.

```python
def azimuth_rerank(dets, img_h, tol=0.05, boost=1.6, anchor_conf=0.5):
    """Boost low-confidence detections sharing azimuth with a confident one."""
    from collections import defaultdict
    by_img = defaultdict(list)
    for d in dets:
        by_img[d["image_id"]].append(d)
    out = []
    for iid, ds in by_img.items():
        H = img_h[iid]
        anchors = [d for d in ds if d["score"] >= anchor_conf]
        for d in ds:
            yc = d["bbox"][1] + d["bbox"][3] / 2
            if d["score"] < anchor_conf and any(
                    abs((a["bbox"][1] + a["bbox"][3] / 2) - yc) / H < tol
                    for a in anchors):
                d = {**d, "score": min(d["score"] * boost, 0.999)}
            out.append(d)
    return out
```

**Retraining — the real lever:**

3. **Add a P2 detection head (stride 4)**: `YOLO('yolo11-p2.yaml')`. This is
   *not* the same as raising `imgsz`. Larger `imgsz` interpolates a 520 px
   source; a P2 head adds a finer prediction grid at the network's own feature
   resolution. Half the boxes are 10 px tall — 2.5 cells at stride 8, 5 cells at
   stride 4.
4. **Reweight the loss toward regression**: `box=10.0, dfl=2.5`
   (defaults 7.5 / 1.5). There is AP50 to spare and AP75 to gain.
5. **Fix the augmentation**: `mosaic=0.5, scale=0.25, close_mosaic=30`.
6. **Keep TTA** — +0.0074 for free at inference.

**Optional, if the composite line is revisited:** swap the E04 channel for the
measured best.

```python
def physics_composite(rgb):
    a = rgb.astype(np.float64)
    r, g = a[..., 0], a[..., 1]
    pol = (g - r) / (g + r + 1.0)          # normalised polarisation contrast
    return np.stack([to_uint8(pol),
                     to_uint8(horizontal_structure(pol)),
                     to_uint8(a.mean(2))], axis=-1)
```

---

## 9. Evidence strength — do not over-trust the weak numbers

| claim | basis | strength |
|---|---|---|
| Box geometry, size classes, azimuth clustering, seam quantisation | all 9,288 boxes from `instances_train.json` | **solid** |
| AP/AR breakdown and the localisation diagnosis | official pycocotools on the 631-image val fold | **solid** |
| Clutter scaling α = 0.426, tail ratios | 7–15 real quicklooks | good |
| Feature AUCs, visibility split | **81 boxes from 15 uploaded images** | directional only |
| "50% of invisible boxes have a visible sibling" | n = 30 | weak, a lead |
| Blind detector evaluation | 7 images, 3 of which had been seen earlier | weak |

## 10. Assistant errors made and corrected during the session

Listed so they are not re-derived: claimed there was no polarimetric RFI
signature (wrong — it is in periodic structure); diagnosed granularity as the
dominant detector error (wrong — fixing it made things 5× worse); recommended
anchor refitting (wrong model family); recommended the dB domain throughout
(measured worse than linear); hypothesised label noise was the mAP ceiling
(wrong — ~0.17 of headroom remains); derived `cyan_excess ≈ 0.75(G−R)` from
`B = (R+G)/2` (wrong — the actual correlation is 0.37).
