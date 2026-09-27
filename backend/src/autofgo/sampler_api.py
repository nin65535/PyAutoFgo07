"""Private API for the dedicated card reference sampler."""

import asyncio
import io
import json
from importlib.resources import files
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from PIL import Image, ImageOps, UnidentifiedImageError

from autofgo.card_references import allocate, read_manifest, save_reference
from autofgo.security import SessionSecurity
from autofgo.status_card_candidates import SIZE_PRESETS, detect_layout, generate_candidates

MAX_IMAGE_BYTES = 12 * 1024 * 1024
MAX_IMAGE_PIXELS = 12_000_000


class SamplerState:
    def __init__(
        self, manifest: Path, scenarios: Path, *, companion_was_running: bool = False
    ) -> None:
        self.manifest = manifest
        self.companion_was_running = companion_was_running
        self.scenarios = scenarios
        self.security = SessionSecurity()
        self.image: Image.Image | None = None
        self.layout = None
        self.source_id = ""
        self.connected = asyncio.Event()
        self.disconnected = asyncio.Event()
        self.had_connection = False
        self.connections = 0
        self.saving = asyncio.Lock()
        self.closing = False

    def clear(self) -> None:
        self.image = None
        self.layout = None
        self.source_id = ""

    def names(self) -> list[dict[str, str]]:
        names: dict[str, str] = {}
        for path in self.scenarios.glob("*.json"):
            if path.stat().st_size > 1024 * 1024:
                raise ValueError(f"scenario is too large: {path.name}")
            data = json.loads(path.read_text(encoding="utf-8"))
            members = data.get("members")
            if not isinstance(members, list):
                raise ValueError(f"invalid scenario members: {path.name}")
            for member in members:
                if not isinstance(member, str):
                    raise ValueError(f"invalid scenario member: {path.name}")
                name = member.split("＋", 1)[0].strip()
                if name.endswith(" guest"):
                    name = name[:-6].strip()
                if name:
                    names.setdefault(name, member)
        return [{"name": name, "displayName": display} for name, display in sorted(names.items())]


