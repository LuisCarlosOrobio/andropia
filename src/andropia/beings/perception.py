"""What one being can see. Pure.

The previous version of this project put raw coordinates into the system
prompt every turn — ``you are at (4.2, 0, -1.8), the pond is at (-8, 0, 3)``.
It worked, and it was the wrong shape for three reasons. It spends tokens on
precision no model uses, since nothing downstream needs six significant
figures to decide whether to walk over. It is allocentric, so the model has to
do trigonometry before it can act, and small models do that badly. And it
describes the whole world rather than what a being could actually perceive,
which quietly makes every being omniscient.

So perception here is **egocentric and qualitative**: distances in words,
directions relative to where the being is facing, and only things within
range. That is both cheaper and more truthful, and it makes the prompt read
like experience rather than telemetry.

Coordinates are not withheld out of purity — a being needs no coordinate to
say "walk to the pond", because :class:`Goto` names a landmark and the
simulation resolves it. The names in an observation are exactly the names the
tag grammar accepts, so anything a being can see, it can refer to.

Everything is derived from ``World``. Nothing is cached, because a cache is
another thing that can disagree with the world, and this is cheap.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..sim import vec
from ..sim.types import EntityId, Utterance, World

#: How far a being notices anything at all, in metres. Beyond this the world
#: is not described — which is what stops every being being omniscient.
SIGHT_RANGE = 25.0

#: Within this, another being is close enough to talk to comfortably.
CONVERSATION_RANGE = 4.0

#: Lines of shared transcript a being is given. Recent speech is the strongest
#: driver of what to do next, and older lines belong in memory instead.
TRANSCRIPT_LINES = 8


@dataclass(frozen=True, slots=True)
class Sighting:
    """Another being, as seen from somewhere."""

    who: EntityId
    distance: float
    bearing: str
    proximity: str
    doing: str
    speaking: str | None = None


@dataclass(frozen=True, slots=True)
class Place:
    """A landmark, as seen from somewhere."""

    name: str
    distance: float
    bearing: str
    proximity: str
    description: str = ""


@dataclass(frozen=True, slots=True)
class Observation:
    """Everything one being perceives at one tick.

    Structured rather than pre-rendered prose, so the same observation can
    become a prompt, a debug panel, or an assertion in a test without three
    implementations drifting apart.
    """

    who: EntityId
    tick: int
    doing: str
    feeling: str
    beings: tuple[Sighting, ...] = ()
    places: tuple[Place, ...] = ()
    heard: tuple[Utterance, ...] = ()
    alone: bool = True


def observe(world: World, eid: EntityId) -> Observation | None:
    """What ``eid`` can perceive right now, or None if it is not in the world."""
    self_ = world.entities.get(eid)
    if self_ is None:
        return None

    beings = tuple(
        sighting
        for other in _sorted(world.entities.values())
        if other.id != eid
        for sighting in (_see_being(self_, other),)
        if sighting is not None
    )

    places = tuple(
        place
        for mark in sorted(world.landmarks.values(), key=lambda m: m.id)
        for place in (_see_place(self_, mark),)
        if place is not None
    )

    return Observation(
        who=eid,
        tick=world.tick,
        doing=_doing(self_),
        feeling=_feeling(self_),
        beings=beings,
        places=places,
        heard=_heard(world, self_),
        alone=not any(s.proximity != "far away" for s in beings),
    )


# --------------------------------------------------------------------------
# internals
# --------------------------------------------------------------------------


def _sorted(entities):
    """Iterate beings by id, never by dict order.

    The same discipline as ``resolve_overlaps``: insertion order differs
    between a live run and one restored from a snapshot, and a prompt whose
    clauses reorder is a prompt whose cache misses.
    """
    return sorted(entities, key=lambda e: e.id)


def _see_being(self_, other) -> Sighting | None:
    offset = vec.flatten_y(vec.sub(other.pos, self_.pos))
    distance = vec.length(offset)
    if distance > SIGHT_RANGE:
        return None

    return Sighting(
        who=other.id,
        distance=distance,
        bearing=_bearing(self_.facing, offset, distance),
        proximity=_proximity(distance),
        doing=_doing(other),
        # What another being is saying. Its expression is visible too, but its
        # emotion is not reported: a being can see a face, not read a mind.
        speaking=other.speech.text if other.speech else None,
    )


def _see_place(self_, mark) -> Place | None:
    offset = vec.flatten_y(vec.sub(mark.pos, self_.pos))
    distance = vec.length(offset)
    if distance > SIGHT_RANGE:
        return None

    return Place(
        name=mark.id,
        distance=distance,
        bearing=_bearing(self_.facing, offset, distance),
        proximity=_proximity(distance),
        description=mark.description,
    )


def _proximity(distance: float) -> str:
    if distance < 1.5:
        return "right next to you"
    if distance < CONVERSATION_RANGE:
        return "close by"
    if distance < 12.0:
        return "a little way off"
    return "far away"


def _bearing(facing, offset, distance: float) -> str:
    """Where something is, relative to the way the being is facing.

    Egocentric on purpose: "behind you" is directly actionable, whereas
    "at (−8, 0, 3)" needs the model to work out which way it is pointing
    first, and that is exactly the arithmetic language models are worst at.

    Uses a dot and a cross product, so no trigonometry and no ``atan2``.
    """
    if distance < 1e-6:
        return "right where you are"

    direction = vec.scale(offset, 1.0 / distance)
    ahead = vec.dot(facing, direction)

    # The Y component of facing × direction, which is positive when the target
    # is to the being's left. Worth deriving rather than guessing, because a
    # flipped sign here is invisible in code review and shows up only as
    # beings consistently turning the wrong way.
    #
    # In a right-handed frame with Y up, right = forward × up. Check it against
    # a standard camera, which looks down −Z with +Y up and +X to the right:
    # (0,0,−1) × (0,1,0) = (1,0,0). So for a being facing +Z, right is −X and
    # left is +X. And for facing = +Z, direction = +X, this expression gives
    # +1 — positive for left, as claimed.
    side = facing.z * direction.x - facing.x * direction.z

    if ahead > 0.85:
        return "straight ahead"
    if ahead < -0.7:
        return "behind you"
    if ahead > 0.3:
        return "ahead and to your left" if side > 0 else "ahead and to your right"
    return "to your left" if side > 0 else "to your right"


def _doing(ent) -> str:
    action = ent.action
    if action.kind == "walk":
        return "walking somewhere"
    if action.kind == "gesture":
        return f"in the middle of a {action.motion}"
    return "standing still"


def _feeling(ent) -> str:
    if ent.emotion == "neutral" or ent.emotion_weight <= 0.0:
        return "nothing in particular"
    strength = "faintly" if ent.emotion_weight < 0.4 else "clearly"
    return f"{strength} {ent.emotion}"


def _heard(world: World, self_) -> tuple[Utterance, ...]:
    """Recent speech from beings close enough to have been audible.

    Filtered by where the speaker is *now* rather than where it was when it
    spoke, which is an approximation: a being that walked away after speaking
    goes unheard. Tracking positions per utterance would be exact and would
    put a coordinate in the transcript for the sake of an edge case that
    resolves itself within a second or two of walking.
    """
    audible = {
        other.id
        for other in world.entities.values()
        if other.id != self_.id
        and vec.length(vec.flatten_y(vec.sub(other.pos, self_.pos))) <= SIGHT_RANGE
    }
    audible.add(self_.id)  # a being remembers what it said

    return tuple(
        line for line in world.transcript if line.speaker in audible
    )[-TRANSCRIPT_LINES:]
