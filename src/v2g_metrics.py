"""
Metric set for the V2G gap study.

Reports the paper's metric *and* the standard-compliant ones side by side, so the
two can be compared directly rather than argued about:

  ViolMean  hours where the FEEDER-MEAN voltage < 0.95      <- the paper's metric
  ViolBus   hours where ANY bus (phase-averaged) < 0.95
  ViolPh    hours where ANY energized phase < 0.95           <- ANSI C84.1
  IntViol   integrated violation magnitude, p.u.-hours       <- continuous, no saturation
  VMean/VMin/VMax   feeder-mean voltage stats, matching the paper's table columns
  VphMin    worst single-phase voltage over the day

Counts saturate (every controller can tie at "all 18 hours violated"); IntViol does
not, so it is the metric that still separates controllers when the counts agree.
"""
import numpy as np

V_MIN, V_MAX = 0.95, 1.05


def hourly_record():
    return {"hour": [], "vmean": [], "vbus_min": [], "vph_min": [],
            "int_viol": [], "disch": [], "soc": [], "n_ev": [], "rho": [],
            "throughput": [], "taps": []}


def log_hour(rec, hour, feeder, disch, soc, n_ev, rho, throughput, taps=None):
    vbus = feeder.bus_vpu()
    vph = feeder.phase_vpu()
    rec["hour"].append(hour)
    rec["vmean"].append(float(np.mean(vbus)))
    rec["vbus_min"].append(float(vbus.min()))
    rec["vph_min"].append(float(vph.min()))
    # integrated magnitude over per-phase undervoltage, p.u. summed across nodes
    rec["int_viol"].append(float(np.clip(V_MIN - vph, 0, None).sum()))
    rec["disch"].append(float(disch))
    rec["soc"].append(float(soc))
    rec["n_ev"].append(float(n_ev))
    rec["rho"].append(float(rho))
    rec["throughput"].append(float(throughput))
    rec["taps"].append(list(taps) if taps else [])


def rainflow_depths(soc_series):
    """Compact rainflow: turning-point extraction then range counting.

    Returns the list of half-cycle depths (in SOC fraction). Used for evaluation
    only -- it is path-dependent and awkward inside an RL reward, so the reward
    uses Ah-throughput instead.
    """
    s = np.asarray(soc_series, dtype=float)
    if s.size < 3:
        return []
    # keep local extrema
    tp = [s[0]]
    for i in range(1, s.size - 1):
        if (s[i] - s[i - 1]) * (s[i + 1] - s[i]) < 0:
            tp.append(s[i])
    tp.append(s[-1])
    depths, stack = [], []
    for v in tp:
        stack.append(v)
        while len(stack) >= 3:
            a, b, c = stack[-3], stack[-2], stack[-1]
            if abs(b - a) <= abs(c - b):
                depths.append(abs(b - a))
                stack.pop(-2)
            else:
                break
    for i in range(len(stack) - 1):
        depths.append(abs(stack[i + 1] - stack[i]))
    return depths


def summarize(rec, soc_series=None):
    vm = np.asarray(rec["vmean"])
    vb = np.asarray(rec["vbus_min"])
    vp = np.asarray(rec["vph_min"])
    depths = rainflow_depths(soc_series) if soc_series is not None else []
    n_taps = 0
    prev = None
    for t in rec["taps"]:
        if prev is not None and t and list(t) != list(prev):
            n_taps += sum(1 for x, y in zip(t, prev) if x != y)
        prev = t
    return dict(
        VMean=round(float(vm.mean()), 3),
        VMin=round(float(vm.min()), 3),
        VMax=round(float(vm.max()), 3),
        ViolMean=int((vm < V_MIN).sum()),
        ViolBus=int((vb < V_MIN).sum()),
        ViolPh=int((vp < V_MIN).sum()),
        VphMin=round(float(vp.min()), 3),
        IntViol=round(float(np.sum(rec["int_viol"])), 2),
        Energy=round(float(np.sum(rec["disch"])), 1),
        Thru=round(float(rec["throughput"][-1]) if rec["throughput"] else 0.0, 1),
        SOCend=round(float(rec["soc"][-1]), 3),
        MaxDoD=round(float(max(depths)) if depths else 0.0, 3),
        SumDoD=round(float(sum(depths)) if depths else 0.0, 3),
        TapOps=int(n_taps),
    )


# ---- multi-seed aggregation with paired (common-random-number) comparisons ---- #
def aggregate(rows, keys=None):
    """rows: list of summarize() dicts across seeds. Returns mean/std/CI per key."""
    keys = keys or [k for k in rows[0] if isinstance(rows[0][k], (int, float))]
    out = {}
    n = len(rows)
    for k in keys:
        v = np.array([r[k] for r in rows], dtype=float)
        sd = float(v.std(ddof=1)) if n > 1 else 0.0
        out[k] = dict(mean=float(v.mean()), std=sd,
                      ci95=1.96 * sd / np.sqrt(n) if n > 1 else 0.0)
    return out


def paired_delta(rows_a, rows_b, key):
    """Paired difference a-b on identical scenarios (CRN). Returns mean, ci95, n_wins."""
    a = np.array([r[key] for r in rows_a], dtype=float)
    b = np.array([r[key] for r in rows_b], dtype=float)
    d = a - b
    n = d.size
    sd = float(d.std(ddof=1)) if n > 1 else 0.0
    return dict(mean=float(d.mean()), ci95=1.96 * sd / np.sqrt(n) if n > 1 else 0.0,
                std=sd, n=n, a_better=int((d < 0).sum()), ties=int((d == 0).sum()))


def fmt_table(title, header, rows):
    w = [max(len(str(header[i])), *(len(str(r[i])) for r in rows)) + 2
         for i in range(len(header))]
    line = "".join(str(header[i]).rjust(w[i]) for i in range(len(header)))
    print(f"\n{title}")
    print(line)
    print("-" * len(line))
    for r in rows:
        print("".join(str(r[i]).rjust(w[i]) for i in range(len(r))))
