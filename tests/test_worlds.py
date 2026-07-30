"""Pack to world: description, projection, loading.

One test here matters more than the others.
``test_every_feature_in_sight_is_described_to_the_being_looking`` is the property
the whole format exists to hold — that a thing which renders is a thing beings
are told about. It is the failure that produced a two-minute conversation about
the water level of a pond that was a point on a flat plane, and it is the only
kind of drift that no other test can see.
"""

from __future__ import annotations

import json
from pathlib import Path

from andropia.beings import perception as per
from andropia.beings import prompt as pr
from andropia.sim.snapshot import from_dict, to_dict
from andropia.sim.types import Entity, Vec3, World
from andropia.worlds import build, describe, load, schema

WORLDS = Path(__file__).resolve().parents[1] / "worlds"
EXAMPLE = WORLDS / "example"


def a_pack(**over):
    raw = {
        "schema": 1,
        "id": "somewhere",
        "name": "Somewhere",
        "license": {"id": "CC0-1.0"},
        **over,
    }
    result = schema.validate(raw)
    assert result.ok, [str(e) for e in result.errors]
    return result.pack


def a_feature(**over):
    base = {
        "id": "pond",
        "pos": [1.0, 0.0, 2.0],
        "shape": "disc",
        "material": "water",
        "description": "a shallow pond",
    }
    return {**base, **over}


def example_pack():
    result = load.load_pack(EXAMPLE)
    assert result.ok, [str(e) for e in result.errors]
    return result.pack


# -- the property the format exists for ------------------------------------


def test_every_feature_in_sight_is_described_to_the_being_looking():
    """The anti-drift test.

    Anything a pack places in the world gets drawn. If the being standing in
    front of it is not told what it is, it can walk into something nobody
    mentioned — the same failure as being told about something that isn't there,
    from the other side. Three beings once settled "is it wet" by consensus.

    Checked through perception rather than the setting, because perception is
    what reports contents: the setting describes the place, and only what is in
    sight is described at all.
    """
    pack = example_pack()
    world = World(
        entities={"ava": Entity(id="ava")}, landmarks=build.landmarks(pack)
    )
    text = pr.situation(per.observe(world, "ava"))

    for feature in pack.features:
        assert feature.id in text, feature.id
        assert feature.description in text, feature.id
        assert feature.material in text, feature.id


def test_the_setting_does_not_list_things_perception_reports():
    """It would contradict the standing rule that a being may refer only to
    what it can currently see, and a world with fifty features would spend its
    whole cached prefix on an inventory."""
    pack = example_pack()
    text = describe.setting(pack)

    for feature in pack.features:
        assert feature.id not in text, feature.id


def test_the_ground_and_sky_are_described_from_the_fields_that_draw_them():
    pack = a_pack(
        ground={"colour": "#3f7a2e", "description": "wet green turf"},
        sky={"colour": "#8fbfe0", "description": "a pale overcast sky"},
    )
    text = describe.setting(pack)
    assert "wet green turf" in text
    assert "a pale overcast sky" in text


def test_atmosphere_is_carried_verbatim():
    # The one field with no rendered counterpart, so the only one that can be
    # authored without risking a contradiction.
    pack = a_pack(atmosphere="It has just stopped raining.")
    assert describe.setting(pack).startswith("It has just stopped raining.")


def test_an_empty_world_says_so():
    """The one exception to leaving contents to perception: that a world has
    nothing in it is a fact about the place rather than an inventory of it, and
    a being given a place and no contents will furnish it."""
    assert "Nothing has been placed here" in describe.setting(a_pack())
    assert "Nothing has been placed" not in describe.setting(example_pack())


def test_a_walkable_feature_says_it_is_walkable():
    pack = example_pack()
    walkable = [f for f in pack.features if f.enterable]
    assert walkable, "the example pack no longer exercises this"

    world = World(
        entities={"ava": Entity(id="ava")}, landmarks=build.landmarks(pack)
    )
    text = pr.situation(per.observe(world, "ava"))

    for feature in walkable:
        line = next(ln for ln in text.split("\n") if ln.startswith(f"- {feature.id} "))
        assert "walk into it" in line
    for feature in (f for f in pack.features if not f.enterable):
        line = next(ln for ln in text.split("\n") if ln.startswith(f"- {feature.id} "))
        assert "walk into it" not in line


