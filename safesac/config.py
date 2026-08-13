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

    reward_scale: float = 1.0
    """Divides the whole reward. A pure rescaling: it leaves the optimal policy
    identical and changes only the conditioning of the optimisation.

    It exists because SAC's entropy temperature is scale-sensitive and this
    reward is large -- about -10 per step, -3000 per episode, against the O(1)
    rewards SAC's defaults assume. Left at 1.0 the temperature diverges (the
    thesis reached alpha = 19.4); capped at 1.0 it pins against the cap and the
    entropy term swamps the task, giving a policy that discharges on 28 % of
    steps while 34 vehicles wait to charge. Neither setting learns.
    """

    shaping_weight: float = 0.0
    """Potential-based reward shaping on the pending user penalty.

    The entire reward signal is the departure penalty: doing nothing scores
    -34.49 against uncoordinated charging's -2.24, and the whole gap is
    ``total_user_penalty`` (68 979 vs 467). That penalty is quadratic in kWh
    shortfall -- about 841 for one unserved vehicle -- and arrives in a single
    step, up to 84 steps after the charging decisions that determined it. SAC
    does not solve the credit assignment: 500 episodes peak at SoC met 0.137
    around episode 150 and then decline to 0.048, while a constant "charge if
    anyone needs it" policy reaches 0.816.

    The potential is the penalty that *would* be levied if every connected
    vehicle departed now, so charging earns immediate credit for the penalty it
    is avoiding. Being potential-based (Ng, Harada & Russell 1999) it leaves the
    optimal policy unchanged -- the same guarantee as `reward_scale`, so the
    weight cannot manufacture a result, only change how fast the optimum is
    found. 0.0 keeps the thesis's reward exactly.
    """

    shaping_gamma: float = 1.0
    """Discount inside the shaping term, ``F = shaping_gamma * Phi(s') - Phi(s)``.

    Ng et al. state the invariance with the agent's own gamma, but at 0.99 the
    residual ``(gamma - 1) * Phi`` dominates: Phi is the pending penalty, of
    order -60 000, so the drift is about +600 per step and *rewards holding
    unmet demand*. Measured, it inverts the ordering the shaping exists to
    sharpen -- shaping sum 156 388 for doing nothing against 116 439 for
    charging everything. At 1.0 the drift vanishes and the ordering is correct
    and monotone in service: 80 577 / 89 561 / 101 939 for zero / droop /
    uncoordinated.

    The cost is that invariance becomes exact for the undiscounted episodic
    return and approximate for gamma = 0.99. That is the better trade: the term
    being dropped is precisely the perverse one.
    """

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

    @classmethod
    def stage1(cls, variant: str = "weak", evs_per_station: float = 30.0) -> "ExperimentConfig":
        """The operating point every Stage 1+ experiment runs at.

        Load scale 0.40 puts the idle feeder at zero violating steps, so every
        violation belongs to a charging decision (audit A4). Difficulty then
        comes from EV penetration rather than background load, which keeps that
        property and reframes the study as hosting capacity: at 30 vehicles per
        station per day the heuristics bracket a wide Pareto gap that neither
        one closes.

        The feeder-loss reward term is off here -- it was 51.6 % of the reward
        magnitude and is not what the abstract claims to optimise (audit B1).

        The projection margin stays at 0.010 pu, but now because it was measured
        rather than inherited. Against a worst-case full-charge request at this
        operating point (`scripts/characterize_operating_point.py`):

            margin   infeasible   realised violations   SoC met
            0.000      0.0000           0.0312           0.810
            0.005      0.0000           0.0003           0.786
            0.010      0.0017           0.0000           0.721
            0.020      0.1684           0.0000           0.611

        Margin 0 shows what the margin is for: first-order sensitivities alone
        leave 3.1 % of steps violating once the AC solve catches up. 0.010 is the
        smallest margin that drives realised violations to zero, and unlike the
        thesis's operating point -- where the same 0.010 was infeasible on 12.5 %
        of steps -- it is essentially always satisfiable here.
        """
        return cls(
            feeder=FeederConfig(variant=variant),
            fleet=FleetConfig(
                size_per_station_mean=evs_per_station,
                size_per_station_std=evs_per_station * 0.20,
            ),
            scenario=ScenarioConfig(load_scale=0.40),
            reward=RewardConfig(
                include_loss_term=False, reward_scale=100.0, shaping_weight=1.0
            ),
        )

    @classmethod
    def stiffness(
        cls,
        substation_z_pct: float,
        *,
        rx_ratio: float = 2.0,
        evs_per_station: float = 30.0,
        load_scale: float = 0.40,
    ) -> "ExperimentConfig":
        """A `stage1` feeder at an arbitrary substation stiffness.

        The deployment axis for the transfer study. The thesis had exactly two
        networks -- "weak" (Z = 6 %) and "strong" (an infinite bus) -- which is
        two points, one of them synthesised. Two points cannot show that
        degradation is systematic rather than anecdotal; a continuum can, and
        it costs no new feeder data.

        Always the *weak* topology, never `variant="strong"`, even at the stiff
        end. The Thevenin bus must exist at every point on the sweep or the bus
        count changes from 34 to 33 mid-study, which changes the observation
        vector and makes zero-shot transfer meaningless. Stiffness is expressed
        by shrinking the impedance, not by deleting the bus: Z = 0.5 % on a
        10 MVA base is a short-circuit ratio of 200, stiff by any measure.
        """
        if substation_z_pct <= 0.0:
            raise ValueError(
                "substation_z_pct must be > 0; use a small value (0.5) for a stiff "
                "feeder so the Thevenin bus survives and the obs vector is stable"
            )
        base = cls.stage1("weak", evs_per_station=evs_per_station)
        return replace(
            base,
            feeder=replace(
                base.feeder,
                substation_z_pct=substation_z_pct,
                substation_rx_ratio=rx_ratio,
            ),
            scenario=replace(base.scenario, load_scale=load_scale),
        )

    @classmethod
    def high_pv_overvoltage(cls, variant: str = "weak") -> "ExperimentConfig":
        """The V2G-safety case the thesis claims but never ran (audit A3).

        Every projection result in the thesis curtails *charging* against the
        lower bound; the abstract describes it as curtailing a V2G request. On
        this testbed V2G cannot cause a lower-bound violation at all, so the
        stated claim had no supporting experiment.

        This is the operating point where it does hold: light load (0.20), a
        high-PV feeder (500 kW at each of three PV buses, ~2x the coincident
        load) and 320 kVA V2G hubs -- four 80 kW bidirectional chargers apiece.

        Idle Vmax is 1.0230, comfortably inside even the margin-tightened upper
        bound of 1.040. Full V2G injection at all four stations lifts it to
        1.0538: a breach *caused by the injection itself*, which the projection
        must curtail against the 1.05 pu **upper** bound. That is the mirror
        image of every projection result the thesis actually published, all of
        which curtail charging against the lower bound.
        """
        return cls(
            feeder=FeederConfig(
                variant=variant,
                pv_rated_kw=(500.0, 500.0, 500.0),
                ev_station_kva=320.0,
            ),
            scenario=ScenarioConfig(load_scale=0.20),
            reward=RewardConfig(include_loss_term=False),
        )

    def with_(self, **kwargs) -> "ExperimentConfig":
        return replace(self, **kwargs)

    def fingerprint(self) -> str:
        blob = json.dumps(asdict(self), sort_keys=True, default=str)
        return hashlib.sha256(blob.encode()).hexdigest()[:16]
