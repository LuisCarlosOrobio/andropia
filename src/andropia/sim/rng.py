"""A deterministic, explicitly-threaded pseudo-random number generator.

The standard library's ``random`` module keeps global mutable state, which
would make the simulation irreproducible the moment anything else touched it.
Here the state is a plain integer carried inside ``World`` and passed through
every call, so a run is a function of its seed and nothing else.

The algorithm is SplitMix64 — small, fast, well-distributed, and trivially
verifiable against published test vectors. It is not cryptographically
secure and is not intended to be.

Every function returns ``(value, next_state)``. Callers thread the new state
forward; forgetting to is a visible bug rather than a silent correlation.
"""

from __future__ import annotations

_MASK64 = 0xFFFFFFFFFFFFFFFF
_GOLDEN = 0x9E3779B97F4A7C15


def seed(n: int) -> int:
    """Turn any integer into a valid initial state."""
    return n & _MASK64


def next_u64(state: int) -> tuple[int, int]:
    """One SplitMix64 step: returns (value, next_state)."""
    state = (state + _GOLDEN) & _MASK64
    z = state
    z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & _MASK64
    z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & _MASK64
    z = z ^ (z >> 31)
    return z, state


def next_float(state: int) -> tuple[float, int]:
    """Uniform in [0.0, 1.0).

    Uses the top 53 bits, which is exactly the mantissa width of a double,
    so every representable value in the range is reachable and the mapping
    involves no rounding.
    """
    v, state = next_u64(state)
    return (v >> 11) * (1.0 / (1 << 53)), state


def next_range(state: int, lo: float, hi: float) -> tuple[float, int]:
    """Uniform in [lo, hi)."""
    f, state = next_float(state)
    return lo + f * (hi - lo), state


def next_below(state: int, n: int) -> tuple[int, int]:
    """Uniform integer in [0, n).

    Uses Lemire's multiply-shift rejection method so the result is unbiased,
    unlike the modulo approach. Rejection is astronomically rare for small
    ``n`` but the loop keeps the distribution exact regardless.
    """
    if n <= 0:
        raise ValueError("n must be positive")
    v, state = next_u64(state)
    m = v * n
    low = m & _MASK64
    if low < n:
        threshold = (-n) % n
        while low < threshold:
            v, state = next_u64(state)
            m = v * n
            low = m & _MASK64
    return m >> 64, state


def split(state: int) -> tuple[int, int]:
    """Derive an independent stream from this one.

    Returns ``(child_state, next_state)``. Use when a subsystem needs its own
    sequence without its consumption pattern perturbing the caller's — for
    example, giving each being a private stream so adding a being does not
    change what the others do.
    """
    child, state = next_u64(state)
    return seed(child), state
