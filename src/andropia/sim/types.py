"""The simulation's data model.

Everything here is a frozen record. ``step`` builds a new ``World`` rather
than editing the one it was given, which is what makes snapshots, replay and
forking fall out for free instead of being features someone has to add.

Three invariants hold across this module, and the tests enforce all three:

1. **Nothing reads the wall clock.** Time enters only as ``dt`` and is
   counted only in ``World.tick``.
2. **Nothing reads global random state.** Randomness comes from
   ``World.rng``, threaded explicitly.
3. **World is plain data.** No sockets, no meshes, no handles — only values
   that survive a round trip through JSON. A being references its body by
   pack id; the mesh itself lives in the renderer, which the simulation
   knows nothing about.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, TypeAlias

from .vec import ZERO, Vec3

EntityId: TypeAlias = str
LandmarkId: TypeAlias = str

# The six VRM standard expression presets. Constrained to these so that any
# conformant avatar works without a mapping table.
Emotion: TypeAlias = Literal[
    "neutral", "happy", "angry", "sad", "relaxed", "surprised"
]


# --------------------------------------------------------------------------
# Actions — what a being is currently doing. Exactly one at a time.
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Idle:
    kind: Literal["idle"] = "idle"


@dataclass(frozen=True, slots=True)
class Walk:
    """Moving toward a fixed point. Resolved by the sim, not the agent.

    ``target`` is a position rather than a landmark id because the landmark
    is looked up once, when the intent is accepted. A being that has started
    walking somewhere keeps walking there even if the landmark is renamed.
    """

    target: Vec3
    kind: Literal["walk"] = "walk"


@dataclass(frozen=True, slots=True)
class Gesture:
    """A one-shot motion. ``elapsed`` counts up; the sim ends it at duration."""

    motion: str
    elapsed: float = 0.0
    duration: float = 1.5
    kind: Literal["gesture"] = "gesture"


Action: TypeAlias = Idle | Walk | Gesture


# --------------------------------------------------------------------------
# Beings
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Speech:
    """Something a being is saying.

    ``word_timings`` is populated once speech synthesis reports back; until
    then it is empty and the renderer falls back to amplitude-driven visemes.
    The text is canonical state, the audio is an artifact of one viewing.
    """

    text: str
    start_tick: int
    duration_ticks: int
    word_timings: tuple[tuple[str, float], ...] = ()


@dataclass(frozen=True, slots=True)
class Memory:
    """One remembered observation.

    Memory lives inside ``World`` rather than an external store, so a replay
    reproduces what each being knew at each moment. An embedding index built
    over these is a derived cache and may be rebuilt at any time.
    """

    tick: int
    text: str
    salience: float = 1.0


@dataclass(frozen=True, slots=True)
class Entity:
    id: EntityId
    pos: Vec3 = ZERO
    facing: Vec3 = Vec3(0.0, 0.0, 1.0)  # unit, horizontal
    vel: Vec3 = ZERO
    action: Action = field(default_factory=Idle)
    emotion: Emotion = "neutral"
    emotion_weight: float = 0.0
    gaze: EntityId | LandmarkId | None = None
    speech: Speech | None = None
    memory: tuple[Memory, ...] = ()
    avatar_pack: str = ""
    # Who this being is, in words, as its own prompt will describe it.
    #
    # World data rather than deployment config, for the same reason
    # ``avatar_pack`` is: the simulation never reads it, but a snapshot that
    # cannot say who its beings were is not a snapshot of the run. Forking is a
    # headline feature, and a fork that lost everyone's personality would be
    # broken. Which *model* answers for a being is a separate matter and lives
    # outside the world, along with its endpoint and key.
    persona: str = ""
    # Per-being random stream, so adding a being cannot change what the
    # others do.
    rng: int = 0

    # Movement characteristics. On the entity rather than global so beings
    # can differ.
    speed: float = 1.6  # metres per second
    turn_rate: float = 4.0  # radians per second, approximated linearly
    radius: float = 0.3  # collision capsule


@dataclass(frozen=True, slots=True)
class Landmark:
    id: LandmarkId
    pos: Vec3
    description: str = ""


@dataclass(frozen=True, slots=True)
class Utterance:
    """A line in the shared transcript, so beings can hear each other."""

    tick: int
    speaker: EntityId
    text: str


# --------------------------------------------------------------------------
# Intents — the only way anything changes
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Speak:
    entity: EntityId
    text: str
    kind: Literal["speak"] = "speak"


@dataclass(frozen=True, slots=True)
class Goto:
    entity: EntityId
    target: LandmarkId
    kind: Literal["goto"] = "goto"


@dataclass(frozen=True, slots=True)
class MoveTo:
    """Walk to a bare position.

    Distinct from :class:`Goto`, which names a landmark. Agents should
    normally use ``Goto`` — a language model reasons about "the pond", not
    about coordinates — but a human clicking the ground has a point and no
    name for it, and inventing a landmark for every click would be worse.
    """

    entity: EntityId
    pos: Vec3
    kind: Literal["moveto"] = "moveto"


@dataclass(frozen=True, slots=True)
class DoGesture:
    entity: EntityId
    motion: str
    kind: Literal["gesture"] = "gesture"


@dataclass(frozen=True, slots=True)
class Emote:
    entity: EntityId
    emotion: Emotion
    kind: Literal["emote"] = "emote"


@dataclass(frozen=True, slots=True)
class Look:
    entity: EntityId
    at: EntityId | LandmarkId | None
    kind: Literal["look"] = "look"


@dataclass(frozen=True, slots=True)
class Stop:
    entity: EntityId
    kind: Literal["stop"] = "stop"


@dataclass(frozen=True, slots=True)
class Remember:
    """Commit something to one being's memory.

    An intent rather than a side effect, so it lands in the intent log and a
    replay reproduces not just what beings did but what they knew when they did
    it. That is the whole reason ``Memory`` lives inside ``World``.

    Deliberately chosen rather than automatic. Recording every utterance within
    earshot would fill memory with a transcript the being can already see, and
    an agent that decides what was worth noticing is both cheaper and more
    interesting than one issued a firehose.
    """

    entity: EntityId
    text: str
    salience: float = 1.0
    kind: Literal["remember"] = "remember"


Intent: TypeAlias = Speak | Goto | MoveTo | DoGesture | Emote | Look | Stop | Remember


# --------------------------------------------------------------------------
# The world
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class World:
    """A complete, serialisable snapshot of the simulation.

    ``entities`` is a plain ``dict`` because Python has no immutable mapping
    in the standard library and adding a dependency for one is not worth it
    at this scale. The invariant — ``step`` never mutates the dict it was
    given, it builds a new one — is enforced by ``test_step_does_not_mutate``
    rather than by the type system. If that test ever fails, purity has been
    lost somewhere.
    """

    tick: int = 0
    rng: int = 0
    entities: dict[EntityId, Entity] = field(default_factory=dict)
    landmarks: dict[LandmarkId, Landmark] = field(default_factory=dict)
    transcript: tuple[Utterance, ...] = ()

    #: What kind of place this is, in words, as a being standing in it would
    #: describe it.
    #:
    #: The simulation never reads this — like ``Entity.avatar_pack``, it is
    #: plain data another layer needs. It exists because without it beings are
    #: told the *names* of things and nothing about the *place*, and a language
    #: model handed a vacuum fills it: three of them once spent two minutes
    #: reporting the water level of a pond that is a point on a plane.
    #:
    #: This must be derived from whatever the renderer actually draws, from one
    #: declaration, for the same reason an avatar pack declares its own rig:
    #: two sources of truth about one world will disagree, and the disagreement
    #: surfaces as beings describing scenery that is not there. A world pack
    #: will own both halves. Until then an author writes it, and writing it
    #: honestly — including "there is nothing here" — is the whole point.
    setting: str = ""

    # Seconds per tick. Fixed: the renderer interpolates between ticks, and
    # nothing in the simulation may consult a clock to discover it.
    dt: float = 0.05  # 20 Hz


def entity(world: World, eid: EntityId) -> Entity | None:
    """Look up a being. Returns ``None`` rather than raising — an intent may
    name a being that has since been removed, and that is ordinary."""
    return world.entities.get(eid)


def with_entity(world: World, ent: Entity) -> World:
    """Return a world in which ``ent`` replaces its previous version."""
    entities = dict(world.entities)
    entities[ent.id] = ent
    return replace_world(world, entities=entities)


def replace_world(world: World, **changes) -> World:
    """``dataclasses.replace`` for ``World``.

    Wrapped so the import stays in one place and call sites read as intent
    rather than as machinery.
    """
    from dataclasses import replace

    return replace(world, **changes)
