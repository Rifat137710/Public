"""
Integration patches for the SafeSAC thesis notebook.

Follows the notebook's existing "Patch N" idiom: each function monkey-patches
one piece of the shipped pipeline in place, is idempotent, and leaves every
call signature unchanged so nothing downstream needs editing.

Apply from a notebook cell after all definition blocks have run::

    import safesac_patch
    safesac_patch.apply_all(globals())

What each patch does
--------------------
``patch_power_flow``
    Replaces ``run_pf`` with :mod:`radial_pf`. Same ``PFResult``, ~1400x
    faster, matching pandapower to ~3e-11 pu.

``patch_sensitivities``
    Replaces the 8-power-flow finite-difference refresh in
    ``compute_grid_sensitivities`` with the analytic LinDistFlow kernel for
    ``dV/dP`` and ``dV/dQ``, and a fast-solver finite difference for the two
    transformer-loading columns. Makes ``sensitivity_refresh_steps = 1``
    affordable, so the projection stops running on an hour-stale linearisation.

``patch_lagrangian``
    Replaces the multiplier update in ``SACLagAgent.train_step`` with
    :class:`lagrangian.LagrangeController`. The shipped update compares a
    discounted cost *return* against a per-step budget — a factor of
    ``1/(1-gamma)`` — and produced ``lambda = 0.0`` in both SAC-Lag runs.

``patch_projection_telemetry``
    The shipped ``SafeSACLagAgent.select_action`` wraps the sensitivity and
    projection path in a bare ``except Exception`` that silently returns the
    unprojected action. This counts those events (and infeasible/frozen
    solves) on the agent so they reach the episode log.

Verification status
-------------------
``patch_power_flow`` and ``patch_sensitivities`` are covered by
``test_integration.py`` against pandapower on the thesis feeders.
``patch_lagrangian`` and ``patch_projection_telemetry`` touch torch code that
cannot be exercised without the full training stack; their first instrumented
run is the check. ``LagrangeController`` itself is covered by
``test_lagrangian.py``.
"""

from __future__ import annotations

import math
from typing import Any, Optional

import numpy as np

from lagrangian import LagrangeController
from radial_pf import RadialPowerFlow, build_topology

__all__ = [
    "apply_all",
    "patch_power_flow",
    "patch_sensitivities",
    "patch_lagrangian",
    "patch_projection_telemetry",
    "get_solver",
    "clear_cache",
]

S_BASE_MVA = 1.0
_CACHE: dict[int, tuple] = {}


# ---------------------------------------------------------------------------
def get_solver(nc) -> tuple:
    """Return ``(topology, solver, meta)`` for a NetworkContext, cached.

    ``meta`` carries the substation-branch index and the current-base constant
    needed to reproduce ``transformer_loading_pu``.
    """
    key = id(nc)
    hit = _CACHE.get(key)
    if hit is not None and hit[0].n_bus == len(nc.net.bus):
        return hit

    net = nc.net
    topo = build_topology(net, s_base_mva=S_BASE_MVA)
    v_slack = complex(float(net.ext_grid.vm_pu.iloc[0]), 0.0)
    solver = RadialPowerFlow(topo, v_slack=v_slack)

    meta: dict[str, Any] = {"thevenin_bus": None, "loading_per_pu_current": 0.0}
    mask = (net.line["name"] == "substation_thevenin").to_numpy()
    if mask.any():
        to_bus = int(net.line.loc[mask, "to_bus"].iloc[0])
        max_i_ka = float(net.line.loc[mask, "max_i_ka"].iloc[0])
        # |I_ka| = |I_pu| * S_base / (sqrt(3) * V_base); loading = |I_ka| / max_i_ka.
        i_base_ka = S_BASE_MVA / (math.sqrt(3.0) * topo.v_base_kv)
        meta["thevenin_bus"] = to_bus
        meta["loading_per_pu_current"] = i_base_ka / max_i_ka

    # Structural index arrays never change during a run; caching them keeps the
    # per-step pandas cost to two column reads per table instead of six.
    meta["load_bus"] = net.load.bus.to_numpy(int) if len(net.load) else np.empty(0, int)
    meta["sgen_bus"] = net.sgen.bus.to_numpy(int) if len(net.sgen) else np.empty(0, int)
    meta["p_buf"] = np.zeros(topo.n_bus)
    meta["q_buf"] = np.zeros(topo.n_bus)

    out = (topo, solver, meta)
    _CACHE[key] = out
    return out