def create_sampler_app(state: SamplerState) -> FastAPI:
    app = FastAPI(title="autoFgo card sampler")

    @app.get("/api/startup-warning")
    def startup_warning():
        return {"companionWasRunning": state.companion_was_running}

    @app.get("/")
    def landing():
        page = files("autofgo").joinpath("sampler_ui.html").read_text(encoding="utf-8")
        return Response(page, media_type="text/html")

    @app.get("/sampler-ui.js")
    def script():
        code = files("autofgo").joinpath("sampler_ui.js").read_text(encoding="utf-8")
        return Response(code, media_type="text/javascript")

    @app.middleware("http")
    async def protect(request: Request, call_next):
        if request.url.path.startswith("/api/"):
            if request.client is None or request.client.host not in {
                "127.0.0.1",
                "::1",
                "testclient",
            }:
                return JSONResponse({"error": "loopback only"}, status_code=403)
            origin = request.headers.get("origin")
            if origin and origin != f"{request.url.scheme}://{request.headers.get('host')}":
                return JSONResponse({"error": "invalid origin"}, status_code=403)
            if not state.security.authenticate(
                request.headers.get("X-AutoFgo-Session-Id"), request.headers.get("authorization")
            ):
                return JSONResponse({"error": "authentication required"}, status_code=401)
            if state.closing:
                return JSONResponse({"error": "sampler is closing"}, status_code=503)
            length = request.headers.get("content-length")
            if length:
                try:
                    if int(length) > MAX_IMAGE_BYTES:
                        return JSONResponse({"error": "image exceeds byte limit"}, status_code=413)
                except ValueError:
                    return JSONResponse({"error": "invalid content length"}, status_code=400)
        return await call_next(request)

    @app.get("/api/catalog")
    def catalog():
        try:
            return {
                "characters": state.names(),
                "manifest": read_manifest(state.manifest, missing_ok=True),
            }
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise HTTPException(500, str(exc)) from exc

    @app.post("/api/image")
    async def receive_image(request: Request):
        if request.headers.get("content-type", "").split(";", 1)[0] != "image/png":
            raise HTTPException(415, "PNG image required")
        chunks = bytearray()
        async for chunk in request.stream():
            chunks.extend(chunk)
            if len(chunks) > MAX_IMAGE_BYTES:
                raise HTTPException(413, "image exceeds byte limit")
        try:
            with Image.open(io.BytesIO(chunks)) as opened:
                if opened.format != "PNG" or opened.width * opened.height > MAX_IMAGE_PIXELS:
                    raise ValueError("invalid PNG or image exceeds pixel limit")
                opened.load()
                image = ImageOps.exif_transpose(opened).convert("RGB")
            layout = detect_layout(image)
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
            state.clear()
            raise HTTPException(422, str(exc)) from exc
        state.image = image
        state.layout = layout
        state.source_id = str(uuid4())
        return {
            "sourceId": state.source_id,
            "sourceSize": layout.source_size,
            "header": layout.header,
            "cards": layout.cards,
            "sizes": SIZE_PRESETS,
        }

    @app.get("/api/image")
    def source_preview():
        if state.image is None:
            raise HTTPException(404, "no image loaded")
        output = io.BytesIO()
        state.image.save(output, format="PNG")
        return Response(output.getvalue(), media_type="image/png")

    @app.get("/api/references/{reference_id}/image")
    def reference_image(reference_id: int):
        try:
            data = read_manifest(state.manifest, missing_ok=True)
            entry = next(item for item in data["references"] if item["id"] == reference_id)
            path = (state.manifest.parent / entry["imagePath"]).resolve()
            if not path.is_relative_to(state.manifest.parent.resolve()):
                raise ValueError("invalid image path")
            return Response(path.read_bytes(), media_type="image/png")
        except StopIteration as exc:
            raise HTTPException(404, "reference not found") from exc
        except (OSError, ValueError) as exc:
            raise HTTPException(500, str(exc)) from exc

    @app.get("/api/candidates/{card_index}/{width}/{height}/{candidate_index}")
    def candidate(card_index: int, width: int, height: int, candidate_index: int):
        if state.image is None or state.layout is None:
            raise HTTPException(409, "no image loaded")
        try:
            item = generate_candidates(state.image, state.layout, card_index, (width, height))[
                candidate_index
            ]
        except (ValueError, IndexError) as exc:
            raise HTTPException(422, str(exc)) from exc
        output = io.BytesIO()
        item.image.save(output, format="PNG")
        return Response(
            output.getvalue(),
            media_type="image/png",
            headers={"X-Crop": ",".join(map(str, item.crop))},
        )

    @app.post("/api/references")
    async def save(request: Request):
        if int(request.headers.get("content-length", "0")) > 4096:
            raise HTTPException(413, "request too large")
        body = await request.body()
        if len(body) > 4096:
            raise HTTPException(413, "request too large")
        try:
            payload = json.loads(body)
            name = payload["characterName"]
            appearance = payload.get("appearanceId")
            card = payload["cardIndex"]
            size = tuple(payload["size"])
            index = payload["candidateIndex"]
            source_id = payload["sourceId"]
            if not isinstance(name, str) or type(card) is not int or type(index) is not int:
                raise ValueError("invalid selection")
            if appearance is not None and (type(appearance) is not int or appearance <= 0):
                raise ValueError("invalid appearanceId")
            if payload.get("confirmed") is not True:
                raise ValueError("confirmation required")
            if name not in {item["name"] for item in state.names()}:
                raise ValueError("character is not in scenarios")
            if state.image is None or state.layout is None or source_id != state.source_id:
                raise ValueError("source image is unavailable")
            item = generate_candidates(state.image, state.layout, card, size)[index]
        except (KeyError, TypeError, IndexError, ValueError, json.JSONDecodeError) as exc:
            raise HTTPException(422, str(exc)) from exc
        async with state.saving:
            try:
                if state.image is None or source_id != state.source_id:
                    raise ValueError("source image is unavailable")
                data = read_manifest(state.manifest, missing_ok=True)
                rid, cid, aid, sample, image_path = allocate(data, name, appearance)
                source = {
                    "kind": "statusScreenshot",
                    "sourceId": source_id,
                    "sourceSize": list(state.image.size),
                    "crop": list(item.crop),
                }
                source_url = payload.get("sourceUrl")
                if source_url is not None:
                    if not isinstance(source_url, str) or len(source_url) > 2048:
                        raise ValueError("invalid sourceUrl")
                    source["sourceUrl"] = source_url
                entry = {
                    "id": rid,
                    "characterId": cid,
                    "appearanceId": aid,
                    "sampleNumber": sample,
                    "imagePath": image_path,
                    "imageSize": list(item.image.size),
                    "source": source,
                    "reviewed": True,
                }
                target = save_reference(state.manifest, data, entry, item.image)
            except (OSError, ValueError) as exc:
                raise HTTPException(422, str(exc)) from exc
            state.clear()
            return {"reference": entry, "saved": target.name}

    @app.delete("/api/image")
    def discard():
        state.clear()
        return {"discarded": True}

    @app.get("/api/events")
    async def events(request: Request):
        async def stream():
            state.had_connection = True
            state.connections += 1
            state.connected.set()
            state.disconnected.clear()
            try:
                while not await request.is_disconnected():
                    yield ": heartbeat\n\n"
                    await asyncio.sleep(1)
            finally:
                state.connections -= 1
                if state.connections == 0:
                    state.disconnected.set()

        return StreamingResponse(stream(), media_type="text/event-stream")

    return app
