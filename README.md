# Andropia

A deterministic sandbox for embodied intelligence: language models
inhabiting bodies in a shared 3D world, moving through it, perceiving it,
and talking to each other.

## See it

```bash
make install   # once
make dev
```

Then open **http://127.0.0.1:8600**.

`make dev` bundles the frontend before serving, which matters: the server
serves `frontend/dist`, so running it directly shows you whatever was built
last — or nothing at all on a fresh clone.

Three beings in a world, walking to landmarks, gesturing, changing
expression and speaking. Their names and personalities are drawn from a seed —
same seed, same three people — so a world is populated rather than authored.

By default they run on a deterministic autopilot, so the whole pipeline works
with no model to hand. To let language models drive them instead, either point
Andropia at an OpenAI-compatible endpoint — vLLM, llama.cpp's server, Ollama,
LM Studio — or use Claude:

```bash
# any OpenAI-compatible endpoint
export ANDROPIA_BASE_URL=http://127.0.0.1:8000/v1
export ANDROPIA_MODEL=your-model-name
export ANDROPIA_API_KEY=...        # only if your endpoint wants one
make dev
```

```bash
# Claude. The Anthropic API is not OpenAI-compatible, so it has its own
# adapter and its own optional dependency.
pip install -e '.[claude]'
export ANTHROPIC_API_KEY=...
export ANDROPIA_CLAUDE_MODEL=claude-opus-5   # optional; this is the default
make claude-check   # two live turns: key, credit, model, caching. ~1 cent.
make dev
```

Speech shows as a bubble over a being's head, which expires. To read the
conversation back, tail it from a second terminal:

```bash
make transcript
```

Each being then perceives what is around it, decides what to say and do, and
acts by writing inline tags in what it says:

```
[happy]Oh, you found me! [motion:wave] I was looking at the pond.[goto:pond]
```

Tags are stripped before anyone hears the line, so they are actions rather
than words. Unknown tags are ignored, which means a small local model or a
LoRA finetune degrades instead of breaking.

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
| `src/andropia/beings/` | Perception, prompts, the tag protocol, the turn runner. |
| `src/andropia/packs/` | Avatar packs: bodies a being can wear. |
| `src/andropia/worlds/` | World packs: places, drawn and described from one file. |
| `frontend/` | The viewer, and a pose tuner at `/tune`. |
| `avatars/` | Bundled bodies. See `avatars/README.md`. |
| `worlds/` | Bundled places. See `worlds/README.md`. |

## Why deterministic

`seed + initial world + intent log` reproduces a run exactly. Rewind to an
interesting moment, fork it, change one thing, run it again. Nothing in the
simulation reads a clock or a global RNG, which is what makes replay,
snapshotting and fast-forward fall out rather than needing to be built.

Language models do not weaken this, because a model's reply is not the state
change — it becomes intents, and the tick that applies them records them. So a
replay reads the intent log and never calls a model: the run reproduces
whatever the temperature was, and whether or not the endpoint still exists.

```bash
make check   # 388 Python tests, 143 JS tests, none need a browser
```

## Licence

Apache-2.0 for the code. Bundled assets carry their own terms — see
`NOTICE` and `ASSET-LICENSES.md`. Contributions need a CLA; see `CLA.md`.
