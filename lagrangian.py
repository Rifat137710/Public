"""
Dual-variable controller for the CMDP constraint in SafeSAC.

Replaces the multiplier update in ``SACLagAgent.train_step``:

    cost_excess = qc_new - self.constraint_threshold      # 0.01
    cv = qc_new.mean() - self.constraint_threshold
    self.lambda_lagrange = max(0.0, self.lambda_lagrange + self.lr_lambda * cv)

That update compares ``qc_new``, which estimates the *discounted return*
``E[sum_t gamma^t c_t]``, against a threshold documented as a *per-step* cost
budget.  At ``gamma = 0.99`` those two quantities differ by a factor of
``1/(1-gamma) = 100``, so the comparison is dimensionally wrong and the
multiplier's behaviour depends on which side of an arbitrary constant the cost
critic happens to land.  In the shipped checkpoints it landed on opposite
sides:

    saclag_weak_v2     lambda = 0.0        <- constraint term contributed nothing
    saclag_strong_v2   lambda = 0.0
    safesac_weak_v3    lambda = 17.32
    safesac_strong_v3  lambda = 17.85

This module fixes four things:

1. **Scale.**  The threshold is specified per step and converted to the return
   scale the cost critic actually predicts (:attr:`d_return`).
2. **Conditioning.**  The dual error is normalised by the threshold, so
   ``lr`` means the same thing regardless of how costs are scaled.
3. **Damping.**  Optional PID control (Stooke, Achiam & Abbeel, ICML 2020)
   removes the overshoot-and-oscillate behaviour of plain dual ascent.
4. **Observability.**  :meth:`health` turns a stalled or diverging multiplier
   into a loud, checkable condition instead of a silent one.  The original bug
   was invisible only because nothing logged ``lambda``.

The controller is deliberately framework-agnostic — it operates on plain floats
— so it can be unit-tested without a simulator and dropped into the existing
torch agent unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

__all__ = ["LagrangeController", "LagrangeHealth"]


@dataclass
class LagrangeHealth:
    """Diagnosis of a multiplier's behaviour over training."""

    ok: bool
    status: str
    detail: str
    lam: float
    jc: float
    d_return: float

    def __str__(self) -> str:  # pragma: no cover - cosmetic
        flag = "OK " if self.ok else "FAIL"
        return f"[{flag}] {self.status}: {self.detail}"


