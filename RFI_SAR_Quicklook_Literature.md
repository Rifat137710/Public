# RFI Detection in SAR RGB Quicklook Imagery — Literature Survey

**Topic:** Radio Frequency Interference (RFI) image preprocessing and bounding-box / localization
techniques for SAR RGB quicklook (preview) images.
**Compiled:** 2026-07-27

---

## 0. How to read this document

The literature splits into **four layers**, and it matters which one a paper sits in, because the
preprocessing and the detection head are completely different:

| Layer | Input domain | Typical output | Relevance to "RGB quicklook + bounding box" |
|---|---|---|---|
| **A** | RGB quicklook / preview PNG (low-res browse image) | image-level label, tile label, mask, box | **Direct hit** |
| **B** | Level-1 SLC / GRD amplitude image | mask, index map, geolocated source | Close — preprocessing transfers |
| **C** | Raw echo / Level-0, via STFT → time–frequency spectrogram | **bounding boxes** (SSD/YOLO), masks | Box machinery transfers, input domain does not |
| **D** | Radio astronomy waterfall plots, wideband spectrum sensing | boxes/masks | Architectural donor only |

The single most important structural fact in this field: **almost nobody publishes true bounding-box
detection directly on RGB quicklooks.** Layer A work is overwhelmingly *classification* (does this
tile have RFI?) or *semantic segmentation* (which pixels are RFI?). The bounding-box detectors
(SSD, YOLO variants) live in Layer C on spectrograms. If you are building box detection on
quicklooks, you are combining Layer A data with Layer C heads — that gap is the novelty, and
Section 6 lists the papers you would cite for each half.

**Access note:** this environment's egress policy blocked every publisher host (arxiv.org,
mdpi.com, ieeexplore, nature.com, pmc.ncbi.nlm.nih.gov, researchgate, semanticscholar, github).
Everything below was assembled from search-index metadata and abstracts. Full URLs are given for
every item so you can pull the PDFs yourself. Where a detail could not be verified from the
abstract, it is explicitly marked **[unverified]**.

---

## 1. LAYER A — Direct: RFI detection on SAR quicklook / preview images

These are the core papers. Read these first.

### A1. A Radio Frequency Interference Screening Framework — From Quick-Look Detection Using Statistics-Assisted Network to Raw Echo Tracing
**Shen et al., *Remote Sensing* 16(22):4195, Nov 2024.**
🔗 https://doi.org/10.3390/rs16224195 · https://www.mdpi.com/2072-4292/16/22/4195
🔗 Dataset/code: https://github.com/JyuanShen/QLDecN_Dataset

**Why it matters:** the closest published work to "detect and localize RFI in a quicklook." It is
the reference architecture for the tile-classification + sliding-window localization pattern.

- **Preprocessing:** Sentinel-1 SLC **preview/quick-look images** cropped into single-frame slices.
  Dataset built from **50 SLC product preview images** expanded by augmentation to **7,580 images
  per class** (2 classes), split 4:1 train/test.
- **Architecture — QLDecN:** residual-backbone classifier that **fuses image histogram statistics
  as an auxiliary input branch** alongside the CNN feature path. This statistics-assisted design is
  the paper's main contribution — RFI shifts the grey-level distribution in a way a pure spatial
  CNN under-uses.
- **Localization:** no learned box regressor. Instead a **sliding-window scan over the full
  quicklook** with an **error-tolerant aggregation strategy** to convert per-slice classifications
  into RFI regions across the whole quick-look. This is effectively weak box localization.
- **Result:** 98.29% slice classification accuracy on the test set.
- **Pipeline scope:** quick-look → SLC → raw echo tracing (screening cascade).

### A2. Intelligent Detection and Segmentation of Space-Borne SAR Radio Frequency Interference
**Zhao, J.; Wang, Y.; Liao, G.; Liu, X.; Li, K.; Yu, C.; Zhai, Y.; Xing, H.; Zhang, X.
*Remote Sensing* 15(22):5462, 2023.**
🔗 https://ui.adsabs.harvard.edu/abs/2023RemS...15.5462Z/abstract
🔗 https://www.mdpi.com/2072-4292/15/22/5462

**Why it matters:** two-stage detect-then-segment directly on **Sentinel-1 RFI-affected quick-look
images**. The best template for a fast screening head + a precise localization head.

- **Stage 1 (detection / presence):** improved **MobileNet** where some inverted-residual blocks are
  replaced by **Ghost blocks** → parameter reduction, **6.1 ms inference per image**. Built for
  operational throughput.
- **Stage 2 (segmentation / localization):** **SISNet (Smart Interference Segmentation Network)**,
  built on **U²-Net**, with (a) VGG-block convolutions replaced by **residual convolutions**,
  (b) **attention mechanisms**, (c) a modified **RFB (Receptive Field Block)** module for multi-scale
  context — RFI stripes span wildly different widths.
- **Result:** **mIoU 87.46%** average, pixel-level, on quick-look images.
- Masks are trivially convertible to bounding boxes via connected components — this is the most
  practical route to boxes on quicklooks today.

