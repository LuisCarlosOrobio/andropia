"""The action protocol: how a language model's text becomes intents.

A being says what it does in the same stream it says what it says::

    [happy]Oh, you found me! [motion:wave] I was just looking at the pond.
    [goto:pond]

Inline tags rather than tool calls or JSON, for three reasons. Every
OpenAI-compatible endpoint emits text, whereas tool-call support is uneven and
differs between vLLM, llama.cpp and the hosted APIs — text is the only format
that works everywhere, which matters when the point is that users bring their
own model. A small local model or a LoRA finetune produces well-formed
bracket tags far more reliably than well-formed JSON, and a malformed tag
costs one tag while a malformed JSON object costs the whole turn. And tags
interleave with speech, so a being can wave *while* greeting rather than
finishing its sentence and then gesturing.

Two layers, kept apart on purpose:

``parse`` and ``feed`` know the grammar — brackets, names, values — and
nothing about what any tag means. ``to_intents`` knows the vocabulary and
nothing about brackets. So a new tag is a change in one function, and the
grammar can be tested exhaustively without reference to the simulation.

Everything here is pure. ``feed`` is a fold with an explicit carry, so a tag
split across two network chunks survives, and no parser object holds state
between calls.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal, TypeAlias

from ..sim.types import DoGesture, Emote, EntityId, Goto, Intent, Look, Speak
from ..vocab import EMOTIONS, GESTURES, NAVIGATION_MOTION

# --------------------------------------------------------------------------
# grammar
# --------------------------------------------------------------------------

OPEN = "["
CLOSE = "]"
SEPARATOR = ":"

#: Longest a tag may be before we conclude the bracket was literal prose.
#: Without a bound, a single stray "[" would swallow the rest of a reply into
#: the carry and the being would fall silent — a small syntax slip should cost
#: a tag, never the turn.
MAX_TAG_LENGTH = 48


@dataclass(frozen=True, slots=True)
class Text:
    """Prose. What the being is actually saying."""

    text: str
    kind: Literal["text"] = "text"


@dataclass(frozen=True, slots=True)
class Tag:
    """A well-formed tag. ``value`` is None for a bare tag like ``[happy]``."""

    name: str
    value: str | None = None
    kind: Literal["tag"] = "tag"


Event: TypeAlias = Text | Tag


def parse(source: str) -> tuple[Event, ...]:
    """Parse a complete reply into text and tags.

    For a whole string in hand. Streaming callers want :func:`feed`, which
    this is defined in terms of so the two can never disagree about the
    grammar.
    """
    events, carry = feed("", source)
    return events + finish(carry)


def feed(carry: str, chunk: str) -> tuple[tuple[Event, ...], str]:
    """Consume one chunk, returning complete events and whatever is left over.

    The carry holds a partial tag — everything from an unmatched ``[`` to the
    end of the chunk. Text before that point is emitted immediately, so a
    being's speech streams out at the rate the model produces it rather than
    waiting for the reply to finish.

    Pure, and a fold: ``feed`` over successive chunks gives exactly what
    :func:`parse` gives for their concatenation. The tests assert that at
    every possible split point.
    """
    events: list[Event] = []
    buffer = carry + chunk
    # Where the unflushed prose starts. Text accumulates rather than being
    # emitted per character, so ordinary prose costs one Text event.
    start = 0
    i = 0

    while i < len(buffer):
        if buffer[i] != OPEN:
            i += 1
            continue

        close = buffer.find(CLOSE, i)

        if close == -1:
            # Unterminated. Either the tag is still arriving, or it was never
            # a tag at all and we should stop holding the rest of the reply
            # hostage waiting for a bracket that is not coming.
            # Measured on the body, excluding the bracket, so this agrees
            # exactly with the closed-tag check below. Counting the bracket
            # here gave up one character early, which made a body of exactly
            # MAX_TAG_LENGTH a tag when parsed whole and prose when streamed.
            if len(buffer) - i - 1 > MAX_TAG_LENGTH:
                i += 1
                continue
            _flush(events, buffer[start:i])
            return tuple(events), buffer[i:]

        if close - i - 1 > MAX_TAG_LENGTH:
            # Closed, but too long to be a tag. Treat the bracket as prose and
            # keep looking; the real tag may be inside.
            i += 1
            continue

        tag = _tag(buffer[i + 1 : close])
        if tag is None:
            # Well-bracketed but malformed — "[]", "[a:b:c]", "[pause, thinking]",
            # "[look:<name>coden]". Dropped rather than spoken.
            #
            # This was the other way round at first, on the reasoning that a
            # being might legitimately write brackets and eating text silently is
            # the harder bug to notice. Two live runs settled it: every bracket a
            # model produced was a protocol artefact — a stage direction, or the
            # prompt's own placeholder syntax copied literally — and none was
            # ever speech. An avatar saying "[pause, thinking]" out loud is a
            # worse failure than losing the odd aside in brackets.
            _flush(events, buffer[start:i])
            i = close + 1
            start = i
            continue

        _flush(events, buffer[start:i])
        events.append(tag)
        i = close + 1
        start = i

    _flush(events, buffer[start:])
    return tuple(events), ""


def finish(carry: str) -> tuple[Event, ...]:
    """Close a stream, discarding an unterminated tag.

    The carry only ever holds a fragment short enough to still be a tag — a
    bracket that grows past :data:`MAX_TAG_LENGTH` has already been released as
    prose. So what is left here is a tag the model started and never closed,
    most often because the reply hit its token ceiling mid-word. Speaking
    "[goto:po" aloud is not a recovery.
    """
    return ()


def _flush(events: list[Event], text: str) -> None:
    if text:
        events.append(Text(text))


def _tag(body: str) -> Tag | None:
    """A tag's innards to a Tag, or None if it is not one."""
    if not body or body != body.strip():
        # Leading or trailing space means prose: "[ see below ]".
        return None

    name, sep, value = body.partition(SEPARATOR)
    if SEPARATOR in value:
        return None  # "[a:b:c]" is not a tag
    if not name or (sep and not value):
        return None

    name = name.lower()
    if not name.replace("_", "").isalnum():
        return None
    if sep and not value.replace("_", "").replace("-", "").isalnum():
        return None

    return Tag(name, value.lower() if sep else None)


# --------------------------------------------------------------------------
# vocabulary
# --------------------------------------------------------------------------

#: Tags that name a target rather than standing alone.
VALUED_TAGS: tuple[str, ...] = ("motion", "look", "goto")


def to_intents(events: tuple[Event, ...], eid: EntityId) -> tuple[Intent, ...]:
    """Turn parsed events into intents for one being.

    Unknown tags are dropped rather than raising. A model will emit tags from
    a stale prompt, a finetune with its own ideas, or a plain hallucination,
    and the correct response to ``[eyeroll]`` on a rig with six expressions is
    to ignore it — not to discard the sentence it was attached to.

    Prose is collected into a single :class:`Speak`. A being's turn is one
    utterance however many tags interrupt it, because the transcript others
    read should be what was said, not fragments split on gesture boundaries.
    """
    said: list[str] = []
    intents: list[Intent] = []

    for event in events:
        if event.kind == "text":
            said.append(event.text)
            continue

        intent = _intent(event, eid)
        if intent is not None:
            intents.append(intent)

    text = _spoken("".join(said))
    # Speech first: a being greets and then waves, and the transcript should
    # not depend on where in the sentence the model happened to put the tag.
    return ((Speak(entity=eid, text=text),) if text else ()) + tuple(intents)


#: Emphasis markers to shed from the edges of an utterance.
_EMPHASIS = "*_ \t\r\n"

#: Paired emphasis around a run of text: ``*to*``, ``**a whole forest**``.
#:
#: The opening marker must be followed by a non-space, which is what keeps
#: arithmetic intact — in ``5 * 3`` the asterisk has a space after it, so this
#: does not match and no digits are eaten.
_WRAPPED = re.compile(r"\*+([^*\s][^*]*?)\*+")


def _spoken(text: str) -> str:
    """What a being actually says, once formatting is discounted.

    Models emit Markdown without being asked, and nothing downstream reads it —
    every line here is spoken aloud by a body. Two live failures, in order of
    discovery:

    ``**[look:pond]``. The tag parsed correctly and the asterisks became the
    utterance, so a being stood by a pond and said "**" into a speech bubble.
    Edge markers are stripped, and an utterance left with no letters or digits
    is silence rather than punctuation.

    ``You're going *to* the rock?``. Emphasis mid-sentence, which the edge strip
    does not reach, so an avatar said the asterisks out loud. Paired markers now
    come off too — the markers only, never the words between them, because
    losing a word is a worse failure than showing a stray mark.
    """
    trimmed = _WRAPPED.sub(r"\1", text).strip(_EMPHASIS)
    return trimmed if any(ch.isalnum() for ch in trimmed) else ""


def _intent(tag: Tag, eid: EntityId) -> Intent | None:
    if tag.value is None:
        # A bare tag is an emotion. Nothing else in the vocabulary is
        # meaningful without a target, which keeps the grammar predictable:
        # brackets with a colon do something, brackets without one are a face.
        return Emote(entity=eid, emotion=tag.name) if tag.name in EMOTIONS else None

    if tag.name == "motion":
        if tag.value in GESTURES:
            return DoGesture(entity=eid, motion=tag.value)
        # `[motion:goto]` with no destination cannot be resolved here, and
        # guessing one would send the being somewhere it never asked for.
        return None

    if tag.name == NAVIGATION_MOTION:
        return Goto(entity=eid, target=tag.value)

    if tag.name == "look":
        return Look(entity=eid, at=None if tag.value == "away" else tag.value)

    return None
