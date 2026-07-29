"""Behaviour of the fold: intents in, world out."""

from __future__ import annotations

from andropia.sim import (
    DoGesture,
    Emote,
    Entity,
    Gesture,
    Goto,
    Idle,
    Landmark,
    Look,
    Speak,
    Stop,
    Vec3,
    Walk,
    World,
    run,
    step,
)
from andropia.sim.movement import ARRIVAL_RADIUS


def world_with(*entities: Entity, **landmarks: Vec3) -> World:
    return World(
        entities={e.id: e for e in entities},
        landmarks={k: Landmark(k, v) for k, v in landmarks.items()},
    )


def test_goto_sets_walk_action_with_resolved_position():
    w = world_with(Entity(id="a"), pond=Vec3(5.0, 0.0, 0.0))
    w = step(w, (Goto(entity="a", target="pond"),))

    action = w.entities["a"].action
    assert isinstance(action, Walk)
    assert action.target == Vec3(5.0, 0.0, 0.0)


def test_goto_unknown_landmark_is_ignored_not_raised():
    """Agents act on a world one tick stale; naming a vanished place is
    ordinary, not exceptional."""
    w = world_with(Entity(id="a"))
    w = step(w, (Goto(entity="a", target="atlantis"),))

    assert isinstance(w.entities["a"].action, Idle)


def test_intent_for_unknown_entity_is_ignored():
    w = world_with(Entity(id="a"))
    before = w.entities["a"]
    w = step(w, (Emote(entity="ghost", emotion="happy"),))

    assert w.entities["a"] == before
    assert "ghost" not in w.entities


def test_walking_being_arrives_and_returns_to_idle():
    w = world_with(Entity(id="a", pos=Vec3(0.0, 0.0, 0.0)), pond=Vec3(4.0, 0.0, 0.0))
    w = step(w, (Goto(entity="a", target="pond"),))

    w = run(w, [() for _ in range(400)])

    ent = w.entities["a"]
    assert isinstance(ent.action, Idle)
    dx = ent.pos.x - 4.0
    dz = ent.pos.z
    assert (dx * dx + dz * dz) ** 0.5 <= ARRIVAL_RADIUS + 1e-6


def test_walking_moves_toward_target_monotonically():
    w = world_with(Entity(id="a"), pond=Vec3(10.0, 0.0, 0.0))
    w = step(w, (Goto(entity="a", target="pond"),))

    def gap(world: World) -> float:
        p = world.entities["a"].pos
        return ((p.x - 10.0) ** 2 + p.z**2) ** 0.5

    previous = gap(w)
    for _ in range(60):
        w = step(w)
        current = gap(w)
        assert current <= previous + 1e-9
        previous = current


def test_stop_halts_a_walking_being():
    w = world_with(Entity(id="a"), pond=Vec3(9.0, 0.0, 0.0))
    w = step(w, (Goto(entity="a", target="pond"),))
    w = run(w, [() for _ in range(10)])
    w = step(w, (Stop(entity="a"),))

    assert isinstance(w.entities["a"].action, Idle)

    resting = w.entities["a"].pos
    w = run(w, [() for _ in range(10)])
    assert w.entities["a"].pos == resting


def test_gesture_expires_after_its_duration():
    """Note the tick semantics: an intent applied during tick N is also
    *advanced* during tick N, so the gesture is already one dt old when the
    step returns. A tick applies what was proposed, then moves the world."""
    w = world_with(Entity(id="a"))
    w = step(w, (DoGesture(entity="a", motion="wave"),))

    action = w.entities["a"].action
    assert isinstance(action, Gesture)
    assert action.elapsed == w.dt

    # Still gesturing well before the 1.5s duration is up.
    w = run(w, [() for _ in range(20)])
    assert isinstance(w.entities["a"].action, Gesture)

    # Counted rather than asserted at an exact index, so accumulated float
    # error in `elapsed` cannot make this brittle.
    ticks = 0
    while isinstance(w.entities["a"].action, Gesture) and ticks < 100:
        w = step(w)
        ticks += 1

    assert isinstance(w.entities["a"].action, Idle)
    assert 28 <= 21 + ticks <= 31  # ≈ 1.5s at 20 Hz


def test_emotion_decays_to_neutral():
    w = world_with(Entity(id="a"))
    w = step(w, (Emote(entity="a", emotion="angry"),))

    assert w.entities["a"].emotion == "angry"
    # One dt of decay has already been applied — see the note above.
    assert 0.99 < w.entities["a"].emotion_weight < 1.0

    w = run(w, [() for _ in range(500)])
    assert w.entities["a"].emotion_weight == 0.0
    assert w.entities["a"].emotion == "neutral"


def test_emotion_decay_is_monotonic():
    w = world_with(Entity(id="a"))
    w = step(w, (Emote(entity="a", emotion="sad"),))

    previous = w.entities["a"].emotion_weight
    for _ in range(100):
        w = step(w)
        current = w.entities["a"].emotion_weight
        assert current <= previous
        previous = current


def test_speech_enters_transcript_and_expires():
    w = world_with(Entity(id="a"))
    w = step(w, (Speak(entity="a", text="hello there friend"),))

    assert w.entities["a"].speech is not None
    assert len(w.transcript) == 1
    assert w.transcript[0].speaker == "a"
    assert w.transcript[0].text == "hello there friend"

    w = run(w, [() for _ in range(200)])
    assert w.entities["a"].speech is None
    # The transcript is permanent; only the act of speaking ends.
    assert len(w.transcript) == 1


def test_look_sets_and_clears_gaze():
    w = world_with(Entity(id="a"), Entity(id="b"))
    w = step(w, (Look(entity="a", at="b"),))
    assert w.entities["a"].gaze == "b"

    w = step(w, (Look(entity="a", at=None),))
    assert w.entities["a"].gaze is None


def test_multiple_intents_in_one_tick_all_apply():
    w = world_with(Entity(id="a"), Entity(id="b"), pond=Vec3(6.0, 0.0, 0.0))
    w = step(
        w,
        (
            Goto(entity="a", target="pond"),
            Emote(entity="a", emotion="happy"),
            Look(entity="b", at="a"),
        ),
    )

    assert isinstance(w.entities["a"].action, Walk)
    assert w.entities["a"].emotion == "happy"
    assert w.entities["b"].gaze == "a"
