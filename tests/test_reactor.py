import random

from seance.ghost import Reactor, Tier, classify_tier


# --- tier classification ----------------------------------------------------

def test_boring_success():
    assert classify_tier(0, 1.0, None, 60) is Tier.BORING


def test_failed_beats_long():
    assert classify_tier(2, 999.0, None, 60) is Tier.FAILED


def test_dangerous_beats_everything():
    assert classify_tier(2, 999.0, "a forced push", 60) is Tier.DANGEROUS


def test_long_threshold_is_inclusive():
    assert classify_tier(0, 60.0, None, 60) is Tier.LONG
    assert classify_tier(0, 59.9, None, 60) is Tier.BORING


def test_unknown_duration_means_never_long():
    assert classify_tier(0, None, None, 60) is Tier.BORING


# --- speak decisions ----------------------------------------------------------

def test_failed_always_speaks():
    r = Reactor(frequency=0.0, min_interval=10_000, rng=random.Random(0))
    assert all(r.should_speak(Tier.FAILED, since) for since in range(100))


def test_dangerous_always_speaks():
    r = Reactor(frequency=0.0, min_interval=10_000, rng=random.Random(0))
    assert all(r.should_speak(Tier.DANGEROUS, since) for since in range(100))


def test_long_always_speaks():
    r = Reactor(frequency=0.0, min_interval=10_000, rng=random.Random(0))
    assert all(r.should_speak(Tier.LONG, since) for since in range(100))


def test_boring_zero_frequency_never_speaks():
    r = Reactor(frequency=0.0, min_interval=0, rng=random.Random(0))
    assert r.should_speak(Tier.BORING, 999) is False


def test_boring_respects_min_interval():
    # frequency=1.0: the dice always pass, so the interval alone decides.
    r = Reactor(frequency=1.0, min_interval=4, rng=random.Random(1))
    got = [r.should_speak(Tier.BORING, since) for since in range(5)]
    assert got == [False, False, False, False, True]


def test_boring_probability_gate():
    r = Reactor(frequency=0.0, min_interval=0, rng=random.Random(0))
    assert r.should_speak(Tier.BORING, 100) is False
    r = Reactor(frequency=1.0, min_interval=0, rng=random.Random(0))
    assert r.should_speak(Tier.BORING, 100) is True


def test_boring_rate_is_at_most_one_in_five():
    """With min_interval=4 the hard cap is <= 1/5 of commands, forever."""
    r = Reactor(frequency=0.2, min_interval=4, rng=random.Random(42))
    since, spoke, total = 10_000, 0, 20_000
    for _ in range(total):
        if r.should_speak(Tier.BORING, since):
            spoke += 1
            since = 0
        else:
            since += 1
    assert spoke > 0  # the throttle is strict, not mute
    assert spoke * 5 <= total
