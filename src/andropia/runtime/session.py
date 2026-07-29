"""A simulation session: the world plus everything needed to control and
reproduce it.

Still pure. A ``Session`` is a value and every transition returns a new one;
nothing here reads a clock, spawns a task or touches a socket. That belongs
to :mod:`andropia.runtime.clock`, which is the only module in the project
permitted to know what time it is.

The session carries three things the bare simulation does not:

* **pending intents** — what agents have proposed since the last tick, which
  arrive asynchronously and are applied at tick boundaries so that a being
  thinking for three seconds never stalls the world;
* **a recording** — the per-tick intent log which, with the initial world,
  reproduces a run exactly;
* **transport state** — paused or running, and at what multiple of real time.

Speed and pause are recorded in the session but *interpreted* by the clock.
The simulation itself has no opinion about how fast it is being asked to run,
which is precisely why it can be run at 10x, single-stepped, or replayed
without a clock at all.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal

from ..sim import Intent, World, step

Mode = Literal["paused", "running"]


@dataclass(frozen=True, slots=True)
class Recording:
    """Everything needed to reproduce a run.

    ``initial`` plus ``batches`` is a complete description: replaying is
    folding ``step`` over the log, and it needs no models, no network and no
    clock. Nondeterminism has already been collapsed into the record of what
    was actually proposed.
    """

    initial: World
    batches: tuple[tuple[Intent, ...], ...] = ()

    @property
    def ticks(self) -> int:
        return len(self.batches)


@dataclass(frozen=True, slots=True)
class Session:
    world: World
    mode: Mode = "paused"
    speed: float = 1.0
    pending: tuple[Intent, ...] = ()
    recording: Recording | None = None
    # Set when the world was restored mid-run; replay from a snapshot starts
    # here rather than at tick zero.
    started_at_tick: int = 0


def begin(world: World, *, record: bool = True, mode: Mode = "paused") -> Session:
    """Open a session on a world."""
    return Session(
        world=world,
        mode=mode,
        recording=Recording(initial=world) if record else None,
        started_at_tick=world.tick,
    )


# --------------------------------------------------------------------------
# transport
# --------------------------------------------------------------------------


def pause(session: Session) -> Session:
    return replace(session, mode="paused")


def resume(session: Session) -> Session:
    return replace(session, mode="running")


def set_speed(session: Session, multiplier: float) -> Session:
    """Set how fast the clock should drive this session.

    A multiplier, not a tick rate: 1.0 is real time, 10.0 runs ten simulated
    seconds per wall second, 0.25 runs in slow motion. The value is advisory
    — the clock will fall short of very high multipliers if a tick costs more
    than its budget, and that shortfall is reported rather than hidden.
    """
    if multiplier <= 0.0:
        raise ValueError("speed multiplier must be positive; use pause() to stop")
    return replace(session, speed=multiplier)


# --------------------------------------------------------------------------
# intents
# --------------------------------------------------------------------------


def propose(session: Session, *intents: Intent) -> Session:
    """Queue intents for the next tick.

    Called from agent runners as their model calls return. Intents queue
    rather than apply immediately so that every tick has a well-defined
    input, whatever order the responses happened to arrive in.
    """
    if not intents:
        return session
    return replace(session, pending=(*session.pending, *intents))


# --------------------------------------------------------------------------
# advancing
# --------------------------------------------------------------------------


def tick(session: Session) -> Session:
    """Advance one tick, regardless of mode.

    Mode governs whether the *clock* calls this; calling it directly is how
    single-stepping works, and it is deliberately still possible while
    paused.
    """
    batch = session.pending
    world = step(session.world, batch)

    recording = session.recording
    if recording is not None:
        recording = replace(recording, batches=(*recording.batches, batch))

    return replace(session, world=world, pending=(), recording=recording)


def advance(session: Session, ticks: int) -> Session:
    """Advance ``ticks`` ticks as fast as the machine allows.

    This is fast-forward. Pending intents apply on the first tick only — the
    rest run with an empty batch, because no agent has had a chance to
    observe the intervening world.
    """
    if ticks < 0:
        raise ValueError("cannot advance a negative number of ticks")
    for _ in range(ticks):
        session = tick(session)
    return session


# --------------------------------------------------------------------------
# replay
# --------------------------------------------------------------------------


def replay(recording: Recording, until: int | None = None) -> World:
    """Reproduce a recorded run, optionally stopping early.

    Pure and offline: no clock, no models, no network. ``until`` is a tick
    offset into the recording, which is what makes "rewind to the interesting
    moment" a one-liner.
    """
    batches = recording.batches if until is None else recording.batches[:until]
    world = recording.initial
    for batch in batches:
        world = step(world, batch)
    return world


def fork(recording: Recording, at: int) -> Session:
    """Open a new session from a point in a recorded run.

    The returned session records afresh, so a fork and its parent diverge
    into two independently reproducible histories.
    """
    return begin(replay(recording, until=at))
