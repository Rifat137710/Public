"""Wrap any controller in the safety projection.

The thesis only ever composed the projection with the learned policy, so
"SafeSAC vs SAC-Lag" silently bundles two questions: does the projection make
actions safe, and does the *learned* policy contribute anything on top of it.
Projecting a heuristic separates them, and it is a two-line experiment any
reviewer can run -- so it belongs in the paper rather than in a rebuttal.

The projection path here is identical to `SafeSACLagAgent.select_action`: same
projector, same cache and refresh clock, same freeze-to-zero fallback, same
clip. Only the source of the raw action differs.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Optional

import numpy as np

from .agents import BaseAgent
from .config import ExperimentConfig
from .env import N_BUS_CANONICAL, ChargingFeederEnv
from .learned import ProjectionStats
from .projection import SensitivityCache, SensitivityProjector


class ProjectedAgent(BaseAgent):
    """Compose a base controller with the sensitivity projection.

    Args:
        base: any agent exposing ``select_action``.
        env: the environment it acts in (needed for the feeder and prior setpoints).
        cfg: overrides ``env.cfg`` -- use it to vary the projection margin.
        skip_when_feasible: pre-check that skips the solve when the raw action
            already satisfies every constraint. Proven equivalent, just faster.
        frozen_sensitivities: the "fixed-model" arm -- a projection parametrised
            on the *training* network rather than the deployment one.
        frozen_mode: what "fixed model" means, and the distinction matters.

            ``"jacobian"`` (default) freezes only ``dv_dp`` / ``dv_dq`` -- the
            part that genuinely requires a network model -- while the base point
            (``v_base``, ``p_base_kw``, ``q_base_kvar``) is refreshed from the
            deployment feeder. This is the fair comparison and the one the prior
            art describes: a deployed controller carries a fixed admittance
            model but *measures* its own voltages.

            ``"snapshot"`` freezes the whole `Sensitivities` object, base point
            included. That conflates model mismatch with linearisation
            staleness: a base point captured on an idle feeder makes the
            constraint inert no matter which network it came from, so every
            frozen arm degenerates to the unprojected action and the comparison
            measures nothing about transfer. Kept only so the confound can be
            demonstrated rather than argued about.
    """

    def __init__(
        self,
        base: BaseAgent,
        env: ChargingFeederEnv,
        cfg: Optional[ExperimentConfig] = None,
        *,
        skip_when_feasible: bool = True,
        frozen_sensitivities=None,
        frozen_loading=None,
        frozen_mode: str = "jacobian",
    ):
        if frozen_mode not in ("jacobian", "snapshot"):
            raise ValueError(f"unknown frozen_mode {frozen_mode!r}")
        self.base = base
        self.env = env
        self.cfg = cfg or env.cfg
        self.projector = SensitivityProjector(self.cfg, env.n_stations, N_BUS_CANONICAL)
        self.cache: Optional[SensitivityCache] = None
        self.stats = ProjectionStats()
        self.skip_when_feasible = skip_when_feasible
        self.frozen_sens = frozen_sensitivities
        self.frozen_loading = frozen_loading
        self.frozen_mode = frozen_mode
        self.name = f"{getattr(base, 'name', 'base')}+projection"

    def reset_episode(self) -> None:
        self.base.reset_episode()
        if self.cache is None:
            self.cache = SensitivityCache(self.cfg, self.env.feeder, self.env._pf_solver)
        else:
            self.cache.rebind(self.env.feeder, self.env._pf_solver)
            self.cache.invalidate()
        self.projector.on_refresh()

    def select_action(self, obs, info=None, deterministic: bool = False) -> np.ndarray:
        raw = np.asarray(
            self.base.select_action(obs, info=info, deterministic=deterministic),
            dtype=np.float32,
        )
        n = self.env.n_stations
        rated = self.cfg.feeder.ev_station_kva

        if self.cache is None or self.env._last_pf is None:
            self.stats.n_unavailable += 1
            return raw

        if self.cache.maybe_refresh(self.env.current_step):
            self.projector.on_refresh()

        if self.frozen_sens is None:
            sens, loading = self.cache.sens, self.cache.loading
        elif self.frozen_mode == "snapshot":
            sens, loading = self.frozen_sens, self.frozen_loading
        else:
            # Carry the training network's Jacobian; measure the base point.
            sens = replace(
                self.frozen_sens,
                v_base=self.cache.sens.v_base,
                p_base_kw=self.cache.sens.p_base_kw,
                q_base_kvar=self.cache.sens.q_base_kvar,
            )
            loading = self.cache.loading

        res = self.projector.project(
            raw[:n] * rated,
            raw[n:] * rated,
            self.env._prev_p_kw,
            self.env._prev_q_kvar,
            sens,
            loading,
            skip_when_feasible=self.skip_when_feasible,
        )
        self.stats.record(res)

        if res.all_frozen:
            safe_p, safe_q = np.zeros(n), np.zeros(n)
        else:
            safe_p, safe_q = res.p_kw, res.q_kvar

        return np.clip(
            np.concatenate([safe_p / rated, safe_q / rated]), -1.0, 1.0
        ).astype(np.float32)


__all__ = ["ProjectedAgent"]
