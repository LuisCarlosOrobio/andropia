"""Prompt assembly.

Two things are worth testing here and they are both structural. The prompt and
the grammar must agree about what a being can do, because a mismatch either way
is silent. And the stable prefix must stay stable, because it is the whole
reason the messages are ordered the way they are.
"""

from __future__ import annotations

import re

from andropia.beings import perception as per
from andropia.beings import prompt as pr
from andropia.beings import protocol
from andropia.sim.types import Entity, Landmark, Memory, Utterance, Vec3, World
from andropia.vocab import EMOTIONS, GESTURES


def a_world(**over):
    me = Entity(id="ava", persona="You are curious.", **over)
    return World(
        entities={"ava": me, "bob": Entity(id="bob", pos=Vec3(0.0, 0.0, 2.0))},
        landmarks={"pond": Landmark("pond", Vec3(0.0, 0.0, 6.0), "the pond")},
    )


def messages_for(world, eid="ava"):
    return pr.messages(world.entities[eid], per.observe(world, eid))


# -- the prompt and the grammar must agree ---------------------------------


def test_every_tag_the_prompt_teaches_is_one_the_grammar_accepts():
    """The loop-closing test.

    A tag in the prompt that the grammar rejects is an instruction to fail. A
    tag in the grammar the prompt never mentions is a capability no being
    discovers. Both are invisible without this.
    """
    taught = set(re.findall(r"\[([a-z_]+(?::[a-z_<>]+)?)\]", pr.RULES))
    assert taught, "found no tags in the prompt at all"

    for tag in taught:
        # Placeholders stand for a value the being fills in; substitute a real
        # one so the grammar has something to chew on.
        concrete = (
            tag.replace("<place>", "pond").replace("<name>", "bob")
            if "<" in tag
            else tag
        )
        intents = protocol.to_intents(protocol.parse(f"[{concrete}]"), "ava")
        assert intents, f"the prompt teaches [{tag}] but the grammar ignores it"


def test_every_emotion_and_gesture_appears_in_the_prompt():
    # Generated from the vocabulary module, so this holds by construction —
    # which is the point. It fails the moment someone hand-writes the list.
    for word in EMOTIONS:
        assert f"[{word}]" in pr.RULES, word
    for word in GESTURES:
        assert f"[motion:{word}]" in pr.RULES, word


def test_the_prompt_names_no_tag_the_vocabulary_lacks():
    motions = set(re.findall(r"\[motion:([a-z_]+)\]", pr.RULES))
    assert motions <= set(GESTURES)

    bare = set(re.findall(r"\[([a-z_]+)\]", pr.RULES))
    assert bare <= set(EMOTIONS)


# -- cache stability -------------------------------------------------------


def test_the_stable_prefix_does_not_change_when_the_situation_does():
    """The reason the messages are ordered stable-to-volatile.

    A being thinks several times a minute for as long as the world runs. If
    anything before the observation changes per turn, the provider's cache is
    invalidated every time and the cost of a long run multiplies by the length
    of the prompt.
    """
    still = messages_for(a_world())
    moved = messages_for(a_world(pos=Vec3(3.0, 0.0, -4.0)))
    turned = messages_for(a_world(facing=Vec3(1.0, 0.0, 0.0)))

    for other in (moved, turned):
        assert other[:-1] == still[:-1]
        assert other[-1] != still[-1]  # and the volatile part really did move


def test_the_prompt_is_ordered_place_then_person_then_situation():
    msgs = messages_for(a_world())
    assert msgs[0].content == pr.RULES
    assert msgs[1].content.startswith("Where you are:")
    assert "Your name is ava" in msgs[2].content
    assert msgs[-1].role == "user"


def test_an_empty_setting_is_stated_rather_than_skipped():
    """A being told nothing about the place invents one.

    Three of them once spent two minutes reporting the falling water level of a
    pond that is a point on a flat plane. "There is nothing here" is a fact
    about the world, and beings should have it.
    """
    where = messages_for(a_world())[1].content
    assert "Nothing has been built here yet" in where
    assert "Do not invent" in where


def test_a_declared_setting_replaces_the_empty_one():
    from dataclasses import replace

    world = replace(a_world(), setting="A wet green meadow under a blue sky.")
    where = messages_for(world)[1].content
    assert "A wet green meadow" in where
    assert "Nothing has been built" not in where