### A3. Deep Learning for RFI Artifact Recognition in Sentinel-1 Data
**Chojka, A.; Artiemjew, P.; Rapiński, J. *Remote Sensing* 13(1):7, Dec 2020.**
🔗 https://doi.org/10.3390/rs13010007 · https://www.mdpi.com/2072-4292/13/1/7
🔗 Open PDF mirrors: https://www.academia.edu/51471094/ ·
https://www.researchgate.net/publication/347901424

- Recognition of RFI artifacts **at different levels of image damage** (graded severity, not just
  binary) in Sentinel-1 quicklook imagery.
- Uses the **TELAVIV quick-look dataset**, a representative RFI-heavy area, purpose-built for this.
- CNN-based (LeNet-family classifiers used to grade RFI damage level), with exploration of
  **complex-valued CNNs**.
- Companion to A4 — same group, deep-learning follow-up to their classical image-processing paper.

### A4. RFI Artefacts Detection in Sentinel-1 Level-1 SLC Data Based On Image Processing Techniques
**Chojka, A.; Artiemjew, P.; Rapiński, J. *Sensors* 20(10):2919, May 2020.**
🔗 https://www.mdpi.com/1424-8220/20/10/2919 · https://pmc.ncbi.nlm.nih.gov/articles/PMC7284985/
🔗 https://ui.adsabs.harvard.edu/abs/2020Senso..20.2919C/abstract

**Why it matters:** the definitive **classical preprocessing** reference. If you need a
non-learned baseline or a feature-engineering starting point, this is it.

- **Preprocessing chain:** feature extraction via **pixel convolution** (kernels matched to RFI
  stripe geometry) → **thresholding** → **nearest-neighbour structure filtering** (morphological
  cleanup of spurious responses).
- A CNN is used as the **reference classifier** for benchmarking the handcrafted pipeline.
- **Operational motivation:** flag and remove RFI-contaminated scenes from the **PSInSAR** stack
  before displacement processing. Explicitly notes that **quick-looks, being low-resolution
  previews, make RFI artefacts easy to detect cheaply** — the whole rationale for quicklook-domain
  screening.

### A5. Radio Frequency Interference Pattern Detection from Sentinel-1 SAR Data Using U-NET-Like Convolutional Neural Network
**Nov 2020.**
🔗 https://www.researchgate.net/publication/345162864
🔗 Figure showing the chip scheme: https://www.researchgate.net/figure/The-visual-representation-of-Sentinel-1-RGB-image-chips-of-image-size-256X256-and_fig1_345162864

- Explicitly operates on **Sentinel-1 RGB image chips at 256×256** — the clearest published
  statement of a quicklook RGB tiling scheme.
- U-Net-like encoder–decoder for RFI **pattern segmentation**.
- Key physical prior stated in this line of work: **RFI appears as bright line signatures always
  roughly perpendicular to the satellite orbit track.** This orientation prior is directly usable
  as an anchor-angle / oriented-box constraint.

### A6. Finding Ship Radars / Ground-based Radars in SAR Images: Localizing RFI Using Unsupervised Deep Learning
**Sørensen, K.A.; Heiselberg, H.; Kusk, A. (DTU Space).**
🔗 Ship radars: https://memorial.scholaris.ca/items/3c00fba4-1c2a-4a70-9679-c5d5252dce6b
🔗 Ground-based radars: https://orbit.dtu.dk/en/publications/finding-ground-based-radars-in-sar-images-localizing-radio-freque
🔗 Semantic Scholar: https://www.semanticscholar.org/paper/ab8a93a3838053f774a23cb4ec3ebda8b96215bb

### A7. Radio Frequency Interference in Synthetic Aperture Radar Images
**Same group, IGARSS 2023.**
🔗 https://orbit.dtu.dk/en/publications/radio-frequency-interference-in-synthetic-aperture-radar-images/

**Why A6/A7 matter:** the only **fully unsupervised localization** approach on quicklooks — no
labels needed, which sidesteps the annotation bottleneck entirely.

- **Method:** a **Convolutional Autoencoder** is trained to reconstruct **RFI-free** Sentinel-1
  quick-look images. RFI and other large-scale anomalies are not reconstructible.
- **Localization:** compute an **anomaly heat-map** = |original − reconstruction|. Peaks localize
  RFI. A **secondary classification scheme** then separates true RFI from other anomaly types.
- Robust across varying environmental/geographical conditions.
- **Application:** localized mid-sea RFI attributed to **ship-borne air-surveillance radars** —
  i.e. RFI as a *signal* for detecting otherwise-invisible vessels, not just as noise.

---

## 2. Datasets, benchmarks and challenges

### D1. ⭐ ClearSAR Challenge — Track 1 (IEEE ICIP 2026 Grand Challenge)
🔗 https://challenges.philab.esa.int/portfolio/clearsar-track-1/
🔗 https://platform-challenges.philab.esa.int/clear-sar
🔗 ICIP 2026 Grand Challenges: https://2026.ieeeicip.org/grand-challenges/
🔗 ESA Φ-lab platform: https://platform.ai4eo.eu/

**This is the single most relevant active resource for your exact task.**

