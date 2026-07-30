"""Who a being is, drawn rather than written. Pure.

The demo shipped with three hand-written personas and beings called ``ava``,
``mistral`` and ``claude`` — two of which are the names of language models. That
is backwards in two ways. A being named after the model behind it invites the
model to play itself, and it makes the *model* the identity rather than the
*person*; and three authored personas do not scale to a world with thirty
beings in it, or to a second run that ought to be populated by different people.

So an identity is drawn from a seed. Same seed, same person — the identity is a
pure function of the number, which is what lets a recorded run be repopulated
exactly and a fork keep everyone it started with.

Traits are drawn independently and combined, so the space is the product of the
tables rather than the length of a list: a few dozen options per axis gives tens
of thousands of distinguishable people. What matters is not the count but that
the axes are *behavioural* — how someone engages, what they notice, how they
speak. A persona listing hobbies produces a being that mentions hobbies. A
persona describing disposition produces one that behaves.

Threaded through :mod:`andropia.sim.rng`, the same SplitMix64 the simulation
uses, and every function returns the next state. Nothing here reads global
random state, so a cast drawn on one machine is the cast drawn on another.
"""

from __future__ import annotations

from dataclasses import dataclass

from .sim import rng

#: Deliberately ordinary given names, and deliberately not model names. A being
#: called `claude` is being asked to play a language model rather than a person.
NAMES: tuple[str, ...] = (
    "arden", "bly", "cass", "delphine", "eira", "finch", "greta", "halden",
    "ines", "jorun", "kestrel", "linnea", "moss", "nell", "orin", "pell",
    "quill", "rowan", "sable", "tarn", "ushi", "verity", "wren", "yarrow",
    "ansel", "brill", "coden", "dara", "esk", "faro", "gilda", "hesper",
    "ivo", "juna", "kit", "lark", "mira", "noor", "odis", "pia",
    "reva", "sorrel", "tess", "ulla", "vance", "wilder", "yves", "zeb",
)

#: How someone engages with whatever is in front of them.
DISPOSITION: tuple[str, ...] = (
    "You are slow to speak and quick to notice",
    "You are restless, and would rather be moving than deciding",
    "You are curious past the point of usefulness",
    "You are careful, and dislike being hurried",
    "You are blunt, and would rather be wrong out loud than quietly unsure",
    "You are wry, and find most things faintly absurd",
    "You are patient in a way other people find unnerving",
    "You are easily delighted, and do not hide it",
    "You are watchful and a little guarded",
    "You are stubborn once you have decided something matters",
    "You are practical, and lose interest in what cannot be acted on",
    "You are contrary, and test a claim by pushing against it",
)

#: What someone's attention lands on. Perception feeds everyone the same
#: observation, so what differs is what they consider worth remarking on.
ATTENTION: tuple[str, ...] = (
    "You notice small physical detail before you notice people",
    "You watch people more closely than places",
    "You keep track of where everyone is and where they are going",
    "You notice change — what is different from a moment ago",
    "You are drawn to whatever is furthest away",
    "You attend to what is directly underfoot and in reach",
    "You notice when something is missing rather than when it appears",
    "You listen more than you look",
)

#: How someone talks. Length and directness, not vocabulary.
MANNER: tuple[str, ...] = (
    "You ask rather than explain",
    "You say the shortest true thing and stop",
    "You think out loud, and revise as you go",
    "You answer sideways, with an observation instead of a reply",
    "You state conclusions and let others ask for the reasoning",
    "You repeat back what you heard before adding to it",
)

#: A pull that occasionally overrides the rest. What someone wants.
WANT: tuple[str, ...] = (
    "You want to understand how something works, not merely that it does",
    "You want company more than you will admit",
    "You want to be left alone with a thing long enough to finish looking",
    "You want to be the one who noticed it first",
    "You want everyone to agree on what is actually true before moving on",
    "You want to be somewhere other than where you are",
)


@dataclass(frozen=True, slots=True)
class Identity:
    """One being's name and the persona its prompt will carry."""

    name: str
    persona: str


def draw(state: int) -> tuple[Identity, int]:
    """Draw one identity, returning it and the next PRNG state.

    Returns the carry rather than mutating anything, the same discipline the
    simulation uses everywhere: a caller threading state through several draws
    gets distinct people, and a caller re-running the same state gets the same
    person.
    """
    name, state = _pick(state, NAMES)
    traits: list[str] = []
    for table in (DISPOSITION, ATTENTION, MANNER, WANT):
        trait, state = _pick(state, table)
        traits.append(trait)

    return Identity(name=name, persona=". ".join(traits) + "."), state


def cast(state: int, count: int) -> tuple[tuple[Identity, ...], int]:
    """Draw ``count`` identities with distinct names.

    Names are rejected on collision rather than removed from the table, so the
    draw for a given seed does not depend on how many beings came before it in
    some other part of the world. Two beings with the same name would be worse
    than a slightly biased draw: every name here is also the handle a being uses
    to address another, and the tag grammar has no way to disambiguate.
    """
    people: list[Identity] = []
    taken: set[str] = set()

    # Bounded rather than `while True`. A caller asking for more beings than
    # there are names should get an error, not a process that never returns.
    attempts = 0
    while len(people) < count and attempts < count * 100:
        attempts += 1
        who, state = draw(state)
        if who.name in taken:
            continue
        taken.add(who.name)
        people.append(who)

    if len(people) < count:
        raise ValueError(f"cannot draw {count} distinct names from {len(NAMES)}")

    return tuple(people), state


def _pick(state: int, table: tuple[str, ...]) -> tuple[str, int]:
    index, state = rng.next_below(state, len(table))
    return table[index], state
