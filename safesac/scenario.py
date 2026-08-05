"""Episode scenarios: background load, PV, price, and the EV fleet.

Ported from `thesis11.ipynb` Block 2 with Patch 1's fleet changes folded in.
The order of every RNG draw is preserved exactly, because the shipped results
are only reproducible if the random stream is identical -- see
`tests/test_scenario.py`.

The residential load profile is still the thesis's parametric placeholder. The
notebook printed its own warning about this; audit item C1 tracks replacing it
with measured data.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List

import numpy as np

from .config import ExperimentConfig, derive_seed


@dataclass
class EV:
    ev_id: int
    station_idx: int
    battery_capacity_kwh: float
    arrival_step: int
    dwell_steps: int
    soc_init: float
    soc_target: float
    v2g_allowed: bool
    no_show: bool
    early_depart_factor: float
    soc: float = 0.0
    connected: bool = False
    departed: bool = False
    energy_delivered_kwh: float = 0.0
    energy_discharged_kwh: float = 0.0


@dataclass
class Scenario:
    n_steps: int
    seed: int
    fleet: List[List[EV]]
    hour_of_day: np.ndarray
    day_of_week: np.ndarray
    day_of_year: np.ndarray
    is_weekend: np.ndarray
    load_multiplier: np.ndarray  # (n_steps, n_loads)
    pv_kw: np.ndarray  # (n_steps, n_pv)
    retail_price: np.ndarray
    cloud_factor: np.ndarray
    metadata: dict = field(default_factory=dict)


# --------------------------------------------------------------------------
# Background load
# --------------------------------------------------------------------------


def residential_daily_multiplier(hour_of_day: float, is_weekend: bool = False) -> float:
    """Normalised residential load multiplier, roughly [0.4, 1.0].

    PLACEHOLDER -- a parametric baseline plus two Gaussian peaks, not measured
    data. Audit item C1.
    """
    if is_weekend:
        morn_h, morn_a, morn_w = 10.0, 0.25, 1.8
        even_h, even_a, even_w = 19.5, 0.55, 2.2
        baseline = 0.45
    else:
        morn_h, morn_a, morn_w = 7.5, 0.40, 1.5
        even_h, even_a, even_w = 19.0, 0.60, 2.0
        baseline = 0.40
    morn = morn_a * math.exp(-0.5 * ((hour_of_day - morn_h) / morn_w) ** 2)
    even = even_a * math.exp(-0.5 * ((hour_of_day - even_h) / even_w) ** 2)
    return baseline + morn + even


def sample_load_trajectory(cfg, n_steps, n_loads, hour_of_day, is_weekend, *, seed):
    rng = np.random.default_rng(seed)
    base = np.array(
        [residential_daily_multiplier(float(h), bool(w)) for h, w in zip(hour_of_day, is_weekend)]
    )
    sigma = cfg.scenario.load_noise_std
    noise = rng.lognormal(mean=-0.5 * sigma * sigma, sigma=sigma, size=(n_steps, n_loads))
    return base[:, None] * noise


# --------------------------------------------------------------------------
# PV
# --------------------------------------------------------------------------


def solar_elevation_deg(day_of_year: int, hour_of_day: float, latitude_deg: float) -> float:
    """Cooper (1969) declination approximation."""
    decl = 23.45 * math.sin(math.radians(360 * (284 + day_of_year) / 365))
    ha = 15.0 * (hour_of_day - 12.0)
    lat_r, decl_r, ha_r = map(math.radians, (latitude_deg, decl, ha))
    sin_elev = math.sin(lat_r) * math.sin(decl_r) + math.cos(lat_r) * math.cos(decl_r) * math.cos(
        ha_r
    )
    return math.degrees(math.asin(max(-1.0, min(1.0, sin_elev))))


def clear_sky_fraction(day_of_year: int, hour_of_day: float, latitude_deg: float) -> float:
    elev = solar_elevation_deg(day_of_year, hour_of_day, latitude_deg)
    return 0.0 if elev <= 0 else math.sin(math.radians(elev))


def sample_cloud_trajectory(cfg, n_steps: int, seed: int) -> np.ndarray:
    """Bounded AR(1) clarity factor. rho near 1 gives slow multi-hour patterns."""
    rng = np.random.default_rng(seed)
    rho, sigma, mean = cfg.scenario.cloud_rho, cfg.scenario.cloud_sigma, cfg.scenario.cloud_mean
    x = np.zeros(n_steps)
    x[0] = rng.uniform(0.6, 1.0)
    for t in range(1, n_steps):
        x[t] = rho * x[t - 1] + (1 - rho) * mean + sigma * rng.standard_normal()
    return np.clip(x, 0.0, 1.0)


def sample_pv_trajectory(cfg, n_steps, day_of_year, hour_of_day, *, seed):
    rated = cfg.feeder.pv_rated_kw
    cloud = sample_cloud_trajectory(cfg, n_steps, derive_seed(seed, "cloud"))
    pv_kw = np.zeros((n_steps, len(rated)))
    for t in range(n_steps):
        clear = clear_sky_fraction(
            int(day_of_year[t]), float(hour_of_day[t]), cfg.scenario.pv_latitude_deg
        )
        for i in range(len(rated)):
            pv_kw[t, i] = rated[i] * clear * cloud[t]
    return pv_kw, cloud


# --------------------------------------------------------------------------
# Price
# --------------------------------------------------------------------------


def tou_price(cfg, hour_of_day: float) -> float:
    h = float(hour_of_day) % 24
    if h < 6 or h >= 22:
        return cfg.scenario.tou_offpeak
    if 16 <= h < 21:
        return cfg.scenario.tou_onpeak
    return cfg.scenario.tou_shoulder


def v2g_buyback_price(cfg, retail_price: float) -> float:
    return cfg.scenario.v2g_price_fraction * retail_price


# --------------------------------------------------------------------------
# Fleet
# --------------------------------------------------------------------------


def _sample_arrival_hours(cfg, rng, n):
    f = cfg.fleet
    h = np.where(
        rng.random(n) < f.arrival_morning_weight,
        rng.normal(f.arrival_morning_peak_hour, f.arrival_morning_std_hour, n),
        rng.normal(f.arrival_evening_peak_hour, f.arrival_evening_std_hour, n),
    )
    return np.clip(h, 0.0, 23.99)


def _sample_dwell_steps(cfg, rng, n):
    f = cfg.fleet
    h = rng.lognormal(mean=math.log(f.dwell_hours_mean), sigma=f.dwell_hours_sigma, size=n)
    h = np.clip(h, f.dwell_hours_min, f.dwell_hours_max)
    return np.maximum(1, (h * cfg.time.steps_per_hour).round().astype(int))


def _sample_battery_capacity(cfg, rng, n):
    f = cfg.fleet
    cap = rng.normal(f.battery_capacity_mean_kwh, f.battery_capacity_std_kwh, n)
    return np.clip(cap, f.battery_capacity_min_kwh, f.battery_capacity_max_kwh)


def sample_fleet(cfg, n_stations: int, episode_days: int, seed: int) -> List[List[EV]]:
    """Draw order is load-bearing: it must match the thesis stream exactly."""
    rng = np.random.default_rng(seed)
    f = cfg.fleet
    mu_n = f.size_per_station_mean * episode_days
    sd_n = f.size_per_station_std * episode_days

    out: List[List[EV]] = []
    next_id = 0
    for stn in range(n_stations):
        n_evs = max(1, int(round(rng.normal(mu_n, sd_n))))
        arrival_h = _sample_arrival_hours(cfg, rng, n_evs)
        day_idx = rng.integers(0, episode_days, size=n_evs)
        arrival_step = day_idx * cfg.time.steps_per_day + (
            arrival_h * cfg.time.steps_per_hour
        ).astype(int)
        dwell_steps = _sample_dwell_steps(cfg, rng, n_evs)
        capacity = _sample_battery_capacity(cfg, rng, n_evs)
        soc_init = rng.uniform(f.soc_init_min, f.soc_init_max, size=n_evs)
        soc_target = rng.uniform(f.soc_target_min, f.soc_target_max, size=n_evs)
        v2g_allowed = rng.random(n_evs) >= f.v2g_optout_prob
        no_show = rng.random(n_evs) < f.no_show_prob
        early_factor = np.where(
            rng.random(n_evs) < f.early_depart_prob,
            rng.uniform(f.early_depart_range[0], f.early_depart_range[1], size=n_evs),
            1.0,
        )

        evs = [
            EV(
                ev_id=next_id + k,
                station_idx=stn,
                battery_capacity_kwh=float(capacity[k]),
                arrival_step=int(arrival_step[k]),
                dwell_steps=int(max(1, dwell_steps[k] * early_factor[k])),
                soc_init=float(soc_init[k]),
                soc_target=float(soc_target[k]),
                v2g_allowed=bool(v2g_allowed[k]),
                no_show=bool(no_show[k]),
                early_depart_factor=float(early_factor[k]),
            )
            for k in range(n_evs)
        ]
        next_id += n_evs
        evs.sort(key=lambda e: e.arrival_step)
        out.append(evs)
    return out


# --------------------------------------------------------------------------
# Assembly
# --------------------------------------------------------------------------


def sample_scenario(cfg: ExperimentConfig, *, seed: int, n_loads: int, n_stations: int) -> Scenario:
    episode_days = cfg.time.episode_days
    n_steps = episode_days * cfg.time.steps_per_day

    step_h = np.arange(n_steps) / cfg.time.steps_per_hour
    hour_of_day = step_h % 24
    day_idx = (step_h // 24).astype(int)
    day_of_year = (cfg.scenario.start_day_of_year + day_idx) % 365
    day_of_week = (cfg.scenario.start_day_of_week + day_idx) % 7
    is_weekend = (day_of_week >= 5).astype(int)

    load_mult = sample_load_trajectory(
        cfg, n_steps, n_loads, hour_of_day, is_weekend, seed=derive_seed(seed, "load")
    )
    pv_kw, cloud = sample_pv_trajectory(cfg, n_steps, day_of_year, hour_of_day, seed=seed)
    retail_price = np.array([tou_price(cfg, h) for h in hour_of_day])
    fleet = sample_fleet(cfg, n_stations, episode_days, seed=derive_seed(seed, "fleet"))

    return Scenario(
        n_steps=n_steps,
        seed=seed,
        fleet=fleet,
        hour_of_day=hour_of_day,
        day_of_week=day_of_week,
        day_of_year=day_of_year,
        is_weekend=is_weekend,
        load_multiplier=load_mult,
        pv_kw=pv_kw,
        retail_price=retail_price,
        cloud_factor=cloud,
        metadata={"n_loads": n_loads, "n_pv": len(cfg.feeder.pv_rated_kw)},
    )
