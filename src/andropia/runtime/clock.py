"""The only module allowed to know what time it is.

Everything in :mod:`andropia.sim` and :mod:`andropia.runtime.session` is a
pure function of its inputs. Something has to decide *when* to call them if
the world is meant to run at a pace a person can watch, and that decision
lives here — which keeps the determinism guarantee auditable: there is
exactly one file to check.

Even here the split holds. :func:`plan` is pure arithmetic: given how much
time has passed, how many whole ticks are owed? :func:`drive` is the thin
effectful loop that reads a clock, calls ``plan``, and sleeps. The policy is
tested exhaustively; the shell is barely worth testing.

The model is a fixed-timestep accumulator. Wall time advances irregularly —
the OS deschedules, a collection lands, a model call blocks a thread — but
the simulation always advances in whole ticks of exactly ``world.dt``. It
never sees a variable timestep, so results do not depend on the machine.

When the machine cannot keep up, simulated time is *dropped* rather than
chased. Unbounded catch-up is the classic way a fixed-step loop turns a
brief stall into a permanent freeze.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from . import session as sess
from .session import Session

# Ceiling on how many ticks one pass may run to catch up after a stall.
MAX_CATCHUP_TICKS = 8

# How often a paused session wakes just to notice it has been resumed.
# Coarser than a tick on purpose: idle worlds should cost nothing.
PAUSED_POLL_SECONDS = 0.1

# Floor on the running sleep interval, so a very high speed multiplier
# cannot turn the loop into a busy-wait.
MIN_SLEEP_SECONDS = 0.001


@dataclass(frozen=True, slots=True)
class Lag:
    """Reported when the loop cannot keep pace.

    Surfaced rather than swallowed: silently dropping simulated time changes
    how fast the world appears to run, and that should be visible.
    """

    dropped_ticks: int
    behind_seconds: float


@dataclass(frozen=True, slots=True)
class Pacing:
    """How many whole ticks are owed, and what is left over."""

    ticks: int
    accumulator: float
    lag: Lag | None = None


def plan(
    accumulator: float,
    elapsed: float,
    *,
    dt: float,
    speed: float = 1.0,
    max_catchup: int = MAX_CATCHUP_TICKS,
) -> Pacing:
    """Decide how far to advance after ``elapsed`` wall seconds. Pure.

    ``accumulator`` carries the fractional remainder between passes, which is
    what keeps the average rate correct even when wake-ups are irregular.
    """
    if dt <= 0.0:
        raise ValueError("dt must be positive")

    accumulator += elapsed * speed
    owed = int(accumulator / dt)

    if owed <= max_catchup:
        return Pacing(ticks=max(0, owed), accumulator=accumulator - owed * dt)

    # Beyond the budget: run what we can, abandon the rest, and say so.
    dropped = owed - max_catchup
    return Pacing(
        ticks=max_catchup,
        accumulator=0.0,
        lag=Lag(dropped_ticks=dropped, behind_seconds=dropped * dt),
    )


def sleep_for(session: Session) -> float:
    """How long to yield before the next pass.

    Paused sessions poll slowly — there is nothing to do but notice a resume,
    so this is deliberately coarser than a tick. Running sessions aim for
    roughly one wake per tick, scaled by speed, and are floored so a high
    multiplier cannot spin the event loop.
    """
    if session.mode == "paused":
        return PAUSED_POLL_SECONDS
    return max(MIN_SLEEP_SECONDS, session.world.dt / session.speed)


OnTick = Callable[[Session], None]
OnLag = Callable[[Lag], None]
Sleeper = Callable[[float], Awaitable[None]]


async def drive(
    session: Session,
    *,
    on_tick: OnTick | None = None,
    on_lag: OnLag | None = None,
    stop: asyncio.Event | None = None,
    now: Callable[[], float] = time.monotonic,
    sleep: Sleeper = asyncio.sleep,
) -> Session:
    """Run a session in real time until ``stop`` is set.

    ``now`` and ``sleep`` are injected so tests can drive the loop with a
    fake clock and no real waiting. Returns the final session, so a caller
    can snapshot or fork it.
    """
    stop = stop or asyncio.Event()
    accumulator = 0.0
    previous = now()

    while not stop.is_set():
        current = now()
        elapsed = current - previous
        previous = current

        if session.mode == "running":
            pacing = plan(
                accumulator,
                elapsed,
                dt=session.world.dt,
                speed=session.speed,
            )
            accumulator = pacing.accumulator

            for _ in range(pacing.ticks):
                session = sess.tick(session)
                if on_tick is not None:
                    on_tick(session)

            if pacing.lag is not None and on_lag is not None:
                on_lag(pacing.lag)
        else:
            # Time spent paused is discarded, so resuming does not trigger a
            # catch-up burst for however long the world sat still.
            accumulator = 0.0

        await sleep(sleep_for(session))

    return session


async def run_for(
    session: Session,
    seconds: float,
    *,
    now: Callable[[], float] = time.monotonic,
) -> Session:
    """Run in real time for a fixed wall-clock duration, then stop.

    Convenience for demos. For fast-forward that is not paced by a clock, use
    :func:`andropia.runtime.session.advance` — it is faster and fully
    deterministic.
    """
    stop = asyncio.Event()

    async def timer() -> None:
        await asyncio.sleep(seconds)
        stop.set()

    task = asyncio.create_task(timer())
    try:
        return await drive(sess.resume(session), stop=stop, now=now)
    finally:
        task.cancel()
