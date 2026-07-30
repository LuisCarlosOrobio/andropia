"""The action protocol.

The grammar is a public contract — prompts and finetune datasets are written
against it — so it is tested exhaustively rather than by example. The property
that matters most is that streaming and non-streaming agree at every possible
chunk boundary: a tag split across two network packets must not become prose,
and prose must not become a tag.
"""

from __future__ import annotations

from andropia.beings import protocol as p
from andropia.sim.types import DoGesture, Emote, Goto, Look, Speak


def texts(events):
    return "".join(e.text for e in events if e.kind == "text")


def tags(events):
    return [(e.name, e.value) for e in events if e.kind == "tag"]


# -- grammar ---------------------------------------------------------------


def test_bare_tag():
    assert tags(p.parse("[happy]")) == [("happy", None)]


def test_valued_tag():
    assert tags(p.parse("[motion:wave]")) == [("motion", "wave")]


def test_prose_survives_untouched():
    assert texts(p.parse("Hello there.")) == "Hello there."


def test_tags_are_removed_from_prose():
    events = p.parse("[happy]Oh! [motion:wave] Hello.")
    assert texts(events) == "Oh!  Hello."
    assert tags(events) == [("happy", None), ("motion", "wave")]


def test_tag_names_and_values_are_lowercased():
    # Models vary on capitalisation and it should never be the reason a
    # gesture silently fails.
    assert tags(p.parse("[MOTION:Wave]")) == [("motion", "wave")]


def test_underscores_are_allowed():
    assert tags(p.parse("[motion:idle_variant]")) == [("motion", "idle_variant")]


def test_hyphens_are_allowed_in_values():
    # Landmark ids are author-chosen and hyphens are ordinary in them.
    assert tags(p.parse("[goto:old-tree]")) == [("goto", "old-tree")]


def test_malformed_brackets_are_dropped_rather_than_spoken():
    """This was the other way round at first.

    The reasoning was that a being might legitimately write brackets, and
    silently eating text is the harder bug to notice. Two live runs settled it:
    every bracket a model produced was a protocol artefact, and none was ever
    speech. An avatar saying "[pause, thinking]" out loud is the worse failure.
    """
    for source in ("[]", "[a:b:c]", "[ spaced ]", "[:value]", "[name:]"):
        assert tags(p.parse(source)) == [], source
        assert texts(p.parse(source)) == "", source


def test_the_two_leaks_that_actually_happened():
    # A stage direction, and the prompt's own placeholder syntax copied back.
    assert texts(p.parse("[pause, thinking]")) == ""
    assert texts(p.parse("[look:<name>coden]")) == ""


def test_the_sentence_around_a_dropped_bracket_survives():
    # Only the fragment goes. Losing the aside is the accepted cost; losing the
    # sentence would not be.
    assert texts(p.parse("I found it [the rock] over there")) == "I found it  over there"


def test_an_unterminated_tag_is_discarded_at_the_end_of_a_stream():
    """The carry only ever holds a fragment short enough to still be a tag, so
    what is left at the end is a tag the model started and never closed —
    usually because the reply hit its token ceiling. Saying "[goto:po" aloud is
    not a recovery."""
    assert texts(p.parse("truncated [goto:po")) == "truncated "


def test_a_stray_bracket_does_not_swallow_the_reply():
    """The bound exists so one syntax slip costs a tag, never the turn.

    A bracket that grows past the limit is released as prose rather than
    dropped, precisely because at that length it is no longer a plausible tag —
    dropping it would eat a whole sentence.
    """
    long_tail = "x" * (p.MAX_TAG_LENGTH * 3)
    assert texts(p.parse(f"[{long_tail}")) == f"[{long_tail}"


def test_a_real_tag_after_a_stray_bracket_still_parses():
    long_tail = "y" * (p.MAX_TAG_LENGTH * 2)
    events = p.parse(f"[{long_tail} [happy] done")
    assert tags(events) == [("happy", None)]


def test_overlong_closed_bracket_is_prose():
    body = "z" * (p.MAX_TAG_LENGTH + 1)
    assert tags(p.parse(f"[{body}]")) == []


