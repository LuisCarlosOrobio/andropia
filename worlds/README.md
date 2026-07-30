# World packs

A world pack is the place beings live in. Drop a directory in here and
Andropia will find it.

```
worlds/my-world/
  world.json       the manifest — and that is all
```

There is nothing else to ship. A world pack is parametric: no meshes, no
textures, no third-party asset, and therefore nothing to have provenance.

## Why the format exists

Before it, a world was described in one place and drawn in another. The
description was a paragraph in Python; the scene was a set of constants in
`stage.js`. Nothing connected them, so a world could be *described* as a lush
meadow and *drawn* as a dark void, and no test would notice.

It showed up the way that kind of bug always does — from the inside. Three
beings spent two minutes discussing the falling water level of a pond that was
a point on a flat plane, having agreed on a glowing seam in a rock that did not
have one. None of it contradicted anything they had been told, because they had
been told almost nothing.

So: **one declaration renders and describes.** The number that colours the
ground writes the sentence about the ground. The `material` that makes water
look wet is the word a being reads when it looks at the water. Everything below
is read twice — once by `src/andropia/worlds/`, once by
`frontend/src/world.js` — and neither side holds a number the other does not.

## The manifest

```json
{
  "schema": 1,
  "id": "my-world",
  "name": "My World",
  "license": { "id": "CC0-1.0" }
}
```

That is a complete, valid pack: bare level ground, an empty dark sky, a
reference grid, and nothing in it. Beings are told exactly that, in those
words, because a being told nothing about a place will invent one.

Everything else is optional and has a default.

### Ground and sky

```json
"ground": {
  "colour": "#4a6b3a",
  "extent": 200,
  "grid": false,
  "description": "damp grass, long enough to move underfoot"
},
"sky": {
  "colour": "#9dbdd6",
  "fog": [45, 130],
  "description": "a wide pale sky going gold at the edges"
}
```

`colour` draws it, `description` describes it. That pairing is the whole idea:
they cannot drift, because changing one without the other is a visible edit to
the same object.

`grid` draws the reference lines. Honest over an unbuilt space, wrong over a
meadow — so it is declared rather than assumed. `fog` is `[near, far]` and
takes the sky's colour, so the horizon closes rather than ending in a seam.

### Light

```json
"light": {
  "key": 2.4,
  "ambient": 0.55,
  "sky_colour": "#dbe9f2",
  "ground_colour": "#48633a"
}
```

`key` is the sun. `ambient` is the light arriving from everywhere else, which
is the difference between a bright overcast afternoon and the same geometry lit
like a stage.

### Features

A feature is a landmark: something drawn, named, walkable-to, and
describable.

```json
"features": [
  {
    "id": "pond",
    "pos": [-9, 0, 4],
    "shape": "disc",
    "radius": 4.5,
    "height": 1.0,
    "colour": "#35617a",
    "material": "water",
    "enterable": true,
    "description": "a broad shallow pond, still enough to hold the sky"
  }
]
```

**`id`** is also the word a being types into `[goto:pond]`, so it must survive
the tag grammar — lowercase, no spaces, no brackets. A validator that let one
through would produce a place nobody could walk to and nothing would say so.

**`shape`** is one of four, each described by the same two numbers so there is
one mental model rather than four:

| | |
|---|---|
| `disc` | flat on the ground — water, a paved circle, a patch of anything |
| `block` | squared and solid — an altar, a slab, a crate |
| `column` | upright and thin — a post, a pillar, a trunk |
| `mound` | a swelling in the ground — a bank, a rise, a stand of reeds |

`pos` is where the feature *meets the ground*, which is also the point a being
walks to. `radius` gives it extent, so arriving means arriving at the edge — a
being standing on the bank of a pond is at the pond.

**`material`** is one of `water, stone, wood, grass, earth, sand, metal, ice`.
It does two jobs from one word: the renderer uses it to decide how the surface
takes light, and perception reports it to beings. "Is it wet" used to be
settled by consensus.

**`enterable`** says a being can walk into it. Declaring stone enterable is
strange rather than invalid — a pack may mean it — so it warns and loads.

**`description`** is required. It is what a being is told when it looks at the
thing, and a feature without one is a name over nothing, which is the failure
this format retires.

### Atmosphere

```json
"atmosphere": "Late afternoon, warm and still, some hours after rain."
```

The one authored field, and the only one with no rendered counterpart to
contradict — it is about mood. Everything else is generated.

### Licence

**Required.** A pack will not validate without one, for the same reason an
avatar pack will not: every time provenance was optional in this project,
something turned out to contradict its own label.

A parametric world has no third-party asset in it, so `CC0-1.0` is usually the
honest answer.

## What is *not* in a manifest

**An inventory in the description.** Beings are told about the ground, the sky
and the atmosphere; what is standing in the world reaches them through
perception, which reports only what is in sight and where it is relative to
them. Listing everything up front would contradict the standing rule that a
being may refer only to what it can currently see, and a world with fifty
features would spend its whole cached prompt prefix on a catalogue.

**Coordinates.** Beings are never given numbers for position. "Behind you,
close by" is directly actionable; `(-8, 0, 3)` requires working out which way
you are facing first.

## Validating

```bash
python -c "from pathlib import Path; from andropia.worlds import load_pack; print(load_pack(Path('worlds/my-world')))"
```

Every problem is reported at once, so a pack is fixed in one pass rather than
one re-run at a time:

```
3 problem(s):
  - license: required
    every pack must declare its terms, e.g. {"id": "CC0-1.0"}
  - features[0].shape: unknown shape 'pyramid'
    available: disc, block, column, mound
  - features[0].description: required, must be a non-empty string
    this is what a being is told when it looks at the place
```

A field the format does not read is a **warning** rather than an error, so a
manifest written against a later schema still loads here — but it says so,
because a declaration that silently does nothing is the failure mode this whole
format exists to remove. Keys beginning with `_` are comments.

## The bundled packs

| | |
|---|---|
| **`meadow/`** | What the demo runs in. Wet grass under a wide pale sky, a pond you can wade into, a mossy rock, a lone fence post, a low rise. |
| **`example/`** | A fixture, not a place worth visiting. It exists to use every shape, so a shape the schema accepts and the renderer does not implement fails a test rather than producing an invisible landmark. Both test suites read it. |

## Adding a shape

Two edits and two tests, and the tests are the point.

1. Add the name to `SHAPES` in `src/andropia/worlds/schema.py`.
2. Add a geometry function to `SHAPES` in `frontend/src/world.js`, returning
   geometry already offset so the feature's position is where it meets the
   ground.
3. Use it in `worlds/example/world.json`.

Step 3 is what closes the loop. The Python suite asserts the example pack uses
every shape the schema accepts; the JavaScript suite asserts every shape in
that pack draws something with a size on all three axes. Either half alone
passes while a shape goes undrawn — and an undrawn shape is a place beings can
walk to and nobody can see, which is no error at all.
