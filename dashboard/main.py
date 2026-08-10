"""FastAPI smart-irrigation training dashboard."""

from contextlib import asynccontextmanager
import asyncio
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from .config import Settings
from .hardware import HardwareController

BASE = Path(__file__).resolve().parent
settings = Settings()
hardware = HardwareController(settings)


@asynccontextmanager
async def lifespan(app: FastAPI):
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


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    if settings.api_key and x_api_key != settings.api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")


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
        return (await asyncio.to_thread(hardware.readings)).as_dict()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Sensor read failed: {exc}") from exc


@app.post("/api/pump/timed", dependencies=[Depends(require_api_key)])
async def pump_timed(request: PumpRequest):
    if request.duration > settings.max_pump_seconds:
        raise HTTPException(
            status_code=422,
            detail=f"Maximum duration is {settings.max_pump_seconds} seconds",
        )
    try:
        elapsed = await asyncio.to_thread(hardware.run_pump, request.duration)
        return {"status": "completed", "elapsed_seconds": elapsed, "pump_on": False}
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/pump/off", dependencies=[Depends(require_api_key)])
async def pump_off():
    await asyncio.to_thread(hardware.pump_off)
    return {"status": "off", "pump_on": False}


@app.post("/api/pump/on", status_code=410)
async def pump_on_disabled():
    raise HTTPException(status_code=410, detail="Indefinite pump operation is disabled")
