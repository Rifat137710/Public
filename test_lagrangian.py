"""
Validation for :mod:`lagrangian`, and a reproduction of the multiplier defect
found in the shipped SafeSAC checkpoints.

Runs standalone (``python test_lagrangian.py``) and under pytest.

The closed-loop model is deliberately crude — a policy whose cost relaxes
toward a lambda-dependent target with a structural floor it cannot go below:

    J_target(lam) = floor + (J_free - floor) / (1 + beta * lam)
    J_C <- J_C + rate * (J_target(lam) - J_C)

That floor is the point: on the weak feeder, background load pins ~26 of 288
steps in violation regardless of what the stations do, so no multiplier can
drive the cost to zero.
"""

from __future__ import annotations

import numpy as np

from lagrangian import LagrangeController

# Cost scale taken from the thesis run: ~26/288 steps in violation, each
# summing ~0.02 pu of excursion across buses -> mean per-step cost ~1.8e-3,
# so a discounted return of ~0.18 at gamma = 0.99.
J_FREE = 0.40      # discounted cost return of an unconstrained policy
FLOOR = 0.12       # structural floor: unreachable below this
BETA = 0.35        # policy responsiveness to lambda
RATE = 0.02        # policy adaptation speed per update


def _rollout(ctrl: LagrangeController, n: int = 20_000, *,
             critic_gain: float = 1.0, noise: float = 0.0,
             delay: int = 0, seed: int = 0) -> dict:
    """Closed-loop sim.

    ``critic_gain`` models cost-critic mis-estimation. ``delay`` is the lag
    between a change in lambda and the policy responding to it — in a real
    agent the actor and cost critic both trail the multiplier by many gradient
    steps, and that lag is what makes plain dual ascent overshoot and ring.
    """
    rng = np.random.default_rng(seed)
    jc = J_FREE
    lam_hist, jc_hist = np.empty(n), np.empty(n)
    lam_queue = [0.0] * max(1, delay)
    for t in range(n):
        lam_eff = lam_queue.pop(0) if delay else ctrl.lam
        target = FLOOR + (J_FREE - FLOOR) / (1.0 + BETA * lam_eff)
        jc += RATE * (target - jc)
        observed = jc * critic_gain
        if noise:
            observed += rng.normal(0.0, noise)
        ctrl.update(observed)
        if delay:
            lam_queue.append(ctrl.lam)
        lam_hist[t], jc_hist[t] = ctrl.lam, jc
    return {"lam": lam_hist, "jc": jc_hist, "final_lam": ctrl.lam, "final_jc": jc}


class _LegacyController:
    """The multiplier update exactly as shipped, for comparison.

    ``threshold`` is the per-step budget, compared directly against a
    discounted-return estimate.
    """

    def __init__(self, threshold: float = 0.01, lr: float = 1e-3,
                 lam_max: float = 100.0):
        self.threshold, self.lr, self.lam_max = threshold, lr, lam_max
        self.lam = 0.0

    def update(self, jc: float) -> float:
        cv = jc - self.threshold
        self.lam = min(self.lam_max, max(0.0, self.lam + self.lr * cv))
        return self.lam


# ---------------------------------------------------------------------------
def test_scale_conversion():
    """d_return is the per-step budget over (1 - gamma)."""
    c = LagrangeController(d_step=0.01, gamma=0.99)
    assert abs(c.d_return - 1.0) < 1e-12
    assert abs(LagrangeController(d_step=0.01, gamma=0.999).d_return - 10.0) < 1e-9
    # The shipped code compared a return against the per-step number, i.e. it
    # silently demanded 1/(1-gamma) = 100x less cost than documented.
    assert abs(c.d_return / c.d_step - 100.0) < 1e-9


def test_tracking_to_budget():
    """A feasible budget is tracked: J_C converges to d_return."""
    d_step = 0.0025                     # d_return = 0.25, above FLOOR = 0.12
    c = LagrangeController(d_step=d_step, gamma=0.99, lr=5e-3, kp=0.5)
    out = _rollout(c)
    assert c.health().ok, c.health()
    assert abs(out["final_jc"] - c.d_return) < 0.02 * c.d_return, out["final_jc"]


def _legacy_rollout(n: int, *, threshold: float = 0.01, gain: float = 1.0):
    legacy = _LegacyController(threshold=threshold)
    jc = J_FREE
    for _ in range(n):
        target = FLOOR + (J_FREE - FLOOR) / (1.0 + BETA * legacy.lam)
        jc += RATE * (target - jc)
        legacy.update(jc * gain)
    return legacy.lam, jc


