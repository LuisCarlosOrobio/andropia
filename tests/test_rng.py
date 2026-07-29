"""The threaded PRNG.

Properties rather than published test vectors: these assert the behaviour the
simulation actually relies on, and they would catch a broken port of the
algorithm without claiming a provenance I have not verified.
"""

from __future__ import annotations

from andropia.sim import rng


def take(state: int, n: int) -> list[int]:
    out = []
    for _ in range(n):
        v, state = rng.next_u64(state)
        out.append(v)
    return out


def test_same_seed_same_sequence():
    assert take(rng.seed(12345), 200) == take(rng.seed(12345), 200)


def test_different_seeds_diverge():
    assert take(rng.seed(1), 200) != take(rng.seed(2), 200)


def test_state_is_threaded_not_global():
    """Interleaving two streams must not disturb either.

    This is the whole point of passing state explicitly: a subsystem that
    draws numbers cannot perturb anyone else's sequence.
    """
    solo = take(rng.seed(7), 50)

    a_state, b_state = rng.seed(7), rng.seed(99)
    interleaved = []
    for _ in range(50):
        v, a_state = rng.next_u64(a_state)
        interleaved.append(v)
        _, b_state = rng.next_u64(b_state)

    assert interleaved == solo


def test_values_stay_in_64_bits():
    state = rng.seed(0)
    for _ in range(1000):
        v, state = rng.next_u64(state)
        assert 0 <= v < (1 << 64)


def test_float_range():
    state = rng.seed(3)
    for _ in range(2000):
        f, state = rng.next_float(state)
        assert 0.0 <= f < 1.0


def test_float_is_reasonably_uniform():
    """A coarse histogram check — enough to catch a badly broken mapping,
    not a statistical certification."""
    state = rng.seed(2024)
    buckets = [0] * 10
    n = 20_000

    for _ in range(n):
        f, state = rng.next_float(state)
        buckets[int(f * 10)] += 1

    expected = n / 10
    for count in buckets:
        assert abs(count - expected) < expected * 0.15


def test_next_below_stays_in_range():
    state = rng.seed(11)
    for bound in (1, 2, 7, 64, 1000):
        for _ in range(500):
            v, state = rng.next_below(state, bound)
            assert 0 <= v < bound


def test_next_below_rejects_non_positive():
    import pytest

    with pytest.raises(ValueError):
        rng.next_below(rng.seed(0), 0)


def test_next_range_respects_bounds():
    state = rng.seed(5)
    for _ in range(1000):
        v, state = rng.next_range(state, -3.5, 8.25)
        assert -3.5 <= v < 8.25


def test_split_produces_independent_streams():
    parent = rng.seed(2023)
    child_a, parent = rng.split(parent)
    child_b, parent = rng.split(parent)

    assert take(child_a, 50) != take(child_b, 50)
    assert child_a != child_b


def test_split_is_reproducible():
    a, _ = rng.split(rng.seed(77))
    b, _ = rng.split(rng.seed(77))
    assert a == b