@dataclass
class LagrangeController:
    """PID-damped dual variable for ``E[sum gamma^t c_t] <= d``.

    Parameters
    ----------
    d_step:
        Per-step cost budget, in the same units as the environment's
        ``constraint_cost`` (for SafeSAC: summed pu voltage excursion plus
        transformer overload).  This is the number a domain expert can reason
        about; the controller converts it internally.
    gamma:
        Discount used by the cost critic.  Must match the agent's ``gamma``.
    lr:
        Integral gain (plain dual ascent uses this alone).
    kp, kd:
        Proportional and derivative gains.  Both zero reproduces vanilla dual
        ascent; ``kp > 0`` responds to the current violation without waiting
        for the integral to build, and ``kd > 0`` damps rising cost.
    lam_max:
        Hard cap.  A multiplier pinned here means the constraint is infeasible
        for the policy class — on a feeder with a structural violation floor
        above ``d_step`` this *will* happen, which is why :meth:`health`
        reports it rather than letting it pass.
    normalise:
        Divide the dual error by ``d_return`` so ``lr`` is scale-free.
    stall_patience:
        Number of consecutive updates with ``lambda == 0`` while the cost
        exceeds budget before :meth:`health` calls it degenerate.
    """

    d_step: float
    gamma: float = 0.99
    lr: float = 1e-3
    kp: float = 0.0
    kd: float = 0.0
    lam_max: float = 100.0
    normalise: bool = True
    stall_patience: int = 2000

    lam: float = field(default=0.0, init=False)
    integral: float = field(default=0.0, init=False)
    n_updates: int = field(default=0, init=False)
    _jc_prev: Optional[float] = field(default=None, init=False)
    _stalled_for: int = field(default=0, init=False)
    _saturated_for: int = field(default=0, init=False)
    _jc_last: float = field(default=0.0, init=False)

    def __post_init__(self) -> None:
        if not 0.0 <= self.gamma < 1.0:
            raise ValueError(f"gamma must be in [0, 1), got {self.gamma}")
        if self.d_step < 0.0:
            raise ValueError(f"d_step must be non-negative, got {self.d_step}")

    # -- scale -------------------------------------------------------------
    @property
    def d_return(self) -> float:
        """Threshold on the discounted-return scale the cost critic predicts.

        A policy holding average per-step cost at ``d_step`` accumulates
        ``d_step / (1 - gamma)`` in discounted cost, so that — not ``d_step``
        — is what ``Q_C`` must be compared against.
        """
        return self.d_step / (1.0 - self.gamma)

    @classmethod
    def from_measured_floor(
        cls,
        floor_step: float,
        *,
        headroom: float = 1.25,
        gamma: float = 0.99,
        **kwargs,
    ) -> "LagrangeController":
        """Build a controller whose budget sits above a measured cost floor.

        On a weak feeder the background load produces violations no station
        command can remove (the SafeSAC testbed pins 26 of 288 steps
        regardless of policy).  Setting ``d_step`` below that floor makes the
        CMDP infeasible and drives ``lambda`` to its cap, which suppresses the
        policy without improving safety.  Measure the floor first — with the
        ``no-charging`` controller — then leave a margin.

        Parameters
        ----------
        floor_step:
            Mean per-step constraint cost under a policy that takes no action.
        headroom:
            Multiplier on the floor.  ``1.0`` demands the controller match the
            floor exactly (achievable but with zero slack); ``1.25`` is a
            reasonable default.
        """
        if floor_step < 0.0:
            raise ValueError(f"floor_step must be non-negative, got {floor_step}")
        if headroom < 1.0:
            raise ValueError(
                f"headroom must be >= 1.0 (a budget below the floor makes the "
                f"CMDP infeasible), got {headroom}"
            )
        return cls(d_step=floor_step * headroom, gamma=gamma, **kwargs)

    # -- update ------------------------------------------------------------
    def update(self, jc: float) -> float:
        """Advance the multiplier given a cost-return estimate.

        Parameters
        ----------
        jc:
            Current estimate of ``E[sum gamma^t c_t]`` — in the torch agent,
            ``cost_critic(obs, new_action).mean().item()``.

        Returns
        -------
        float
            The updated multiplier.
        """
        jc = float(jc)
        d = self.d_return
        err = jc - d
        if self.normalise:
            err = err / max(d, 1e-8)

        # Integral term: the classical dual ascent, kept non-negative so a long
        # compliant stretch cannot bank credit that delays the next response.
        self.integral = max(0.0, self.integral + self.lr * err)

        # Derivative term acts only on *rising* cost, so relaxing toward the
        # budget is never penalised (Stooke et al., 2020).
        deriv = 0.0
        if self.kd and self._jc_prev is not None:
            deriv = max(0.0, jc - self._jc_prev)
            if self.normalise:
                deriv = deriv / max(d, 1e-8)

        lam = self.integral + self.kp * max(0.0, err) + self.kd * deriv
        self.lam = float(min(self.lam_max, max(0.0, lam)))

        # -- telemetry --
        if self.lam <= 0.0 and err > 0.0:
            self._stalled_for += 1
        else:
            self._stalled_for = 0
        if self.lam >= self.lam_max:
            self._saturated_for += 1
        else:
            self._saturated_for = 0

        self._jc_prev = jc
        self._jc_last = jc
        self.n_updates += 1
        return self.lam

    def reset(self) -> None:
        self.lam = 0.0
        self.integral = 0.0
        self.n_updates = 0
        self._jc_prev = None
        self._stalled_for = 0
        self._saturated_for = 0

    # -- diagnosis ---------------------------------------------------------
    def health(self) -> LagrangeHealth:
        """Classify the multiplier's behaviour.

        ``ok=False`` should fail a training run rather than be logged and
        ignored — a degenerate multiplier means the constraint was never
        actually enforced, which is the defect that invalidated the shipped
        SAC-Lag baseline.
        """
        lam, jc, d = self.lam, self._jc_last, self.d_return

        if self._stalled_for >= self.stall_patience:
            return LagrangeHealth(
                ok=False,
                status="DEGENERATE",
                detail=(
                    f"lambda pinned at 0 for {self._stalled_for} updates while "
                    f"J_C={jc:.4g} exceeds d={d:.4g}. The constraint term is "
                    f"contributing nothing to the actor loss; this run is an "
                    f"unconstrained agent wearing a constrained agent's name."
                ),
                lam=lam, jc=jc, d_return=d,
            )

        if self._saturated_for >= self.stall_patience:
            return LagrangeHealth(
                ok=False,
                status="SATURATED",
                detail=(
                    f"lambda pinned at the cap {self.lam_max:g} for "
                    f"{self._saturated_for} updates with J_C={jc:.4g} vs "
                    f"d={d:.4g}. The budget is likely below the structural "
                    f"cost floor — measure the floor and use "
                    f"LagrangeController.from_measured_floor()."
                ),
                lam=lam, jc=jc, d_return=d,
            )

        if self.n_updates == 0:
            return LagrangeHealth(
                ok=False, status="UNUSED", detail="no updates recorded",
                lam=lam, jc=jc, d_return=d,
            )

        return LagrangeHealth(
            ok=True,
            status="HEALTHY",
            detail=f"lambda={lam:.4g}, J_C={jc:.4g}, d={d:.4g}",
            lam=lam, jc=jc, d_return=d,
        )

    # -- integration -------------------------------------------------------
    def state_dict(self) -> dict:
        return {
            "lam": self.lam,
            "integral": self.integral,
            "n_updates": self.n_updates,
            "jc_prev": self._jc_prev,
            "d_step": self.d_step,
            "gamma": self.gamma,
        }

    def load_state_dict(self, s: dict) -> None:
        self.lam = float(s["lam"])
        self.integral = float(s["integral"])
        self.n_updates = int(s["n_updates"])
        self._jc_prev = s["jc_prev"]
