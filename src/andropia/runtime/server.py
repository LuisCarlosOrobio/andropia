"""HTTP and WebSocket surface for watching and controlling a running world.

The imperative shell. Everything below is I/O around pure functions: the
world advances via :mod:`andropia.runtime.session`, is paced by
:mod:`andropia.runtime.clock`, and is projected for the wire by
:mod:`andropia.runtime.view`. Nothing here decides what happens in the
simulation — it only decides who gets told about it.

Design notes:

* **The world runs whether anyone is watching.** Viewers subscribe to a
  broadcast; they do not drive it. Close every tab and the sandbox keeps
  going, which is the whole point of a headless simulation.
* **Broadcast is best-effort.** A slow viewer is dropped from a frame rather
  than allowed to stall the tick loop. Falling behind is a viewer's problem.
* **Control is coarse and explicit.** Pause, resume, speed, step, and
  propose. No hidden state machine.

This is bound to loopback by default. It is unauthenticated: anything that
can reach it can drive the world.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from ..beings import adapter, claude
from ..beings import runner as beings
from ..demo import autopilot
from ..packs import discover
from ..sim import DoGesture, Emote, Goto, Look, MoveTo, Speak, Stop, Vec3, World
from . import clock, view
from . import session as sess
from .session import Session

REPO_ROOT = Path(__file__).resolve().parents[3]
FRONTEND_DIR = REPO_ROOT / "frontend" / "dist"
AVATARS_DIR = REPO_ROOT / "avatars"

_INTENTS = {
    "goto": Goto,
    "moveto": MoveTo,
    "gesture": DoGesture,
    "emote": Emote,
    "look": Look,
    "speak": Speak,
    "stop": Stop,
}


@dataclass
class Hub:
    """Mutable process state: the live session and its viewers.

    The one intentionally mutable object in the codebase. It exists because
    a server is a long-lived process with connections attached, and pretending
    otherwise would be dishonest rather than functional. Everything it holds
    is either a pure value (``session``) or an OS resource (``viewers``).
    """

    session: Session
    viewers: set[WebSocket] = field(default_factory=set)
    task: asyncio.Task | None = None
    minds_task: asyncio.Task | None = None
    stop: asyncio.Event = field(default_factory=asyncio.Event)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    #: Run the stand-in autopilot instead of waiting for real agents.
    drive_beings: bool = False
    #: Language models driving beings, if any were configured. When this is
    #: present the autopilot stays off: two things proposing intents for the
    #: same being would fight, and the model should win.
    cast: beings.Cast | None = None
    #: Intents produced by minds since the last tick. A plain list, appended
    #: from thinking tasks and drained by the tick loop under the lock — which
    #: keeps `propose` non-async and keeps the tick loop the only writer of
    #: `session`.
    pending: list = field(default_factory=list)


def create_app(
    world: World,
    *,
    autostart: bool = False,
    drive_beings: bool = False,
    cast: beings.Cast | None = None,
) -> FastAPI:
    """Build an app serving one world.

    ``cast`` wires language models to beings. When given, those beings think for
    themselves and the autopilot is switched off for everyone — two sources
    proposing intents for one being would fight, and the model should win.

    ``drive_beings`` runs the deterministic autopilot instead. It remains useful
    with no model to hand: it exercises the whole pipeline from intent to
    rendered body, and it is what the animation work was built against.
    """
    hub = Hub(session=sess.begin(world, mode="running" if autostart else "paused"))
    hub.cast = cast
    hub.drive_beings = drive_beings and cast is None

    @contextlib.asynccontextmanager
    async def lifespan(_: FastAPI):
        """Start the tick loop with the app and stop it cleanly after.

        A lifespan handler rather than the deprecated ``@app.on_event``,
        which also gives a single place for setup and teardown to see the
        same scope.
        """
        hub.task = asyncio.create_task(_run(hub))
        if hub.cast is not None:
            hub.minds_task = asyncio.create_task(_think(hub))
        try:
            yield
        finally:
            hub.stop.set()
            for task in (hub.task, hub.minds_task):
                if task is not None:
                    task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await task

    app = FastAPI(title="Andropia", version="0.1.0", lifespan=lifespan)
    app.state.hub = hub

    # ---------------------------------------------------------------- view

    @app.websocket("/ws/view")
    async def watch(ws: WebSocket) -> None:
        await ws.accept()
        # The static parts once, then only what moves.
        world = hub.session.world
        await ws.send_text(json.dumps({"type": "scene", **view.scene(world)}))
        await ws.send_text(json.dumps({"type": "frame", **view.frame(world)}))
        hub.viewers.add(ws)
        try:
            while True:
                # Viewers may send control messages on the same socket.
                raw = await ws.receive_text()
                await _handle(hub, json.loads(raw))
        except (WebSocketDisconnect, json.JSONDecodeError, KeyError):
            pass
        finally:
            hub.viewers.discard(ws)

    # ------------------------------------------------------------- control

    @app.get("/api/state")
    async def state() -> dict[str, Any]:
        s = hub.session
        return {
            "mode": s.mode,
            "speed": s.speed,
            "tick": s.world.tick,
            "entities": len(s.world.entities),
            "recorded": s.recording.ticks if s.recording else None,
            "viewers": len(hub.viewers),
        }

    @app.get("/api/transcript")
    async def transcript(since: int = 0) -> dict[str, Any]:
        """What has been said, for reading rather than rendering.

        The 3D view shows speech as a bubble over a being's head, which is the
        right thing for watching and the wrong thing for judging: bubbles
        expire, and a being can walk out of frame mid-sentence. Evaluating
        whether a cast of language models actually holds a conversation needs
        the lines in a form you can scroll back through.

        ``since`` filters by tick so a poller can tail without re-reading, and
        also reports each being's trouble — an endpoint that says who is talking
        should say who cannot.
        """
        world = hub.session.world
        return {
            "tick": world.tick,
            "lines": [
                {"tick": u.tick, "speaker": u.speaker, "text": u.text}
                for u in world.transcript
                if u.tick >= since
            ],
            # What each being is *doing*, not just saying. Tags are stripped
            # before a line reaches the transcript, so speech alone cannot
            # distinguish a being that said "I'm going to the tree" and emitted
            # [goto:tree] from one that narrated the move and stood still —
            # which is the characteristic failure of an action protocol.
            "doing": {
                eid: {
                    "action": ent.action.kind,
                    "emotion": ent.emotion if ent.emotion_weight > 0 else None,
                    "gaze": ent.gaze,
                }
                for eid, ent in sorted(world.entities.items())
            },
            "trouble": dict(hub.cast.trouble) if hub.cast else {},
        }

    @app.post("/api/control/{command}")
    async def control(
        command: str, body: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        body = body or {}
        async with hub.lock:
            match command:
                case "pause":
                    hub.session = sess.pause(hub.session)
                case "resume":
                    hub.session = sess.resume(hub.session)
                case "step":
                    hub.session = sess.tick(hub.session)
                    await _broadcast(hub)
                case "advance":
                    hub.session = sess.advance(hub.session, int(body.get("ticks", 1)))
                    await _broadcast(hub)
                case "speed":
                    try:
                        hub.session = sess.set_speed(
                            hub.session, float(body.get("value", 1.0))
                        )
                    except ValueError as exc:
                        raise HTTPException(400, str(exc)) from exc
                case _:
                    raise HTTPException(404, f"unknown command {command!r}")
        return {
            "mode": hub.session.mode,
            "speed": hub.session.speed,
            "tick": hub.session.world.tick,
        }

    @app.post("/api/intent")
    async def intent(body: dict[str, Any]) -> dict[str, Any]:
        parsed = _parse_intent(body)
        async with hub.lock:
            hub.session = sess.propose(hub.session, parsed)
        return {"queued": len(hub.session.pending)}

    # --------------------------------------------------------------- packs

    @app.get("/api/packs")
    async def packs() -> dict[str, Any]:
        """Every avatar pack found, including the broken ones.

        Failures are reported rather than filtered out. A user who made a
        typo in a manifest should see why their avatar is missing, not a
        list that is quietly one shorter than they expect.
        """
        found = discover(AVATARS_DIR)
        return {
            "packs": [
                {
                    "id": r.pack.id,
                    "name": r.pack.name,
                    "type": r.pack.type,
                    "model": f"/packs/{d}/{r.pack.model}",
                    "emotions": list(r.pack.supported_emotions),
                    "gestures": list(r.pack.supported_gestures),
                    "clips": {k: v.clip for k, v in r.pack.motions.items()},
                    "locomotion": dict(r.pack.locomotion),
                    "license": r.pack.license.id,
                    "attribution": r.pack.license.attribution,
                    "warnings": list(r.warnings),
                }
                for d, r in found.items()
                if r.ok
            ],
            "broken": {d: str(r) for d, r in found.items() if not r.ok},
        }

    # Model files. A StaticFiles mount, deliberately — it normalises paths
    # and enforces containment. Hand-rolled path concatenation is what made
    # the previous codebase's file serving a latent arbitrary read.
    if AVATARS_DIR.is_dir():
        app.mount("/packs", StaticFiles(directory=AVATARS_DIR), name="packs")

    # -------------------------------------------------------------- static

    if FRONTEND_DIR.is_dir():
        app.mount(
            "/assets", StaticFiles(directory=FRONTEND_DIR / "assets"), name="assets"
        )

        @app.get("/")
        async def index() -> FileResponse:
            return FileResponse(FRONTEND_DIR / "index.html")

        @app.get("/tune")
        async def tune() -> FileResponse:
            """The pose tuner — a development tool, not part of the product.

            Loads one avatar with no simulation attached so gesture
            keyframes can be scrubbed and edited live.
            """
            return FileResponse(FRONTEND_DIR / "tune.html")

    return app


# --------------------------------------------------------------------------
# internals
# --------------------------------------------------------------------------


def _parse_intent(body: dict[str, Any]):
    kind = body.get("kind")
    cls = _INTENTS.get(kind)
    if cls is None:
        raise HTTPException(400, f"unknown intent kind {kind!r}")

    payload = {k: v for k, v in body.items() if k != "kind"}

    # JSON has no vectors, so positions arrive as [x, y, z]. Coerce here
    # rather than making the simulation accept two shapes for one field.
    if "pos" in payload:
        try:
            x, y, z = payload["pos"]
            payload["pos"] = Vec3(float(x), float(y), float(z))
        except (TypeError, ValueError) as exc:
            raise HTTPException(400, "pos must be [x, y, z]") from exc

    # Names must be strings. Dataclasses do not enforce their annotations, so
    # a coordinate array sent as a landmark name would construct happily here
    # and only fail deep in the simulation, where the message is useless.
    # The boundary is where a wrong shape should be caught.
    for key in ("entity", "target", "motion", "emotion"):
        value = payload.get(key)
        if value is not None and not isinstance(value, str):
            raise HTTPException(
                400,
                f"{key} must be a string, got {type(value).__name__}"
                + (
                    " — to send a being to a bare position use "
                    "{'kind': 'moveto', 'pos': [x, y, z]}"
                    if key == "target"
                    else ""
                ),
            )

    try:
        return cls(**payload)
    except TypeError as exc:
        raise HTTPException(400, f"bad {kind} intent: {exc}") from exc


async def _handle(hub: Hub, msg: dict[str, Any]) -> None:
    """Control messages arriving on a viewer's socket.

    Nothing a viewer sends may tear down its own connection. A malformed
    message is logged and dropped, because the alternative — a socket that
    dies on one bad payload — is indistinguishable from a paused world, and
    the client has no way to tell which happened.
    """
    match msg.get("type"):
        case "intent":
            try:
                parsed = _parse_intent(msg.get("intent") or {})
            except HTTPException as exc:
                print(f"[andropia] ignoring malformed intent: {exc.detail}")
                return
            async with hub.lock:
                hub.session = sess.propose(hub.session, parsed)
        case "pause":
            hub.session = sess.pause(hub.session)
        case "resume":
            hub.session = sess.resume(hub.session)
        case "step":
            hub.session = sess.tick(hub.session)
            await _broadcast(hub)
        case "speed":
            with contextlib.suppress(ValueError):
                hub.session = sess.set_speed(hub.session, float(msg.get("value", 1.0)))


async def _run(hub: Hub) -> None:
    """Drive the session, broadcasting each tick.

    Uses :func:`clock.plan` — the pure pacing policy — rather than
    :func:`clock.drive`, deliberately. ``drive`` threads a session through
    its own loop, which is correct for a standalone runner but wrong here:
    the hub must be the *single owner* of ``session``, or an intent proposed
    by an HTTP handler between two ticks is silently discarded when the loop
    writes back its own private copy. One value, one owner.
    """
    accumulator = 0.0
    previous = time.monotonic()

    while not hub.stop.is_set():
        current = time.monotonic()
        elapsed = current - previous
        previous = current

        if hub.session.mode == "running":
            pacing = clock.plan(
                accumulator,
                elapsed,
                dt=hub.session.world.dt,
                speed=hub.session.speed,
            )
            accumulator = pacing.accumulator

            for _ in range(pacing.ticks):
                async with hub.lock:
                    if hub.drive_beings:
                        proposed = autopilot(hub.session.world)
                        if proposed:
                            hub.session = sess.propose(hub.session, *proposed)
                    if hub.pending:
                        # Drained rather than read, so an intent cannot be
                        # applied twice if a tick is slow.
                        thought, hub.pending[:] = tuple(hub.pending), []
                        hub.session = sess.propose(hub.session, *thought)
                    hub.session = sess.tick(hub.session)
                await _broadcast(hub)

            if pacing.lag is not None:
                print(f"[andropia] behind by {pacing.lag.dropped_ticks} ticks; dropped")
        else:
            # Time spent paused is discarded, so resuming does not fire a
            # catch-up burst for however long the world sat still.
            accumulator = 0.0

        await asyncio.sleep(clock.sleep_for(hub.session))


async def _think(hub: Hub) -> None:
    """Let the configured beings think, alongside the tick loop.

    The runner is given two callables rather than the hub, so it cannot become
    a second owner of the session — the tick loop stays the only writer. This
    is the same mistake that bit `clock.drive` earlier: it threaded its own
    session, and intents proposed over HTTP were silently overwritten.

    Proposals land in a plain list rather than calling `sess.propose` directly.
    `propose` returns a *new* session, so a thinking task that read the session
    and replaced it would silently drop whatever the tick loop had done in
    between. Appending to a list needs no lock — there is no await between the
    read and the write, so the event loop cannot interleave — and the tick loop
    drains it while holding the lock it already holds.
    """

    def snapshot() -> World:
        return hub.session.world

    def propose(intents) -> None:
        # Queued for the next tick. Deliberately not applied here: the tick is
        # where intents enter the recording, and that is what makes a run with
        # language models in it replayable without them.
        hub.pending.extend(intents)

    await beings.drive(hub.cast, snapshot, propose, stop=hub.stop)


async def _broadcast(hub: Hub) -> None:
    """Send the current frame to every viewer.

    Best-effort by design. A viewer that errors is dropped rather than
    retried — the world does not slow down for a stalled tab.
    """
    if not hub.viewers:
        return

    payload = json.dumps({"type": "frame", **view.frame(hub.session.world)})
    dead: list[WebSocket] = []

    for ws in tuple(hub.viewers):
        try:
            await ws.send_text(payload)
        except Exception:
            dead.append(ws)

    for ws in dead:
        hub.viewers.discard(ws)


#: Starting personalities for the demo world.
#:
#: Short on purpose. A persona is a nudge, not a script — a paragraph of
#: instructions produces a being that recites its brief, whereas a line or two
#: of disposition produces one that behaves. Different enough from each other
#: that a conversation between them has somewhere to go.
PERSONAS = {
    "ava": (
        "You are quiet and watchful, and you notice things before you mention "
        "them. You like water and open space. You would rather ask than "
        "explain."
    ),
    "mistral": (
        "You are restless and direct. You would rather be walking somewhere "
        "than standing still, and you say what you think without much "
        "padding."
    ),
    "claude": (
        "You are curious to a fault and easily delighted by small details. You "
        "get interested in whatever is nearest and follow it further than "
        "anyone asked."
    ),
}


def demo_world() -> World:
    """A small world to look at, for `python -m andropia.runtime.server`."""
    from ..sim import Entity, Landmark, Vec3

    return World(
        entities={
            "ava": Entity(
                id="ava",
                pos=Vec3(0.0, 0.0, 0.0),
                avatar_pack="ava",
                persona=PERSONAS["ava"],
            ),
            "mistral": Entity(
                id="mistral",
                pos=Vec3(4.0, 0.0, 2.0),
                avatar_pack="robot",
                persona=PERSONAS["mistral"],
            ),
            "claude": Entity(
                id="claude",
                pos=Vec3(-3.0, 0.0, 3.0),
                avatar_pack="robot",
                persona=PERSONAS["claude"],
            ),
        },
        landmarks={
            "tree": Landmark("tree", Vec3(12.0, 0.0, -4.0), "the old tree"),
            "pond": Landmark("pond", Vec3(-8.0, 0.0, 3.0), "the pond"),
            "rock": Landmark("rock", Vec3(5.0, 0.0, 9.0), "a mossy rock"),
        },
    )


def demo_cast(world: World) -> tuple[beings.Cast | None, str, object]:
    """Wire every being in the world to a model, if one is configured.

    One model for all of them, which is the common case: a single endpoint,
    three beings, three different personas. Their behaviour differs because
    their persona, position and memory differ — not because they run on
    different weights.

    Returns the cast, a line describing it, and the client to close on
    shutdown. The client is returned rather than closed here because it has to
    outlive this function by the length of the run — and rather than being
    created inside the runner, because the runner is deliberately ignorant of
    which provider it is driving.

    None when nothing is configured, so the demo still runs on a machine with
    no model to hand. Not a fallback for its own sake: the autopilot is what the
    whole animation and rendering pipeline was built against.
    """
    if claude.configured():
        try:
            import anthropic
        except ImportError:
            missing = (
                "claude configured but its SDK is missing — "
                "pip install 'andropia[claude]'"
            )
            return None, missing, None

        model = claude.Claude.from_env()
        client = anthropic.AsyncAnthropic()
        brain = claude.brain(client, model)
        cast = beings.personas(world, dict.fromkeys(world.entities, brain))
        return cast, f"{model.name} (anthropic, effort={model.effort})", client

    if os.environ.get(beings.ENV_BASE_URL):
        import httpx

        model = beings.Model.from_env()
        client = httpx.AsyncClient()
        brain = adapter.brain(client, model)
        cast = beings.personas(world, dict.fromkeys(world.entities, brain))
        return cast, f"{model.name} at {model.base_url}", client

    return None, "", None


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    world = demo_world()
    cast, describe, _client = demo_cast(world)

    app = create_app(world, autostart=True, drive_beings=True, cast=cast)

    print("\n  Andropia — http://127.0.0.1:8600")
    if cast is None:
        print("  beings: deterministic autopilot")
        if describe:
            print(f"  note:   {describe}")
        print(f"  models: set {beings.ENV_BASE_URL}, or an ANTHROPIC_API_KEY\n")
    else:
        print(f"  beings: {', '.join(sorted(cast.minds))}")
        print(f"  model:  {describe}\n")

    uvicorn.run(app, host="127.0.0.1", port=8600, log_level="warning")
