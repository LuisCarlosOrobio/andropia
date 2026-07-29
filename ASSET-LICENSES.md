# Asset licenses

Apache-2.0 (see `LICENSE`) covers **the source code of this project and nothing
else**. Every bundled asset carries its own terms, recorded here.

Each entry records what the asset is, where it came from, its exact license, the
date it was retrieved, and — where the format supports it — a dump of the
license metadata embedded in the file itself, verified at inclusion time.

> **Policy: verify the file, not the badge.**
> During asset selection for this project, three separate sources were found
> asserting a license the file itself contradicted — a repository badge, a
> filename suffix, and a curated registry index. Before any asset enters this
> repository, its embedded metadata is dumped and read. The dumps below are that
> evidence.

---

## `avatars/robot/RobotExpressive.glb`

| | |
|---|---|
| **License** | CC0 1.0 Universal (public domain dedication) |
| **Author** | Tomás Laulhé ([Quaternius](https://quaternius.com)) |
| **Modifications** | Don McCurdy — 3 facial expression morph targets, FBX2GLTF conversion, material cleanup |
| **Source** | `github.com/mrdoob/three.js` → `examples/models/gltf/RobotExpressive/` |
| **Retrieved** | 2026-07-28 |
| **Redistribute** | ✅ | **Modify** ✅ | **Commercial** ✅ | **Attribution required** ❌ |

License text, quoted in full from the `README.md` in the model's own directory:

> # RobotExpressive
>
> Model by [Tomás Laulhé](https://www.patreon.com/quaternius). Before using this
> model on a project, consider supporting the creator's Patreon. **CC0 1.0.**
>
> Modifications by [Don McCurdy](https://donmccurdy.com/):
> - Added three facial expression morph targets
> - Converted with FBX2GLTF
> - Removed duplicate materials and reduced material metalness

The Patreon line is a *request*, not a condition — CC0 imposes no conditions.
Credit is given in `NOTICE` voluntarily.

**Verified contents** (parsed from the GLB JSON chunk, 2026-07-28):

```
size        463,988 bytes
generator   FBX2glTF
textures    0        materials 3        skins 2 × 43 joints
clips (14)  Dance, Death, Idle, Jump, No, Punch, Running, Sitting,
            Standing, ThumbsUp, Walking, WalkJump, Wave, Yes
morphs      Head: [Angry, Surprised, Sad]
```

Provenance is corroborated: Tomás Laulhé is Quaternius, whose CC0 practice is
documented across his asset packs, and the byte-identical file is redistributed
by both three.js and Google's `model-viewer`.

---

## `avatars/ava/AvatarSample_B.vrm`

| | |
|---|---|
| **License** | VRoid sample model terms of use — **not** CC0, **not** Apache-2.0 |
| **Author** | VRoid Project |
| **Copyright** | © pixiv Inc. |
| **Source** | `github.com/pixiv/ChatVRM` → `public/AvatarSample_B.vrm` |
| **Terms** | `vroid.pixiv.help/hc/en-us/articles/4402394424089` (dated copy archived alongside the asset) |
| **Retrieved** | 2026-07-28 |
| **Redistribute** | ✅ | **Modify** ✅ | **Commercial** ✅ | **Attribution required** ❌ |

**⚠️ This asset is not licensed under Apache-2.0.** pixiv permits redistribution,
modification, and commercial use, but has not granted sublicensing rights, and
their terms **expressly prohibit redistributing the model under a CC0
dedication**. Never represent this file as covered by this project's license.

These are website terms of use that pixiv may change without notice. A copy as
published on the retrieval date is archived next to the asset so the terms at
time of inclusion are evidenced.

**Verified embedded metadata** (`VRMC_vrm.meta`, parsed 2026-07-28):

```json
{
  "name": "AvatarSample_B",
  "version": "1.1",
  "authors": ["VRoid Project"],
  "copyrightInformation": "pixiv Inc.",
  "licenseUrl": "https://vrm.dev/licenses/1.0/",
  "avatarPermission": "everyone",
  "commercialUsage": "corporation",
  "creditNotation": "unnecessary",
  "allowRedistribution": true,
  "modification": "allowModificationRedistribution",
  "allowExcessivelyViolentUsage": true,
  "allowExcessivelySexualUsage": true,
  "allowPoliticalOrReligiousUsage": true,
  "allowAntisocialOrHateUsage": false
}
```

**Verified rig** (parsed 2026-07-28): VRM 1.1, generator VRoid Studio 1.22.0,
21,047,556 bytes. 54 humanoid bones mapped with **no required bone missing**,
including full finger chains. Expressions `neutral, happy, angry, sad, relaxed,
surprised`; visemes `aa, ih, ou, ee, oh`; blinks `blink, blinkLeft, blinkRight`.
22 spring-bone chains. **0 animation clips** — motion is supplied separately.

---

## `static/dist/src/Grass.js`, `shaders.js`

| | |
|---|---|
| **License** | ⚠️ **Unresolved — see below** |
| **Origin** | A WebGL stylized-grass demo, forked via CodeSandbox |

These files were inherited from a third-party template. Evidence of origin: the
package name is still `webgl-grass`, a CodeSandbox `sandbox.config.json` remains
in the tree, and `Grass.js` credits `smythdesign.com/blog/stylized-grass-webgl`.

**The upstream license was never carried over when the template was forked.**
This is an open item: either obtain and record the upstream terms, or replace
these files with an original implementation before relying on them.

---

## Assets removed from this repository and its history

Recorded for transparency. These were removed from **all** commits via
`git filter-repo`, not merely deleted in a later commit, because deletion alone
leaves the blobs reachable in history.

| Asset | Reason |
|---|---|
| `eurostile.TTF`, `EuroStyle Normal.ttf` | Eurostile is a commercial typeface (Linotype/Monotype). Committing and web-serving the binaries is redistribution, which standard desktop font EULAs prohibit. |
| `Animetest.gltf` / `.bin`, `*albedo*.png`, `ashamed_albedo_alpha.png` | Derived from "Oono Akiroid" by Dr_Stef, **CC-BY-NC-SA-4.0**. The NonCommercial clause would bar commercial use of any project bundling them. |
| `suit girl update NEW.gltf` / `.bin` | Same source, same NC restriction. |
| `SpokenRoses.m4a` | No documented provenance or license. |
| `node_modules/` (both trees), `.cache/` | Vendored dependencies and bundler caches; 17,800+ files, ~230 MB. |
| `*.DS_Store` | macOS metadata; these leak directory listings including files never committed. |
| `*.pyc` | Compiled bytecode embedding a prior developer's absolute paths. |

---

## Assets *not* bundled

Andropia connects to models the user supplies. **No model weights ship with this
project** and their licenses are the user's responsibility. Two notes that
routinely trip people up:

- **Mixamo** animations may be used in projects but **may not be redistributed
  as raw files** — Adobe's terms prohibit "any type of free distribution of
  character or animation raw files." Obtain them yourself; they will never be
  vendored here.
- **License splits are common.** Several widely-recommended models carry a
  permissive *code* license over restrictively-licensed *weights*. Check the two
  separately, and read the model card body rather than trusting a metadata
  field — at least one popular model publishes an empty license field while its
  card declares CC-BY-NC.
