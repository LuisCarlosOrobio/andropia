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