def _injections(nc, topo, meta):
    """Per-bus injections in pu. Positive = into the network."""
    net = nc.net
    p = meta["p_buf"]; q = meta["q_buf"]
    p.fill(0.0); q.fill(0.0)
    if meta["load_bus"].size:
        lp = net.load.p_mw.to_numpy(float)
        lq = net.load.q_mvar.to_numpy(float)
        meta["load_total"] = (float(lp.sum()), float(lq.sum()))
        np.add.at(p, meta["load_bus"], -lp)
        np.add.at(q, meta["load_bus"], -lq)
    else:
        meta["load_total"] = (0.0, 0.0)
    if meta["sgen_bus"].size:
        np.add.at(p, meta["sgen_bus"], net.sgen.p_mw.to_numpy(float))
        np.add.at(q, meta["sgen_bus"], net.sgen.q_mvar.to_numpy(float))
    if S_BASE_MVA != 1.0:
        p /= S_BASE_MVA; q /= S_BASE_MVA
    return p, q


def clear_cache() -> None:
    _CACHE.clear()


def _solve_arrays(solver, meta, p, q, warm_start: bool = True):
    """Solve from injection arrays directly — no pandas round-trip."""
    res = solver.solve(p, q, tol=1e-10, max_iter=60, warm_start=warm_start)
    p_loss = solver.losses_pu(res.v, p, q) * S_BASE_MVA
    loading = 0.0
    if meta["thevenin_bus"] is not None:
        j = solver.branch_currents(res.v, p, q)
        loading = abs(j[meta["thevenin_bus"]]) * meta["loading_per_pu_current"]
    return res, p_loss, loading


def _solve(nc, warm_start: bool = True):
    """Solve and return everything ``PFResult`` needs."""
    topo, solver, meta = get_solver(nc)
    p, q = _injections(nc, topo, meta)
    res, p_loss, loading = _solve_arrays(solver, meta, p, q, warm_start)
    return res, p, q, p_loss, loading


# ---------------------------------------------------------------------------
def patch_power_flow(ns: dict) -> None:
    """Swap ``run_pf`` for the fast radial solver."""
    if getattr(ns.get("run_pf"), "_safesac_patched", False):
        print("run_pf already patched - skipping.")
        return

    PFResult = ns["PFResult"]

    def run_pf_fast(nc, *, max_iter: int = 30):
        try:
            res, p, q, p_loss, loading = _solve(nc)
        except Exception:
            n = len(nc.net.bus)
            nan = float("nan")
            return PFResult(converged=False, v_pu=np.full(n, nan),
                            v_angle_deg=np.full(n, nan), p_load_mw_total=nan,
                            q_load_mvar_total=nan, p_ext_mw=nan, p_loss_mw=nan,
                            transformer_loading_pu=nan)

        _, _, meta = get_solver(nc)
        p_load, q_load = meta["load_total"]   # already read by _injections
        # Slack import balances the net injection plus network losses.
        p_ext = float(-p.sum() * S_BASE_MVA + p_loss)

        return PFResult(
            converged=bool(res.converged),
            v_pu=res.vm_pu,
            v_angle_deg=res.va_deg,
            p_load_mw_total=p_load,
            q_load_mvar_total=q_load,
            p_ext_mw=p_ext,
            p_loss_mw=float(p_loss),
            transformer_loading_pu=float(loading),
        )

    run_pf_fast._safesac_patched = True
    ns["run_pf"] = run_pf_fast
    print("Patched run_pf: fast radial solver (~1400x, 3e-11 pu vs pandapower).")


