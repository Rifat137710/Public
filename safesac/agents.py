"""Controllers. Torch-free ones live here; the learned agents import lazily.

Sign convention throughout: action component > 0 commands V2G injection,
< 0 commands charging.
"""

from __future__ import annotations

import numpy as np


class BaseAgent:
    name = "base"

    def select_action(self, obs, info=None, deterministic=False):
        raise NotImplementedError

    def reset_episode(self):
        pass


class ZeroAgent(BaseAgent):
    """Do-nothing reference: chargers idle.

    Not in the thesis. It is the missing baseline from audit item A4 -- without
    it there is no way to say which violations the controller actually caused.
    """

    name = "zero"

    def __init__(self, env):
        self.env = env

    def select_action(self, obs=None, info=None, deterministic=False):
        return np.zeros(self.env.action_dim, dtype=np.float32)


class UncoordinatedAgent(BaseAgent):
    """Charge every connected vehicle at full rate until it hits target."""

    name = "uncoordinated"

    def __init__(self, env):
        self.env = env

    def select_action(self, obs=None, info=None, deterministic=False):
        n = self.env.n_stations
        p = np.zeros(n, dtype=np.float32)
        for j in range(n):
            if any(ev.soc < ev.soc_target for ev in self.env.active_evs[j]):
                p[j] = -1.0
        return np.concatenate([p, np.zeros(n, dtype=np.float32)])


class DroopAgent(BaseAgent):
    """Time-of-use active schedule plus an IEEE 1547-2018 Category-B Q-V droop."""

    name = "droop"

    V_LOW = 0.92
    V_DEADBAND_LO = 0.98
    V_DEADBAND_HI = 1.02
    V_HIGH = 1.08

    def __init__(self, env):
        self.env = env

    @classmethod
    def _qv_droop(cls, v: float) -> float:
        if v < cls.V_LOW:
            return 1.0
        if v < cls.V_DEADBAND_LO:
            return (cls.V_DEADBAND_LO - v) / (cls.V_DEADBAND_LO - cls.V_LOW)
        if v <= cls.V_DEADBAND_HI:
            return 0.0
        if v < cls.V_HIGH:
            return -(v - cls.V_DEADBAND_HI) / (cls.V_HIGH - cls.V_DEADBAND_HI)
        return -1.0

    def select_action(self, obs=None, info=None, deterministic=False):
        env = self.env
        n = env.n_stations
        t = min(env.current_step, env.scenario.n_steps - 1)
        hour = float(env.scenario.hour_of_day[t])

        if hour < 6 or hour >= 22:
            p_default = -1.0  # charge hard off-peak
        elif 16 <= hour < 21:
            p_default = +0.5  # discharge into the evening peak
        else:
            p_default = -0.3

        p = np.full(n, p_default, dtype=np.float32)
        for j in range(n):
            if not env.active_evs[j]:
                p[j] = 0.0

        v = env._last_pf.v_pu if env._last_pf is not None else np.ones(env.feeder.n_bus)
        q = np.array(
            [self._qv_droop(float(v[bus])) for bus in env.feeder.ev_buses], dtype=np.float32
        )
        return np.concatenate([p, q])
