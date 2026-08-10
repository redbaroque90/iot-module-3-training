"""FastAPI smart-irrigation training dashboard."""

from __future__ import annotations

from contextlib import asynccontextmanager
import asyncio
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from .config import Settings
from .hardware import HardwareController
from .storage import SensorStore

BASE = Path(__file__).resolve().parent
settings = Settings()
hardware = HardwareController(settings)
store = SensorStore(BASE / "data" / "irrigation.db")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await asyncio.to_thread(store.initialize)
    dry_value, wet_value = await asyncio.to_thread(
        store.calibration, settings.dry_value, settings.wet_value
    )
    await asyncio.to_thread(hardware.set_calibration, dry_value, wet_value)
    await asyncio.to_thread(hardware.initialize)
    try:
        yield
    finally:
        await asyncio.to_thread(hardware.pump_off)
        await asyncio.to_thread(hardware.close)


app = FastAPI(
    title="IoT Smart-Irrigation Training Dashboard",
    lifespan=lifespan,
    docs_url="/docs" if settings.enable_docs else None,
    redoc_url=None,
)
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
templates = Jinja2Templates(directory=BASE / "templates")


class PumpRequest(BaseModel):
    duration: float = Field(gt=0)


class CalibrationRequest(BaseModel):
    dry_value: int = Field(ge=-32768, le=32767)
    wet_value: int = Field(ge=-32768, le=32767)


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "mode": settings.hardware_mode,
            "default_duration": settings.default_pump_seconds,
            "max_duration": settings.max_pump_seconds,
        },
    )


@app.get("/health")
async def health():
    try:
        reading = await asyncio.to_thread(hardware.readings)
        return {"status": "ready", "hardware_mode": reading.hardware_mode, "pump_on": reading.pump_on}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Hardware unavailable: {exc}") from exc


@app.get("/api/readings")
async def readings():
    try:
        reading = (await asyncio.to_thread(hardware.readings)).as_dict()
        await asyncio.to_thread(store.add_reading, reading)
        return reading
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Sensor read failed: {exc}") from exc


@app.get("/api/history")
async def history(limit: int = 120):
    safe_limit = max(10, min(limit, 500))
    return {"readings": await asyncio.to_thread(store.history, safe_limit)}


@app.get("/api/config/calibration")
async def get_calibration():
    return await asyncio.to_thread(hardware.calibration)


@app.put("/api/config/calibration")
async def update_calibration(request: CalibrationRequest):
    if request.dry_value == request.wet_value:
        raise HTTPException(status_code=422, detail="Dry and wet values must be different")
    await asyncio.to_thread(hardware.set_calibration, request.dry_value, request.wet_value)
    await asyncio.to_thread(store.save_calibration, request.dry_value, request.wet_value)
    return {"status": "saved", **(await asyncio.to_thread(hardware.calibration))}


@app.post("/api/pump/timed")
async def pump_timed(request: PumpRequest):
    if request.duration > settings.max_pump_seconds:
        raise HTTPException(
            status_code=422,
            detail=f"Maximum duration is {settings.max_pump_seconds} seconds",
        )
    try:
        elapsed = await asyncio.to_thread(hardware.run_pump, request.duration)
        await asyncio.to_thread(store.add_pump_event, "manual_timed", elapsed)
        return {"status": "completed", "elapsed_seconds": elapsed, "pump_on": False}
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/pump/off")
async def pump_off():
    await asyncio.to_thread(hardware.pump_off)
    await asyncio.to_thread(store.add_pump_event, "manual_stop")
    return {"status": "off", "pump_on": False}


@app.post("/api/pump/on", status_code=410)
async def pump_on_disabled():
    raise HTTPException(status_code=410, detail="Indefinite pump operation is disabled")
