"""Kaggle driver for the transfer study (T4 + T5) -- the learned request source.

Generates `notebooks/kaggle_transfer_study.ipynb`. Kept as a plain script so the
cells stay diffable in git.

Kaggle settings that matter:
  * Accelerator: **None**. CPU-bound on power flow and the SOCP solve; the nets
    are 372k parameters. A GPU changes nothing and costs quota.
  * Internet: **On** (pip + git clone).
  * Expect ~2.5-3.5 h. The 12 h session cap is ample.

What this produces: the *supporting* row of the conference paper -- the learned
policy as one request source on the refresh-staleness axis, to show the cliff
sits in the same place whether a greedy heuristic or a trained SAC-Lag policy
generates the request.

It is deliberately not the headline. G0 found no operating point on this
testbed where a learner beats a greedy request passed through the projection,
so the paper's claim is about the safety layer; this run answers "does it also
hold for the RL controller?" rather than carrying the argument.

Three seeds is enough for a supporting row. Five if the quota is there.
"""

# ========================= CELL 1 -- get the code =========================
CLONE = r"""
# Pin the branch so a later push cannot silently change what a finished run
# was produced by. If the repo is private, add a token:
#   https://<PAT>@github.com/Rifat137710/Public.git
!rm -rf /kaggle/working/safesac-repo
!git clone -q --branch claude/thesis-q1-journal-path-komv2c \
    https://github.com/Rifat137710/Public.git /kaggle/working/safesac-repo
%cd /kaggle/working/safesac-repo
!git rev-parse --short HEAD
"""

# ========================= CELL 2 -- dependencies =========================
# Install from requirements.txt, never hand-pinned versions: pandapower 3.x and
# 2.x differ enough to break the network build, and the repo is the authority
# on which one the results were produced under.
DEPS = r"""
!pip -q install -r requirements.txt 2>&1 | tail -3
import torch, pandapower, cvxpy, clarabel, gymnasium
print("torch", torch.__version__)
print("pandapower", pandapower.__version__, "(must be 3.2.0)")
print("cvxpy", cvxpy.__version__, "| gymnasium", gymnasium.__version__)
"""

# =========================== CELL 3 -- sanity ============================
# Two minutes. If this does not come out clean, stop -- do not spend three
# hours of quota on a broken environment.
SANITY = r"""
!python -m pytest tests/test_powerflow.py -q 2>&1 | tail -4
!python -u scripts/learned_source.py --seeds 0 --episodes 3 --eval-episodes 2 \
    --eval-z 6.0 --refresh 1 288 --out-dir /kaggle/working/smoke \
    2>&1 | grep -v "UserWarning\|warnings.warn" | tail -12
"""
# Read only the *pattern* -- 3 episodes means nothing numerically. In the
# reference block, refresh=1 must be 0.0000 and refresh=288 must equal the raw
# rate. If refresh=288 is not the raw rate, the projection is still acting when
# it should be inert and the run is invalid.

# ========================= CELL 4 -- the experiment =======================
# Operating point fixed by G0 (scripts/operating_point_sweep.py): load 0.40 is
# the highest scale at which the idle feeder is violation-free, which is what
# keeps every observed violation attributable to a charging decision.
RUN = r"""
import os
os.environ["OMP_NUM_THREADS"] = "4"
os.environ["MKL_NUM_THREADS"] = "4"

!python -u scripts/learned_source.py \
    --seeds 0 1 2 \
    --episodes 200 \
    --eval-episodes 20 \
    --alpha 0.003 \
    --train-z 6.0 \
    --eval-z 6.0 8.0 \
    --refresh 1 12 48 288 \
    --load 0.40 \
    --evs 30 \
    --out-dir /kaggle/working/results/learned_source \
    2>&1 | grep -v "UserWarning\|warnings.warn"
"""

# =========================== CELL 5 -- collect ===========================
COLLECT = r"""
import json, shutil
from pathlib import Path

d = json.loads(
    Path("/kaggle/working/results/learned_source/learned_source.json").read_text())
print("train Z", d["train_z_pct"], "| eval Z", d["eval_z_pct"],
      "| refresh", d["refresh"], "| seeds", d["seeds"],
      "| fingerprint", d["fingerprint"])
cols = ["raw"] + [str(r) for r in d["refresh"]]
print(f"{'Z%':>6}" + "".join(f"{c:>14}" for c in cols))
for z, row in d["summary"].items():
    print(f"{z:>6}" + "".join(f"{row[c]['viol'][0]:>14.4f}" for c in cols))

shutil.make_archive("/kaggle/working/learned_source_results", "zip",
                    "/kaggle/working/results")
print("\ndownload /kaggle/working/learned_source_results.zip and send it back")
"""

CELLS = [CLONE, DEPS, SANITY, RUN, COLLECT]

if __name__ == "__main__":
    import json
    from pathlib import Path

    nb = {
        "cells": [
            {"cell_type": "code", "execution_count": None, "metadata": {},
             "outputs": [], "source": (c.strip() + "\n").splitlines(keepends=True)}
            for c in CELLS
        ],
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python",
                           "name": "python3"},
            "language_info": {"name": "python", "version": "3.11"},
        },
        "nbformat": 4, "nbformat_minor": 5,
    }
    out = Path(__file__).with_suffix(".ipynb")
    out.write_text(json.dumps(nb, indent=1))
    print(f"wrote {out} with {len(CELLS)} cells")