def patch_sensitivities(ns: dict, *, analytic_dv: bool = True) -> None:
    """Swap the finite-difference sensitivity refresh for the analytic kernel.

    ``analytic_dv=False`` keeps a finite difference for ``dV`` too, still on
    the fast solver (~1 ms, machine-exact against pandapower) — use it if the
    LinDistFlow error (median ~3%) must be eliminated.
    """
    if getattr(ns.get("compute_grid_sensitivities"), "_safesac_patched", False):
        print("compute_grid_sensitivities already patched - skipping.")
        return

    GridSensitivities = ns["GridSensitivities"]
    CFG = ns["CFG"]

    def compute_fast(nc, *, perturb_kw=None):
        if perturb_kw is None:
            perturb_kw = CFG("sensitivity_perturbation_kw")
        topo, solver, meta = get_solver(nc)
        ev_buses = list(nc.ev_station_buses)
        sg = list(nc.ev_sgen_idx)

        base_p_mw = nc.net.sgen.loc[sg, "p_mw"].to_numpy(float).copy()
        base_q_mvar = nc.net.sgen.loc[sg, "q_mvar"].to_numpy(float).copy()

        p, q = _injections(nc, topo, meta)
        p = p.copy(); q = q.copy()   # _injections hands back shared buffers
        res, p_loss, loading = _solve_arrays(solver, meta, p, q)
        if not res.converged:
            raise RuntimeError("Base PF did not converge.")
        p_ext = float(-p.sum() * S_BASE_MVA + p_loss)

        # dV: analytic kernel, pu per pu -> pu per kW.
        if analytic_dv:
            dv_dp, dv_dq = solver.sensitivities(v=res.v, buses=ev_buses)
        else:
            d_pu = perturb_kw / 1000.0 / S_BASE_MVA
            dv_dp, dv_dq = solver.sensitivities_fd(p, q, ev_buses, delta_pu=d_pu)
        dv_dp = dv_dp / (1000.0 * S_BASE_MVA)
        dv_dq = dv_dq / (1000.0 * S_BASE_MVA)

        # dL: central difference on the injection arrays directly. Perturbing a
        # station's bus injection is equivalent to perturbing its sgen, and
        # avoids 16 pandas round-trips per refresh.
        n_st = len(sg)
        dl_dp = np.zeros(n_st)
        dl_dq = np.zeros(n_st)
        if meta["thevenin_bus"] is not None:
            d_pu = perturb_kw / 1000.0 / S_BASE_MVA
            for j, bus in enumerate(ev_buses):
                for vec, out in ((p, dl_dp), (q, dl_dq)):
                    base = vec[bus]
                    vec[bus] = base + d_pu
                    _, _, l_hi = _solve_arrays(solver, meta, p, q)
                    vec[bus] = base - d_pu
                    _, _, l_lo = _solve_arrays(solver, meta, p, q)
                    vec[bus] = base
                    out[j] = (l_hi - l_lo) / (2.0 * perturb_kw)
            _solve_arrays(solver, meta, p, q)  # restore the warm start

        return GridSensitivities(
            dV_dP=dv_dp, dV_dQ=dv_dq, dL_dP=dl_dp, dL_dQ=dl_dq,
            v_base=res.vm_pu.copy(),
            L_base=float(loading),
            p_base_kw=base_p_mw * 1000.0,
            q_base_kvar=base_q_mvar * 1000.0,
            operating_point={"config": nc.config, "perturb_kw": perturb_kw,
                             "p_ext_mw": p_ext,
                             "p_loss_mw": float(p_loss),
                             "method": "analytic" if analytic_dv else "fd_fast"},
        )

    compute_fast._safesac_patched = True
    ns["compute_grid_sensitivities"] = compute_fast
    mode = "analytic" if analytic_dv else "fast finite-difference"
    print(f"Patched compute_grid_sensitivities: {mode} dV, fast-FD dL.")
    print("  -> set CONFIG['sensitivity_refresh_steps'] = 1 (per-step refresh "
          "is now affordable).")