- **Track 1 task:** automated **RFI detection in Sentinel-1 SAR quicklook (RGB) imagery**.
- **Dataset:** AI-ready, **3,940 Sentinel-1 quicklook RGB images**, curated for realistic mission
  conditions and broad RFI diversity, with **annotated RFI events**.
- **Track 2:** moves beyond quicklooks into the Sentinel-1 processing chain (higher product levels /
  raw constraints).
- **Stated motivation** (worth quoting in a paper intro): most RFI research targets large raw SAR
  products, but real Sentinel-1 workflows predominantly consume **compact products — quicklooks and
  GRD**; the absence of robust RFI handling at those levels limits large-scale automated use.
- **Award:** winners announced at **IEEE ICIP 2026, Tampere, Finland, 13–17 Sept 2026**.
- ⚠️ **[unverified]** — I could not fetch the portal (403), so I could **not confirm whether the
  annotations are bounding boxes or segmentation masks**, nor the evaluation metric (mAP vs IoU vs
  F1). **Check this first** — it determines your whole head design.

### D2. QLDecN_Dataset
🔗 https://github.com/JyuanShen/QLDecN_Dataset
Quick-look slice dataset accompanying A1. 7,580 images/class, 2 classes, derived from 50 Sentinel-1
SLC previews via augmentation.

### D3. RFInject: Injection of Simulated Radio Frequency Interference in Sentinel-1 Level-0 Data
**Research Square preprint, Dec 2025.**
🔗 https://www.researchsquare.com/article/rs-8337726/v1
🔗 PDF: https://www.researchsquare.com/article/rs-8337726/v1.pdf
🔗 Models/data: https://huggingface.co/RFInject
🔗 Sciety: https://sciety.org/articles/activity/10.21203/rs.3.rs-8337726/v1

**Why it matters:** solves the label-scarcity problem. Ground truth is *known by construction* —
you get exact RFI extent, so you can **auto-generate bounding boxes** for free.

- First open framework for **controlled injection** of narrowband terrestrial interference —
  continuous-wave tones, pulsed radar signals, frequency-hopping emitters — into **clean Sentinel-1
  raw bursts**.
- **Signal model:** parametric; superimposes modulated chirp trains and tone-like components onto
  authentic radar echoes while preserving spectral/statistical characteristics of operational
  systems. Scalable control over waveform diversity, temporal behaviour, spatial extent, and
  interference power.
- **Coverage:** **145 globally distributed Sentinel-1 IW products (2019–2025)**, decoded at burst
  level, **10 independent RFI realizations per burst**.
- Stores clean echoes **plus full RFI parameter vectors** → on-demand regeneration, fully
  reproducible.
- Caveat: Level-0 raw. You must run your own focusing + multilook + RGB compositing to get
  quicklook-like products, but the geometry of injected RFI is analytically known.

### D4. Standardized Dataset and Image-Subspace-Based Method for Strip-Mode SAR Block-Type RFI Suppression
**Remote Sensing 17(22):3688, Nov 2025.**
🔗 https://doi.org/10.3390/rs17223688
- Standardized dataset combining **laboratory-annotated data + Sentinel-1 open measured data**,
  directly usable for training/validating deep models.
- Includes a **block-type interference mathematical model** for data generation.
- Validated across **cross-dataset, same-distribution, and domain-shift** experiments — useful
  protocol design for your generalization claims.

### D5. S-1 RFI Maps (Aresys, operational)
🔗 https://s1rfimap.aresys.it/
Interactive global map of RFI events (>2500 K) detected by Sentinel-1 per orbit cycle; circle
colour/radius ∝ RFI brightness temperature. Useful for **geographic sampling and weak labels** —
you can bias your quicklook download toward known hot zones.

### D6. Sentinel-1 RFI annotations (SAR-MPC / official)
🔗 https://sentiwiki.copernicus.eu/__attachments/1673968/DI-MPC-OTH-0540%20-%20Sentinel-1%20Using%20the%20RFI%20annotations%202023%20-%201.1.pdf
🔗 https://www.researchgate.net/publication/358661571_SAR-MPC_Sentinel-1_Using_the_RFI_annotations
🔗 https://sar-mpc.eu/about/faq/ · https://sar-mpc.eu/product-performances/
🔗 Mission performance: https://elib.dlr.de/215074/1/S1MPC_S1_Performance_LPS2025.pdf

- Since **IPF 3.40 (4 Nov 2021)**, every Sentinel-1 L1 product carries **RFI mitigation
  annotations** — machine-readable flags identifying RFI-impacted products.
- Operational RFI detection+mitigation activated in the SAR processor **23 Mar 2022**.
- IPF v3.9 retuned detection parameters to reduce mis-detection (typically <2% of slices).
- **These annotations are free weak labels** for any quicklook you download. Strongly recommend
  using them for pretraining or label-noise-tolerant training.

---

## 3. LAYER B — RFI detection/localization in the Sentinel-1 image domain (SLC/GRD)

### B1. Radio Frequency Interference Detection and Localization in Sentinel-1 Images
**IEEE TGRS, 2021.**
🔗 https://ieeexplore.ieee.org/document/9335969/
🔗 PDF: https://ieeexplore.ieee.org/iel7/36/4358825/09335969.pdf
🔗 https://www.researchgate.net/publication/348801979

