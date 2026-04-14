"""
utils/data_ingestion.py
-----------------------
Reads JSON lines from ESP32 over serial port and appends to a
rolling 24-hour in-memory DataFrame.  Falls back to synthetic
simulation when no serial device is attached (demo / dev mode).
"""

import json
import random
import threading
import time
from collections import deque
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

try:
    import serial  # pyserial
    SERIAL_AVAILABLE = True
except ImportError:
    SERIAL_AVAILABLE = False


# ── Constants ────────────────────────────────────────────────────────────────
MAX_ROWS        = 24 * 60 * 60   # one reading per second, 24 h rolling window
BASELINE = {
    "turbidity": 45.0,   # NTU  – typical settled effluent
    "tds":       320.0,  # ppm
    "level":     55.0,   # %
    "flow":      12.0,   # L/min
}

# ── Thread-safe ring buffer ───────────────────────────────────────────────────
_lock   = threading.Lock()
_buffer: deque[dict] = deque(maxlen=MAX_ROWS)


# ── Synthetic data generator (demo mode) ─────────────────────────────────────
def _synthetic_record(t: datetime) -> dict:
    """Simulate realistic STP sensor readings with slow drift + spikes."""
    hour = t.hour
    # Higher inflow during morning (6–9) and evening (17–20)
    peak = 1.0 + 0.4 * (np.exp(-((hour - 7.5) ** 2) / 4)
                        + np.exp(-((hour - 18.5) ** 2) / 4))

    def noisy(base, scale, peak_mult=1.0, lo=0.0, hi=1e9):
        return float(np.clip(base * peak_mult + random.gauss(0, scale), lo, hi))

    # Occasional anomaly spike (1 % chance per second)
    spike = random.random() < 0.01
    return {
        "timestamp": t.isoformat(),
        "turbidity": noisy(BASELINE["turbidity"], 5, peak, 0, 3000) * (3 if spike else 1),
        "tds":       noisy(BASELINE["tds"],       15, 1.0,  0, 5000),
        "level":     noisy(BASELINE["level"],      2, peak, 0, 100),
        "flow":      noisy(BASELINE["flow"],        1, peak, 0, 200),
        "source":    "simulated",
    }


def _simulation_loop(interval: float = 1.0):
    """Background thread – pushes one synthetic record per `interval` seconds."""
    while True:
        rec = _synthetic_record(datetime.now())
        with _lock:
            _buffer.append(rec)
        time.sleep(interval)


# ── Serial reader ─────────────────────────────────────────────────────────────
def _serial_loop(port: str, baud: int = 115200):
    """Background thread – reads JSON lines from ESP32 serial port."""
    while True:
        try:
            with serial.Serial(port, baud, timeout=2) as ser:
                while True:
                    line = ser.readline().decode("utf-8", errors="replace").strip()
                    if not line or line.startswith("{\"status\""):
                        continue
                    try:
                        data = json.loads(line)
                        rec = {
                            "timestamp": datetime.now().isoformat(),
                            "turbidity": float(data.get("turbidity", 0)),
                            "tds":       float(data.get("tds",       0)),
                            "level":     float(data.get("level",     0)),
                            "flow":      float(data.get("flow",      0)),
                            "source":    "hardware",
                        }
                        with _lock:
                            _buffer.append(rec)
                    except (json.JSONDecodeError, KeyError, ValueError):
                        pass
        except Exception as exc:
            print(f"[serial] Error: {exc}  – retrying in 5 s")
            time.sleep(5)


# ── Public API ────────────────────────────────────────────────────────────────
_started = False

def start_ingestion(port: str | None = None, baud: int = 115200,
                    demo: bool = True):
    """
    Start background ingestion.

    Parameters
    ----------
    port  : Serial port string, e.g. '/dev/ttyUSB0' or 'COM3'.
            If None and demo=True, uses synthetic data.
    baud  : Baud rate (must match ESP32 firmware – 115200).
    demo  : Force simulation even if port is given.
    """
    global _started
    if _started:
        return
    _started = True

    # Pre-fill 60 minutes of historical synthetic data so charts
    # render immediately on first launch
    now = datetime.now()
    for i in range(3600, 0, -1):
        t = now - timedelta(seconds=i)
        _buffer.append(_synthetic_record(t))

    if port and SERIAL_AVAILABLE and not demo:
        t = threading.Thread(target=_serial_loop, args=(port, baud),
                             daemon=True)
    else:
        t = threading.Thread(target=_simulation_loop, daemon=True)
    t.start()


def get_dataframe() -> pd.DataFrame:
    """Return a snapshot of the rolling buffer as a sorted DataFrame."""
    with _lock:
        if not _buffer:
            return pd.DataFrame(columns=["timestamp","turbidity","tds","level","flow"])
        df = pd.DataFrame(list(_buffer))
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("timestamp").reset_index(drop=True)
    # Rolling 24-hour window
    cutoff = df["timestamp"].max() - timedelta(hours=24)
    return df[df["timestamp"] >= cutoff]


def get_latest() -> dict:
    """Return the most recent sensor reading."""
    with _lock:
        if not _buffer:
            return {}
        return dict(_buffer[-1])
