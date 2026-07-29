"""The load-bearing test.

If this fails, something in the simulation has started reading the wall
clock, consulting global random state, or depending on dict iteration order.
All three are silent failures that erode replay until it simply does not
work and nobody can say when it broke.

It is worth keeping this test fast enough to run on every commit.
"""

from __future__ import annotations

from andropia.sim import (
    DoGesture,
    Emote,
    Entity,
    Goto,
    Landmark,
    Speak,
    Vec3,
    World,
    rng,
    run,
    snapshot,
    step,
)

TICKS = 10_000
EMOTIONS = ("neutral", "happy", "angry", "sad", "relaxed", "surprised")
MOTIONS = ("wave", "nod", "shake", "shrug", "think", "point", "cheer")
PLACES = ("tree", "pond", "rock", "gate")


def build_world(seed: int = 20231117) -> World:
    """A small populated world. Deterministic in its own right."""
    return World(
        rng=rng.seed(seed),
        entities={
            "ava": Entity(id="ava", pos=Vec3(0.0, 0.0, 0.0), avatar_pack="ava", rng=1),
            "mistral": Entity(id="mistral", pos=Vec3(3.0, 0.0, 1.0), avatar_pack="robot", rng=2),
            "claude": Entity(id="claude", pos=Vec3(-2.0, 0.0, 4.0), avatar_pack="robot", rng=3),
        },
        landmarks={
            "tree": Landmark("tree", Vec3(12.0, 0.0, -4.0), "the old tree"),
            "pond": Landmark("pond", Vec3(-8.0, 0.0, 3.0), "the pond"),
            "rock": Landmark("rock", Vec3(5.0, 0.0, 9.0), "a mossy rock"),
            "gate": Landmark("gate", Vec3(-6.0, 0.0, -7.0), "the gate"),
        },
    )


def build_script(n_ticks: int, seed: int = 42) -> list[tuple]:
    """A pseudo-random but fully reproducible stream of intents.

    Stands in for what agents would propose. Generated from the project's own
    threaded PRNG rather than ``random``, so the script itself is stable.
    """
    state = rng.seed(seed)
    people = ("ava", "mistral", "claude")
    script: list[tuple] = []

    for tick in range(n_ticks):
        batch: list = []
        # Roughly one intent every eight ticks.
        roll, state = rng.next_below(state, 8)
        if roll == 0:
            who_i, state = rng.next_below(state, len(people))
            kind, state = rng.next_below(state, 4)
            who = people[who_i]

            if kind == 0:
                place_i, state = rng.next_below(state, len(PLACES))
                batch.append(Goto(entity=who, target=PLACES[place_i]))
            elif kind == 1:
                m_i, state = rng.next_below(state, len(MOTIONS))
                batch.append(DoGesture(entity=who, motion=MOTIONS[m_i]))
            elif kind == 2:
                e_i, state = rng.next_below(state, len(EMOTIONS))
                batch.append(Emote(entity=who, emotion=EMOTIONS[e_i]))
            else:
                batch.append(Speak(entity=who, text=f"tick {tick} speaking"))

        script.append(tuple(batch))

    return script


def test_same_seed_same_run():
    """Two independent runs of the same inputs agree byte for byte."""
    script = build_script(TICKS)

    a = run(build_world(), script)
    b = run(build_world(), script)

    assert snapshot.dump(a) == snapshot.dump(b)
    assert a.tick == TICKS


def test_different_seed_diverges():
    """A different script produces a different world.

    Guards against the opposite failure: a simulation that is 'deterministic'
    because nothing it does depends on its inputs at all.
    """
    a = run(build_world(), build_script(500, seed=1))
    b = run(build_world(), build_script(500, seed=2))

    assert snapshot.dump(a) != snapshot.dump(b)


def test_snapshot_resume_matches_uninterrupted():
    """Forking mid-run continues into a bit-identical future.

    This is the property the whole sandbox rests on: pause at an interesting
    moment, save, come back later, and carry on as if nothing happened.
    """
    script = build_script(TICKS)
    half = TICKS // 2

    straight_through = run(build_world(), script)

    paused = run(build_world(), script[:half])
    revived = snapshot.load(snapshot.dump(paused))
    resumed = run(revived, script[half:])

    assert snapshot.dump(resumed) == snapshot.dump(straight_through)


def test_snapshot_round_trip_is_exact():
    world = run(build_world(), build_script(1_000))
    restored = snapshot.load(snapshot.dump(world))

    assert restored == world
    assert snapshot.dump(restored) == snapshot.dump(world)


def test_step_does_not_mutate_input():
    """``step`` builds a new world; it never edits the one it was handed.

    Enforced by test rather than by the type system, because ``World.entities``
    is a plain dict. If this fails, purity has been lost and every property
    above is void.
    """
    world = build_world()
    before = snapshot.dump(world)
    before_entities = world.entities

    step(world, (Goto(entity="ava", target="pond"), Emote(entity="ava", emotion="happy")))

    assert snapshot.dump(world) == before
    assert world.entities is before_entities
    assert world.tick == 0


def test_tick_advances_exactly_once():
    world = build_world()
    for expected in range(1, 51):
        world = step(world)
        assert world.tick == expected


def test_no_wall_clock_dependency():
    """The same inputs produce the same output regardless of when they run.

    A crude but effective check: interleaving a real delay between two runs
    changes nothing, because nothing in the simulation can observe time
    passing except through ``dt``.
    """
    import time

    script = build_script(200)
    a = run(build_world(), script)
    time.sleep(0.05)
    b = run(build_world(), script)

    assert snapshot.dump(a) == snapshot.dump(b)