# ---------------------------------------------------------------------------
def patch_lagrangian(
    ns: dict,
    *,
    d_step: float = 0.01,
    lr: Optional[float] = None,
    kp: float = 0.0,
    kd: float = 0.0,
    lam_max: float = 100.0,
) -> None:
    """Replace the multiplier update in ``SACLagAgent.train_step``.

    ``d_step`` is the per-step cost budget. Set it *above* the structural cost
    floor measured in Phase 1 — a budget below the floor makes the CMDP
    infeasible and pins ``lambda`` at ``lam_max``.  Prefer
    ``LagrangeController.from_measured_floor`` once that number exists.
    """
    torch = ns["torch"]
    SACLagAgent = ns["SACLagAgent"]

    if getattr(SACLagAgent.train_step, "_safesac_patched", False):
        print("SACLagAgent.train_step already patched - skipping.")
        return

    def train_step(self):
        if len(self.replay) < self.batch_size:
            return None

        if not hasattr(self, "lag"):
            self.lag = LagrangeController(
                d_step=d_step, gamma=self.gamma,
                lr=self.lr_lambda if lr is None else lr,
                kp=kp, kd=kd, lam_max=lam_max)

        batch = self.replay.sample(self.batch_size)
        obs = torch.tensor(batch["obs"], device=self.device)
        action_e = torch.tensor(batch["action_exec"], device=self.device)
        reward = torch.tensor(batch["reward"], device=self.device)
        cost = torch.tensor(batch["cost"], device=self.device)
        next_obs = torch.tensor(batch["next_obs"], device=self.device)
        done = torch.tensor(batch["done"], device=self.device)

        with torch.no_grad():
            next_action, next_log_prob, _ = self.actor.sample(next_obs)
            tq1 = self.target_critic1(next_obs, next_action)
            tq2 = self.target_critic2(next_obs, next_action)
            target_q = torch.min(tq1, tq2) - self.alpha * next_log_prob
            y = reward + self.gamma * (1.0 - done) * target_q
            y_c = cost + self.gamma * (1.0 - done) * self.target_cost_critic(
                next_obs, next_action)

        F = ns["F"]
        loss_q1 = F.mse_loss(self.critic1(obs, action_e), y)
        loss_q2 = F.mse_loss(self.critic2(obs, action_e), y)
        loss_qc = F.mse_loss(self.cost_critic(obs, action_e), y_c)
        self.critic1_optim.zero_grad(); loss_q1.backward(); self.critic1_optim.step()
        self.critic2_optim.zero_grad(); loss_q2.backward(); self.critic2_optim.step()
        self.cost_critic_optim.zero_grad(); loss_qc.backward(); self.cost_critic_optim.step()

        new_action, log_prob, _ = self.actor.sample(obs)
        q_new = torch.min(self.critic1(obs, new_action), self.critic2(obs, new_action))
        qc_new = self.cost_critic(obs, new_action)

        # -- the fix: compare the cost RETURN against a RETURN-scale budget --
        cost_excess = qc_new - self.lag.d_return
        lag_term = self.lag.lam * cost_excess.mean()
        quad_term = (self.quad_penalty / 2.0) * torch.clamp(
            cost_excess, min=0).pow(2).mean()
        actor_loss = (self.alpha * log_prob - q_new).mean() + lag_term + quad_term
        self.actor_optim.zero_grad(); actor_loss.backward(); self.actor_optim.step()

        alpha_loss = -(self.log_alpha * (log_prob.detach() + self.target_entropy)).mean()
        self.alpha_optim.zero_grad(); alpha_loss.backward(); self.alpha_optim.step()

        with torch.no_grad():
            jc = float(qc_new.mean().item())
        self.lambda_lagrange = self.lag.update(jc)
        self.quad_penalty = min(
            self.quad_penalty_max,
            (self.update_step / max(1, self.quad_warmup_steps)) * self.quad_penalty_max)

        self._polyak(self.target_critic1, self.critic1)
        self._polyak(self.target_critic2, self.critic2)
        self._polyak(self.target_cost_critic, self.cost_critic)
        self.update_step += 1

        return {"loss_q1": float(loss_q1.item()), "loss_q2": float(loss_q2.item()),
                "loss_qc": float(loss_qc.item()), "actor_loss": float(actor_loss.item()),
                "alpha_loss": float(alpha_loss.item()), "alpha": float(self.alpha),
                "lambda": float(self.lambda_lagrange),
                "quad_penalty": float(self.quad_penalty),
                "mean_qc": jc, "d_return": self.lag.d_return,
                "cost_excess": jc - self.lag.d_return}

    train_step._safesac_patched = True
    SACLagAgent.train_step = train_step
    c = LagrangeController(d_step=d_step, gamma=0.99)
    print(f"Patched SACLagAgent.train_step: LagrangeController "
          f"(d_step={d_step:g} -> d_return={c.d_return:g} at gamma=0.99).")
    print("  -> check agent.lag.health() at the end of every run.")


