"""What a being can see.

Perception is egocentric, so most of these tests are about handedness and
range. The bearing sign in particular is pinned from several directions: it is
invisible in review and shows up only as beings consistently turning the wrong
way, which is easy to mistake for an animation bug.
"""

from __future__ import annotations

from andropia.beings import perception as per
from andropia.sim.types import (
    Entity,
    Gesture,
    Landmark,
    Speech,
    Utterance,
    Vec3,
    Walk,
    World,
)

NORTH = Vec3(0.0, 0.0, 1.0)  # +Z, the default facing


def world_with(*entities, landmarks=(), transcript=()):
    return World(
        entities={e.id: e for e in entities},
        landmarks={m.id: m for m in landmarks},
        transcript=tuple(transcript),
    )


def bearing_to(target: Vec3, facing: Vec3 = NORTH) -> str:
    me = Entity(id="me", pos=Vec3(0.0, 0.0, 0.0), facing=facing)
    them = Entity(id="them", pos=target)
    return per.observe(world_with(me, them), "me").beings[0].bearing


# -- handedness ------------------------------------------------------------


def test_straight_ahead():
    assert bearing_to(Vec3(0.0, 0.0, 5.0)) == "straight ahead"


def test_behind():
    assert bearing_to(Vec3(0.0, 0.0, -5.0)) == "behind you"


def test_plus_x_is_left_when_facing_plus_z():
    """The handedness anchor.

    In a right-handed frame with Y up, right = forward × up. Against a standard
    camera looking down −Z with +X right, that gives right = −X for a being
    facing +Z. So +X is its left.
    """
    assert bearing_to(Vec3(5.0, 0.0, 0.0)) == "to your left"
    assert bearing_to(Vec3(-5.0, 0.0, 0.0)) == "to your right"


def test_bearing_is_relative_to_facing_not_the_world():
    # The same world position, seen by a being turned around, is on the other
    # side. This is what makes the observation egocentric rather than a
    # coordinate dump in words.
    east = Vec3(5.0, 0.0, 0.0)
    assert bearing_to(east, facing=NORTH) == "to your left"
    assert bearing_to(east, facing=Vec3(0.0, 0.0, -1.0)) == "to your right"


def test_diagonals_name_both_axes():
    assert bearing_to(Vec3(3.0, 0.0, 3.0)) == "ahead and to your left"
    assert bearing_to(Vec3(-3.0, 0.0, 3.0)) == "ahead and to your right"


def test_coincident_position_does_not_divide_by_zero():
    assert bearing_to(Vec3(0.0, 0.0, 0.0)) == "right where you are"


def test_height_is_ignored():
    # The world is a horizontal plane; a being is not asked to think in 3D.
    assert bearing_to(Vec3(0.0, 9.0, 5.0)) == "straight ahead"


# -- range ----------------------------------------------------------------


def test_beings_beyond_sight_range_are_not_seen():
    me = Entity(id="me")
    far = Entity(id="far", pos=Vec3(0.0, 0.0, per.SIGHT_RANGE + 1.0))
    assert per.observe(world_with(me, far), "me").beings == ()


def test_landmarks_beyond_sight_range_are_not_described():
    me = Entity(id="me")
    mark = Landmark("moon", Vec3(0.0, 0.0, per.SIGHT_RANGE + 1.0))
    obs = per.observe(world_with(me, landmarks=[mark]), "me")
    assert obs.places == ()


def test_proximity_bands_are_ordered_by_distance():
    me = Entity(id="me")
    seen = []
    for z in (1.0, 3.0, 8.0, 20.0):
        them = Entity(id="them", pos=Vec3(0.0, 0.0, z))
        seen.append(per.observe(world_with(me, them), "me").beings[0].proximity)
    assert seen == ["right next to you", "close by", "a little way off", "far away"]


def test_alone_means_nobody_within_reach():
    me = Entity(id="me")
    distant = Entity(id="distant", pos=Vec3(0.0, 0.0, 20.0))
    assert per.observe(world_with(me, distant), "me").alone is True

    near = Entity(id="near", pos=Vec3(0.0, 0.0, 2.0))
    assert per.observe(world_with(me, near), "me").alone is False


# -- self ------------------------------------------------------------------


def test_a_being_does_not_see_itself_as_another():
    me = Entity(id="me")
    assert per.observe(world_with(me), "me").beings == ()


def test_missing_being_observes_nothing():
    # An intent may name a being that has since been removed, and that is
    # ordinary rather than an error.
    assert per.observe(world_with(Entity(id="me")), "ghost") is None


def test_own_action_is_reported():
    walker = Entity(id="me", action=Walk(target=Vec3(1.0, 0.0, 1.0)))
    assert per.observe(world_with(walker), "me").doing == "walking somewhere"

    waver = Entity(id="me", action=Gesture(motion="wave"))
    assert "wave" in per.observe(world_with(waver), "me").doing


def test_feeling_reflects_weight_not_just_emotion():
    faint = Entity(id="me", emotion="sad", emotion_weight=0.2)
    strong = Entity(id="me", emotion="sad", emotion_weight=0.9)
    unset = Entity(id="me", emotion="sad", emotion_weight=0.0)

    assert "faintly" in per.observe(world_with(faint), "me").feeling
    assert "clearly" in per.observe(world_with(strong), "me").feeling
    # Weight zero means the emotion was never actually applied.
    assert per.observe(world_with(unset), "me").feeling == "nothing in particular"


