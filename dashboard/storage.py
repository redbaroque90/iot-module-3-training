"""SQLite persistence for sensor history and pump activity."""

from __future__ import annotations

from pathlib import Path
import sqlite3
import threading
import time


class SensorStore:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS sensor_readings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    recorded_at INTEGER NOT NULL,
                    temperature_c REAL NOT NULL,
                    humidity_percent REAL NOT NULL,
                    soil_raw INTEGER NOT NULL,
                    soil_moisture_percent REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_sensor_recorded_at
                    ON sensor_readings(recorded_at);
                CREATE TABLE IF NOT EXISTS pump_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    recorded_at INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    duration_seconds REAL
                );
                CREATE TABLE IF NOT EXISTS app_settings (
                    setting_key TEXT PRIMARY KEY,
                    setting_value TEXT NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    def add_reading(self, reading: dict) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO sensor_readings (
                    recorded_at, temperature_c, humidity_percent,
                    soil_raw, soil_moisture_percent
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    int(time.time()),
                    reading["temperature_c"],
                    reading["humidity_percent"],
                    reading["soil_raw"],
                    reading["soil_moisture_percent"],
                ),
            )

    def history(self, limit: int = 120) -> list[dict]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                """
                SELECT recorded_at, temperature_c, humidity_percent,
                       soil_raw, soil_moisture_percent
                FROM sensor_readings
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in reversed(rows)]

    def add_pump_event(self, action: str, duration: float | None = None) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                "INSERT INTO pump_events (recorded_at, action, duration_seconds) VALUES (?, ?, ?)",
                (int(time.time()), action, duration),
            )

    def calibration(self, default_dry: int, default_wet: int) -> tuple[int, int]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                "SELECT setting_key, setting_value FROM app_settings WHERE setting_key IN (?, ?)",
                ("soil_dry", "soil_wet"),
            ).fetchall()
        values = {row["setting_key"]: int(row["setting_value"]) for row in rows}
        return values.get("soil_dry", default_dry), values.get("soil_wet", default_wet)

    def save_calibration(self, dry_value: int, wet_value: int) -> None:
        now = int(time.time())
        with self._lock, self._connect() as connection:
            connection.executemany(
                """
                INSERT INTO app_settings (setting_key, setting_value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(setting_key) DO UPDATE SET
                    setting_value=excluded.setting_value,
                    updated_at=excluded.updated_at
                """,
                (("soil_dry", str(dry_value), now), ("soil_wet", str(wet_value), now)),
            )
