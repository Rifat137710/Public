"""Blind RFI detector v5 -- granularity by multi-scale matched filter + scale selection.

THE GRANULARITY BUG AND ITS FIX

Training prior, measured with the 7 blind images removed: an annotated box is
10 px tall at the median (q05=4, q25=7, q75=13) on a ~520x341 image, and
bimodal in width -- 33% narrower than 10% of the image, 46% exactly one
sub-swath.  Median 2 boxes per image, q90=6, max 28.

v1 collapsed each sub-swath to a 1-D azimuth profile and emitted runs of hot
rows, using a 9-row smoother and a 5-row merge gap on objects whose median
height is 10 px.  One event became many strips; adjacent events welded
together; a box narrower than the sub-swath was averaged out of existence.

v2 replaced runs with 2-D connected components.  Still wrong: threshold-and-
label carries no size prior, and a MAD z-score on a spatially correlated map put
20% of pixels over "4.5 sigma", so every sub-swath flooded into one component.

v4 detects each object at its own scale:

  1. a bank of matched filters over the prior's size grid;
  2. each scale normalised by its own measured 99.9th percentile, which is what
     makes scales comparable.  Two cheaper normalisations were tried and are
     both wrong, for reasons that were measured on these images:

       MAD z-score -- the clutter is violently non-Gaussian.  The top-hat's
       q99.9/MAD ratio runs 33 at h=4 px down to 13 at h=43 px (Gaussian: 3.3),
       so the smallest scale has a 2.5x heavier tail and wins every argmax on
       tail shape alone.  This is also what flooded v2.

       a shifted null -- circularly shifting columns destroys the range
       coherence the periodogram measures, so the null became trivially
       beatable and every terrain row scored as pulsed RFI.

     Normalising by the measured q99.9 equalises the tails directly.

     The background here is TERRAIN-CLUTTER-limited, not speckle-limited:
     averaging an h x w window reduces sigma as (h*w)^-0.21, not (h*w)^-0.5
     (fitted alpha = 0.426 over these images).  A 4x12 window averages 48 pixels
     and gains a factor 1.07.  That is why integration alone cannot rescue a
     weak box, and why absolute thresholds have to be measured, not assumed;
  3. per-pixel scale selection by LARGEST CLEARING SCALE, not by argmax of the
     response.  Argmax cannot size an object here: even after tail equalisation
     the small scales keep the heavier tail and take every pixel, so every
     detection came out 4 px tall.  Instead a box is as big as the largest
     window that still shows the anomaly -- a 10 px band still responds at
     h=11 but dilutes at h=27, so the largest clearing scale tracks the true
     extent, and clutter that only clears at h=4 never grows a large box.
     The winning scale IS the box size: granularity is set by the data, not by
     post-hoc merging or splitting;
  4. non-maximum suppression on min-area overlap, not IoU, so a small box
     contained in a larger one is suppressed (IoU cannot see containment).

THE FILTER

RFI here is range-extended and azimuth-confined: interference arrives during a
short along-track interval and spreads across range.  Terrain has no such
preferred orientation.  The response for a candidate h tall and w wide is an
azimuth top-hat on the polarisation difference R-G,

    T = mean(centre h x w) - 1/2 mean(band h above) - 1/2 mean(band h below)

whose symmetric flanks cancel any azimuth trend to first order.  That is what
removes terrain without requiring the anomaly to span the whole sub-swath, which
is the property v1 lacked.  A transposed copy (range-confined, azimuth-extended)
measures how much of the response is an unoriented edge such as a coastline and
is subtracted.
"""
import glob, json
import numpy as np
from PIL import Image
from scipy.ndimage import uniform_filter, uniform_filter1d, median_filter, maximum_filter

BASE = "/tmp/claude-0/-home-user-Public/5b046774-858a-59c1-8937-914a8e1fd428/scratchpad"
S = f"{BASE}/blind/New folder (5)"

HEIGHTS = (4, 7, 11, 17, 27, 43, 69)      # spans q05..q95 of annotated heights
WIDTHS = (12, 24, 48, 96, 160)            # narrow mode and sub-swath mode
BG_ROWS = 61          # range-terrain removal, ~6 object heights
NORM_Q = 99.9         # per-scale quantile that defines 1.0; equalises the
                      # measured scale-dependent tail (33 at h=4 -> 13 at h=43)
Z_DET = 1.40          # floor in units of that q99.9; set so mean boxes/image
                      # = 3.3 vs the training prior 2.97 -- calibrated on the
                      # PRIOR, not on the test labels