- Proposes an **RFI Index (RFII)** computed from **dual-polarization GRD** images (cross-pol vs
  co-pol behaviour differs under RFI — a cheap, powerful discriminator).
- **Geolocation trick:** intersect detections from **ascending and descending** passes; the
  intersection forms a diamond of **≈88.76 km²** bounding the ground emitter.
- This is *source* localization on the ground, not box localization in the image — but the RFII is
  an excellent engineered feature to concatenate as an extra channel.

### B2. Identification of C-Band Radio Frequency Interferences from Sentinel-1 Data
**Monti-Guarnieri, A.; Giudici, D.; Recchia, A. *Remote Sensing* 9(11):1183, 2017.**
🔗 https://www.mdpi.com/2072-4292/9/11/1183 · https://core.ac.uk/outputs/154336334/
🔗 https://www.researchgate.net/publication/321140216

- Exploits the **first 8–10 echoes at the start of each burst** (noise/receive-only window) as a
  passive radiometer: 50–70 MHz bandwidth, ~25 km (az) × 70 km (rg) footprint, revisit better than
  3 days using both satellites and both passes.
- **Detection statistic: KL divergence on grey-level histograms** — RFI is identified where the
  echo histogram diverges from the expected thermal-noise distribution.
  🔗 Figure: https://www.researchgate.net/figure/Example-of-histograms-where-RFI-can-be-identified-only-by-KL-divergence-a-and-of-RFI_fig9_321140216
  🔗 Block diagram: https://www.researchgate.net/figure/Schematic-block-diagram-for-the-identification-of-RFI_fig3_321140216
- **Direct relevance:** this is the intellectual ancestor of QLDecN's histogram-statistics branch.
  If you fuse histogram features into a quicklook detector, cite B2 → A1.

### B3. A Global C-Band RFI Monitoring System Based on Sentinel-1 Data
**IGARSS 2021.**
🔗 https://ieeexplore.ieee.org/document/9554119/
🔗 https://www.researchgate.net/publication/355255390
Uses Sentinel-1 **thermal noise measurements** to auto-generate **world RFI maps on a 12-day
periodicity**; feeds denoising/RFI removal back into product generation. Operational counterpart
to D5.

### B4. Mutual interferences between C-Band SAR: prediction of occurrences, identification of sources (ESA)
🔗 https://earth.esa.int/eogateway/documents/20142/2986799/Mutual_interferences_between_C_Band_SAR_Prediction_of_occurrences_identification_of_sources.pdf

### B5. On the Mutual Interference between Spaceborne SARs: Modeling, Characterization, and Mitigation
🔗 https://arxiv.org/pdf/2010.06819
Physics of SAR-on-SAR interference — the signature model behind what you see in quicklooks.

### B6. Global radio frequency interference in L-band SAR data from ALOS-1 and JERS-1 satellites
***Remote Sensing of Environment*, 2025.**
🔗 https://www.sciencedirect.com/science/article/abs/pii/S0034425725003591

### B7. Radio frequency interference in ALOS-2 PALSAR-2 interferograms
🔗 https://ieeexplore.ieee.org/document/8104494 ·
🔗 Open PDF: https://www.ursi.org/proceedings/procGA17/papers/Paper_EFGHJ1-3(1800).pdf
Notes that some RFI exhibits **high interferometric coherence** — it can masquerade as real ground
signal. Important negative result for anyone using coherence as an RFI filter.

### B8. Observations and Mitigation of RFI in ALOS PALSAR SAR Data (NASA/NTRS)
🔗 https://ntrs.nasa.gov/citations/20150008601

### B9. BSF: Block Subspace Filtering for Removing Narrowband and Wideband Radio Interference Artefacts in SLC SAR Images
🔗 https://www.researchgate.net/publication/353969633
Image-domain (SLC) removal — useful as a "clean" reference generator for supervised pairs.

---

## 4. LAYER C — Bounding-box and box-adjacent detectors for RFI (time–frequency domain)

**This is where the actual bounding-box literature lives.** All of these run on STFT spectrograms
of raw echo, *not* on quicklooks — but the detection heads, loss functions and anchor strategies
are exactly what you would port.

### C1. ⭐ Multiclass Radio Frequency Interference Detection and Suppression for SAR Based on the Single Shot MultiBox Detector
**Tao et al. (Beihang University), *Sensors* 18(11):4034, 2018.**
🔗 https://www.mdpi.com/1424-8220/18/11/4034 · https://pmc.ncbi.nlm.nih.gov/articles/PMC6263903/

**The canonical bounding-box RFI paper. Cite this as the origin of box-based RFI detection.**

- **Dataset construction:** echo–interference dataset built by **randomly combining target signal
  with various RFI types in simulation** (synthetic-first strategy — same idea RFInject later
  industrialized).
- **Preprocessing:** **Short-Time Fourier Transform (STFT)** → 2-D time–frequency images.
- **Architecture:** **SSD (Single Shot MultiBox Detector)** trained on the T-F images. Outputs
  **class + bounding box** per interference instance → simultaneously **detects, classifies
  (multiclass), and estimates parameters** of the interference (box extent = time/frequency support).
