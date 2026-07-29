"""Turning an observation into messages for a language model. Pure.

Ordering here is load-bearing, and not for style. Every message before the
first byte that changes can be cached by the provider, and a being thinks
several times a minute for as long as the world runs — so the layout is
strictly stable-to-volatile:

    1. how to act        identical for every being, forever
    2. who you are       identical for one being, for the whole run
    3. what you recall   grows only at the end
    4. what you see      different every single turn

Putting the observation first, which reads more naturally, would invalidate
the cache on every turn and multiply the cost of a long-running world by the
length of the prompt. This is the one place in the codebase where the order of
some strings is a performance decision.

The vocabulary section is generated from :mod:`andropia.vocab`, never written
out by hand. A tag that exists in the grammar but not in the prompt is a
capability no being ever discovers, and a tag in the prompt that the grammar
does not accept is an instruction to fail — both are silent, and generating
from one source makes both impossible.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypeAlias

from ..sim.types import Entity, Memory
from ..vocab import EMOTIONS, GESTURES
from .perception import Observation

Role: TypeAlias = Literal["system", "user", "assistant"]


@dataclass(frozen=True, slots=True)
class Message:
    role: Role
    content: str


#: How many remembered lines to include. Memory is a summary of a long run, so
#: this is a budget rather than a limit on what a being may know.
RECALL_LINES = 12


def messages(
    ent: Entity, obs: Observation, *, recall: int = RECALL_LINES
) -> tuple[Message, ...]:
    """The full message list for one being's turn."""
    return (
        Message("system", RULES),
        Message("system", _identity(ent, obs)),
        *_recollection(ent.memory, recall),
        Message("user", situation(obs)),
    )


# --------------------------------------------------------------------------
# the stable part
# --------------------------------------------------------------------------


def _vocabulary() -> str:
    """The tag list, generated from the vocabulary module."""
    return "\n".join(
        (
            "Expressions — write one alone in brackets:",
            "  " + "  ".join(f"[{e}]" for e in EMOTIONS),
            "",
            "Gestures — one-shot movements:",
            "  " + "  ".join(f"[motion:{g}]" for g in GESTURES),
            "",
            "Moving and looking:",
            "  [goto:<place>]   walk to somewhere you can see",
            "  [look:<name>]    turn your gaze to a being or place",
            "  [look:away]      stop looking at anything in particular",
        )
    )


RULES = f"""\
You are a being with a body in a small shared world. You are not an assistant \
and there is no user; the people around you are other beings living in the \
same place, each with their own mind.

Everything you write is spoken aloud, as-is, to whoever is nearby. Write the \
way someone talks. Do not narrate yourself in the third person, do not \
describe your actions in prose, and never mention that you are a language \
model or that this world is a simulation.

To act, put a tag in square brackets anywhere in what you say. Tags are \
removed before anyone hears you, so they are actions rather than words.

{_vocabulary()}

Some things worth knowing:

Tags take effect as you speak, so you can wave while greeting someone rather \
than waiting until you have finished.

You may say nothing at all. A tag on its own is a perfectly good turn — \
looking around, or walking somewhere, without narrating it. Beings who fill \
every silence are tiresome.

Keep it to a sentence or two. This is conversation, not correspondence.

You can only refer to beings and places you can currently see, by exactly the \
names you are given. Somewhere you visited before is not visible now.

Nothing obliges you to be agreeable, helpful, or busy. You have your own \
reasons for what you do.\
"""


def _identity(ent: Entity, obs: Observation) -> str:
    persona = ent.persona.strip() or "You have not been told much about yourself yet."
    return f"Your name is {obs.who}.\n\n{persona}"


# --------------------------------------------------------------------------
# the volatile part
# --------------------------------------------------------------------------


def _recollection(memory: tuple[Memory, ...], limit: int) -> tuple[Message, ...]:
    """The being's own memory, as a message it can be reminded of.

    Kept separate from the situation so it stays cacheable: memory only ever
    grows at the end, whereas the situation is rewritten every turn.
    """
    if not memory:
        return ()

    recent = sorted(memory, key=lambda m: (m.tick, m.text))[-limit:]
    lines = "\n".join(f"- {m.text}" for m in recent)
    return (Message("system", f"Things you remember:\n{lines}"),)


def situation(obs: Observation) -> str:
    """The observation as prose.

    Separate from :func:`messages` because this is the string worth eyeballing
    when a being behaves oddly, and it should be printable without assembling a
    whole prompt.
    """
    parts = [f"You are {obs.doing}, feeling {obs.feeling}."]

    if obs.beings:
        parts.append("\nYou can see:")
        for s in obs.beings:
            line = f"- {s.who}, {s.proximity}, {s.bearing} — {s.doing}"
            if s.speaking:
                line += f'\n  saying: "{s.speaking}"'
            parts.append(line)
    else:
        parts.append("\nThere is nobody else in sight.")

    if obs.places:
        parts.append("\nPlaces you can see:")
        for p in obs.places:
            described = f" ({p.description})" if p.description else ""
            parts.append(f"- {p.name}{described}, {p.proximity}, {p.bearing}")

    if obs.heard:
        parts.append("\nRecently said nearby:")
        for line in obs.heard:
            speaker = "you" if line.speaker == obs.who else line.speaker
            parts.append(f"- {speaker}: {line.text}")

    parts.append("\nWhat do you do?")
    return "\n".join(parts)