def test_the_setting_extends_the_prefix_every_being_shares():
    # Identical for all of them, so it belongs before identity — otherwise each
    # being starts its own cached prefix one message earlier.
    world = a_world()
    mine = messages_for(world, "ava")
    theirs = pr.messages(world.entities["bob"], per.observe(world, "bob"))
    assert mine[:2] == theirs[:2]


def test_rules_are_identical_for_every_being():
    a = messages_for(a_world())
    b = pr.messages(
        Entity(id="bob", persona="You are blunt."),
        per.observe(a_world(), "bob"),
    )
    assert a[0] == b[0]


def test_memory_only_grows_at_the_end():
    # So the recollection message stays cacheable as a being accumulates a run.
    early = (Memory(tick=1, text="first"),)
    later = early + (Memory(tick=2, text="second"),)

    a = messages_for(a_world(memory=early))[3].content
    b = messages_for(a_world(memory=later))[3].content
    assert b.startswith(a)


# -- content ---------------------------------------------------------------


def test_persona_is_carried_into_the_prompt():
    assert "You are curious." in messages_for(a_world())[2].content


def test_a_being_with_no_persona_still_gets_a_usable_prompt():
    world = World(entities={"ava": Entity(id="ava")})
    msgs = pr.messages(world.entities["ava"], per.observe(world, "ava"))
    assert "Your name is ava" in msgs[2].content
    assert msgs[0].content == pr.RULES


def test_no_memory_means_no_recollection_message():
    assert len(messages_for(a_world())) == 4
    assert len(messages_for(a_world(memory=(Memory(tick=1, text="x"),)))) == 5


def test_recollection_is_budgeted():
    many = tuple(Memory(tick=i, text=f"thing {i}") for i in range(50))
    recalled = messages_for(a_world(memory=many))[3].content
    assert recalled.count("\n- ") == pr.RECALL_LINES
    assert "thing 49" in recalled


def test_situation_names_beings_and_places_the_being_can_refer_to():
    """Every name in the situation must be usable in a tag.

    The prompt tells a being to refer to things "by exactly the names you are
    given", so those names have to be landmark and entity ids rather than
    descriptions.
    """
    text = pr.situation(per.observe(a_world(), "ava"))
    assert "bob" in text
    assert "pond" in text


def test_situation_reports_being_alone():
    world = World(entities={"ava": Entity(id="ava")})
    assert "nobody else in sight" in pr.situation(per.observe(world, "ava"))


def test_a_being_sees_its_own_speech_attributed_to_itself():
    # "ava: hello" would invite a model to reply to itself.
    world = a_world()
    from dataclasses import replace

    world = replace(
        world, transcript=(Utterance(tick=1, speaker="ava", text="hello"),)
    )
    assert "- you: hello" in pr.situation(per.observe(world, "ava"))


def test_no_coordinates_leak_into_the_prompt():
    """The whole point of qualitative perception.

    The previous version of this project put raw coordinates in the prompt
    every turn. Numbers with decimal points reaching the model means something
    has regressed to telemetry.
    """
    world = a_world(pos=Vec3(4.237, 0.0, -1.881))
    for message in messages_for(world):
        assert not re.search(r"-?\d+\.\d+", message.content), message.content


def test_the_prompt_says_that_announcing_a_move_is_not_moving():
    """A live run had one being announce a destination three times and never
    take a step, while another kept catching it: "two announcements, zero
    steps." Saying "I'll be there" is not the same as emitting [goto:...], and
    nothing in the prompt said so.

    The others can see where it actually is, so the failure is not cosmetic —
    it makes a being wrong about its own body in front of witnesses.
    """
    lowered = pr.RULES.lower()
    assert "does not do it" in lowered
    assert "[goto:pond] moves you" in pr.RULES


def test_the_prompt_does_not_present_the_being_as_an_assistant():
    # These beings talk to each other. Framing one as an assistant with a user
    # is what produces "How can I help you today?" in a field.
    lowered = pr.RULES.lower()
    assert "assistant" in lowered  # mentioned only to deny it
    assert "you are not an assistant" in lowered
