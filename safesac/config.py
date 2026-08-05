"""Configuration and seed derivation.

The thesis kept its settings in a module-level ``CONFIG`` dict that later cells
mutated through monkey-patches. Whether a given number was in force depended on
which cells had run, in which order -- which is how audit items A1, A2 and B1
happened. Here every setting lives in a frozen dataclass, an experiment is one
``ExperimentConfig``, and nothing mutates it after construction.

``ExperimentConfig.thesis_final()`` reproduces the state the shipped results
were actually produced under: Block 1 defaults, plus Patch 1's fleet tightening
and load scale 0.50, plus Patch 6's projection margin.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field, replace
from typing import Tuple

from .network import FeederConfig

MASTER_SEED = 137710

_TRAIN_SEED_OFFSET = 1_000_000
_EVAL_SEED_OFFSET = 9_000_000


def derive_seed(master: int, *tags) -> int:
    """BLAKE2b-derived child seed. Byte-for-byte the thesis's scheme."""
    h = hashlib.blake2b(digest_size=8)
    h.update(str(master).encode())
    for t in tags:
        h.update(b"|")
        h.update(str(t).encode())
    return int.from_bytes(h.digest()[:4], "little")


def train_episode_seed(master: int, episode_idx: int, run_label: str = "") -> int:
    return derive_seed(master, "train", run_label, _TRAIN_SEED_OFFSET + episode_idx)


def eval_episode_seed(master: int, episode_idx: int, run_label: str = "eval") -> int:
    return derive_seed(master, "eval", run_label, _EVAL_SEED_OFFSET + episode_idx)


@dataclass(frozen=True)
class TimeConfig:
    step_minutes: int = 5
    steps_per_hour: int = 12
    steps_per_day: int = 288
    episode_days: int = 1


@dataclass(frozen=True)
class FleetConfig:
    """Post-Patch-1 values; the pre-patch defaults are in `thesis_block1()`."""

    size_per_station_mean: float = 10.0
    size_per_station_std: float = 2.0

    battery_capacity_mean_kwh: float = 60.0
    battery_capacity_std_kwh: float = 15.0
    battery_capacity_min_kwh: float = 30.0
    battery_capacity_max_kwh: float = 100.0

    charge_efficiency: float = 0.92
    discharge_efficiency: float = 0.92

    arrival_morning_peak_hour: float = 8.5
    arrival_morning_std_hour: float = 1.0
    arrival_morning_weight: float = 0.55
    arrival_evening_peak_hour: float = 18.0
    arrival_evening_std_hour: float = 1.5

    dwell_hours_mean: float = 7.0
    dwell_hours_sigma: float = 0.45
    dwell_hours_min: float = 2.0
    dwell_hours_max: float = 12.0

    soc_init_min: float = 0.15
    soc_init_max: float = 0.55
    soc_target_min: float = 0.70
    soc_target_max: float = 0.90

    v2g_optout_prob: float = 0.20
    no_show_prob: float = 0.05
    early_depart_prob: float = 0.10
    early_depart_range: Tuple[float, float] = (0.70, 0.95)

    max_charge_kw: float = 22.0
    max_discharge_kw: float = 22.0
    soc_floor_discharge: float = 0.20


@dataclass(frozen=True)
class ScenarioConfig:
    load_scale: float = 0.50
    load_noise_std: float = 0.02
    start_day_of_year: int = 120
    start_day_of_week: int = 0

    pv_latitude_deg: float = 40.0
    cloud_rho: float = 0.96
    cloud_sigma: float = 0.04
    cloud_mean: float = 0.85

    tou_offpeak: float = 0.08
    tou_shoulder: float = 0.15
    tou_onpeak: float = 0.30
    v2g_price_fraction: float = 0.70


@dataclass(frozen=True)
class RewardConfig:
    """Weights and scales exactly as they were in force for the shipped results.

    ``include_loss_term`` exposes audit item B1: the feeder-loss term is 51.6 %
    of the reward magnitude under a random policy while the economic term the
    abstract leads with is 2.1 %. Stage 1 turns it off.
    """

    weight_cost: float = 1.0
    weight_user: float = 5.0
    weight_deg: float = 0.5
    weight_loss: float = 1.0

    scale_cost: float = 5.0
    scale_user: float = 100.0
    scale_deg: float = 1.0
    scale_loss: float = 1.0

    include_loss_term: bool = True
    user_penalty_quadratic: bool = True
    degradation_usd_per_kwh: float = 0.040
    pf_failure_penalty: float = 10.0


@dataclass(frozen=True)
class SafetyConfig:
    voltage_lower_pu: float = 0.95
    voltage_upper_pu: float = 1.05
    transformer_loading_limit_pu: float = 1.0

    projection_margin_pu: float = 0.010
    sensitivity_refresh_steps: int = 12
    max_consecutive_failures: int = 3
    station_ramp_per_step_pu: float = 0.50


@dataclass(frozen=True)
class ExperimentConfig:
    feeder: FeederConfig = field(default_factory=FeederConfig)
    time: TimeConfig = field(default_factory=TimeConfig)
    fleet: FleetConfig = field(default_factory=FleetConfig)
    scenario: ScenarioConfig = field(default_factory=ScenarioConfig)
    reward: RewardConfig = field(default_factory=RewardConfig)
    safety: SafetyConfig = field(default_factory=SafetyConfig)
    master_seed: int = MASTER_SEED

    # ---- named presets ---------------------------------------------------

    @classmethod
    def thesis_final(cls, variant: str = "weak") -> "ExperimentConfig":
        """The configuration the shipped results were produced under."""
        return cls(feeder=FeederConfig(variant=variant))

    @classmethod
    def thesis_block1(cls, variant: str = "weak") -> "ExperimentConfig":
        """Pre-Patch-1 defaults, for reproducing the Block 1-4 validation cells."""
        return cls(
            feeder=FeederConfig(variant=variant),
            fleet=FleetConfig(
                dwell_hours_mean=6.0,
                dwell_hours_min=0.5,
                dwell_hours_max=14.0,
                soc_init_min=0.10,
                soc_init_max=0.60,
                soc_target_max=0.95,
                early_depart_range=(0.4, 0.9),
            ),
            scenario=ScenarioConfig(load_scale=1.0),
            safety=SafetyConfig(projection_margin_pu=0.0),
        )

    @classmethod
    def clean_operating_point(cls, variant: str = "weak") -> "ExperimentConfig":
        """Stage 1 onward: load scale 0.40.

        The only scale where the idle feeder is fully compliant (0/288 violating
        steps) *and* full-rate charging genuinely violates (0.0868), so every
        violation is attributable to the controller. See docs/01-audit item A4.
        """
        return cls(
            feeder=FeederConfig(variant=variant),
            scenario=ScenarioConfig(load_scale=0.40),
        )

    def with_(self, **kwargs) -> "ExperimentConfig":
        return replace(self, **kwargs)

    def fingerprint(self) -> str:
        blob = json.dumps(asdict(self), sort_keys=True, default=str)
        return hashlib.sha256(blob.encode()).hexdigest()[:16]
