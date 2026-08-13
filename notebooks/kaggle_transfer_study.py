"""Kaggle driver for the transfer study (T4 + T5).

Paste the cells below into a Kaggle notebook, or run this file directly with
`%run`. Written as a plain script so it stays diffable in git; the CELL markers
show where to split it if you prefer a notebook.

Settings that matter on Kaggle:
  * Accelerator: **None**. This workload is CPU-bound on power flow and the SOCP
    solve; the networks are 372k parameters and a GPU changes nothing. Picking
    one only costs you quota.
  * Internet: **On** (needed for pip and the git clone).
  * Session: the default 12 h cap is ample -- 5 seeds x 200 episodes is roughly
    3 h on 4 vCPUs.
"""

# ============================== CELL 1 -- setup ==============================
SETUP = r"""
!pip -q install pandapower==2.14.6 cvxpy clarabel 2>&1 | tail -2
import torch, pandapower, cvxpy
print("torch", torch.__version__, "| pandapower", pandapower.__version__,
      "| cvxpy", cvxpy.__version__)
"""

# ============================== CELL 2 -- code ==============================
# Public repo, so no token is needed. Pin the branch so a later push cannot
# silently change what a finished run was produced by.
CLONE = r"""
!rm -rf /kaggle/working/safesac-repo
!git clone -q --branch claude/thesis-q1-journal-path-komv2c \
    https://github.com/Rifat137710/Public.git /kaggle/working/safesac-repo
%cd /kaggle/working/safesac-repo
!git rev-parse --short HEAD
"""

# ============================ CELL 3 -- sanity =============================
# Two minutes. If this does not print a clean table, stop -- do not spend three
# hours of quota on a broken environment.
SANITY = r"""
!python -m pytest tests/test_powerflow.py tests/test_projection.py -q 2>&1 | tail -5
!python scripts/projected_heuristics.py --episodes 5 2>&1 | grep -v Warning | tail -20
"""

# ======================== CELL 4 -- the experiment =========================
# Fill in the operating point from G0 (scripts/operating_point_sweep.py) before
# running. The defaults below are the Stage 1 point, which G0 may move.
RUN = r"""
import os
os.environ["OMP_NUM_THREADS"] = "4"
os.environ["MKL_NUM_THREADS"] = "4"

!python scripts/transfer_study.py \
    --seeds 0 1 2 3 4 \
    --episodes 200 \
    --eval-episodes 20 \
    --alpha 0.003 \
    --train-z 0.5 \
    --deploy-z 0.5 2.0 4.0 6.0 \
    --load 0.40 \
    --evs 30 \
    --out-dir /kaggle/working/results/transfer \
    2>&1 | grep -v "UserWarning\|warnings.warn"
"""

# =========================== CELL 5 -- collect =============================
# Kaggle keeps /kaggle/working as the notebook output. Copy the results out and
# check them in -- an unsaved run is a run you have to pay for twice.
COLLECT = r"""
import json, shutil
from pathlib import Path

res = Path("/kaggle/working/results/transfer/transfer.json")
d = json.loads(res.read_text())
print("train Z", d["train_z_pct"], "| deploy", d["deploy_z_pct"],
      "| seeds", d["seeds"], "| fingerprint", d["train_fingerprint"])
for z, row in d["summary"].items():
    print(f"Z={z:>4}%  " + "  ".join(
        f"{a}: {r['viol'][0]:.4f}/{r['soc'][0]:.3f}" for a, r in row.items()))

shutil.make_archive("/kaggle/working/transfer_results", "zip",
                    "/kaggle/working/results")
print("download /kaggle/working/transfer_results.zip")
"""

CELLS = [SETUP, CLONE, SANITY, RUN, COLLECT]

if __name__ == "__main__":
    for i, c in enumerate(CELLS, 1):
        print(f"# ---------- CELL {i} ----------")
        print(c.strip(), "\n")
