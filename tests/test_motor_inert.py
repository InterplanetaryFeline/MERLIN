"""Motor-level solid inert: the STAR dataset and the relation fitted to it.

Why this file exists. Every other solid relation in this tool predicts a STAGE - a motor plus its skirts,
interstage, avionics and separation hardware. The book's own k_SRM (Eq. 8:18) does not: it is a MOTOR
coefficient. Testing a motor coefficient against stage-level figures is what made the solid comparisons so
hard to read, because the gap between the two is real hardware that varies enormously from vehicle to
vehicle - on Scout's third stage it is 237 kg against a 98 kg motor.

MOTOR_DATASET closes that hole: 55 STAR motors whose loaded and burnout masses are published together, so
the difference is motor inert with no stage equipment in it. What it shows is that motor inert fraction is
not constant - it falls from about 0.18 at 30 kg of propellant towards a floor near 0.06 - so the book's
single k = 0.1154 crosses the real curve near 150-200 kg and is wrong in opposite directions either side.

The tests below pin three things: that the data is internally consistent, that the stored fit constants are
genuinely the least-squares answer rather than magic numbers, and that the relation beats the book on a
motor it has never seen.
"""
import statistics

from launch_vehicle import solid_inert as si
from launch_vehicle.solid_motor import casing_mass, is_stage_level

LBM = 0.45359237


# ------------------------------------------------------------------ the data
def test_the_motor_dataset_is_motor_level_and_separate_from_the_stage_sets():
    """Three populations, three lists. Mixing them is the mistake this whole file guards against."""
    assert len(si.MOTOR_DATASET) >= 50
    stage_names = {s.name for s in si.DATASET} | {s.name for s in si.OUT_OF_SAMPLE}
    for m in si.MOTOR_DATASET:
        assert m.name not in stage_names, f"{m.name} is in both a stage list and the motor list"
        assert m.m_prop_kg > 0 and m.m_inert_kg > 0
        assert m.diameter_m > 0


def test_every_motor_has_a_believable_inert_fraction():
    """A solid motor that is 95 % propellant or 60 % inert would be a typo, not a motor."""
    for m in si.MOTOR_DATASET:
        assert 0.04 < m.f_inert < 0.35, f"{m.name}: f = {m.f_inert:.3f}"


def test_the_dataset_spans_the_small_launch_vehicle_range():
    """The whole point of it: the book's constant is least defensible exactly here."""
    props = [m.m_prop_kg for m in si.MOTOR_DATASET]
    assert min(props) < 50, "no motors small enough to show where the book's k goes low"
    assert max(props) > 4000, "no motors large enough to show the floor"


def test_motor_inert_fraction_really_does_fall_with_size():
    """The finding the relation rests on. If this stopped being true, a constant k would be fine."""
    small = [m.f_inert for m in si.MOTOR_DATASET if m.m_prop_kg < 100]
    large = [m.f_inert for m in si.MOTOR_DATASET if m.m_prop_kg > 1000]
    assert small and large
    assert statistics.median(small) > 1.8 * statistics.median(large), (
        f"small motors median f = {statistics.median(small):.3f}, large = {statistics.median(large):.3f}")


# ------------------------------------------------------------------ the fit
def test_the_stored_constants_are_the_fit_and_not_magic_numbers():
    """Refit from the data and require the stored pair to match. Constants that drift get caught here."""
    f_min, c, mape, bias = si.fit_motor_asymptotic()
    assert abs(f_min - si.STAR_F_MIN) < 5e-4, f"refit f_min {f_min:.4f} vs stored {si.STAR_F_MIN}"
    assert abs(c - si.STAR_C) < 5e-4, f"refit C {c:.4f} vs stored {si.STAR_C}"
    assert mape < 0.20, f"MAPE {mape:.1%} - the fit is no longer good enough to ship"
    assert abs(bias) < 0.05, f"bias {bias:+.1%} - the fit has developed a systematic offset"


