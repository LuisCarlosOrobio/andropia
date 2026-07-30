"""Drawn identities.

The properties that matter are determinism — a seed must reproduce a person, or
a recorded run cannot be repopulated — and distinctness, because a name is also
the handle beings use to address each other and the tag grammar cannot
disambiguate two of them.
"""

from __future__ import annotations

import pytest

from andropia.identity import (
    ATTENTION,
    DISPOSITION,
    MANNER,
    NAMES,
    WANT,
    cast,
    draw,
)
from andropia.sim import rng


def test_a_seed_reproduces_a_person():
    """Or a fork loses everyone it started with."""
    assert draw(rng.seed(42))[0] == draw(rng.seed(42))[0]


def test_different_seeds_give_different_people():
    a, _ = cast(rng.seed(1), 5)
    b, _ = cast(rng.seed(2), 5)
    assert [p.name for p in a] != [p.name for p in b]


def test_the_carry_advances_so_successive_draws_differ():
    # Threading state is the whole discipline: a caller that forgets to carry it
    # gets the same being over and over.
    first, state = draw(rng.seed(3))
    second, _ = draw(state)
    assert first != second


def test_a_cast_has_distinct_names():
    """A name is the handle beings use to address each other, and the tag
    grammar has no way to disambiguate two of them."""
    for seed in range(30):
        people, _ = cast(rng.seed(seed), 6)
        names = [p.name for p in people]
        assert len(set(names)) == len(names), names


def test_asking_for_more_people_than_there_are_names_raises():
    # Rather than looping forever looking for a name that cannot exist.
    with pytest.raises(ValueError, match="distinct names"):
        cast(rng.seed(0), len(NAMES) + 1)


def test_a_whole_cast_can_be_drawn_from_the_table():
    people, _ = cast(rng.seed(11), len(NAMES))
    assert len({p.name for p in people}) == len(NAMES)


def test_a_persona_draws_from_every_axis():
    """Independently, so the space is the product of the tables rather than the
    length of a list."""
    who, _ = draw(rng.seed(99))
    for table in (DISPOSITION, ATTENTION, MANNER, WANT):
        assert any(trait in who.persona for trait in table), table[0]


def test_no_being_is_named_after_a_language_model():
    """A being called `claude` is being asked to play a language model rather
    than a person, and it makes the model the identity instead of the person."""
    models = {"claude", "gpt", "gemini", "llama", "mistral", "qwen", "grok", "ava"}
    assert not (set(NAMES) & models)


def test_identities_are_plain_data():
    # They become `Entity.persona`, which has to survive a snapshot round trip.
    who, _ = draw(rng.seed(5))
    assert isinstance(who.name, str) and isinstance(who.persona, str)
    assert who.persona.strip() and who.name.strip()


def test_personas_describe_behaviour_rather_than_biography():
    """A persona listing hobbies produces a being that mentions hobbies. Every
    trait here is about disposition, attention, manner or want."""
    who, _ = draw(rng.seed(77))
    assert who.persona.startswith("You are") or who.persona.startswith("You ")
    assert who.persona.count(".") >= 4