NMS_OVR = 0.35        # suppression by intersection / min(area), catches containment
MIN_BOXES = 1         # every annotated image in the dataset carries >=1 box
MAX_BOXES = 14        # training prior q99
PMIN, PMAX = 4, 28    # pulsed-RFI period range, px
ANISO = 1.0
SNAP_FRAC = 0.75      # 46% of training boxes are exactly one sub-swath wide
RNG = np.random.default_rng(0)


def dB(v):
    return 20 * np.log10(v + 0.5)


def valid_mask(a):
    lum = a.mean(2)
    return lum > 0.12 * np.percentile(lum, 99)


def detect_seams(a, search=0.07):
    """Refine the nominal IW seams locally (unchanged -- this part worked).

    Training x-edges cluster at 0.338 / 0.688 of width, so seams are anchored
    there and may only move within +/-`search`; an unconstrained gradient search
    locks onto coastlines instead.
    """
    ok = valid_mask(a)
    lum = np.where(ok, a.mean(2), np.nan)
    has = np.isfinite(lum).any(0)
    W = lum.shape[1]
    nominal = [int(0.325 * W), int(0.675 * W)]
    if not has.any():
        return nominal
    prof = np.full(W, np.nan)
    prof[has] = np.nanmean(lum[:, has], axis=0)
    prof = np.nan_to_num(prof, nan=float(np.nanmean(prof[has])))
    g = np.abs(np.gradient(uniform_filter1d(prof, 5))) / np.maximum(prof, 1e-6)
    win = int(search * W)
    seams = []
    for nom in nominal:
        lo, hi = max(nom - win, 1), min(nom + win, W - 1)
        seams.append(int(lo + np.argmax(g[lo:hi])) if hi > lo else nom)
    return sorted(seams)


def shift_rows(a, k):
    """out[y] == a[y - k], edges replicated."""
    out = np.empty_like(a)
    if k == 0:
        return a.copy()
    if k > 0:
        out[k:], out[:k] = a[:-k], a[0]
    else:
        out[:k], out[k:] = a[-k:], a[-1]
    return out


def shift_cols(a, k):
    out = np.empty_like(a)
    if k == 0:
        return a.copy()
    if k > 0:
        out[:, k:], out[:, :k] = a[:, :-k], a[:, :1]
    else:
        out[:, :k], out[:, k:] = a[:, -k:], a[:, -1:]
    return out


def response(A, h, w):
    """Azimuth top-hat minus its transpose: range-extended, azimuth-confined."""
    C = uniform_filter(A, size=(h, w), mode="nearest")
    T = C - 0.5 * (shift_rows(C, h) + shift_rows(C, -h))
    Cp = uniform_filter(A, size=(w, h), mode="nearest")
    Tp = Cp - 0.5 * (shift_cols(Cp, h) + shift_cols(Cp, -h))
    return np.abs(T), np.abs(Tp)


def periodicity(A, h, rwin=64, rstep=8):
    """Along-range periodogram peak in the pulsed band, then an azimuth top-hat.

    A pulsed burst is confined in azimuth; periodic terrain texture (dunes,
    ocean swell) is not, so the top-hat keeps the former and cancels the latter.
    """
    Hh, Wm = A.shape
    out = np.zeros_like(A)
    if Wm < rwin:
        return out
    Ds = uniform_filter1d(A, max(h, 3), axis=0, mode="nearest")
    han = np.hanning(rwin)
    fr = np.fft.rfftfreq(rwin)
    sel = (fr > 1 / PMAX) & (fr < 1 / PMIN)
    if sel.sum() < 2:
        return out
    for x in range(0, Wm - rwin + 1, rstep):
        seg = Ds[:, x:x + rwin]
        seg = seg - seg.mean(1, keepdims=True)
        F = np.abs(np.fft.rfft(seg * han, axis=1))
        r = F[:, sel].max(1) / np.maximum(np.median(F[:, 1:], axis=1), 1e-9)
        blk = out[:, x:x + rwin]
        np.maximum(blk, r[:, None], out=blk)
    return np.abs(out - 0.5 * (shift_rows(out, h) + shift_rows(out, -h)))


def calib(x, good):
    """Per-scale normalisation by the measured NORM_Q percentile of the response.

    Equalises the scale-dependent clutter tail so the argmax over scales reflects
    signal shape rather than tail shape.  Limitation: it is relative, so the
    detector cannot declare an image clean -- it always ranks something first.
    """
    v = x[good]
    return max(float(np.percentile(v, NORM_Q)), 1e-9) if v.size else 1.0


def overlap(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    m = min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1]))
    return inter / m if m > 0 else 0.0