def test_the_fitted_floor_is_close_to_the_value_kibbey_published():
    """An independent corroboration worth keeping.

    Kibbey (NTRS 20190027424) quotes f_i,min = 0.060 for advanced technology, fitted to stages and to a
    much smaller sample. Refitting his functional form to 55 motors lands on essentially the same floor.
    """
    assert abs(si.STAR_F_MIN - 0.060) < 0.01, (
        f"fitted floor {si.STAR_F_MIN} has moved away from Kibbey's 0.060; that agreement was evidence")


def test_a_pure_power_law_is_worse_than_the_asymptotic_form():
    """Why the relation has a floor at all: without one it keeps falling and misses the big motors."""
    import math
    xs = [math.log(m.m_prop_kg) for m in si.MOTOR_DATASET]
    ys = [math.log(m.f_inert) for m in si.MOTOR_DATASET]
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
    a = math.exp(my - b * mx)
    big = [m for m in si.MOTOR_DATASET if m.m_prop_kg > 3000]
    power_err = [(a * m.m_prop_kg ** b * m.m_prop_kg - m.m_inert_kg) / m.m_inert_kg for m in big]
    asym_err = [(si.RELATIONS["star_motor"].inert_kg(m.m_prop_kg) - m.m_inert_kg) / m.m_inert_kg
                for m in big]
    assert statistics.mean([abs(e) for e in asym_err]) < statistics.mean([abs(e) for e in power_err]), (
        "the power law now fits the largest motors better than the asymptotic form")


# ------------------------------------------------------------------ the relation in the tool
def test_the_relation_is_motor_level_so_the_build_up_still_runs():
    """If this were tagged `stage`, the skirts and avionics would be suppressed and the stage under-built."""
    assert si.RELATIONS["star_motor"].predicts == "motor"
    assert not is_stage_level("star_motor")


def test_the_relation_declares_the_range_it_was_fitted_to():
    rel = si.RELATIONS["star_motor"]
    lo, hi = rel.valid_kg
    assert lo <= min(m.m_prop_kg for m in si.MOTOR_DATASET)
    assert hi >= max(m.m_prop_kg for m in si.MOTOR_DATASET) * 0.9
    assert not rel.in_range(50_000), "a first-stage booster must fall outside this relation's range"


def test_the_source_warns_that_these_are_not_booster_motors():
    """The one way to misuse this relation badly, so the warning travels with every number it produces."""
    _m, _k, src = casing_mass(1000.0, "star_motor")
    assert "UPPER-STAGE" in src.upper()
    assert "TVC" in src


def test_it_beats_the_book_on_a_motor_it_has_never_seen():
    """Star 31 (TE-M-762) is absent from MOTOR_DATASET and its figures come from Thiokol, not Wikipedia.

    Thiokol's 1989 catalogue: 2,835 lbm of propellant at a propellant mass fraction of 0.929, so the motor
    inert is 2,835 lbm x 0.071/0.929. The book over-predicts it by about half; the fitted relation lands
    within a few per cent.
    """
    m_prop = 2835.0 * LBM
    actual = m_prop * (1 - 0.929) / 0.929
    book, _k, _s = casing_mass(m_prop, "book_composite")
    star, _k, _s = casing_mass(m_prop, "star_motor")
    assert abs(star - actual) / actual < 0.15, f"star_motor {star:.1f} kg vs actual {actual:.1f} kg"
    assert (book - actual) / actual > 0.35, "the book used to over-predict Star 31 by about half"
    assert abs(star - actual) < abs(book - actual)


def test_the_book_constant_is_high_for_motors_and_the_relation_is_not():
    """The headline, as a number that has to keep being true."""
    errs_book, errs_star = [], []
    for m in si.MOTOR_DATASET:
        if m.m_prop_kg < 200:
            continue                                  # the band where the book runs low instead
        b, _k, _s = casing_mass(m.m_prop_kg, "book_composite")
        s, _k, _s2 = casing_mass(m.m_prop_kg, "star_motor")
        errs_book.append((b - m.m_inert_kg) / m.m_inert_kg)
        errs_star.append((s - m.m_inert_kg) / m.m_inert_kg)
    assert statistics.median(errs_book) > 0.25, (
        f"the book's median error on motors above 200 kg is {statistics.median(errs_book):+.1%}; "
        "it was +34% when this relation was added")
    assert abs(statistics.median(errs_star)) < 0.12