def test_legacy_diverges_on_infeasible_budget():
    """The shipped comparison makes the budget unreachable, so lambda diverges.

    Read as a return, threshold 0.01 sits far below the structural floor
    (0.12 here), so the constraint can never be satisfied: the multiplier
    grows without bound and the policy is crushed onto its floor. Nothing in
    the shipped code detects this — there is no cap, no health check, and
    lambda was never logged.
    """
    lam_20k, jc_20k = _legacy_rollout(20_000)
    lam_40k, jc_40k = _legacy_rollout(40_000)

    # No equilibrium. Once the policy nears its floor the dual error settles at
    # (FLOOR - threshold), so lambda grows at >= lr * (FLOOR - threshold) per
    # update, forever. Growth over the second 20k updates must clear that rate.
    asymptotic_growth = 20_000 * 1e-3 * (FLOOR - 0.01)
    assert lam_40k - lam_20k > 0.9 * asymptotic_growth, (lam_20k, lam_40k)
    assert FLOOR < jc_40k < jc_20k < J_FREE, (jc_20k, jc_40k)

    # The fixed controller sees the same infeasibility and reports it.
    c = LagrangeController(d_step=0.0001, gamma=0.99, lr=1e-3, stall_patience=500)
    _rollout(c)
    assert not c.health().ok and c.health().status == "SATURATED"


def test_legacy_penalises_a_satisfied_constraint():
    """With a perfect cost critic and the budget met, legacy lambda still diverges.

    This is the clearest statement of the defect. Take ``d_step = 0.01`` and
    ``gamma = 0.99``: the documented budget is a discounted return of 1.0. The
    policy settles at ``J_C ~ 0.22`` — comfortably inside the budget. Yet
    because the shipped code compares that return against ``0.01``, the dual
    error stays positive and the multiplier climbs without bound, suppressing a
    policy that was never violating anything.

    The correctly scaled controller leaves lambda at zero on the same run.
    """
    lam_legacy, jc = _legacy_rollout(20_000)
    d_return = LagrangeController(d_step=0.01, gamma=0.99).d_return

    assert jc < 0.5 * d_return, (jc, d_return)      # constraint comfortably met
    assert lam_legacy > 1.0, lam_legacy             # ... and still penalised hard

    fixed = LagrangeController(d_step=0.01, gamma=0.99, lr=1e-3)
    out = _rollout(fixed)
    assert fixed.lam == 0.0, fixed.lam              # correctly inactive
    assert out["final_jc"] > 0.9 * J_FREE           # policy left alone
    return {"jc": jc, "d_return": d_return,
            "lam_legacy": lam_legacy, "lam_fixed": fixed.lam}


def test_response_is_bounded_under_critic_error():
    """Legacy lambda tracks the critic's absolute scale; the fix tracks violation.

    Sweeping a multiplicative cost-critic error shows the legacy multiplier
    responding across the whole range — any bias in the critic changes the
    effective constraint — while the correctly scaled controller stays at zero
    until the *true* cost approaches the budget.
    """
    gains = np.geomspace(1e-3, 1.0, 25)
    legacy = np.array([_legacy_rollout(20_000, gain=g)[0] for g in gains])
    fixed = np.array([
        _rollout(LagrangeController(d_step=0.0025, gamma=0.99, lr=5e-3, kp=0.5),
                 critic_gain=g)["final_lam"]
        for g in gains
    ])
    # Legacy activates far earlier and over a much wider slice of the sweep.
    assert (legacy > 1e-9).sum() > (fixed > 1e-9).sum(), (legacy, fixed)
    assert fixed.max() < 20.0, fixed.max()
    return {"gains": gains, "legacy": legacy, "fixed": fixed}


def test_infeasible_budget_is_reported():
    """A budget below the structural floor saturates, and health() says so."""
    c = LagrangeController(d_step=0.0005, gamma=0.99, lr=5e-3,  # d_return=0.05 < FLOOR
                           lam_max=100.0, stall_patience=500)
    _rollout(c)
    h = c.health()
    assert not h.ok and h.status == "SATURATED", h


def test_degenerate_multiplier_is_reported():
    """Cost over budget but lambda pinned at zero is flagged, not ignored."""
    c = LagrangeController(d_step=0.0025, gamma=0.99, lr=0.0, kp=0.0,
                           stall_patience=100)
    for _ in range(500):
        c.update(10.0)                  # far over budget, but gains are zero
    h = c.health()
    assert c.lam == 0.0
    assert not h.ok and h.status == "DEGENERATE", h


def test_from_measured_floor():
    """Budget derived from a measured floor stays feasible."""
    c = LagrangeController.from_measured_floor(
        floor_step=FLOOR * (1 - 0.99), headroom=1.5, gamma=0.99, lr=5e-3, kp=0.5)
    assert c.d_return > FLOOR
    _rollout(c)
    assert c.health().ok, c.health()

    try:
        LagrangeController.from_measured_floor(floor_step=0.001, headroom=0.5)
    except ValueError:
        pass
    else:  # pragma: no cover
        raise AssertionError("headroom < 1 should be rejected")


