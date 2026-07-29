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
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

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
    stop: asyncio.Event = field(default_factory=asyncio.Event)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    #: Run the stand-in autopilot instead of waiting for real agents.
    drive_beings: bool = False


def create_app(
    world: World, *, autostart: bool = False, drive_beings: bool = False
) -> FastAPI:
    """Build an app serving one world.

    ``drive_beings`` runs the deterministic autopilot, which proposes the
    kinds of intents an agent will once Phase 3 lands. It exists so the whole
    pipeline can be seen working by running one command.
    """
    hub = Hub(session=sess.begin(world, mode="running" if autostart else "paused"))
    hub.drive_beings = drive_beings

    @contextlib.asynccontextmanager
    async def lifespan(_: FastAPI):
        """Start the tick loop with the app and stop it cleanly after.

        A lifespan handler rather than the deprecated ``@app.on_event``,
        which also gives a single place for setup and teardown to see the
        same scope.
        """
        hub.task = asyncio.create_task(_run(hub))
        try:
            yield
        finally:
            hub.stop.set()
            if hub.task is not None:
                hub.task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await hub.task

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

    try:
        return cls(**payload)
    except TypeError as exc:
        raise HTTPException(400, f"bad {kind} intent: {exc}") from exc


async def _handle(hub: Hub, msg: dict[str, Any]) -> None:
    """Control messages arriving on a viewer's socket."""
    match msg.get("type"):
        case "intent":
            async with hub.lock:
                parsed = _parse_intent(msg["intent"])
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
                    hub.session = sess.tick(hub.session)
                await _broadcast(hub)

            if pacing.lag is not None:
                print(f"[andropia] behind by {pacing.lag.dropped_ticks} ticks; dropped")
        else:
            # Time spent paused is discarded, so resuming does not fire a
            # catch-up burst for however long the world sat still.
            accumulator = 0.0

        await asyncio.sleep(clock.sleep_for(hub.session))


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


def demo_world() -> World:
    """A small world to look at, for `python -m andropia.runtime.server`."""
    from ..sim import Entity, Landmark, Vec3

    return World(
        entities={
            "ava": Entity(id="ava", pos=Vec3(0.0, 0.0, 0.0), avatar_pack="ava"),
            "mistral": Entity(
                id="mistral", pos=Vec3(4.0, 0.0, 2.0), avatar_pack="robot"
            ),
            "claude": Entity(
                id="claude", pos=Vec3(-3.0, 0.0, 3.0), avatar_pack="robot"
            ),
        },
        landmarks={
            "tree": Landmark("tree", Vec3(12.0, 0.0, -4.0), "the old tree"),
            "pond": Landmark("pond", Vec3(-8.0, 0.0, 3.0), "the pond"),
            "rock": Landmark("rock", Vec3(5.0, 0.0, 9.0), "a mossy rock"),
        },
    )


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    app = create_app(demo_world(), autostart=True, drive_beings=True)
    print("\n  Andropia — http://127.0.0.1:8600\n")
    uvicorn.run(app, host="127.0.0.1", port=8600, log_level="warning")
