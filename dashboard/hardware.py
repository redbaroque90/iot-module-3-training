"""Thread-safe hardware boundary with fail-safe pump control."""

from __future__ import annotations

from dataclasses import dataclass, asdict
import random
import threading
import time

from .config import Settings


@dataclass
class Readings:
    temperature_c: float
    humidity_percent: float
    soil_raw: int
    soil_moisture_percent: float
    pump_on: bool
    hardware_mode: str

    def as_dict(self) -> dict:
        return asdict(self)


class HardwareController:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._state_lock = threading.RLock()
        self._pump_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._pump_on = False
        self._closed = False
        self._relay = self._led = self._bus = None

    def initialize(self) -> None:
        self.settings.validate()
        if self.settings.hardware_mode == "mock":
            return

        from gpiozero import LED, OutputDevice
        from smbus2 import SMBus

        try:
            self._bus = SMBus(1)
            self._led = LED(self.settings.led_pin)
            self._relay = OutputDevice(
                self.settings.relay_pin,
                active_high=self.settings.relay_active_high,
                initial_value=False,
            )
            self.pump_off()
            self.readings()
        except Exception:
            self.close()
            raise

    def _read_sht31(self) -> tuple[float, float]:
        from smbus2 import i2c_msg

        self._bus.i2c_rdwr(
            i2c_msg.write(self.settings.sht31_address, [0x24, 0x00])
        )
        time.sleep(0.02)
        message = i2c_msg.read(self.settings.sht31_address, 6)
        self._bus.i2c_rdwr(message)
        data = list(message)
        raw_temperature = (data[0] << 8) | data[1]
        raw_humidity = (data[3] << 8) | data[4]
        temperature = -45.0 + (175.0 * raw_temperature / 65535.0)
        humidity = 100.0 * raw_humidity / 65535.0
        return temperature, humidity

    def _read_ads1115_a0(self) -> int:
        # Single-shot A0-to-GND, +/-4.096 V range, 128 samples/s.
        self._bus.write_i2c_block_data(
            self.settings.ads1115_address, 0x01, [0xC3, 0x83]
        )
        time.sleep(0.01)
        data = self._bus.read_i2c_block_data(
            self.settings.ads1115_address, 0x00, 2
        )
        raw = (data[0] << 8) | data[1]
        return raw - 65536 if raw & 0x8000 else raw

    def _moisture(self, raw: int) -> float:
        value = (
            (self.settings.dry_value - raw)
            / (self.settings.dry_value - self.settings.wet_value)
            * 100
        )
        return max(0.0, min(100.0, value))

    def readings(self) -> Readings:
        with self._state_lock:
            if self._closed:
                raise RuntimeError("Hardware controller is closed")
            if self.settings.hardware_mode == "mock":
                raw = random.randint(
                    min(self.settings.dry_value, self.settings.wet_value),
                    max(self.settings.dry_value, self.settings.wet_value),
                )
                temperature, humidity = 27.5, 70.0
            else:
                temperature, humidity = self._read_sht31()
                raw = self._read_ads1115_a0()
            if not -40 <= temperature <= 125 or not 0 <= humidity <= 100:
                raise RuntimeError("Implausible sensor reading")
            return Readings(
                round(temperature, 2),
                round(humidity, 2),
                raw,
                round(self._moisture(raw), 1),
                self._pump_on,
                self.settings.hardware_mode,
            )

    def _set_outputs(self, on: bool) -> None:
        with self._state_lock:
            if self.settings.hardware_mode == "real":
                if self._relay is not None:
                    (self._relay.on if on else self._relay.off)()
                if self._led is not None:
                    (self._led.on if on else self._led.off)()
            self._pump_on = on

    def run_pump(self, duration: float) -> float:
        if not 0 < duration <= self.settings.max_pump_seconds:
            raise ValueError("Duration outside configured safe range")
        if not self._pump_lock.acquire(blocking=False):
            raise RuntimeError("Pump is already active")
        self._stop_event.clear()
        started = time.monotonic()
        try:
            self._set_outputs(True)
            self._stop_event.wait(duration)
        finally:
            self._set_outputs(False)
            self._pump_lock.release()
        return round(time.monotonic() - started, 2)

    def pump_off(self) -> None:
        self._stop_event.set()
        self._set_outputs(False)

    @property
    def pump_on(self) -> bool:
        with self._state_lock:
            return self._pump_on

    def close(self) -> None:
        self._stop_event.set()
        with self._state_lock:
            if self._closed:
                return
            try:
                self._set_outputs(False)
            finally:
                for device in (self._relay, self._led):
                    if device is not None:
                        device.close()
                if self._bus is not None:
                    self._bus.close()
                self._closed = True