def detect_subswath(D, good, x0, x1, H):
    """Best-scale calibrated response map for one sub-swath, plus scale maps."""
    Wm = x1 - x0
    A = D - median_filter(D, size=(BG_ROWS, 1), mode="nearest")

    peak = np.full(A.shape, -np.inf)     # strongest response over all scales
    best = np.full(A.shape, -np.inf)     # response at the selected scale
    bh = np.zeros(A.shape, int)
    bw = np.zeros(A.shape, int)
    bd = np.zeros(A.shape, int)          # 0 = level, 1 = period
    scales = sorted(((h, w) for h in HEIGHTS for w in WIDTHS
                     if h * 3 < H and w <= Wm), key=lambda s: s[0] * s[1])
    percache = {}
    for h, w in scales:
        if h not in percache:
            pm = periodicity(A, h)
            percache[h] = (pm, calib(pm, good))
        per, cper = percache[h]
        T, Tp = response(A, h, w)
        z = T / calib(T, good) - ANISO * Tp / calib(Tp, good)
        zz, drv = z, np.zeros(A.shape, int)
        if w >= 64:
            zp = per / cper
            drv = (zp > z).astype(int)
            zz = np.maximum(z, zp)
        np.maximum(peak, zz, out=peak)
        # scales are visited smallest-area first, so the LAST one to clear wins
        upd = zz > Z_DET
        best[upd], bh[upd], bw[upd], bd[upd] = zz[upd], h, w, drv[upd]
    # pixels that never cleared at any scale keep their strongest response
    none_cleared = bh == 0
    best[none_cleared] = peak[none_cleared]
    bh[none_cleared], bw[none_cleared] = scales[0]
    best[~good] = -np.inf

    # one local maximum per neighbourhood of the winning scale
    loc = maximum_filter(best, size=(9, 15), mode="nearest")
    ys, xs = np.nonzero((best >= loc) & (best > 0.6 * Z_DET))
    out = []
    for y, x in zip(ys, xs):
        h, w = int(bh[y, x]), int(bw[y, x])
        by0, by1 = max(y - h // 2, 0), min(y - h // 2 + h, H)
        bx0, bx1 = max(x - w // 2, 0), min(x - w // 2 + w, Wm)
        if by1 - by0 < 3 or bx1 - bx0 < 6:
            continue
        if bx1 - bx0 > SNAP_FRAC * Wm:
            bx0, bx1 = 0, Wm
        out.append((float(best[y, x]), x0 + bx0, by0, x0 + bx1, by1,
                    "period" if bd[y, x] else "level", f"{h}x{w}"))
    return out


def nms(cands, thr=NMS_OVR):
    out = []
    for c in sorted(cands, key=lambda z: -z[0]):
        if all(overlap(c[1:5], o[1:5]) < thr for o in out):
            out.append(c)
    return out


results = {}
for p in sorted(glob.glob(f"{S}/*.png")):
    fn = p.split("/")[-1]
    a = np.asarray(Image.open(p).convert("RGB"), dtype=np.float64)
    H, W = a.shape[:2]
    seams = detect_seams(a)
    edges = [0, *seams, W]
    ok = valid_mask(a)
    Draw = np.where(ok, dB(a[:, :, 0]) - dB(a[:, :, 1]), np.nan)

    cands = []
    for si in range(3):
        x0, x1 = edges[si], edges[si + 1]
        if x1 - x0 < 16:
            continue
        Dsub = Draw[:, x0:x1]
        g = np.isfinite(Dsub)
        if g.any(1).sum() < BG_ROWS:
            continue
        Dsub = np.nan_to_num(Dsub, nan=float(np.nanmedian(Dsub[g])))
        cands += [c + (si + 1,) for c in detect_subswath(Dsub, g, x0, x1, H)]

    ranked = nms(cands)
    keep = [c for c in ranked if c[0] > Z_DET][:MAX_BOXES] or ranked[:MIN_BOXES]
    dets = [dict(bbox=[int(c[1]), int(c[2]), int(c[3]), int(c[4])],
                 score=round(c[0], 2), subswath=c[7], driver=c[5], scale=c[6])
            for c in keep]
    results[fn] = dict(width=W, height=H, seams=seams, detections=dets)
    print(f"{fn}  {W}x{H}  seams={seams}  -> {len(dets)} dets (of {len(cands)} cands)")
    for d in dets:
        u, v, s, t = d["bbox"]
        print(f"    IW{d['subswath']}  ({u},{v})-({s},{t})  {s-u:3d}x{t-v:<3d} "
              f"score={d['score']:5.2f}  scale={d['scale']:6s} {d['driver']}")

json.dump(results, open(f"{BASE}/blind_predictions_v5.json", "w"), indent=1)
print(f"\ntotal detections: {sum(len(v['detections']) for v in results.values())}")
