"""Kaggle driver for the transfer study (T4 + T5) -- the learned request source.

Generates `notebooks/kaggle_transfer_study.ipynb`. Kept as a plain script so the
cells stay diffable in git.

Kaggle settings that matter:
  * Accelerator: **None**. CPU-bound on power flow and the SOCP solve; the nets
    are 372k parameters. A GPU changes nothing and costs quota.
  * Internet: **On** (pip + git clone).
  * Expect ~2.5-3.5 h. The 12 h session cap is ample.

What this produces: the learned policy as one request source in the transfer
study, deployed zero-shot across the stiffness axis under three treatments
(raw / frozen model / deployment model). The heuristic sources run locally in
minutes -- only this arm needs real compute.
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
!python -u scripts/transfer_study.py --seeds 0 --episodes 3 --eval-episodes 2 \
    --train-z 0.5 --deploy-z 0.5 6.0 --out-dir /kaggle/working/smoke \
    2>&1 | grep -v "UserWarning\|warnings.warn" | tail -12
"""
# Expected from the smoke run (3 episodes is far too few to mean anything, so
# read only the *pattern*): at Z=6% arm A and arm B should show the SAME
# violation rate and arm C should show 0.0000. If B differs from A, the frozen
# sensitivities are not being used and the run is invalid.

# ========================= CELL 4 -- the experiment =======================
# Operating point fixed by G0 (scripts/operating_point_sweep.py): load 0.40 is
# the highest scale at which the idle feeder is violation-free, which is what
# keeps every observed violation attributable to a charging decision.
RUN = r"""
import os
os.environ["OMP_NUM_THREADS"] = "4"
os.environ["MKL_NUM_THREADS"] = "4"

!python -u scripts/transfer_study.py \
    --seeds 0 1 2 3 4 \
    --episodes 200 \
    --eval-episodes 20 \
    --alpha 0.003 \
    --train-z 0.5 \
    --deploy-z 0.5 4.0 6.0 8.0 10.0 12.0 \
    --load 0.40 \
    --evs 30 \
    --out-dir /kaggle/working/results/transfer \
    2>&1 | grep -v "UserWarning\|warnings.warn"
"""

# =========================== CELL 5 -- collect ===========================
COLLECT = r"""
import json, shutil
from pathlib import Path

d = json.loads(Path("/kaggle/working/results/transfer/transfer.json").read_text())
print("train Z", d["train_z_pct"], "| deploy", d["deploy_z_pct"],
      "| seeds", d["seeds"], "| fingerprint", d["train_fingerprint"])
print(f"{'Z%':>6}{'A raw':>18}{'B frozen':>18}{'C deploy':>18}")
for z, row in d["summary"].items():
    print(f"{z:>6}" + "".join(
        f"{row[a]['viol'][0]:>9.4f}/{row[a]['soc'][0]:.3f}"
        for a in ("A_raw", "B_frozen_proj", "C_deploy_proj")))

shutil.make_archive("/kaggle/working/transfer_results", "zip",
                    "/kaggle/working/results")
print("\ndownload /kaggle/working/transfer_results.zip and send it back")
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
