"""Environment-backed dashboard configuration."""

from dataclasses import dataclass
import os


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)), 0)


@dataclass(frozen=True)
class Settings:
    hardware_mode: str = os.getenv("IOT_HARDWARE_MODE", "mock").lower()
    dry_value: int = _int("IOT_DRY_VALUE", 22000)
    wet_value: int = _int("IOT_WET_VALUE", 9000)
    sht31_address: int = _int("IOT_SHT31_ADDRESS", 0x44)
    ads1115_address: int = _int("IOT_ADS1115_ADDRESS", 0x48)
    led_pin: int = _int("IOT_LED_PIN", 17)
    relay_pin: int = _int("IOT_RELAY_PIN", 27)
    relay_active_high: bool = _bool("IOT_RELAY_ACTIVE_HIGH", True)
    default_pump_seconds: float = float(os.getenv("IOT_DEFAULT_PUMP_SECONDS", "3"))
    max_pump_seconds: float = float(os.getenv("IOT_MAX_PUMP_SECONDS", "5"))
    api_key: str = os.getenv("IOT_API_KEY", "")
    enable_docs: bool = _bool("IOT_ENABLE_DOCS", False)

    def validate(self) -> None:
        if self.hardware_mode not in {"mock", "real"}:
            raise ValueError("IOT_HARDWARE_MODE must be mock or real")
        if self.dry_value == self.wet_value:
            raise ValueError("Dry and wet calibration values must differ")
        if self.sht31_address not in {0x44, 0x45}:
            raise ValueError("SHT31 address must be 0x44 or 0x45")
        if not 0x48 <= self.ads1115_address <= 0x4B:
            raise ValueError("ADS1115 address must be between 0x48 and 0x4B")
        if not 0 < self.default_pump_seconds <= self.max_pump_seconds <= 5:
            raise ValueError("Pump duration must satisfy 0 < default <= maximum <= 5")
        if self.hardware_mode == "real" and len(self.api_key) < 16:
            raise ValueError("Real hardware mode requires IOT_API_KEY of at least 16 characters")
