# Andropia

A deterministic sandbox for embodied intelligence: language models
inhabiting bodies in a shared 3D world, moving through it, perceiving it,
and talking to each other.

## See it

```bash
python -m andropia.runtime.server
```

Then open **http://127.0.0.1:8600**.

Three beings in a world, walking to landmarks, gesturing, changing
expression and speaking. They are driven by a deterministic autopilot —
language models take over in the next phase.

Click a being to select it, then click the ground to send it there. The
controls pause, single-step, and run at up to 20x.

The Ava avatar is fetched rather than committed, at 21 MB:

```bash
./avatars/ava/fetch.sh
```

Without it the world still runs; beings appear as capsules.

## What is here

| | |
|---|---|
| `src/andropia/sim/` | The simulation. Pure, no dependencies, no clock. |
| `src/andropia/runtime/` | Sessions, the tick loop, the wire format, the server. |
| `src/andropia/packs/` | Avatar packs: bodies a being can wear. |
| `frontend/` | The viewer, and a pose tuner at `/tune`. |
| `avatars/` | Bundled bodies. See `avatars/README.md`. |

## Why deterministic

`seed + initial world + intent log` reproduces a run exactly. Rewind to an
interesting moment, fork it, change one thing, run it again. Nothing in the
simulation reads a clock or a global RNG, which is what makes replay,
snapshotting and fast-forward fall out rather than needing to be built.

```bash
pytest              # 146 tests
cd frontend && npm test   # 62 tests, none need a browser
```

## Licence

Apache-2.0 for the code. Bundled assets carry their own terms — see
`NOTICE` and `ASSET-LICENSES.md`. Contributions need a CLA; see `CLA.md`.
