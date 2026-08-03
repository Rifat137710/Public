# clearsar-rfi — physics-aware decomposition for RFI detection in Sentinel-1 quicklooks

Tooling for the problem behind the [ESA Φ-lab **ClearSAR** Track-1](https://challenges.philab.esa.int/portfolio/clearsar-track-1/)
dataset: some annotated radio-frequency-interference boxes in Sentinel-1
quicklook RGBs are invisible to the eye *and* to a standard RGB object detector.

The premise is that this is not primarily a model-capacity problem. It is that
the input is being read as a natural RGB image when it is nothing of the kind,
and that several of the channels interference actually perturbs are never
computed at all.

---

## The one fact that reframes the problem

Per the [Sentinel-1 product spec](https://sentinel.esa.int/en/web/sentinel/user-guides/sentinel-1-sar/data-formats/sar-formats),
quicklooks are power-detected, averaged and decimated, scaled to 8 bit, and for
**dual-polarisation** products composed as:

| channel | contents |
|---------|----------|
| **R** | first polarisation (co-pol — VV, or HH in EW mode) |
| **G** | second polarisation (cross-pol — VH / HV) |
| **B** | average of the absolute values of the two polarisations |

So **B ≈ (R+G)/2 carries no independent information.** The image has *two* real
degrees of freedom, not three, and its two real planes are separate radar
receive channels — a fact no RGB backbone is told.

`scripts/check_composition.py` verifies this on your own copy in seconds. On the
included synthetic data it recovers `B = 0.5000·R + 0.5000·G + 0.00`, R² = 0.9999.

Two consequences drive the whole toolkit:

1. **The polarimetric ratio is the RFI-sensitive channel.** Terrain drives both
   polarisations in a strongly correlated way — scene structure is largely
   common-mode — while interference enters the receiver in one polarisation
   channel only. Differencing in the log domain cancels the scene and keeps the
   interference. (This is the principle behind the published dual-pol
   [RFI Index](https://ieeexplore.ieee.org/abstract/document/9335969).)
2. **Cross-pol sits 8–13 dB lower**, much closer to the noise floor, so a given
   interference power is a large relative bump there and a negligible one in
   co-pol. In an RGB rendering that is a near-**isoluminant chromatic** change,
   which human vision and ImageNet-pretrained CNNs are both poor at.

Measured on the synthetic benchmark: the box-versus-surround z-score of an
*interference-free* box is ~84 in a single polarisation (pure terrain response)
but ~4.5 in the ratio channel. That ~18× terrain suppression is the sensitivity
headroom the un-mixing buys.

---

## Why "ghost" boxes are invisible — five distinct mechanisms

| # | mechanism | what to do about it |
|---|-----------|---------------------|
| a | **Contrast compression.** Interference adds power; visibility depends on interference-to-signal *ratio*, not brightness. The emitter that saturates dark water is 0.2 dB over bright forest. | Work on the background-normalised residual (`directional.detail_image`) |
| b | **Quantisation.** Power detection + multilook + decimation + 8 bit. A sub-dB bump is under one digital number and is gone *per pixel*. | Not gone in aggregate — speckle dithers the quantiser, so integration recovers it |
| c | **The IPF already partly removed it.** RFI mitigation since IPF 3.40 is [deliberately conservative](https://sar-mpc.eu/about/faq/); what survives is a *spectral hole* → altered bandwidth → altered texture at unchanged mean brightness. | Speckle-statistics and spectral features (`speckle`, `spectral`) — no brightness method can reach this |
| d | **Polarisation masking.** | The ratio channel (`unmix`) |
| e | **The label may not be image-derived.** Sentinel-1 carries RFI annotations from echo-domain detection, and MPC screening notes weak RFI of small extent is not always reported. | Some boxes are genuinely unrecoverable from a PNG. Quantify rather than chase — see `triage_boxes.py` |

---

## What survives into a quicklook, and what does not

| information axis | available? |
|---|---|
| Polarisation diversity (2 channels) | ✅ the only signal diversity left |
| Spatial anisotropy / orientation / periodicity | ✅ |
| Local speckle statistics | ✅ degraded by multilook + 8 bit |
| Acquisition geometry (subswath / burst) | ✅ inferable |
| Temporal | ✅ if you fetch the stack |
| Interferometric phase | ❌ gone at detection |
| Range spectrum / sublooks | ❌ gone |
| Doppler / azimuth spectrum | ❌ gone |
| Absolute calibration, full dynamic range | ❌ gone |

**Sublook and subband decomposition — the textbook answer to "decompose the SAR
signal" — is therefore not available on quicklooks.** [Multi-chromatic
analysis](https://www.semanticscholar.org/paper/dbeb38d8c5fabc0ab4a1031e42fec05a181d7120)
and [spatial-spectral chromatic coding of interference](https://arxiv.org/abs/2509.08693)
both need SLC data. If you want them, pull SLCs for a subset of your hardest
scenes and use them to establish which boxes carry any quicklook signature at
all.

---

## Install and run

```bash
pip install -r requirements.txt

# 0. Verify what your channels actually contain, and fit the speckle model.
python scripts/check_composition.py --images /path/to/clearsar/train/images -n 40

# 1. Measure every annotated box against control boxes; find the ghosts.
python scripts/triage_boxes.py \
    --images /path/to/clearsar/train/images \
    --annotations /path/to/clearsar/train/annotations.json \
    --out triage.csv

# 2. Calibrate the detectability floor of the product itself.
python scripts/calibrate_sensitivity.py --out sensitivity.csv

# 3. Export the multi-channel feature stack for detector training.
python scripts/build_features.py --images .../images --out features/ --workers 4
```

No real data yet? `python scripts/make_demo_dataset.py --out demo/ -n 12`
builds synthetic quicklooks composed exactly per the spec, with a COCO JSON.

`scripts/triage_boxes.py` accepts COCO JSON, YOLO `.txt`, Pascal-VOC XML or CSV
— the loader sniffs the layout.

---

## The triage output

For every box it measures contrast in both polarimetric channels and their
ratio, departure of local speckle statistics from the fitted model, Radon
matched-filter SNR of any linear structure, and block-wise spectral anisotropy —
then repeats all of it on **control boxes** of the same size distribution placed
where nothing is annotated.

The controls matter. They carry the null distribution of every metric *on this
data*, so thresholds are empirical rather than asserted; whatever speckle
correlation and terrain texture do to a z-score, they do to the controls too.

Boxes are then attributed to the mechanism that makes them findable:
`brightness` → `polarimetric` → `directional` → `statistical` → `spectral` →
`none`. **The `none` bucket is a label-noise estimate for this product level**,
and it belongs in your model card next to any recall number.

On the 12-scene demo set with known injection levels, verdicts land exactly
where they should:

```
injected_db  brightness  none  polarimetric
0.2                   0     2             1
0.5                   0     1             2
1.0                   0     0             2
3.0                   0     0             2
8.0                   1     0             1
```

Everything ≥1 dB is recovered, almost entirely through the **polarimetric ratio
rather than brightness** — only the 8 dB patch is visible as brightness at all.
One 0.2 dB case was recovered despite the interference moving the 8-bit image by
**zero digital numbers** across its footprint.

---

## Calibrating the floor

`calibrate_sensitivity.py` injects interference at a known interference-to-signal
ratio into synthetic quicklooks built with the same detection, multilooking,
quantisation and B=(R+G)/2 composition as the real product.

The measurement is **paired**: each scene is generated twice from one speckle
realisation, with and without the interference, and every metric is compared to
its own interference-free twin at the identical box. This is not a detail — raw
box contrast is dominated by whatever terrain lies under the box, so an unpaired
sweep measures terrain and not sensitivity. That mistake is easy to make and it
silently inflates every number.

It reports, per morphology, the median digital-number change the interference
actually caused and the fraction of footprint pixels the quantiser left
untouched, alongside the win rate of each metric. Rows where the image barely
moved but a metric still fires are detections of signal absent from most pixels.

### Measured results (3 morphologies × 9 levels × 4 repeats, cross-pol injection)

**Terrain baseline** — each metric on an interference-free box, i.e. pure
terrain response:

| morphology | z (co-pol) | z (cross-pol) | **z (ratio)** |
|------------|-----------:|--------------:|--------------:|
| patch      | 38.6 | 43.3 | **1.4** |
| periodic   | 24.4 | 27.7 | **1.6** |
| stripe     | 45.0 | 48.2 | **2.8** |

A **15–30× terrain suppression**, and it is the whole ballgame: the interference
has to out-compete that baseline, not the speckle floor.

**Win rates** (fraction of scenes where the injected metric beat its own
interference-free twin by ≥1.15×):

| morphology | dB | median ΔDN | pixels unchanged | z co-pol | z cross-pol | **z ratio** | Radon (ratio) |
|---|---:|---:|---:|---:|---:|---:|---:|
| patch | 0.2 | 0.0 | 66% | 0.00 | 0.00 | **1.00** | 0.00 |
| patch | 1.0 | 2.0 | 2% | 0.00 | 0.00 | **1.00** | 0.25 |
| patch | 8.0 | 21.0 | 0% | 0.00 | 0.75 | **1.00** | 1.00 |
| stripe | 0.5 | 1.0 | 11% | 0.00 | 0.00 | **0.75** | 0.25 |
| stripe | 2.0 | 5.0 | 0% | 0.00 | 0.25 | **0.75** | 1.00 |
| periodic | 0.5 | 1.5 | 15% | 0.00 | 0.25 | **1.00** | 0.00 |

Three things to take from this:

1. **Co-pol never fires — at any level.** The injection is cross-pol only, so
   this is the negative control, and it passes cleanly. Any co-pol response
   would have meant the measurement was picking up a scene-wide artefact.
2. **Raw cross-pol contrast is nearly useless**, reaching only 0.5–0.75 even at
   8 dB, because terrain swamps it. This is the quantitative reason a detector
   fed the plain RGB struggles: the signal is there, but the channel it is
   presented in has a terrain background 30× larger than the effect.
3. **The ratio channel detects a patch at 0.2 dB** — where the median digital
   number change is **zero** and two thirds of the footprint pixels are
   bit-identical to the interference-free scene.

Directional integration is complementary rather than better: it wins on stripes
(where it pools thousands of pixels) and loses on compact patches. Which of the
two carries a given box depends on morphology and on the terrain underneath, so
the triage measures both.

Caveat on the printed "detection floor" line: with only 4 repeats a single miss
drops a win rate below 1.0, so the reported floor is noisy at the level of one
sweep step. Raise `--repeats` before quoting it.

---

## Feature stack

`features.FEATURE_NAMES` defines 17 planes: raw R/G/B, the un-mixed dB channels
and their ratio, blue-channel residual, PC2, background-removed details, speckle
CV/kurtosis departures, oriented-filter responses, and spectral anisotropy /
peak-z.

**Planes 0–2 are the untouched R/G/B**, so an RGB-pretrained backbone can be
fine-tuned by inflating its stem convolution and seeding the extra input
channels at zero — training then starts from exactly the pretrained behaviour.

Two-stage detection is worth trying before end-to-end training: use the
directional and statistical maps to generate high-recall candidate regions, then
classify candidates with a small CNN. Asking a detector to learn a 0.2 dB
anisotropic texture change from ~3k boxes is a much harder ask than giving it
the transform.

---

## What this does not do

* No SLC / raw-echo processing — see the caveat above.
* No multitemporal stacking. This is likely the strongest remaining lever
  (scene persistent = low-rank, RFI transient = sparse; see the published
  [time-series RFI extraction](https://ieeexplore.ieee.org/document/9606769/) and
  [SSIM-based screening](https://ieeexplore.ieee.org/document/10959716/) work,
  and [REACTIV](https://github.com/elisecolin/REACTIV) for HSV coding of a
  stack). Quicklooks for the same relative orbit are free.
* No subswath/burst geometry test. RFI respects subswath and burst boundaries
  and terrain does not, which is a strong and nearly free discriminator.
* `stripe_snr` treats adjacent Radon bins as independent, so its SNR is an
  optimistic bound. Read it against the controls, not as a Gaussian sigma.

## Tests

```bash
python tests/test_pipeline.py     # also runs under pytest
```

11 tests, asserting real behaviour against synthetic ground truth: closed-form
speckle moments, spec-conformant composition, amplitude-vs-intensity
identification, terrain suppression by the ratio channel, stripe-layer recovery,
sub-quantiser detection, and stack integrity.

---

## Addendum: acquisition geometry (`clearsar_rfi.geometry`)

Analysis of 12 annotated ClearSAR scenes turned up the most exploitable
structure in the labels: **RFI boxes are quantised to Sentinel-1 IW sub-swath
boundaries.** Column-profile seams sit at ~0.35 and ~0.69 of image width (found
in 12/12 scenes), box widths cluster at 1/3 and 2/3, and ~70% of box x-edges
land on a seam or the image edge.

Measured consequences:

| claim | result |
|---|---|
| box x-extent matches a sub-swath union | median 1-D IoU **0.80**; 70% ≥0.5 |
| snapping a jittered detector's x-edges to seams | **+3%** mean IoU at 15–25 px jitter |
| azimuth interval by thresholding a 1-D profile | **fails** — median y-IoU 0.26; 22% recall @IoU 0.25 |

So: the x-half of the problem is close to solved by geometry, and the azimuth
half is not solved at all by a hand-built statistic. `propose_boxes` is retained
as a documented weak baseline, not a detector. Terrain varies along azimuth just
as interference does, and thresholding an excursion structurally cannot emit a
box covering most of a sub-swath — which is what the large annotations are.

The implied architecture: a **1-D sequence model over azimuth, run per
sub-swath**, taking the physics feature planes collapsed across range. That
respects the label geometry exactly while learning the azimuth signature instead
of guessing it.

### Warning about annotated preview renderings

Some ClearSAR previews circulate with the boxes drawn into the pixels. Files
like that are re-renders, not the product, and measurably degraded:

* annotation rectangles burned in as pure `(255,0,0)` (0.3–1.3% of pixels)
* `B = (R+G)/2` **does not hold** — B is negatively correlated with R even after
  masking the overlay, so the un-mixing in `clearsar_rfi.unmix` does not apply
* local CV 0.013–0.07 where a 4-look quicklook should be ~0.26 — the speckle has
  been smoothed away
* 9–39% of horizontally adjacent pixels bit-identical (resampling)
* the **cross-pol (G) channel is quantised to a 3-DN step**, using only 55–93 of
  256 levels, versus 133–229 for R

That last two points matter most: the sub-quantiser recovery demonstrated in
`calibrate_sensitivity.py` depends on speckle dithering the quantiser. Smooth
the speckle away and coarsen the step 3×, and faint interference is *erased*
rather than merely hidden. Run `check_composition.py` on any copy of the data
before trusting it, and work from the original dataset PNGs.
