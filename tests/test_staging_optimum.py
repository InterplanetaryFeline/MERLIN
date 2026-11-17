"""R4: the analytical (Lagrange) staging optimum, book Sec. 5.8 (method register M58, M59).

The strongest available verification is the book's own Fig. 5.11 bar graph, which this module reproduces to the
two decimals the figure prints. Beyond that the tests pin the three properties the closed form must have: it
satisfies the delta-v it was given, it collapses to the restricted-staging result when every step is identical,
and it really is an optimum (neighbouring splits carry less payload).
"""
import math
import pytest
from helpers import *                                        # noqa: F401,F403
from launch_vehicle import optimization as opt
from launch_vehicle.units import G0
from launch_vehicle.validation import InputError


# ------------------------------------------------------------------ book Eq. 5:40 / Fig. 5.11
def test_restricted_staging_reproduces_book_figure_5_11():
    """Fig. 5.11 (p.290) prints v_f/v_e for pi = 0.05, sigma = 0.10 and N = 1..9, plus the N -> infinity limit."""
    printed = [1.93, 2.40, 2.52, 2.57, 2.60, 2.62, 2.63, 2.64, 2.65]
    got = [opt.restricted_staging_speed_ratio(n, 0.05, 0.10) for n in range(1, 10)]
    for n, (g, p) in enumerate(zip(got, printed), start=1):
        assert round(g, 2) == p, f"N = {n}: {g:.4f} vs printed {p}"
    assert round(opt.restricted_staging_speed_ratio(None, 0.05, 0.10), 2) == 2.70


def test_restricted_staging_gain_per_added_step_collapses():
    """The engineering point of Eq. 5:40: the third step buys a tenth of what the second one did."""
    v = [opt.restricted_staging_speed_ratio(n, 0.05, 0.10) for n in range(1, 6)]
    gains = [b - a for a, b in zip(v, v[1:])]
    assert gains[0] > 0.4 and gains[1] < 0.15 and gains[2] < 0.06
    assert all(a > b for a, b in zip(gains, gains[1:]))


def test_restricted_staging_rejects_impossible_ratios():
    for bad in ((2, 0.0, 0.1), (2, 1.0, 0.1), (2, 0.05, 0.0), (2, 0.05, 1.0)):
        with pytest.raises(InputError):
            opt.restricted_staging_speed_ratio(*bad)


# ------------------------------------------------------------------ the Lagrange optimum
def test_analytical_optimum_delivers_the_delta_v_it_was_asked_for():
    c = [G0 * 290.0, G0 * 340.0]
    sig = [0.07, 0.09]
    out = opt.analytical_optimum(c, sig, 9000.0)
    assert out["dv_total_mps"] == pytest.approx(9000.0, rel=1e-8)
    assert sum(out["fractions"]) == pytest.approx(1.0, rel=1e-12)
    for mu, s in zip(out["mass_ratios"], sig):
        assert 1.0 < mu < 1.0 / s                      # feasible by construction (book p.288)


def test_the_printed_and_implemented_multiplier_are_the_same_quantity():
    """The book writes mu = (1 + L c)/(L c sigma) with L negative; this module solves with lam = -L."""
    c, sig = [G0 * 300.0, G0 * 330.0], [0.08, 0.10]
    out = opt.analytical_optimum(c, sig, 9200.0)
    lam, L = out["lagrange_lambda"], out["lagrange_L"]
    assert L == pytest.approx(-lam)
    for ci, si, mu in zip(c, sig, out["mass_ratios"]):
        assert mu == pytest.approx((1.0 + L * ci) / (L * ci * si), rel=1e-9)


def test_equal_isp_and_equal_sigma_give_an_even_split():
    """Book p.289: with identical steps, minimum mass means each step provides 1/N of the speed."""
    for n in (2, 3, 4):
        c = [G0 * 320.0] * n
        sig = [0.08] * n
        out = opt.analytical_optimum(c, sig, 9000.0)
        for f in out["fractions"]:
            assert f == pytest.approx(1.0 / n, rel=1e-6)
        for dv in out["dv_mps"]:
            assert dv == pytest.approx(9000.0 / n, rel=1e-6)


def test_equal_isp_closed_form_agrees_with_the_general_solution():
    """Eqs. 5:37-5:39 are the special case of Eqs. 5:32-5:33 when every c is the same; they must not disagree."""
    c, sig, dv = G0 * 310.0, [0.06, 0.09, 0.12], 9400.0
    a = opt.equal_isp_optimum(c, sig, dv)
    b = opt.analytical_optimum([c] * 3, sig, dv)
    for x, y in zip(a["mass_ratios"], b["mass_ratios"]):
        assert x == pytest.approx(y, rel=1e-6)
    assert a["dv_total_mps"] == pytest.approx(dv, rel=1e-6)


def test_the_optimum_really_maximises_the_payload_fraction():
    """Walk the split around the optimum and check the payload ratio of the whole stack falls off both sides."""
    c, sig, dv = [G0 * 290.0, G0 * 340.0], [0.07, 0.09], 9000.0
    best = opt.analytical_optimum(c, sig, dv)["fractions"][0]

    def payload_ratio(f1):
        out = 1.0
        for ci, si, dvi in zip(c, sig, (f1 * dv, (1 - f1) * dv)):
            mu = math.exp(dvi / ci)
            if mu * si >= 1.0:
                return 0.0
            out *= (1.0 - mu * si) / (mu * (1.0 - si))     # payload ratio of one step (book Eq. 5:12 form)
        return out

    at_best = payload_ratio(best)
    for d in (0.02, 0.05, 0.10):
        assert payload_ratio(best - d) < at_best
        assert payload_ratio(best + d) < at_best


def test_analytical_optimum_rejects_degenerate_input():
    with pytest.raises(InputError):
        opt.analytical_optimum([3000.0], [0.08], 9000.0)
    with pytest.raises(InputError):
        opt.analytical_optimum([3000.0, 3300.0], [0.08, 1.2], 9000.0)


# ------------------------------------------------------------------ against the tool's own numerical search
def test_analytical_and_numerical_optima_bracket_the_same_minimum():
    """They differ - the closed form assumes a fixed structural ratio and this tool computes one - but both must
    land on the flat part of the GLOM curve, and the numerical one must be the lower of the two by construction."""
    res = default_result()
    ana = opt.analytical_optimum_from_result(res)
    num = opt.optimize_dv_split(res.spec)
    g_ana = opt.glom_for_fractions(res.spec, ana["fractions"])
    assert g_ana is not None
    assert num["glom_kg"] <= g_ana + 1e-6
    assert (g_ana - num["glom_kg"]) / num["glom_kg"] < 0.05      # the assumption costs a few per cent, not more
    assert 0.15 < ana["fractions"][0] < 0.75


def test_staging_sweep_is_a_curve_with_a_minimum_inside_it():
    res = default_result()
    sw = opt.staging_sweep(res.spec, n=15)
    # splits that make a stage infeasible are dropped rather than plotted as a penalty value, so the surviving
    # curve is shorter than the request - that is the honest shape, and it must still contain the minimum
    assert 5 < len(sw) <= 15
    glo = [p["glom_kg"] for p in sw]
    k = glo.index(min(glo))
    assert 0 < k < len(glo) - 1, "the minimum must be interior, not at a bound"