def test_prose_is_not_fragmented():
    # One Text event per run of prose, not one per character.
    events = p.parse("a longer sentence with no tags in it at all")
    assert len([e for e in events if e.kind == "text"]) == 1


# -- streaming -------------------------------------------------------------

STREAMS = (
    "[happy]Oh, you found me! [motion:wave] I was looking at the pond.[goto:pond]",
    "no tags here at all",
    "[happy]",
    "trailing bracket [",
    "[motion:wave][motion:nod][sad]",
    "brackets [] and [a:b:c] in prose",
    "unicode: héllo — [happy] ça va",
    # The carry interacting with the length bound: the bracket looks like a
    # pending tag until it grows past the limit, and it grows across chunks.
    "[" + "x" * (p.MAX_TAG_LENGTH * 2) + " then [happy] a real one",
    # A tag whose body straddles the limit exactly.
    "[" + "y" * p.MAX_TAG_LENGTH + "] and [motion:nod]",
    # The two malformed brackets a live model actually produced. Dropping has
    # to fold identically to parsing whole, or a chunk boundary inside one
    # changes whether it is spoken.
    "Right then. [pause, thinking] So the moss —",
    "[look:<name>coden] You said the tree, then the pond.",
)


def test_streaming_matches_whole_at_every_split():
    """The fold property. This is the test that justifies the carry.

    A model streams in chunks nobody chooses, so the parser has to be correct
    at every boundary rather than at the ones a test author thought of.
    """
    for source in STREAMS:
        expected = p.parse(source)
        for cut in range(len(source) + 1):
            events, carry = p.feed("", source[:cut])
            more, carry2 = p.feed(carry, source[cut:])
            got = events + more + p.finish(carry2)

            assert texts(got) == texts(expected), (source, cut)
            assert tags(got) == tags(expected), (source, cut)


def test_streaming_matches_whole_for_single_character_chunks():
    """The worst case: every character its own packet."""
    for source in STREAMS:
        carry = ""
        got: tuple[p.Event, ...] = ()
        for ch in source:
            events, carry = p.feed(carry, ch)
            got += events
        got += p.finish(carry)

        assert texts(got) == texts(p.parse(source)), source
        assert tags(got) == tags(p.parse(source)), source


def test_prose_streams_before_a_pending_tag_completes():
    # A being's speech should appear at the rate the model produces it, not
    # wait on a bracket that is still arriving.
    events, carry = p.feed("", "Hello there [moti")
    assert texts(events) == "Hello there "
    assert carry == "[moti"


def test_carry_holds_only_the_partial_tag():
    _, carry = p.feed("", "spoken words [goto:po")
    assert carry == "[goto:po"


# -- vocabulary ------------------------------------------------------------


def test_speech_becomes_one_utterance():
    intents = p.to_intents(p.parse("[happy]Hello [motion:wave] there."), "ava")
    speaks = [i for i in intents if isinstance(i, Speak)]
    assert len(speaks) == 1
    assert speaks[0].text == "Hello  there."


def test_speech_comes_first_regardless_of_tag_position():
    # Where the model put the tag should not reorder the transcript.
    early = p.to_intents(p.parse("[motion:wave]Hi"), "ava")
    late = p.to_intents(p.parse("Hi[motion:wave]"), "ava")
    assert isinstance(early[0], Speak) and isinstance(late[0], Speak)
    assert [type(i) for i in early] == [type(i) for i in late]


def test_silence_produces_no_speak():
    intents = p.to_intents(p.parse("[motion:nod]"), "ava")
    assert not any(isinstance(i, Speak) for i in intents)


def test_whitespace_only_reply_produces_no_speak():
    assert p.to_intents(p.parse("   \n  "), "ava") == ()


def test_emotions_map_to_emote():
    intents = p.to_intents(p.parse("[surprised]"), "ava")
    assert intents == (Emote(entity="ava", emotion="surprised"),)


def test_gestures_map_to_do_gesture():
    intents = p.to_intents(p.parse("[motion:shrug]"), "ava")
    assert intents == (DoGesture(entity="ava", motion="shrug"),)


