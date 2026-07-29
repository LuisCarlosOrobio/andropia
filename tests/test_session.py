"""Time control: stepping, fast-forward, recording, replay and forking."""

from __future__ import annotations

import pytest

from andropia.runtime import session as sess
from andropia.sim import Emote, Entity, Goto, Landmark, Speak, Vec3, World, snapshot


def a_world() -> World:
    return World(
        entities={
            "ava": Entity(id="ava", pos=Vec3(0.0, 0.0, 0.0)),
            "mistral": Entity(id="mistral", pos=Vec3(4.0, 0.0, 0.0)),
        },
        landmarks={
            "pond": Landmark("pond", Vec3(-6.0, 0.0, 2.0)),
            "tree": Landmark("tree", Vec3(9.0, 0.0, -3.0)),
        },
    )


# --------------------------------------------------------------------------
# stepping
# --------------------------------------------------------------------------


def test_begin_starts_paused_and_records():
    s = sess.begin(a_world())
    assert s.mode == "paused"
    assert s.recording is not None
    assert s.recording.ticks == 0


def test_tick_works_while_paused():
    """Single-stepping a paused world is the point of a sandbox."""
    s = sess.begin(a_world())
    s = sess.tick(s)

    assert s.mode == "paused"
    assert s.world.tick == 1


def test_pending_intents_apply_on_the_next_tick_only():
    s = sess.begin(a_world())
    s = sess.propose(s, Goto(entity="ava", target="pond"))

    assert s.world.entities["ava"].action.kind == "idle"
    assert len(s.pending) == 1

    s = sess.tick(s)
    assert s.world.entities["ava"].action.kind == "walk"
    assert s.pending == ()


def test_proposals_accumulate_between_ticks():
    s = sess.begin(a_world())
    s = sess.propose(s, Goto(entity="ava", target="pond"))
    s = sess.propose(s, Emote(entity="mistral", emotion="happy"))

    assert len(s.pending) == 2
    s = sess.tick(s)

    assert s.world.entities["ava"].action.kind == "walk"
    assert s.world.entities["mistral"].emotion == "happy"


def test_advance_fast_forwards():
    s = sess.begin(a_world())
    s = sess.advance(s, 500)
    assert s.world.tick == 500


def test_advance_rejects_negative():
    with pytest.raises(ValueError):
        sess.advance(sess.begin(a_world()), -1)


# --------------------------------------------------------------------------
# transport
# --------------------------------------------------------------------------


def test_pause_and_resume():
    s = sess.begin(a_world())
    assert sess.resume(s).mode == "running"
    assert sess.pause(sess.resume(s)).mode == "paused"


def test_speed_must_be_positive():
    s = sess.begin(a_world())
    assert sess.set_speed(s, 10.0).speed == 10.0

    for bad in (0.0, -1.0):
        with pytest.raises(ValueError):
            sess.set_speed(s, bad)


def test_speed_does_not_affect_simulation_outcome():
    """Speed is a clock concern. The same ticks produce the same world
    whether they were run at 1x or 100x."""
    slow = sess.advance(sess.set_speed(sess.begin(a_world()), 0.5), 300)
    fast = sess.advance(sess.set_speed(sess.begin(a_world()), 50.0), 300)

    assert snapshot.dump(slow.world) == snapshot.dump(fast.world)


# --------------------------------------------------------------------------
# recording and replay
# --------------------------------------------------------------------------


def test_recording_captures_every_tick():
    s = sess.begin(a_world())
    s = sess.propose(s, Goto(entity="ava", target="pond"))
    s = sess.advance(s, 10)

    assert s.recording.ticks == 10
    assert len(s.recording.batches[0]) == 1
    assert all(b == () for b in s.recording.batches[1:])


def test_replay_reproduces_the_run_exactly():
    s = sess.begin(a_world())
    s = sess.propose(s, Goto(entity="ava", target="pond"))
    s = sess.advance(s, 50)
    s = sess.propose(s, Goto(entity="mistral", target="tree"))
    s = sess.propose(s, Speak(entity="ava", text="over here"))
    s = sess.advance(s, 200)

    replayed = sess.replay(s.recording)
    assert snapshot.dump(replayed) == snapshot.dump(s.world)


def test_replay_can_stop_early():
    s = sess.begin(a_world())
    s = sess.propose(s, Goto(entity="ava", target="pond"))
    s = sess.advance(s, 100)

    midpoint = sess.replay(s.recording, until=40)
    assert midpoint.tick == 40


def test_replay_needs_no_clock_or_models():
    """Offline reproduction is the whole point — a recording is a complete,
    self-contained description of a run."""
    s = sess.advance(sess.propose(sess.begin(a_world()),
                                  Goto(entity="ava", target="pond")), 120)

    first = sess.replay(s.recording)
    second = sess.replay(s.recording)

    assert snapshot.dump(first) == snapshot.dump(second)


def test_recording_can_be_disabled():
    s = sess.begin(a_world(), record=False)
    s = sess.advance(s, 5)
    assert s.recording is None


# --------------------------------------------------------------------------
# forking
# --------------------------------------------------------------------------


def test_fork_resumes_from_a_point_in_history():
    s = sess.begin(a_world())
    s = sess.propose(s, Goto(entity="ava", target="pond"))
    s = sess.advance(s, 300)

    branch = sess.fork(s.recording, at=100)
    assert branch.world.tick == 100
    assert branch.recording.ticks == 0  # a fresh history


def test_forks_diverge_independently():
    """Rewind to an interesting moment, change one thing, and compare."""
    s = sess.begin(a_world())
    s = sess.propose(s, Goto(entity="ava", target="pond"))
    s = sess.advance(s, 200)

    left = sess.advance(sess.propose(sess.fork(s.recording, at=50),
                                     Goto(entity="ava", target="tree")), 150)
    right = sess.advance(sess.fork(s.recording, at=50), 150)

    assert left.world.tick == right.world.tick
    assert snapshot.dump(left.world) != snapshot.dump(right.world)


def test_fork_of_the_same_point_is_identical():
    s = sess.begin(a_world())
    s = sess.propose(s, Goto(entity="ava", target="pond"))
    s = sess.advance(s, 200)

    a = sess.advance(sess.fork(s.recording, at=80), 60)
    b = sess.advance(sess.fork(s.recording, at=80), 60)

    assert snapshot.dump(a.world) == snapshot.dump(b.world)