def test_integral_gain_dominates_overshoot():
    """The integral gain, not PID damping, is what controls overshoot here.

    Recorded because it contradicts the obvious expectation. With the policy
    lagging lambda by 300 updates:

      * ``kp`` gives a small real improvement (13.0% -> 11.8% undershoot);
      * ``kd`` is *inert* — the derivative term fires only on rising cost
        (Stooke et al.), and the approach to the budget is monotone, so there
        is no rising phase to damp;
      * quartering ``lr`` removes the overshoot entirely and reaches the same
        equilibrium multiplier.

    So PID gains are worth exposing, but the honest tuning advice is to set
    ``lr`` conservatively first. ``kd`` should only be expected to help where
    cost is noisy or non-monotone.
    """
    kw = dict(d_step=0.0025, gamma=0.99, lr=2e-2)
    d = LagrangeController(**kw).d_return
    delay = 300

    def undershoot(**extra):
        r = _rollout(LagrangeController(**{**kw, **extra}), delay=delay)
        return max(0.0, (d - float(r["jc"].min())) / d), float(r["lam"].max())

    u_plain, peak_plain = undershoot()
    u_kp, peak_kp = undershoot(kp=0.5)
    u_kd, _ = undershoot(kd=4.0)
    u_slow, _ = undershoot(lr=5e-3)

    assert u_plain > 0.10, u_plain                 # there is overshoot to fix
    assert u_kp < u_plain and peak_kp < peak_plain  # kp helps, modestly
    assert abs(u_kd - u_plain) < 1e-9, (u_plain, u_kd)   # kd inert, as documented
    assert u_slow < 0.01, u_slow                   # lr is the dominant knob
    return {"plain": u_plain, "kp": u_kp, "kd": u_kd, "slow_lr": u_slow}


# ---------------------------------------------------------------------------
def main() -> None:
    print("=" * 72)
    print("lagrangian.py validation")
    print("=" * 72)

    c = LagrangeController(d_step=0.01, gamma=0.99)
    print(f"\n[scale]  d_step=0.01, gamma=0.99  ->  d_return={c.d_return:.4g}")
    print(f"         shipped code compared Q_C against 0.01 directly,")
    print(f"         i.e. a budget {c.d_return / c.d_step:.0f}x tighter than documented")

    tests = [
        ("scale conversion", test_scale_conversion),
        ("tracking to budget", test_tracking_to_budget),
        ("legacy diverges (infeasible)", test_legacy_diverges_on_infeasible_budget),
        ("legacy penalises satisfied constraint", test_legacy_penalises_a_satisfied_constraint),
        ("bounded under critic error", test_response_is_bounded_under_critic_error),
        ("infeasible budget reported", test_infeasible_budget_is_reported),
        ("degenerate lambda reported", test_degenerate_multiplier_is_reported),
        ("from_measured_floor", test_from_measured_floor),
        ("integral gain dominates", test_integral_gain_dominates_overshoot),
    ]
    print()
    results = {}
    for name, fn in tests:
        try:
            results[name] = fn()
            print(f"  PASS  {name}")
        except AssertionError as exc:
            print(f"  FAIL  {name}: {exc}")
            raise

    sat = results["legacy penalises satisfied constraint"]
    print(f"\n[satisfied constraint] J_C={sat['jc']:.3g} vs budget d_return="
          f"{sat['d_return']:.3g}  ->  constraint met with "
          f"{sat['d_return'] / sat['jc']:.1f}x margin")
    print(f"  legacy lambda = {sat['lam_legacy']:.3g} (and still climbing)")
    print(f"  fixed  lambda = {sat['lam_fixed']:.3g} (correctly inactive)")

    ke = results["bounded under critic error"]
    print(f"\n[critic error] final lambda vs cost-critic gain")
    print(f"  {'gain':>8} {'legacy':>12} {'fixed':>12}")
    for g, l, f in list(zip(ke["gains"], ke["legacy"], ke["fixed"]))[::4]:
        print(f"  {g:>8.4f} {l:>12.4g} {f:>12.4g}")
    print(f"  legacy active on {int((ke['legacy'] > 1e-9).sum())}/25 gains, "
          f"max {ke['legacy'].max():.3g}")
    print(f"  fixed  active on {int((ke['fixed'] > 1e-9).sum())}/25 gains, "
          f"max {ke['fixed'].max():.3g}")

    dmp = results["integral gain dominates"]
    print(f"\n[damping] undershoot below budget (policy lags lambda by 300):")
    print(f"  plain lr=2e-2 : {dmp['plain'] * 100:5.1f}%")
    print(f"  + kp=0.5      : {dmp['kp'] * 100:5.1f}%   (small real gain)")
    print(f"  + kd=4.0      : {dmp['kd'] * 100:5.1f}%   (inert: approach is monotone)")
    print(f"  lr=5e-3       : {dmp['slow_lr'] * 100:5.1f}%   (lr is the dominant knob)")

    print("\nAll checks passed.")


if __name__ == "__main__":
    main()