def test_goto_maps_to_navigation():
    intents = p.to_intents(p.parse("[goto:pond]"), "ava")
    assert intents == (Goto(entity="ava", target="pond"),)


def test_look_maps_to_gaze():
    assert p.to_intents(p.parse("[look:mistral]"), "ava") == (
        Look(entity="ava", at="mistral"),
    )


def test_look_away_releases_gaze():
    # The one value that means "nothing", so a being can stop staring.
    assert p.to_intents(p.parse("[look:away]"), "ava") == (Look(entity="ava", at=None),)


def test_unknown_tags_are_ignored_not_fatal():
    # A finetune with its own ideas must degrade, not break. The sentence
    # survives; only the tag is lost.
    intents = p.to_intents(p.parse("[eyeroll]Fine.[motion:backflip]"), "ava")
    assert intents == (Speak(entity="ava", text="Fine."),)


def test_motion_goto_without_a_destination_is_ignored():
    # Resolvable only with a target, and guessing one would send a being
    # somewhere it never asked to go.
    assert p.to_intents(p.parse("[motion:goto]"), "ava") == ()


def test_markdown_emphasis_is_not_spoken_aloud():
    """A live run produced `**[look:pond]`.

    The tag parsed correctly and the two asterisks became an utterance — a being
    stood by a pond and said "**", which the renderer put in a speech bubble.
    Models emit Markdown without being asked, and nothing here reads emphasis.
    """
    from andropia.sim.types import Look

    assert p.to_intents(p.parse("**[look:pond]"), "ava") == (
        Look(entity="ava", at="pond"),
    )
    assert p.to_intents(p.parse("**[relaxed]**"), "ava") == (
        Emote(entity="ava", emotion="relaxed"),
    )


def test_emphasis_around_real_speech_is_stripped_not_the_speech():
    intents = p.to_intents(p.parse("**Hello there.**"), "ava")
    assert intents == (Speak(entity="ava", text="Hello there."),)


def test_an_utterance_with_no_words_is_silence():
    # Punctuation and formatting are not speech; a bubble containing "..." or
    # "**" is a bug wearing a costume.
    for noise in ("**", "...", "  *  ", "—", "* *"):
        assert p.to_intents(p.parse(noise), "ava") == (), noise


def test_emphasis_inside_a_sentence_is_stripped_too():
    """The second half of the same bug, found in a later live run.

    An avatar said "You're going *to* the rock?" — asterisks and all — because
    the edge strip does not reach into a sentence. The markers come off; the
    words between them never do.
    """
    for source, spoken in (
        ("You're going *to* the rock?", "You're going to the rock?"),
        ("somewhere to *go*.", "somewhere to go."),
        ("**bold** and *italic*", "bold and italic"),
    ):
        assert p.to_intents(p.parse(source), "ava")[0].text == spoken, source


def test_arithmetic_is_not_mistaken_for_emphasis():
    # An opening marker must be followed by a non-space, which is what keeps
    # "5 * 3" intact. Eating a digit would be a far worse failure than showing
    # a stray asterisk.
    for source in ("It costs 5 * 3 coins.", "a * b * c"):
        assert p.to_intents(p.parse(source), "ava")[0].text == source, source


def test_every_vocabulary_word_round_trips():
    """No word in the public vocabulary may be unreachable through the
    grammar. This is what stops a tag being documented but dead."""
    from andropia.vocab import EMOTIONS, GESTURES

    for emotion in EMOTIONS:
        assert p.to_intents(p.parse(f"[{emotion}]"), "ava") == (
            Emote(entity="ava", emotion=emotion),
        ), emotion

    for gesture in GESTURES:
        assert p.to_intents(p.parse(f"[motion:{gesture}]"), "ava") == (
            DoGesture(entity="ava", motion=gesture),
        ), gesture


def test_intents_name_the_being_they_came_from():
    # A being may not act on another's behalf; the entity is supplied by the
    # runner, never parsed out of model output.
    for intent in p.to_intents(p.parse("[happy]hi[motion:wave]"), "mistral"):
        assert intent.entity == "mistral"