def test_another_beings_emotion_is_not_reported():
    """A being can see a face, not read a mind.

    Handing over another being's emotion label would let a model reason about
    internal state it has no access to, which is the kind of omniscience that
    makes multi-agent conversation feel scripted.
    """
    me = Entity(id="me")
    them = Entity(id="them", pos=Vec3(0.0, 0.0, 2.0), emotion="angry", emotion_weight=1.0)
    sighting = per.observe(world_with(me, them), "me").beings[0]
    assert "angry" not in repr(sighting)


# -- hearing ---------------------------------------------------------------


def test_speech_of_a_nearby_being_is_seen():
    me = Entity(id="me")
    them = Entity(
        id="them",
        pos=Vec3(0.0, 0.0, 2.0),
        speech=Speech(text="hello", start_tick=0, duration_ticks=20),
    )
    assert per.observe(world_with(me, them), "me").beings[0].speaking == "hello"


def test_transcript_is_limited_to_recent_lines():
    me = Entity(id="me")
    lines = [Utterance(tick=i, speaker="me", text=f"line {i}") for i in range(30)]
    heard = per.observe(world_with(me, transcript=lines), "me").heard

    assert len(heard) == per.TRANSCRIPT_LINES
    assert heard[-1].text == "line 29"


def test_a_being_hears_itself():
    # It should know what it just said, or it will repeat itself.
    me = Entity(id="me")
    lines = [Utterance(tick=1, speaker="me", text="I said this")]
    assert per.observe(world_with(me, transcript=lines), "me").heard == tuple(lines)


def test_speech_from_out_of_range_is_not_heard():
    me = Entity(id="me")
    far = Entity(id="far", pos=Vec3(0.0, 0.0, per.SIGHT_RANGE + 5.0))
    lines = [Utterance(tick=1, speaker="far", text="too distant")]
    assert per.observe(world_with(me, far, transcript=lines), "me").heard == ()


# -- determinism -----------------------------------------------------------


def test_observation_does_not_depend_on_dict_order():
    """Insertion order differs between a live run and one restored from a
    snapshot. A prompt whose clauses reorder is a prompt whose cache misses."""
    me = Entity(id="me")
    a = Entity(id="aaa", pos=Vec3(1.0, 0.0, 1.0))
    b = Entity(id="bbb", pos=Vec3(-1.0, 0.0, 1.0))
    marks = [Landmark("zed", Vec3(2.0, 0.0, 0.0)), Landmark("ash", Vec3(0.0, 0.0, 2.0))]

    forward = World(
        entities={"me": me, "aaa": a, "bbb": b},
        landmarks={m.id: m for m in marks},
    )
    shuffled = World(
        entities={"bbb": b, "me": me, "aaa": a},
        landmarks={m.id: m for m in reversed(marks)},
    )

    assert per.observe(forward, "me") == per.observe(shuffled, "me")


def test_observation_is_plain_data():
    # It has to survive being logged, diffed and asserted on.
    me = Entity(id="me")
    obs = per.observe(world_with(me, Entity(id="them", pos=Vec3(0.0, 0.0, 3.0))), "me")
    assert obs == per.observe(
        world_with(me, Entity(id="them", pos=Vec3(0.0, 0.0, 3.0))), "me"
    )


# -- perceiving time -------------------------------------------------------


def test_silence_is_perceivable():
    """A being that cannot perceive time cannot notice a wait has failed.

    A live run deadlocked on exactly this: the three of them agreed to watch a
    ripple in the pond and stay quiet until it showed itself, then stood in
    silence for over two minutes — because the ripple was invented, the world
    has no creature in it, and nothing they could perceive would ever settle it.
    """
    me = Entity(id="me")
    said = Utterance(tick=0, speaker="me", text="nobody speak")

    def quiet_at(tick):
        return per.observe(
            World(tick=tick, entities={"me": me}, transcript=(said,)), "me"
        ).quiet_for

    assert quiet_at(0) is None  # just spoke; nothing to remark on
    assert quiet_at(100) is None  # 5s — an ordinary pause
    assert quiet_at(600) == "a little while"  # 30s
    assert quiet_at(2000) == "a minute or two"  # 100s
    assert quiet_at(6000) == "several minutes"  # 300s


def test_silence_is_qualitative_like_every_other_distance():
    # Reporting a number invites arithmetic, and the exact seconds are precision
    # no model needs to conclude that a wait has gone on too long.
    me = Entity(id="me")
    world = World(
        tick=4000,
        entities={"me": me},
        transcript=(Utterance(tick=0, speaker="me", text="x"),),
    )
    assert not any(ch.isdigit() for ch in per.observe(world, "me").quiet_for)


def test_a_world_where_nothing_was_ever_said_reports_no_silence():
    # There is a difference between a lull and a world that has not begun.
    world = World(tick=9999, entities={"me": Entity(id="me")})
    assert per.observe(world, "me").quiet_for is None
