"""The world pack format.

Most of these are ordinary validator tests. Two are structural and matter more
than the rest: the example pack must use every declared shape, because it is the
fixture the JavaScript side tests against, and a feature id must survive the tag
grammar, because it is also the word a being types into ``[goto:...]``.
"""

from __future__ import annotations

import json
from pathlib import Path

from andropia.beings import protocol
from andropia.worlds import schema

EXAMPLE = Path(__file__).resolve().parents[1] / "worlds" / "example" / "world.json"


def a_manifest(**over):
    """A minimal valid manifest, overridable field by field."""
    base = {
        "schema": 1,
        "id": "somewhere",
        "name": "Somewhere",
        "license": {"id": "CC0-1.0"},
    }
    return {**base, **over}


def a_feature(**over):
    base = {
        "id": "pond",
        "pos": [1.0, 0.0, 2.0],
        "shape": "disc",
        "material": "water",
        "description": "a shallow pond",
    }
    return {**base, **over}


# -- the example pack ------------------------------------------------------


def test_the_example_pack_validates():
    assert schema.validate(json.loads(EXAMPLE.read_text())).ok


def test_the_example_pack_uses_every_shape():
    """The cross-language seam.

    A shape this schema accepts and `world.js` does not implement is an
    invisible landmark and no error at all. The example pack is the fixture
    both suites read, so it has to exercise the whole vocabulary — otherwise
    the JavaScript test can pass while a shape goes undrawn.
    """
    result = schema.validate(json.loads(EXAMPLE.read_text()))
    assert result.ok
    assert {f.shape for f in result.pack.features} == set(schema.SHAPES)


def test_the_example_pack_declares_a_licence():
    result = schema.validate(json.loads(EXAMPLE.read_text()))
    assert result.ok and result.pack.license.id


# -- feature ids are also tag values ---------------------------------------


def test_a_feature_id_must_survive_the_tag_grammar():
    """A being reaches a place by writing [goto:<id>]. An id the grammar
    rejects is a place nobody can walk to, and nothing would say so."""
    bad = schema.validate(a_manifest(features=[a_feature(id="the pond")]))
    assert not bad.ok
    assert any("tag" in e.problem or "tag" in e.hint for e in bad.errors)


def test_every_valid_feature_id_round_trips_through_the_grammar():
    result = schema.validate(json.loads(EXAMPLE.read_text()))
    assert result.ok

    for feature in result.pack.features:
        intents = protocol.to_intents(protocol.parse(f"[goto:{feature.id}]"), "ava")
        assert intents, f"[goto:{feature.id}] does not parse"


def test_duplicate_feature_ids_are_rejected():
    # A being names a place by its id and has no way to disambiguate two.
    result = schema.validate(
        a_manifest(features=[a_feature(id="pond"), a_feature(id="pond")])
    )
    assert not result.ok
    assert any("more than once" in e.problem for e in result.errors)


# -- provenance is structural ----------------------------------------------


def test_a_pack_without_a_licence_is_invalid():
    """Every time provenance was optional in this project, something turned out
    to contradict its own label."""
    raw = a_manifest()
    del raw["license"]
    result = schema.validate(raw)
    assert not result.ok
    assert any(e.field == "license" for e in result.errors)


def test_a_licence_without_an_id_is_invalid():
    result = schema.validate(a_manifest(license={"url": "http://example.com"}))
    assert not result.ok
    assert any(e.field == "license.id" for e in result.errors)


# -- totality --------------------------------------------------------------


def test_every_problem_is_reported_at_once():
    """An author who fixes one field, re-runs, and meets the next has been
    failed by the validator."""
    result = schema.validate(
        {
            "schema": 99,
            "name": "",
            "license": {},
            "features": [a_feature(shape="pyramid", material="cheese")],
        }
    )
    assert not result.ok
    fields = {e.field for e in result.errors}
    assert {"schema", "id", "name", "license.id"} <= fields
    assert any("shape" in f for f in fields)
    assert any("material" in f for f in fields)


def test_an_unknown_shape_names_the_ones_that_work():
    result = schema.validate(a_manifest(features=[a_feature(shape="pyramid")]))
    assert not result.ok
    hint = next(e.hint for e in result.errors if "shape" in e.field)
    for shape in schema.SHAPES:
        assert shape in hint


def test_an_unknown_material_names_the_ones_that_work():
    result = schema.validate(a_manifest(features=[a_feature(material="cheese")]))
    assert not result.ok
    hint = next(e.hint for e in result.errors if "material" in e.field)
    assert "water" in hint


def test_a_manifest_that_is_not_an_object_fails_cleanly():
    for raw in ([], "world", None, 3):
        result = schema.validate(raw)
        assert not result.ok and len(result.errors) == 1


# -- fields ----------------------------------------------------------------


def test_defaults_stand_in_for_an_omitted_block():
    # A pack that declares only its identity is legal; the rest is the bare
    # space this project started with.
    result = schema.validate(a_manifest())
    assert result.ok
    assert result.pack.ground.grid is True
    assert result.pack.sky.fog is None
    assert result.pack.features == ()


def test_colours_must_be_hex():
    """Named colours would mean two lookup tables agreeing across two
    languages, which is the seam this format exists to remove."""
    result = schema.validate(a_manifest(ground={"colour": "green"}))
    assert not result.ok
    assert any(e.field == "ground.colour" for e in result.errors)


def test_colours_are_normalised():
    result = schema.validate(a_manifest(ground={"colour": "#AABBCC"}))
    assert result.ok and result.pack.ground.colour == "#aabbcc"


def test_fog_must_be_near_then_far():
    result = schema.validate(a_manifest(sky={"fog": [90, 30]}))
    assert not result.ok
    assert any("not before" in e.problem for e in result.errors)


def test_omitted_fog_means_none():
    assert schema.validate(a_manifest(sky={})).pack.sky.fog is None


def test_a_description_is_required_on_a_feature():
    # It is what a being is told when it looks at the place. A feature without
    # one is a name over nothing, which is the failure this format retires.
    result = schema.validate(a_manifest(features=[a_feature(description="  ")]))
    assert not result.ok
    assert any("description" in e.field for e in result.errors)


def test_a_position_must_be_three_numbers():
    for pos in ([1, 2], "over there", [1, 2, "z"], None):
        result = schema.validate(a_manifest(features=[a_feature(pos=pos)]))
        assert not result.ok, pos


def test_a_negative_radius_is_rejected():
    result = schema.validate(a_manifest(features=[a_feature(radius=-2)]))
    assert not result.ok


def test_booleans_are_not_accepted_as_numbers():
    # `True` is an int in Python, and a radius of True would validate and then
    # draw something a millimetre across.
    result = schema.validate(a_manifest(features=[a_feature(radius=True)]))
    assert not result.ok


def test_an_odd_enterable_material_warns_rather_than_fails():
    """Walking into stone is strange, not invalid — a pack may mean it, and a
    warning tells the author without refusing the world."""
    result = schema.validate(
        a_manifest(features=[a_feature(material="stone", enterable=True)])
    )
    assert result.ok
    assert any("enterable" in w for w in result.warnings)


def test_a_wrong_schema_version_is_refused():
    result = schema.validate(a_manifest(schema=2))
    assert not result.ok
    assert any(e.field == "schema" for e in result.errors)