- **Downstream:** interference signals **reconstructed from the SSD box predictions** and removed
  with an adaptive filter.
- **Metrics:** improved **SINR** of contaminated echoes and **PSLR** after pulse compression.
- The "box → parameter estimate → reconstruct → subtract" loop is the key transferable idea.

### C2. ⭐ Self-Supervised Transformers for Unsupervised SAR Complex Interference Detection Using Canny Edge Detector (CEVIT)
***Remote Sensing* 16(2):306, Jan 2024.**
🔗 https://doi.org/10.3390/rs16020306 · https://www.mdpi.com/2072-4292/16/2/306
🔗 **Code:** https://github.com/yugangf/CEVIT
🔗 https://www.researchgate.net/publication/377353360

**The most sophisticated detection-head paper in this space, and it has released code.**

- **Preprocessing:** time–frequency spectrogram input, **plus a Canny edge-detection map** used as
  an auxiliary/prior channel — a cheap classical operator injected into a transformer. Directly
  portable to quicklooks, where RFI stripes have strong, coherent edges.
- **Architecture:** **Vision Transformer** feature-extraction module + a **detection head module**
  (i.e. box outputs). Multi-head attention maps are combined with feature maps and edge maps.
  Rationale given: attention handles **long-range dependencies** better than CNNs — and RFI stripes
  are long, thin, globally-extended structures, which is exactly the CNN failure mode.
- **Training:** **unsupervised / self-supervised**. To cope with ground-truth masks that miss some
  interference, uses a **dynamic loss descent strategy** to recover missed objects, further improved
  by **multiple rounds of self-training** (pseudo-label bootstrapping).
- Handles **multi-interference and multiple interference types** simultaneously.

### C3. DFN-YOLO: Detecting Narrowband Signals in Broadband Spectrum
***Sensors* 25(13):4206, 2025.**
🔗 https://www.mdpi.com/1424-8220/25/13/4206 · https://pmc.ncbi.nlm.nih.gov/articles/PMC12252476/
🔗 https://pubmed.ncbi.nlm.nih.gov/40648464/

Not SAR, but **the best modern YOLO-on-spectrogram design**, and the closest thing to a
state-of-the-art box baseline you can adapt:
- **DCFFN (Deformable Channel Feature Fusion Network)** replaces YOLOv8's **C2f** module;
  **deformable attention** adaptively focuses on signal regions — well matched to thin, oblique,
  variable-length RFI streaks.
- Loss changed to **Focal_SIoU** (focal-scaled IoU) for low-SNR robustness — directly relevant to
  faint RFI in quicklooks.
- **mAP@50–95 = 0.850**, beating stock YOLOv8.

### C4. Spectro-Temporal RF Identification using Deep Learning
🔗 https://arxiv.org/pdf/2107.05114
Box detection over spectro-temporal representations; useful for anchor design on elongated signals.

### C5. A Radio Frequency Region-of-Interest Convolutional Neural Network for Wideband Spectrum Sensing
🔗 https://www.researchgate.net/publication/372744862
Two-stage (RoI proposal → refine) on RF data — the Faster R-CNN analogue.

---

## 5. LAYER C/B — Segmentation networks for RFI (masks → boxes)

Semantic masks convert to bounding boxes trivially (connected components + `cv2.boundingRect`).
For thin, multi-instance RFI this is often **more accurate than direct box regression**.

### S1. Lightweight deep neural network for RFI detection and segmentation in SAR (LDNet)
***Scientific Reports*, Sep/Oct 2024.**
🔗 https://www.nature.com/articles/s41598-024-71775-8 · https://pmc.ncbi.nlm.nih.gov/articles/PMC11377538/
🔗 **Author Correction:** https://www.nature.com/articles/s41598-024-75441-x ← *read this too*
🔗 https://www.researchgate.net/publication/383791474 · https://d-nb.info/1353474631/34

- Time–frequency domain segmentation; delineates RFI pixel regions in spectrograms.
- **Design:** explicit **local information extraction + global information extraction** branches;
  **lightweight modules + pruning**.
- **Results:** MIoU **+24.56%** vs threshold-based detection, **+13.29%** vs generic DL segmentation
  nets, **+7.54%** vs **AC-UNet**; **model size −99.03%**, **inference latency −24.53%** vs AC-UNet.
- The strongest efficiency argument in the field — relevant if you target operational throughput.

### S2. Radio frequency interference detection based on the AC-UNet model
***Research in Astronomy and Astrophysics* 21(5):119.**
🔗 https://iopscience.iop.org/article/10.1088/1674-4527/21/5/119
U-Net with **atrous (dilated) convolution**. The standard baseline everyone benchmarks against.

### S3. Radio Frequency Interference Detection Using Efficient Multi-Scale Convolutional Attention UNet (EMSCA-UNet)
***MNRAS* 529(4):4719, 2024.**
🔗 https://arxiv.org/abs/2404.00277 · https://arxiv.org/pdf/2404.00277
🔗 https://academic.oup.com/mnras/article/529/4/4719/7635671
Multi-scale convolutions for RFI of varying scale + attention weighting of feature maps. Emphasizes
**fine edge delineation** — important when boxes are derived from masks.