def test_the_setting_describes_the_place_and_nothing_in_it():
    """Which is what makes it cacheable: it is true for as long as the world is,
    while everything perception reports changes every turn."""
    pack = a_pack(
        atmosphere="Still and warm.",
        ground={"description": "wet turf"},
        sky={"description": "a pale sky"},
        features=[a_feature()],
    )
    assert describe.setting(pack) == (
        "Still and warm.\n\nUnderfoot: wet turf.\n\nOverhead: a pale sky."
    )


# -- projection into the simulation ----------------------------------------


def test_features_become_landmarks_with_their_substance_intact():
    marks = build.landmarks(example_pack())
    pond = marks["pond"]
    assert pond.material == "water"
    assert pond.enterable is True
    assert pond.radius > 0.0


def test_landmark_order_is_stable():
    """Perception iterates landmarks to write a prompt, so file order leaking in
    would make a restored run miss the cache a live one hits."""
    pack = example_pack()
    assert list(build.landmarks(pack)) == sorted(build.landmarks(pack))


def test_a_landmark_keeps_its_position():
    marks = build.landmarks(example_pack())
    for feature in example_pack().features:
        assert marks[feature.id].pos == Vec3(*feature.pos)


def test_landmarks_survive_a_snapshot_round_trip():
    # Or a world restored from a recording loses what everything is made of, and
    # beings start guessing again.
    world = World(
        entities={"ava": Entity(id="ava")},
        landmarks=build.landmarks(example_pack()),
        setting=describe.setting(example_pack()),
        world_pack="example",
    )
    back = from_dict(to_dict(world))
    assert back.landmarks == world.landmarks
    assert back.setting == world.setting
    assert back.world_pack == world.world_pack


# -- what a being actually ends up seeing ----------------------------------


def test_a_being_is_told_what_a_place_is_made_of():
    """The end of the chain: a pack field reaches a prompt without anyone
    typing it twice. Three beings once settled "is it wet" by consensus."""
    world = World(
        entities={"ava": Entity(id="ava", pos=Vec3(0.0, 0.0, 0.0))},
        landmarks=build.landmarks(example_pack()),
    )
    text = pr.situation(per.observe(world, "ava"))
    assert "water" in text
    assert "walk into it" in text


def test_a_wide_place_is_near_when_you_are_on_its_edge():
    """Proximity measures to the edge, not the centre. A being standing on the
    bank of a pond is at the pond, and telling it the pond is ten metres away
    while its feet are in the water is the drift this format removes."""
    pack = example_pack()
    pond = next(f for f in pack.features if f.id == "pond")
    edge = Vec3(pond.pos[0], 0.0, pond.pos[2] - pond.radius)

    world = World(
        entities={"ava": Entity(id="ava", pos=edge)},
        landmarks=build.landmarks(pack),
    )
    place = next(p for p in per.observe(world, "ava").places if p.name == "pond")
    # Compared against the band for zero distance rather than a quoted phrase,
    # so rewording the vocabulary does not break the property being tested.
    assert place.proximity == per._proximity(0.0)
    assert place.proximity != per._proximity(place.distance)


# -- loading ---------------------------------------------------------------


def test_the_example_pack_loads_from_disk():
    assert load.load_pack(EXAMPLE).ok


def test_a_directory_with_no_manifest_says_which_file_is_missing():
    result = load.load_pack(WORLDS)
    assert not result.ok
    assert any(load.MANIFEST in e.problem or load.MANIFEST in e.hint
               for e in result.errors)


def test_broken_json_is_an_error_rather_than_an_exception(tmp_path):
    (tmp_path / load.MANIFEST).write_text("{ not json")
    result = load.load_pack(tmp_path)
    assert not result.ok
    assert "JSON" in result.errors[0].problem


def test_discovery_finds_the_example_pack():
    assert "example" in load.discover(WORLDS)


def test_discovery_reports_failures_rather_than_hiding_them(tmp_path):
    """A pack that does not load is the thing its author most needs to hear
    about, and a dict comprehension that skips it is how someone spends an
    afternoon wondering why their world never appears."""
    good = tmp_path / "good"
    good.mkdir()
    (good / load.MANIFEST).write_text(
        json.dumps({"schema": 1, "id": "g", "name": "G", "license": {"id": "CC0-1.0"}})
    )
    (tmp_path / "bad").mkdir()

    found = load.discover(tmp_path)
    assert set(found) == {"good", "bad"}
    assert found["good"].ok and not found["bad"].ok


def test_discovering_a_missing_root_is_empty_rather_than_an_error(tmp_path):
    assert load.discover(tmp_path / "nowhere") == {}