def patch_projection_telemetry(ns: dict) -> None:
    """Count silent projection bypasses instead of swallowing them."""
    SafeSACLagAgent = ns["SafeSACLagAgent"]
    if getattr(SafeSACLagAgent.select_action, "_safesac_patched", False):
        print("SafeSACLagAgent.select_action already patched - skipping.")
        return

    CFG = ns["CFG"]
    SACLagAgent = ns["SACLagAgent"]

    def select_action(self, obs, info=None, deterministic=False):
        for name in ("proj_exceptions", "proj_calls"):
            if not hasattr(self, name):
                setattr(self, name, 0)
        self.proj_calls += 1
        self.last_projection_exception = False
        self.last_projection_frozen = False
        self.last_projection_delta_kw = 0.0

        raw_action = SACLagAgent.select_action(
            self, obs, info=info, deterministic=deterministic)
        try:
            if self.env_ref.nc is None:
                raise RuntimeError("env not reset yet")
            if self.sens_cache.maybe_refresh(self.env_ref.nc,
                                             self.env_ref.current_step):
                self.projector.on_sensitivity_refresh()
            sm = self.sens_cache.get()
        except Exception as exc:
            # Previously swallowed. A safety layer that can disable itself
            # without leaving a trace is not a safety layer.
            self.proj_exceptions += 1
            self.last_projection_exception = True
            self.last_projection_error = f"{type(exc).__name__}: {exc}"
            self._last_raw_action = raw_action
            self._last_safe_action = raw_action.copy()
            return raw_action

        s_rated = CFG("ev_station_S_rated_kva")
        n_st = self.env_ref.n_stations
        res = self.projector.project(
            raw_action[:n_st] * s_rated, raw_action[n_st:] * s_rated,
            self.env_ref._prev_p_kw, self.env_ref._prev_q_kvar, sm)

        if res["all_frozen"]:
            safe_p = np.zeros(n_st); safe_q = np.zeros(n_st)
            self.last_projection_frozen = True
        else:
            safe_p, safe_q = res["safe_p_kw"], res["safe_q_kvar"]

        safe_action = np.clip(
            np.concatenate([safe_p / s_rated, safe_q / s_rated]), -1.0, 1.0
        ).astype(np.float32)

        self.last_projection_delta_kw = float(
            np.max(np.abs(raw_action - safe_action))) * s_rated
        self._last_raw_action = raw_action
        self._last_safe_action = safe_action
        return safe_action

    select_action._safesac_patched = True
    SafeSACLagAgent.select_action = select_action

    # Count exceptions at the source rather than inferring them.
    proj_cls = ns["SensitivityProjector"]
    if not getattr(proj_cls.project, "_safesac_patched", False):
        inner_project = proj_cls.project

        def project(self, raw_p_kw, raw_q_kvar, prev_p_kw, prev_q_kvar, sm):
            res = inner_project(self, raw_p_kw, raw_q_kvar, prev_p_kw, prev_q_kvar, sm)
            self.n_calls = getattr(self, "n_calls", 0) + 1
            if str(res.get("status", "")) != "ok":
                self.n_infeasible = getattr(self, "n_infeasible", 0) + 1
            if res.get("all_frozen"):
                self.n_frozen = getattr(self, "n_frozen", 0) + 1
            return res

        project._safesac_patched = True
        proj_cls.project = project

    print("Patched projection telemetry: exception/infeasible/frozen counters "
          "on the agent and projector.")


# ---------------------------------------------------------------------------
def apply_all(ns: dict, *, d_step: float = 0.01, analytic_dv: bool = True) -> None:
    """Apply every patch. Idempotent."""
    print("=" * 64)
    print("SafeSAC pipeline patches")
    print("=" * 64)
    patch_power_flow(ns)
    patch_sensitivities(ns, analytic_dv=analytic_dv)
    patch_lagrangian(ns, d_step=d_step)
    patch_projection_telemetry(ns)
    print("=" * 64)