### S4. Radio Frequency Interference Detection for SAR Data Using Spectrogram-Based Semantic Network
**Tao, M.; Tang, S.; Li, J.; Zhang, X.; Fan, Y.; Su, J. IGARSS 2021, Brussels.**
🔗 https://ieeexplore.ieee.org/document/9553478/ · DOI: 10.1109/IGARSS47720.2021.9553478
🔗 https://pure.nwpu.edu.cn/en/publications/radio-frequency-interference-detection-using-spectro
- U-Net on 2-D time–frequency representation; separates target echo vs RFI signature.
- **Threshold-free** detection and works **without large training sets** — good few-shot argument.

### S5. Detection of Radio Frequency Interference in Raw SAR Data Using U-Net Segmentation
🔗 https://www.techrxiv.org/users/706268/articles/1245246
🔗 https://smartsatcrc.com/smartsat-publications/detection-of-radio-frequency-interference-in-raw-sar-data-using-u-net-segmentation/
🔗 https://ieeexplore.ieee.org/iel8/11031247/11031249/11031638.pdf
**Notable methodology:** trains a DCNN on **simulated spaceborne SAR data**, then tests on **real
Sentinel-1 data zero-shot** — demonstrating sim-to-real generalization *without any real labels*.
This is the strategy to pair with RFInject (D3).

### S6. RFI Mitigation on Raw SAR Data Using U-Net for Enhanced Signal Reconstruction
🔗 https://www.researchgate.net/publication/397974426

### S7. Prompting and Tuning: In-Band Interference Segmentation Using Segment Anything Model
**IEEE, 2024.**
🔗 https://ieeexplore.ieee.org/document/10530199/
🔗 https://pure.bit.edu.cn/en/publications/prompting-and-tuning-in-band-interference-segmentation-using-segm
🔗 https://www.researchgate.net/publication/380587201
**Foundation-model route, and the prompting trick is clever and cheap:**
- Vanilla SAM fails on in-band interference (pre-trained on natural images, blurred TFI boundaries).
- **Prompt generation:** exploit **single-channel luminance differences among grey-scaled TFI
  pixels**, run **mean-shift clustering**, and use the resulting clusters as **automatic point/box
  prompts** for SAM. No manual prompting.
- Only SAM's **lightweight mask decoder is fine-tuned**, on an augmented dataset of refined in-band
  interference examples. Encoder frozen → very low training cost.
- **Highly portable to RGB quicklooks**, since the prompting is luminance-based and SAM natively
  expects 3-channel RGB.

---

## 6. Preprocessing techniques catalogue (extracted across all papers)

Consolidated so you can pick a pipeline. Source paper in brackets.

**Quicklook-domain (Layer A) preprocessing**
1. **Tiling into fixed chips** — 256×256 RGB chips [A5]; single-frame slices [A1].
2. **Sliding-window scan with overlap + error-tolerant aggregation** to convert tile labels into
   region localization over the full quicklook [A1]. *This is the de-facto localization method.*
3. **Histogram statistics as an auxiliary network input** — fused with CNN features [A1];
   ancestor: **KL divergence between echo histogram and thermal-noise distribution** [B2].
4. **RGB → grey-scale luminance**, then **mean-shift clustering on luminance** to auto-generate
   segmentation prompts [S7].
5. **Pixel convolution with stripe-matched kernels → thresholding → nearest-neighbour structure
   filtering** (classical, no training) [A4].
6. **Histogram equalization, grey variance, contrast normalization** — standard SAR image
   preprocessing; note the non-uniform grey histogram of SAR highlights texture/contours.
7. **Orientation prior:** RFI lines are **bright and roughly perpendicular to the orbit track**
   [A5] → constrain anchor angles / use oriented boxes.
8. **Severity-graded labelling** rather than binary presence [A3].
9. **Heavy augmentation** — 50 source previews → 7,580 images/class [A1].
10. **Autoencoder reconstruction residual → anomaly heat-map** for label-free localization [A6/A7].

**Signal/T-F-domain (Layer B/C) preprocessing**
11. **STFT → 2-D time–frequency spectrogram** — the universal input for box detectors [C1, C2, S1, S4].
12. **Canny edge map as auxiliary input channel** alongside the spectrogram [C2].
13. **Spectral subband decomposition → RGB/HSV dual-space chromatic coding** [X1, below] —
    *the most interesting preprocessing idea in the whole survey for RGB-domain work.*
14. **Dual-polarization ratio features / RFI Index (RFII)** from GRD [B1].
15. **Noise-echo window exploitation** (first 8–10 echoes per burst) as a passive radiometer [B2].
16. **Synthetic RFI injection into clean echoes** for exact ground truth [C1, D3, D4, S5].
17. **FFT → CFAR detection in 2-D frequency domain → adaptive weighting → IFFT** (classical
    narrowband suppression, ALOS-2 line).

