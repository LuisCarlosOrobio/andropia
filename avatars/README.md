# Avatar packs

A pack is a body a being can wear. Drop a directory in here and Andropia will
find it.

```
avatars/my-avatar/
  avatar.json      the manifest
  my-avatar.vrm    the model (.vrm or .glb)
  LICENSE          the model's terms
```

## The manifest

```json
{
  "schema": 1,
  "id": "my-avatar",
  "name": "My Avatar",
  "type": "vrm",
  "model": "my-avatar.vrm",
  "persona": "You are…",
  "license": { "id": "CC0-1.0", "attribution": "…" }
}
```

That is a complete, valid pack. Note what is **not** there.

### Expressions

Andropia's six canonical emotions — `neutral, happy, angry, sad, relaxed,
surprised` — are exactly the VRM standard expression presets. So **a
conformant VRM needs no expression mapping at all**; the loader reads the
rig and works out what it supports.

A plain glTF has no such standard, so it must say which morph target means
what:

```json
"expressions": { "happy": "Smiling", "sad": "Ashamed" }
```

Canonical name on the left, whatever your artist called it on the right.
Application code only ever refers to the left-hand side.

`neutral` is never declared: it is the *absence* of expression, so every rig
can do it.

### Motions

Eight canonical gestures: `wave, nod, shake, shrug, think, point, cheer,
idle_variant`.

**All of them work on every body**, whether or not you declare anything.
Gestures with no clip are generated procedurally in normalised humanoid
space, which is why an avatar that ships zero animations — as essentially
every VRM does — is still fully expressive.

Declare a motion only to override the procedural version with a baked clip:

```json
"motions": { "wave": { "clip": "Wave" }, "nod": { "clip": "Yes" } }
```

### Licence

**Required.** A pack will not validate without one.

This is deliberate. While selecting the bundled avatars, three separate
sources were found asserting a licence the file itself contradicted — a
repository badge, a filename suffix, and a curated registry index. Making
provenance structurally mandatory is cheaper than discovering later that
something in your world cannot be shipped.

If you intend to share your pack: its terms must permit redistribution,
modification, and **commercial use**. Non-commercial licences (CC-BY-NC and
relatives) restrict every downstream user of any project that bundles them.

## Validating

Loading always checks the manifest against the **actual model file**, so a
name that does not exist in the rig is an error rather than a silent no-op at
render time:

```
2 problem(s):
  - motions.wave.clip: 'Waev' is not in the model
    available: Dance, Idle, No, Walking, Wave, Yes
  - expressions.happy: 'Smile' is not in the model
    available: Angry, Sad, Surprised
```

Every problem is reported at once, and the message names what the rig really
contains — so you can fix a pack in one pass rather than one re-run at a time.

Check yours:

```bash
python -c "from pathlib import Path; from andropia.packs import load_pack; print(load_pack(Path('avatars/my-avatar')))"
```

## The bundled packs

| | |
|---|---|
| **`robot/`** | RobotExpressive, **CC0-1.0**, 453 KB. Committed. Three expression morphs and fourteen clips, four of them mapped to canonical gestures — a worked example of a partial rig. |
| **`ava/`** | VRoid sample avatar, 21 MB. **Not committed** — run `ava/fetch.sh`. Full expression and viseme set, zero animation clips, so every gesture is procedural. |

Ava's terms permit redistribution and commercial use but are **not**
Apache-2.0 and **not** CC0; pixiv has not granted sublicensing rights. See
`../ASSET-LICENSES.md`.

---

## Tuning gestures

Gesture angles cannot be tuned by reasoning about a rig — they have to be
watched. Triggering one through the simulation and waiting out its 1.5
seconds is far too slow a loop to converge on anything, so there is a
dedicated tuner:

```bash
# terminal 1 — the simulation server, which serves the models
python -m andropia.runtime.server

# terminal 2 — the frontend dev server, for hot reload
cd frontend && npm run dev
```

Then open **`/tune`**.

It loads one avatar with no simulation attached. Pick a gesture, scrub its
phase or loop it at half speed, and drag the per-bone sliders — edits apply
live. When it looks right, **copy gesture as JSON** puts the whole keyframe
list on your clipboard, formatted to paste straight over the entry in
`src/anim/gestures.js`. Saving that file hot-reloads the tuner.

Some notes from authoring the current set:

- **The rest pose is a T-pose.** Every rotation in a gesture is a delta from
  arms-straight-out, which is why `REST` exists and why the arm values are
  large. Toggle the idle layer off to see the raw T-pose.
- **Keep the first and last keyframe empty.** A gesture that does not start
  and end at rest will snap.
- **Left and right take opposite signs.** The left arm points +X and the
  right points −X, so mirroring a pose means negating the Z rotation.
- **Watch it with the idle layer on.** Gestures compose additively over
  breathing and sway, and a pose that looks right in isolation can fight it.
- **Procedural poses need a VRM.** A plain glTF has no normalised humanoid
  rig, so the sliders will do nothing on the robot — use Ava.
