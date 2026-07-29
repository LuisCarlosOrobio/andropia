"""The real-time driver.

Split the way the module is: :func:`plan` is pure arithmetic and gets
exhaustive tests, while :func:`drive` is a thin shell exercised with an
injected clock and a no-op sleeper so nothing here waits on real time.
"""

from __future__ import annotations

import asyncio

import pytest

from andropia.runtime import clock
from andropia.runtime import session as sess
from andropia.sim import Entity, Vec3, World, snapshot

DT = 0.05


def a_world(dt: float = DT) -> World:
    return World(entities={"ava": Entity(id="ava", pos=Vec3(0.0, 0.0, 0.0))}, dt=dt)


# --------------------------------------------------------------------------
# plan — pure pacing policy
# --------------------------------------------------------------------------


def test_no_elapsed_time_owes_no_ticks():
    p = clock.plan(0.0, 0.0, dt=DT)
    assert p.ticks == 0
    assert p.lag is None


def test_exactly_one_dt_owes_one_tick():
    p = clock.plan(0.0, DT, dt=DT)
    assert p.ticks == 1
    assert p.accumulator == pytest.approx(0.0, abs=1e-12)


def test_partial_time_owes_nothing_but_is_carried():
    p = clock.plan(0.0, DT * 0.6, dt=DT)
    assert p.ticks == 0
    assert p.accumulator == pytest.approx(DT * 0.6)


def test_remainder_accumulates_into_a_later_tick():
    """Irregular wake-ups must still average out to the right rate."""
    acc, total = 0.0, 0
    for _ in range(10):
        p = clock.plan(acc, DT * 0.5, dt=DT)
        acc = p.accumulator
        total += p.ticks

    assert total == 5  # ten half-ticks make five whole ones


def test_speed_multiplies_the_tick_rate():
    # A generous budget, so this measures the multiplier rather than the cap.
    slow = clock.plan(0.0, DT * 4, dt=DT, speed=1.0, max_catchup=100)
    fast = clock.plan(0.0, DT * 4, dt=DT, speed=4.0, max_catchup=100)

    assert slow.ticks == 4
    assert fast.ticks == 16


def test_slow_motion_owes_fewer_ticks():
    p = clock.plan(0.0, DT * 4, dt=DT, speed=0.25)
    assert p.ticks == 1


def test_catch_up_is_bounded_and_reported():
    """A 60-second stall is 1200 ticks of backlog. Run the budget, drop the
    rest, and report it — chasing it would freeze the loop."""
    p = clock.plan(0.0, 60.0, dt=DT)

    assert p.ticks == clock.MAX_CATCHUP_TICKS
    assert p.lag is not None
    assert p.lag.dropped_ticks == int(60.0 / DT) - clock.MAX_CATCHUP_TICKS
    assert p.lag.behind_seconds > 50.0


def test_dropping_a_backlog_clears_the_accumulator():
    """Otherwise the next pass would immediately owe the backlog again."""
    p = clock.plan(0.0, 60.0, dt=DT)
    assert p.accumulator == 0.0


def test_a_backlog_within_budget_is_not_lag():
    p = clock.plan(0.0, DT * clock.MAX_CATCHUP_TICKS, dt=DT)
    assert p.ticks == clock.MAX_CATCHUP_TICKS
    assert p.lag is None


def test_plan_rejects_non_positive_dt():
    for bad in (0.0, -0.05):
        with pytest.raises(ValueError):
            clock.plan(0.0, 1.0, dt=bad)


def test_sleep_interval_shortens_as_speed_rises():
    s = sess.resume(sess.begin(a_world()))
    assert clock.sleep_for(s) == pytest.approx(DT)
    assert clock.sleep_for(sess.set_speed(s, 10.0)) == pytest.approx(DT / 10.0)
    # Floored, so a huge multiplier cannot spin the event loop.
    assert clock.sleep_for(sess.set_speed(s, 10_000.0)) >= 0.001


def test_paused_sessions_poll_slowly():
    """An idle world should cost nothing — wake coarser than a tick."""
    paused = sess.begin(a_world())
    running = sess.resume(paused)

    assert clock.sleep_for(paused) > clock.sleep_for(running)
    assert clock.sleep_for(paused) == clock.PAUSED_POLL_SECONDS


# --------------------------------------------------------------------------
# drive — the effectful shell, with time and sleeping injected
# --------------------------------------------------------------------------


class FakeClock:
    """A monotonic clock that only moves when a sleep is awaited.

    Stops the loop once a wall-clock *duration* has elapsed rather than after
    a number of passes — a speed multiplier means more ticks per second, not
    more ticks per wake, so seconds are the meaningful axis.
    """

    def __init__(self, run_for: float) -> None:
        self.t = 0.0
        self.limit = run_for

    def now(self) -> float:
        return self.t

    def sleeper(self, stop: asyncio.Event):
        async def sleep(seconds: float) -> None:
            self.t += seconds
            if self.t >= self.limit:
                stop.set()
            await asyncio.sleep(0)

        return sleep


async def drive_seconds(session, seconds: float, *, on_tick=None, on_lag=None):
    """Run the loop for ``seconds`` of fake wall time."""
    fake = FakeClock(seconds)
    stop = asyncio.Event()
    return await clock.drive(
        session,
        stop=stop,
        now=fake.now,
        sleep=fake.sleeper(stop),
        on_tick=on_tick,
        on_lag=on_lag,
    )


async def test_paused_session_never_advances():
    s = await drive_seconds(sess.begin(a_world()), 5.0)
    assert s.world.tick == 0


async def test_one_second_of_real_time_is_about_one_second_of_ticks():
    """At 1x and dt=0.05, a second should be roughly 20 ticks.

    A range rather than an exact count: the accumulator deliberately carries
    a fractional remainder, so individual passes vary by one either way.
    """
    s = await drive_seconds(sess.resume(sess.begin(a_world())), 1.0)
    assert 18 <= s.world.tick <= 21


async def test_speed_multiplier_produces_more_ticks_per_second():
    slow = await drive_seconds(sess.resume(sess.begin(a_world())), 1.0)
    fast = await drive_seconds(
        sess.set_speed(sess.resume(sess.begin(a_world())), 5.0), 1.0
    )

    assert fast.world.tick > slow.world.tick * 3


async def test_slow_motion_produces_fewer_ticks_per_second():
    normal = await drive_seconds(sess.resume(sess.begin(a_world())), 1.0)
    slowmo = await drive_seconds(
        sess.set_speed(sess.resume(sess.begin(a_world())), 0.25), 1.0
    )

    assert slowmo.world.tick < normal.world.tick


async def test_on_tick_fires_once_per_tick_in_order():
    seen: list[int] = []
    s = await drive_seconds(
        sess.resume(sess.begin(a_world())), 0.5, on_tick=lambda x: seen.append(x.world.tick)
    )

    assert seen == list(range(1, s.world.tick + 1))


async def test_pausing_does_not_bank_time():
    """Time spent paused must not cause a burst when the world resumes."""
    paused = await drive_seconds(sess.begin(a_world()), 30.0)
    assert paused.world.tick == 0

    resumed = await drive_seconds(sess.resume(paused), 0.1)
    assert resumed.world.tick <= clock.MAX_CATCHUP_TICKS


async def test_driving_records_a_replayable_run():
    """A real-time run reproduces exactly like a fast-forwarded one."""
    s = await drive_seconds(sess.resume(sess.begin(a_world())), 0.6)

    assert s.recording.ticks == s.world.tick
    assert snapshot.dump(sess.replay(s.recording)) == snapshot.dump(s.world)