### X1. ⭐ Spatial-Spectral Chromatic Coding of Interference Signatures in SAR Imagery: Signal Modeling and Physical-Visual Interpretation
**arXiv:2509.08693, 10 Sep 2025.**
🔗 https://arxiv.org/abs/2509.08693 · https://arxiv.org/pdf/2509.08693

**Read this if you do nothing else on the preprocessing side.** It is the only paper that explicitly
addresses *how to build an RGB image in which RFI is maximally visible* — i.e. it questions the
quicklook representation itself instead of accepting it.

- Generates a series of **spatial-spectral images via spectral subband decomposition** of SLC data,
  preserving **both spatial structure and spectral signature** (conventional grey amplitude
  quicklooks throw the spectral signature away).
- **Chromatically codes** these into colour via **RGB/HSV dual-space coding** with a purpose-designed
  palette.
- Result: interference becomes **visually discernible without further processing**; also highlights
  unfocused echoes, blurring, ambiguities, moving-target effects.
- **Implication for you:** a custom RGB composite could be a strictly better detector input than the
  standard ESA quicklook. A defensible novelty axis.

**Related colour-representation reference:**
🔗 Perceptually Optimal Color Representation of Fully Polarimetric SAR Imagery —
https://www.mdpi.com/2313-433X/8/3/67 · https://pmc.ncbi.nlm.nih.gov/articles/PMC8953311/

---

## 7. RFI suppression networks (context — detection is usually stage 1 of these)

Not detection papers, but they define the downstream task and often contain a detection front-end.

- **Mitigation of RFI in SAR Data: Current Status and Future Trends** (review) —
  *Remote Sensing* 11(20):2438 — 🔗 https://www.mdpi.com/2072-4292/11/20/2438
  🔗 https://www.researchgate.net/publication/336686308 · 🔗 https://core.ac.uk/works/9402742
  **Start here for the taxonomy** (narrowband / wideband / composite RFI).
- **DIFNet: SAR RFI suppression based on domain invariant features** — 🔗 https://arxiv.org/pdf/2403.02894
  Pipeline: RFI detection → echo localization → STFT → DIFNet prediction → ISTFT.
- **SAR RFI Suppression Based on Kurtosis-Guided Attention Network (KANet)** —
  🔗 https://doi.org/10.3390/rs18020255 — uses **temporal kurtosis** to steer attention onto
  interference-corrupted regions. The kurtosis statistic is a strong handcrafted RFI feature.
- **Regularized Optimization Feature Decomposition Network** — 🔗 https://www.mdpi.com/2072-4292/16/14/2540
  (notes **VGG-16** used for two-class T-F spectrogram RFI screening).
- **PKCNet** — prior-knowledge-constrained network in the T-F domain for periodic RFI.
- **Interference Mitigation for SAR Based on Deep Residual Network** — 🔗 https://ouci.dntb.gov.ua/en/works/l1vB61O9/
- **SLC-Domain SAR RFI Suppression via Sliding-Window Local Tensorization and Energy-Guided CUR
  Projection** — 🔗 https://www.mdpi.com/2072-4292/18/4/652
- **An Efficient SAR Interference Suppression Method Based on Image Domain Regularization** —
  🔗 https://doi.org/10.3390/electronics14051054
- **RFI Removal from SAR Imagery via Sparse Parametric Estimation of LFM Interferences** —
  🔗 https://arxiv.org/pdf/2509.18809
- **RFI Mitigation in SAR Systems via Multi-Polarization Framework** —
  🔗 https://www.researchgate.net/publication/380010228
- **An Efficient RFI Mitigation Algorithm in Real SAR Data** — 🔗 https://ieeexplore.ieee.org/document/9729704/
- **Narrowband Interference Separation via Sensing Matrix Optimization-Based Block Sparse Bayesian
  Learning** — 🔗 https://doi.org/10.3390/electronics8040458
- **Wideband Noise Interference Suppression for Sparsity-Based SAR Imaging** —
  🔗 https://doi.org/10.3390/electronics8091019
- **RFI Suppression for SAR via Block Sparse Bayesian Learning** —
  🔗 https://www.researchgate.net/publication/328623802

---

## 8. Adjacent / architectural donors (radio astronomy & spectrum sensing)

Different domain (waterfall plots, not SAR images), but methodologically the closest neighbours —
and where the SAM/transformer experimentation is happening first.

- **Performance of the Segment Anything Model in Various RFI/Events Detection in Radio Astronomy**
  — arXiv:2410.22497; *PASA* —
  🔗 https://arxiv.org/abs/2410.22497 · https://arxiv.org/html/2410.22497v1 · https://arxiv.org/pdf/2410.22497
  🔗 https://www.cambridge.org/core/journals/publications-of-the-astronomical-society-of-australia/article/182A87AB5075A1B961ED64203E96C15B
  **Documented failure modes worth designing around:** HQ-SAM merges **two nearby RFI events into
  one** (a real risk for closely-spaced RFI stripes — argues for instance-aware boxes over semantic
  masks); noisy output; coarse profile segmentation; misses extremely faint RFI. Comparable to or
  better than **SumThreshold** for large-area broadband RFI.
- **SAM-RFI — RFI Detection with SAM2** (code) — 🔗 https://github.com/preshanth/SAM-RFI
- **RFI Detection Using Swin Transformer Embedding U²-Net (ST-U2Net)** — *Advances in Astronomy*, 2025
  🔗 https://onlinelibrary.wiley.com/doi/full/10.1155/aa/3232269 — dual-encoder Swin + RSU blocks.
  Note: **U²-Net again**, as in SISNet (A2) — U²-Net is the recurring backbone for RFI segmentation.
- **Deep residual detection of RFI for FAST** — 🔗 https://arxiv.org/pdf/2001.06669
- **Spiking Neural Networks for RFI Detection in Radio Astronomy** — 🔗 https://arxiv.org/pdf/2412.06124
- **RFI mitigation using deep convolutional neural networks** — 🔗 https://www.researchgate.net/publication/308744521
- **Deep Learning improves Radio Frequency Interference Classification** —
  🔗 https://www.academia.edu/100950624/ · https://www.academia.edu/142949425/
- **Interference Suppression Using Deep Learning: Current Approaches and Open Challenges** —
  🔗 https://arxiv.org/pdf/2112.08988
- **Multi-Level Pre-Correlation RFI Flagging for Real-Time Implementation on UniBoard** —
  🔗 https://arxiv.org/pdf/1703.00473

---

## 9. General SAR object-detection infrastructure (for the box head)

If you build a box detector on quicklooks, these supply backbone/benchmark/augmentation practice.

- **SARDet-100K** (NeurIPS 2024) — 🔗 https://arxiv.org/html/2403.06534v2 ·
  🔗 https://proceedings.neurips.cc/paper_files/paper/2024/file/e7eb8128eb26eafbe901348df1dbacdc-Paper-Conference.pdf
- **RSAR: Restricted State Angle Resolver and Rotated SAR Benchmark** (CVPR 2025) —
  🔗 https://openaccess.thecvf.com/content/CVPR2025/papers/Zhang_RSAR_Restricted_State_Angle_Resolver_and_Rotated_SAR_Benchmark_CVPR_2025_paper.pdf
  **Rotated/oriented boxes** — the right box parameterization for orbit-perpendicular RFI streaks.
- **M4-SAR** — 🔗 https://arxiv.org/pdf/2505.10931
- **DenoDet V2: Phase-Amplitude Cross Denoising for SAR Object Detection** — 🔗 https://arxiv.org/pdf/2508.09392
- **Vehicle Detection in SAR Satellite Images Using YOLOv8 Oriented Bounding Box** —
  🔗 https://indjst.org/articles/vehicle-detection-in-sar-satellite-images-using-yolov8-oriented-bounding-box-detection-algorithm
  (notes **speckle-noise augmentation** + anchor-free + multi-scale aggregation)
- **A Novel CNN-Based Detector for Ship Detection Based on Rotatable Bounding Box in SAR Images** —
  🔗 https://www.researchgate.net/publication/348359261
- **satellite-image-deep-learning/techniques** — 🔗 https://github.com/satellite-image-deep-learning/techniques

---

## 10. Gap analysis / where the novelty is

Summarizing what the survey shows is **missing**:

1. **No published true bounding-box detector operating directly on Sentinel-1 RGB quicklooks.**
   Layer A is classification (A1, A3) or segmentation (A2, A5) or unsupervised heatmaps (A6/A7).
   Boxes exist only in Layer C on spectrograms (C1, C2). **This gap is the opportunity.**
2. **Localization on quicklooks is currently done by sliding window + aggregation (A1)** — crude,
   no learned box regression, no instance separation. A one-stage oriented-box detector would be a
   clear methodological advance.
3. **Instance separation is an unsolved, documented failure** — SAM merges adjacent RFI events
   (Section 8). Semantic masks cannot count RFI events; boxes can.
4. **Label scarcity is now solvable** — RFInject (D3), the standardized dataset (D4), sim-to-real
   zero-shot (S5), IPF ≥3.40 RFI annotations as weak labels (D6), and ClearSAR's 3,940 annotated
   quicklooks (D1). This constraint has largely lifted since ~2024.
5. **The RGB representation itself is under-exploited** (X1). Everyone consumes the default ESA
   quicklook; nobody optimizes the colour composite *for detectability*.

**Suggested reading order:** D1 → A1 → A2 → C1 → C2 → X1 → S7 → D3.

---

## 11. Access note

All publisher domains were blocked by this environment's egress policy (403 at the proxy on
arxiv.org, mdpi.com, ieeexplore.ieee.org, nature.com, pmc.ncbi.nlm.nih.gov, researchgate.net,
semanticscholar.org, github.com, sar-mpc.eu, philab.esa.int). Content above is derived from search
indices and abstracts; every entry carries its URL for direct retrieval.

**Items requiring verification on your side:**
- **D1 ClearSAR Track 1** — annotation type (boxes vs masks) and evaluation metric. Highest priority.
- **A3** — exact CNN architecture and the number/definition of RFI damage-severity classes.
- **A5** — venue and full author list (only the ResearchGate record surfaced).
- **S1 LDNet** — read the Author Correction alongside the original.
