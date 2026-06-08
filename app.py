#!/usr/bin/env python3
"""
NeuroDrive — EEG Anxiety Monitoring System
===========================================
Streams raw EEG electrode voltages from Muse headband via LSL,
computes band powers and anxiety estimate server-side using
sliding-window FFT, and displays on a browser dashboard via Socket.IO.

Architecture:
  - MuseStreamManager (Singleton) — one LSL inlet, one acquisition thread
  - Flask + Socket.IO — serves dashboard and streams real-time data
  - Raw electrode voltages (AF7, AF8, TP9, TP10) + computed band powers
    + anxiety score all sent to the browser in every update
  - Session data saved per-row to CSV (survives crashes)
"""

from __future__ import annotations

import csv
import math
import os
import sys
import threading
import time
import webbrowser
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

try:
    import pylsl
    StreamInlet = getattr(pylsl, "StreamInlet", None)
    resolve_stream = (
        getattr(pylsl, "resolve_stream", None)
        or getattr(pylsl, "resolve_streams", None)
        or getattr(pylsl, "resolve", None)
    )
except Exception:
    StreamInlet = None
    resolve_stream = None

from flask import Flask, render_template, Response, jsonify, request
from flask_socketio import SocketIO, emit
from utils.anxiety_calculator import calculate_anxiety_estimate

try:
    from utils.ml_predictor import MlPredictor
except ImportError:
    MlPredictor = None


# ============================================================================
# Constants
# ============================================================================

APP_NAME = "NeuroDrive"
TARGET_HZ = 20.0
TARGET_INTERVAL = 1.0 / TARGET_HZ
FFT_WINDOW_SIZE = 256
STREAM_DISCOVERY_TIMEOUT = 10.0
STREAM_STALE_SECONDS = 4.0
EMA_BAND_ALPHA = 0.10
EMA_ANXIETY_ALPHA = 0.05
DATA_DIR_NAME = "data"
CSV_PREFIX = "neurodrive_session"
DASHBOARD_URL = "http://localhost:5000"

# Normalised electrode labels we stream to the dashboard
EEG_ELECTRODES = ("tp9", "af7", "af8", "tp10")

ANXIETY_LABEL_SCALE: Dict[str, float] = {
    "low": 0.0,
    "medium": 50.0,
    "high": 100.0,
}


# ============================================================================
# LSL helpers (module-level)
# ============================================================================


def _resolve_lsl_streams(timeout: Optional[float] = None) -> List[Any]:
    if resolve_stream is None:
        return []
    try:
        if timeout is None:
            return list(resolve_stream() or [])
        try:
            return list(resolve_stream(timeout=timeout) or [])
        except TypeError:
            return list(resolve_stream(wait_time=timeout) or [])
    except Exception:
        return []


def _stream_value(stream_info: Any, field_name: str, default: Any = "") -> Any:
    try:
        value = getattr(stream_info, field_name, default)
        if callable(value):
            value = value()
        return default if value is None else value
    except Exception:
        return default


def _looks_like_muse_stream(stream_info: Any) -> bool:
    name = str(_stream_value(stream_info, "name", "")).lower()
    stream_type = str(_stream_value(stream_info, "type", "")).lower()
    if "muse" in name or "muse" in stream_type:
        return True
    channel_count = int(_stream_value(stream_info, "channel_count", 0) or 0)
    if "eeg" in stream_type and channel_count >= 4:
        return True
    return False


# ============================================================================
# StreamRecord
# ============================================================================


@dataclass
class StreamRecord:
    sequence: int
    timestamp_iso: str
    timestamp_epoch: float
    af7: float
    af8: float
    tp9: float
    tp10: float
    right_aux: float
    delta: float
    theta: float
    alpha: float
    beta: float
    gamma: float
    anxiety: float
    anxiety_label: str
    anxiety_method: str
    theta_beta_ratio: float
    alpha_sum_ratio: float
    high_freq_ratio: float
    stream_name: str

    def to_row(self) -> List[str]:
        return [
            str(self.sequence),
            self.timestamp_iso,
            f"{self.timestamp_epoch:.6f}",
            f"{self.af7:.6f}",
            f"{self.af8:.6f}",
            f"{self.tp9:.6f}",
            f"{self.tp10:.6f}",
            f"{self.right_aux:.6f}",
            f"{self.delta:.6f}",
            f"{self.theta:.6f}",
            f"{self.alpha:.6f}",
            f"{self.beta:.6f}",
            f"{self.gamma:.6f}",
            f"{self.anxiety:.6f}",
            self.anxiety_label,
            self.anxiety_method,
            f"{self.theta_beta_ratio:.6f}",
            f"{self.alpha_sum_ratio:.6f}",
            f"{self.high_freq_ratio:.6f}",
            self.stream_name,
        ]

    @staticmethod
    def csv_header() -> List[str]:
        return [
            "sequence", "timestamp_iso", "timestamp_epoch",
            "af7", "af8", "tp9", "tp10", "right_aux",
            "delta", "theta", "alpha", "beta", "gamma",
            "anxiety", "anxiety_label", "anxiety_method",
            "theta_beta_ratio", "alpha_sum_ratio", "high_freq_ratio",
            "stream_name",
        ]


# ============================================================================
# MuseStreamManager — SINGLETON
# ============================================================================


class MuseStreamManager:
    """
    SINGLETON manager for the Muse LSL stream.

    Guarantees:
      - Exactly ONE instance per process
      - Exactly ONE active LSL StreamInlet at any moment
      - Dashboards attach as passive listeners (never create new connections)
      - Sliding-window FFT for band-power extraction
      - Per-row CSV persistence (survives crashes)
    """

    _instance: Optional["MuseStreamManager"] = None
    _instance_lock = threading.Lock()

    def __new__(cls, *args: Any, **kwargs: Any) -> "MuseStreamManager":
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    @staticmethod
    def get_instance() -> Optional["MuseStreamManager"]:
        return MuseStreamManager._instance

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def __init__(self, data_dir: Path) -> None:
        if hasattr(self, "_initialised"):
            return
        self._initialised = True

        # Threading
        self._stop_event = threading.Event()
        self._lock = threading.RLock()
        self._inlet_lock = threading.Lock()

        # Data
        self._data_dir = data_dir
        self._records: List[StreamRecord] = []
        self._ml_predictor: Optional[Any] = None
        if MlPredictor is not None:
            try:
                self._ml_predictor = MlPredictor.get_instance()
                if not self._ml_predictor.available:
                    self._ml_predictor = None
            except Exception:
                self._ml_predictor = None
        self._current_sequence = 0
        self._latest_payload: Optional[Dict[str, Any]] = None
        self._latest_band_powers: Dict[str, float] = {
            "delta": 0.0, "theta": 0.0, "alpha": 0.0,
            "beta": 0.0, "gamma": 0.0,
        }
        self._band_ema: Dict[str, float] = {
            "delta": 0.0, "theta": 0.0, "alpha": 0.0, "beta": 0.0, "gamma": 0.0,
        }
        self._anxiety_ema: float = 0.0

        # Sliding FFT window (deque auto-evicts oldest when maxlen reached)
        self._raw_eeg_window: deque = deque(maxlen=FFT_WINDOW_SIZE)

        # LSL state
        self._is_running = False
        self._stream_active = False
        self._status = "Idle"
        self._inlet: Any = None
        self._stream_name = ""
        self._stream_type = ""
        self._sample_rate = 256.0
        self._sample_count = 0
        self._last_emit_time = 0.0

        # CSV file handle (open during session)
        self._csv_path: Optional[Path] = None
        self._csv_file: Any = None
        self._csv_writer: Any = None

        # SocketIO & listeners
        self._socketio: Any = None
        self._emission_listeners: Set[Any] = set()

        self._data_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # SocketIO wiring
    # ------------------------------------------------------------------

    def set_socketio(self, sio: Any) -> None:
        self._socketio = sio

    def attach_listener(self, listener: Any) -> None:
        with self._lock:
            self._emission_listeners.add(listener)

    def detach_listener(self, listener: Any) -> None:
        with self._lock:
            self._emission_listeners.discard(listener)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> bool:
        with self._lock:
            if self._is_running:
                return True
            if self._inlet is not None:
                self._close_inlet_unlocked()
            self._is_running = True

        thread = threading.Thread(target=self._run, daemon=True, name="muse-stream")
        thread.start()
        return True

    def stop(self) -> None:
        with self._lock:
            was_running = self._is_running
            self._is_running = False
            self._stream_active = False
        if was_running:
            self._stop_event.set()
        self._close_inlet()
        self._close_csv()

    @property
    def is_streaming(self) -> bool:
        with self._lock:
            return self._stream_active

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._is_running

    @property
    def status(self) -> str:
        with self._lock:
            return self._status

    def get_latest_payload(self) -> Optional[Dict[str, Any]]:
        with self._lock:
            if self._latest_payload is None:
                return None
            return dict(self._latest_payload)

    def stream_count(self) -> int:
        with self._lock:
            return self._sample_count

    def state_snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "is_running": self._is_running,
                "status": self._status,
                "stream_active": self._stream_active,
                "stream_name": self._stream_name,
                "sample_count": self._sample_count,
                "sample_rate": self._sample_rate,
                "records_buffered": len(self._records),
                "latest_payload": self.get_latest_payload(),
            }

    # ------------------------------------------------------------------
    # Main acquisition thread
    # ------------------------------------------------------------------

    def _run(self) -> None:
        self._stop_event.clear()
        self._reset_acquisition_state()
        self._set_status("Starting...")

        if StreamInlet is None or resolve_stream is None:
            self._set_status("LSL unavailable — pylsl not installed.")
            self._close_csv()
            self._mark_stopped()
            return

        # Outer loop: stream discovery & connection
        consecutive_failures = 0
        while not self._stop_event.is_set():
            stream_info = self._discover_muse_stream()
            if stream_info is None:
                consecutive_failures += 1
                backoff = min(1.0 * (2 ** (consecutive_failures - 1)), 8.0)
                self._set_status(f"Waiting for Muse stream... (attempt {consecutive_failures}, retrying in {backoff:.0f}s)")
                self._sleep_with_stop(backoff)
                continue

            self._stream_name = self._safe_call(stream_info, "name") or "Muse Stream"
            self._stream_type = self._safe_call(stream_info, "type") or "LSL"
            self._sample_rate = self._safe_float(stream_info, "nominal_srate") or 256.0
            if self._sample_rate <= 0:
                self._sample_rate = 256.0

            self._raw_eeg_window.clear()
            self._set_status(f"Connected to {self._stream_name}")

            consecutive_failures = 0

            inlet_created = self._create_inlet(stream_info)
            if not inlet_created:
                consecutive_failures += 1
                backoff = min(1.0 * (2 ** (consecutive_failures - 1)), 8.0)
                self._set_status(f"Reconnecting... (attempt {consecutive_failures}, retrying in {backoff:.0f}s)")
                self._sleep_with_stop(backoff)
                continue

            labels = self._extract_channel_labels(stream_info)
            channel_count = self._safe_int(stream_info, "channel_count")
            print(f"[DEBUG] Stream: name={self._stream_name!r}, type={self._stream_type!r}")
            print(f"[DEBUG] Sample rate: {self._sample_rate} Hz, channels: {channel_count}")
            print(f"[DEBUG] Labels ({len(labels)}): {labels}")

            try:
                self._capture_loop(labels)
            except Exception as exc:
                self._set_status(f"Stream interrupted: {exc}")
            finally:
                self._close_inlet()

            consecutive_failures += 1
            backoff = min(1.0 * (2 ** (consecutive_failures - 1)), 8.0)
            self._set_status(f"Reconnecting... (attempt {consecutive_failures}, retrying in {backoff:.0f}s)")
            self._sleep_with_stop(backoff)

        self._close_csv()
        self._set_status("Session closed.")
        self._mark_stopped()

    # ------------------------------------------------------------------
    # Capture loop — the heart of the system
    # ------------------------------------------------------------------

    def _capture_loop(self, labels: List[str]) -> None:
        inlet = self._get_inlet_safe()
        if inlet is None:
            raise RuntimeError("No inlet available for capture loop")

        # Initialise per-session CSV
        self._init_csv()

        last_sample_time = time.monotonic()
        last_emit_time = time.perf_counter()
        debug_printed = 0
        debug_max = 5

        while not self._stop_event.is_set():
            current_inlet = self._get_inlet_safe()
            if current_inlet is None:
                raise RuntimeError("Inlet disappeared during capture")

            try:
                sample, timestamp = current_inlet.pull_sample(timeout=0.01)
            except Exception as exc:
                raise RuntimeError(str(exc)) from exc

            if sample is not None:
                sample_values = [self._coerce_float(v) for v in sample]
                self._sample_count += 1
                with self._lock:
                    self._latest_payload = self._build_payload(
                        sample_values, timestamp, labels
                    )
                last_sample_time = time.monotonic()

                if debug_printed < debug_max:
                    label_map = self._map_sample_values(sample_values, labels)
                    print(f"[DEBUG] Sample #{self._sample_count}: raw={[f'{v:.1f}' for v in sample_values[:5]]}")
                    print(f"[DEBUG]   labels={labels}, mapped_keys={list(label_map.keys())}")
                    print(f"[DEBUG]   payload af7={self._latest_payload.get('af7',0):.1f} af8={self._latest_payload.get('af8',0):.1f} tp9={self._latest_payload.get('tp9',0):.1f} tp10={self._latest_payload.get('tp10',0):.1f}")
                    print(f"[DEBUG]   band_powers delta={self._latest_payload.get('delta',0):.1f} theta={self._latest_payload.get('theta',0):.1f} alpha={self._latest_payload.get('alpha',0):.1f}")
                    print(f"[DEBUG]   anxiety={self._latest_payload.get('anxiety',0):.1f} label={self._latest_payload.get('anxiety_label','?')}")
                    debug_printed += 1
                    if debug_printed == debug_max:
                        fft_size = len(self._raw_eeg_window)
                        min_needed = max(64, int(self._sample_rate // 2))
                        print(f"[DEBUG] FFT window: {fft_size}/{min_needed} samples accumulated (will run FFT at {min_needed})")
                        bp = self._latest_band_powers
                        if any(v > 0 for v in bp.values()):
                            print(f"[DEBUG] Band powers active: {bp}")
                        else:
                            print(f"[DEBUG] Band powers still all zero — need {min_needed - fft_size} more samples")

            # --- Rate-limited broadcast (TARGET_HZ) ---
            now = time.perf_counter()
            payload = self._latest_payload
            if payload is not None and now - last_emit_time >= TARGET_INTERVAL:
                self._current_sequence += 1

                display = dict(payload)
                display["sequence"] = self._current_sequence

                record = self._record_from_payload(display)
                with self._lock:
                    self._records.append(record)

                self._broadcast_metrics(display)
                self._write_csv_row(record)

                last_emit_time = now
                self._last_emit_time = time.time()

                if self._current_sequence % 100 == 0:
                    bp = self._latest_band_powers
                    p = self._latest_payload or {}
                    print(f"[DEBUG] Seq#{self._current_sequence}: samples={self._sample_count} | bands d={bp.get('delta',0):.1f} t={bp.get('theta',0):.1f} a={bp.get('alpha',0):.1f} b={bp.get('beta',0):.1f} g={bp.get('gamma',0):.1f} | anxiety={p.get('anxiety',0):.1f} {p.get('anxiety_label','?')}")

            # Stale-stream detection
            if time.monotonic() - last_sample_time > STREAM_STALE_SECONDS:
                raise RuntimeError("No samples received for several seconds")

    # ------------------------------------------------------------------
    # Payload construction
    # ------------------------------------------------------------------

    def _build_payload(
        self, sample_values: Sequence[Any], timestamp: float, labels: Sequence[str]
    ) -> Dict[str, Any]:
        label_map = self._map_sample_values(sample_values, labels)

        # --- Raw electrode voltages ---
        af7 = label_map.get("af7", 0.0)
        af8 = label_map.get("af8", 0.0)
        tp9 = label_map.get("tp9", 0.0)
        tp10 = label_map.get("tp10", 0.0)
        right_aux = label_map.get("right_aux", 0.0)

        # --- Band powers via sliding-window FFT ---
        band_powers = self._extract_band_powers(sample_values, label_map)
        delta = band_powers.get("delta", 0.0)
        theta = band_powers.get("theta", 0.0)
        alpha = band_powers.get("alpha", 0.0)
        beta = band_powers.get("beta", 0.0)
        gamma = band_powers.get("gamma", 0.0)

        # --- Anxiety estimation ---
        estimate = calculate_anxiety_estimate(
            delta=delta, theta=theta, alpha=alpha, beta=beta, gamma=gamma,
        )

        anxiety = estimate.score
        anxiety_label = estimate.label
        anxiety_method = estimate.method
        model_active = "qeeg"

        if estimate.label != "no signal":
            self._anxiety_ema = EMA_ANXIETY_ALPHA * anxiety + (1 - EMA_ANXIETY_ALPHA) * self._anxiety_ema
            anxiety = self._anxiety_ema

        if self._ml_predictor is not None:
            try:
                self._ml_predictor.accumulate(
                    af7=af7, af8=af8, tp9=tp9, tp10=tp10, right_aux=right_aux,
                    delta=delta, theta=theta, alpha=alpha, beta=beta, gamma=gamma,
                )
                ml_result = self._ml_predictor.predict()
                if ml_result.get("available"):
                    anxiety = float(ml_result.get("score", anxiety))
                    anxiety = max(0.0, min(100.0, anxiety))
                    anxiety_method = "Camber RandomForest (119 features)"
                    model_active = "camber_rf"
            except Exception:
                pass

        timestamp_epoch = float(timestamp if timestamp is not None else time.time())
        timestamp_iso = datetime.now().isoformat(timespec="milliseconds")

        return {
            "sequence": self._current_sequence + 1,
            "timestamp_iso": timestamp_iso,
            "timestamp_epoch": timestamp_epoch,
            "af7": float(af7),
            "af8": float(af8),
            "tp9": float(tp9),
            "tp10": float(tp10),
            "right_aux": float(right_aux),
            "delta": float(delta),
            "theta": float(theta),
            "alpha": float(alpha),
            "beta": float(beta),
            "gamma": float(gamma),
            "anxiety": float(anxiety),
            "anxiety_label": anxiety_label,
            "anxiety_method": anxiety_method,
            "model_active": model_active,
            "theta_beta_ratio": float(estimate.theta_beta_ratio),
            "alpha_sum_ratio": float(estimate.alpha_sum_ratio),
            "high_freq_ratio": float(estimate.high_freq_ratio),
            "stream_name": self._stream_name,
            "sample_count": self._sample_count,
        }

    # ------------------------------------------------------------------
    # Band-power extraction (sliding-window FFT)
    # ------------------------------------------------------------------

    def _extract_band_powers(
        self, sample_values: Sequence[float], label_map: Dict[str, Any]
    ) -> Dict[str, float]:
        # If stream already provides pre-computed band powers, use them directly
        if any(
            label_map.get(k) is not None
            for k in ("delta", "theta", "alpha", "beta", "gamma")
        ):
            return {
                "delta": float(label_map.get("delta", 0.0)),
                "theta": float(label_map.get("theta", 0.0)),
                "alpha": float(label_map.get("alpha", 0.0)),
                "beta": float(label_map.get("beta", 0.0)),
                "gamma": float(label_map.get("gamma", 0.0)),
            }

        # Average EEG electrode values for this time-point
        eeg_values: List[float] = []
        for electrode in EEG_ELECTRODES:
            val = label_map.get(electrode)
            if val is not None and math.isfinite(float(val)):
                eeg_values.append(float(val))

        if not eeg_values:
            if self._sample_count <= 5:
                print(f"[DEBUG] _extract_band_powers: no EEG values found in label_map keys={list(label_map.keys())}")
            return dict(self._latest_band_powers)

        avg = sum(eeg_values) / len(eeg_values)
        self._raw_eeg_window.append(avg)

        # Minimum window size for meaningful FFT
        min_window = max(64, int(self._sample_rate // 2))
        if len(self._raw_eeg_window) < min_window:
            return dict(self._latest_band_powers)

        # Run FFT
        try:
            import numpy as np

            values = np.asarray(list(self._raw_eeg_window), dtype=float)
            values = values - np.mean(values)
            if not np.any(values):
                return dict(self._latest_band_powers)

            windowed = values * np.hanning(len(values))
            freqs = np.fft.rfftfreq(len(windowed), d=1.0 / self._sample_rate)
            spectrum = np.abs(np.fft.rfft(windowed)) ** 2

            bands = {
                "delta": (1.0, 4.0),
                "theta": (4.0, 8.0),
                "alpha": (8.0, 13.0),
                "beta": (13.0, 30.0),
                "gamma": (30.0, 45.0),
            }
            powers: Dict[str, float] = {}
            for key, (low, high) in bands.items():
                mask = (freqs >= low) & (freqs < high)
                powers[key] = float(np.mean(spectrum[mask])) if np.any(mask) else 0.0

            total = sum(powers.values())
            if total > 0:
                powers = {key: (value / total) * 100.0 for key, value in powers.items()}

            for key in ("delta", "theta", "alpha", "beta", "gamma"):
                if key in powers:
                    self._band_ema[key] = EMA_BAND_ALPHA * powers[key] + (1 - EMA_BAND_ALPHA) * self._band_ema[key]
                    powers[key] = self._band_ema[key]
            self._latest_band_powers = powers
            if any(v > 0 for v in powers.values()):
                print(f"[DEBUG] FFT RUN at sample #{self._sample_count}: { {k: f'{v:.1f}%' for k, v in powers.items()} }")
            return dict(powers)
        except Exception:
            return dict(self._latest_band_powers)

    # ------------------------------------------------------------------
    # Label mapping
    # ------------------------------------------------------------------

    def _map_sample_values(
        self, sample_values: Sequence[float], labels: Sequence[str]
    ) -> Dict[str, Any]:
        """Map raw LSL channel values to named keys (electrodes, bands, HR, anxiety)."""
        normalized: Dict[str, float] = {}
        for i, label in enumerate(labels):
            if i >= len(sample_values):
                break
            key = self._normalize_label(label)
            if key:
                normalized[key] = float(sample_values[i])

        mapped: Dict[str, Any] = {}

        # EEG electrode channels — try multiple matching strategies
        # Strategy 1: exact match (tp9, af7, af8, tp10)
        for electrode in EEG_ELECTRODES:
            if electrode in normalized:
                mapped[electrode] = normalized[electrode]

        # Strategy 2: eeg_ prefix (eeg_af7, eeg_tp9, etc.)
        if all(e not in mapped for e in EEG_ELECTRODES):
            for electrode in EEG_ELECTRODES:
                prefixed = f"eeg_{electrode}"
                if prefixed in normalized:
                    mapped[electrode] = normalized[prefixed]

        # Strategy 3: positional fallback — assume first 4 EEG channels
        # are in Muse standard order: TP9, AF7, AF8, TP10
        if all(e not in mapped for e in EEG_ELECTRODES):
            eeg_values = [
                (i, v) for i, (lbl, v) in enumerate(zip(labels, sample_values))
                if v is not None and math.isfinite(float(v))
                and not any(n in str(lbl).lower() for n in ("aux", "acc", "gyro", "ppg", "hr", "heart"))
            ]
            if len(eeg_values) >= 4:
                for pos, electrode in enumerate(EEG_ELECTRODES):
                    if pos < len(eeg_values):
                        mapped[electrode] = float(eeg_values[pos][1])

        # AUX / accelerometer
        for aux_key in ("right_aux", "aux", "right", "eeg_right_aux"):
            if aux_key in normalized and "right_aux" not in mapped:
                mapped["right_aux"] = normalized[aux_key]
                break

        # Pre-computed band powers (if stream provides them)
        for band in ("delta", "theta", "alpha", "beta", "gamma"):
            if band in normalized:
                mapped[band] = normalized[band]

        # Anxiety (if stream provides it)
        for anx_key in ("anxiety", "anxiety_score", "stress"):
            if anx_key in normalized:
                mapped["anxiety"] = normalized[anx_key]
                break

        return mapped

    # ------------------------------------------------------------------
    # Inlet management
    # ------------------------------------------------------------------

    def _create_inlet(self, stream_info: Any) -> bool:
        with self._inlet_lock:
            if self._inlet is not None:
                try:
                    self._inlet.close_stream()
                except Exception:
                    pass
                self._inlet = None

            try:
                self._inlet = StreamInlet(stream_info, max_buflen=16, recover=True)
                with self._lock:
                    self._stream_active = True
                return True
            except Exception as exc:
                self._set_status(f"Inlet creation failed: {exc}")
                self._inlet = None
                return False

    def _close_inlet(self) -> None:
        with self._inlet_lock:
            self._close_inlet_unlocked()

    def _close_inlet_unlocked(self) -> None:
        if self._inlet is not None:
            try:
                self._inlet.close_stream()
            except Exception:
                pass
            self._inlet = None
        with self._lock:
            self._stream_active = False

    def _get_inlet_safe(self) -> Optional[Any]:
        with self._inlet_lock:
            return self._inlet

    # ------------------------------------------------------------------
    # Stream discovery
    # ------------------------------------------------------------------

    def _discover_muse_stream(self) -> Optional[Any]:
        try:
            streams = _resolve_lsl_streams(timeout=STREAM_DISCOVERY_TIMEOUT)
        except Exception as exc:
            self._set_status(f"LSL discovery error: {exc}")
            return None

        if not streams:
            return None

        scored: List[Tuple[int, Any]] = []
        for stream in streams:
            score = self._score_stream(stream)
            scored.append((score, stream))

        scored.sort(key=lambda item: item[0], reverse=True)
        best_score, best_stream = scored[0]
        return best_stream if best_score > 0 else None

    def _score_stream(self, stream: Any) -> int:
        name = (self._safe_call(stream, "name") or "").lower()
        stream_type = (self._safe_call(stream, "type") or "").lower()
        labels_set = {label.lower() for label in self._extract_channel_labels(stream)}
        score = 0

        if "muse" in name:
            score += 100
        if "muse" in stream_type:
            score += 60
        if "eeg" in stream_type:
            score += 30
        if any(
            token in name
            for token in ("delta", "theta", "alpha", "beta", "gamma", "anxiety")
        ):
            score += 40
        if labels_set & {"delta", "theta", "alpha", "beta", "gamma", "anxiety"}:
            score += 80

        channel_count = self._safe_int(stream, "channel_count")
        if channel_count >= 6:
            score += 20
        elif channel_count >= 4:
            score += 10

        return score

    # ------------------------------------------------------------------
    # Broadcast helpers
    # ------------------------------------------------------------------

    def _set_status(self, status: str) -> None:
        with self._lock:
            self._status = status
        self._broadcast("status_update", {"status": status})

    def _broadcast_metrics(self, payload: Dict[str, Any]) -> None:
        self._broadcast("metrics_update", payload)

    def _broadcast(self, event: str, data: Dict[str, Any]) -> None:
        sio = self._socketio
        if sio is not None:
            try:
                sio.emit(event, data)
            except Exception:
                pass

        listeners: Set[Any] = set()
        with self._lock:
            listeners = set(self._emission_listeners)

        for listener in listeners:
            try:
                if hasattr(listener, "emit"):
                    listener.emit(event, data)
                elif callable(listener):
                    listener(event, data)
            except Exception:
                pass

    def _mark_stopped(self) -> None:
        with self._lock:
            self._is_running = False
            self._stream_active = False

    def _reset_acquisition_state(self) -> None:
        self._records.clear()
        self._current_sequence = 0
        self._latest_payload = None
        self._csv_path = None
        self._stream_name = ""
        self._stream_type = ""
        self._sample_rate = 256.0
        self._sample_count = 0
        self._last_emit_time = 0.0
        self._raw_eeg_window.clear()
        self._latest_band_powers = {
            "delta": 0.0, "theta": 0.0, "alpha": 0.0,
            "beta": 0.0, "gamma": 0.0,
        }
        self._band_ema = {"delta": 0.0, "theta": 0.0, "alpha": 0.0, "beta": 0.0, "gamma": 0.0}
        self._anxiety_ema = 0.0

    # ------------------------------------------------------------------
    # CSV persistence (per-row, survives crashes)
    # ------------------------------------------------------------------

    def _init_csv(self) -> None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._csv_path = self._data_dir / f"{CSV_PREFIX}_{timestamp}.csv"
        self._csv_file = self._csv_path.open("w", newline="", encoding="utf-8")
        self._csv_writer = csv.writer(self._csv_file)
        self._csv_writer.writerow(StreamRecord.csv_header())
        self._csv_file.flush()

    def _write_csv_row(self, record: StreamRecord) -> None:
        if self._csv_writer is not None and self._csv_file is not None:
            try:
                self._csv_writer.writerow(record.to_row())
                self._csv_file.flush()
            except Exception:
                pass

    def _close_csv(self) -> None:
        if self._csv_file is not None:
            try:
                self._csv_file.close()
            except Exception:
                pass
            self._csv_file = None
            self._csv_writer = None

    # ------------------------------------------------------------------
    # Record construction
    # ------------------------------------------------------------------

    def _record_from_payload(self, payload: Dict[str, Any]) -> StreamRecord:
        return StreamRecord(
            sequence=int(payload.get("sequence", 0)),
            timestamp_iso=str(payload.get("timestamp_iso", "")),
            timestamp_epoch=float(payload.get("timestamp_epoch", 0.0)),
            af7=float(payload.get("af7", 0.0)),
            af8=float(payload.get("af8", 0.0)),
            tp9=float(payload.get("tp9", 0.0)),
            tp10=float(payload.get("tp10", 0.0)),
            right_aux=float(payload.get("right_aux", 0.0)),
            delta=float(payload.get("delta", 0.0)),
            theta=float(payload.get("theta", 0.0)),
            alpha=float(payload.get("alpha", 0.0)),
            beta=float(payload.get("beta", 0.0)),
            gamma=float(payload.get("gamma", 0.0)),
            anxiety=float(payload.get("anxiety", 0.0)),
            anxiety_label=str(payload.get("anxiety_label", "")),
            anxiety_method=str(payload.get("anxiety_method", "")),
            theta_beta_ratio=float(payload.get("theta_beta_ratio", 0.0)),
            alpha_sum_ratio=float(payload.get("alpha_sum_ratio", 0.0)),
            high_freq_ratio=float(payload.get("high_freq_ratio", 0.0)),
            stream_name=str(payload.get("stream_name", "")),
        )

    # ------------------------------------------------------------------
    # Utility helpers
    # ------------------------------------------------------------------

    def _normalize_label(self, label: str) -> str:
        token = label.strip().lower().replace("-", "_").replace(" ", "_")

        # EEG electrodes
        if token in EEG_ELECTRODES:
            return token

        # AUX channel
        if token in {"right_aux", "right", "aux", "aux_right"}:
            return "right_aux"

        # Anxiety
        if token in {"anxiety", "anxiety_score", "stress"}:
            return "anxiety"

        # Band powers
        if token in {"delta", "band_delta", "spectral_delta"}:
            return "delta"
        if token in {"theta", "band_theta", "spectral_theta"}:
            return "theta"
        if token in {"alpha", "band_alpha", "spectral_alpha"}:
            return "alpha"
        if token in {"beta", "band_beta", "spectral_beta", "low_beta", "high_beta"}:
            return "beta"
        if token in {"gamma", "band_gamma", "spectral_gamma"}:
            return "gamma"

        return token

    def _coerce_float(self, value: Any) -> float:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return 0.0
            try:
                return float(text)
            except ValueError:
                return ANXIETY_LABEL_SCALE.get(text.lower(), 0.0)
        return 0.0

    def _safe_call(self, stream_info: Any, method_name: str) -> str:
        try:
            value = getattr(stream_info, method_name)()
            return "" if value is None else str(value)
        except Exception:
            return ""

    def _safe_int(self, stream_info: Any, method_name: str) -> int:
        try:
            return int(getattr(stream_info, method_name)() or 0)
        except Exception:
            return 0

    def _safe_float(self, stream_info: Any, method_name: str) -> float:
        try:
            return float(getattr(stream_info, method_name)() or 0.0)
        except Exception:
            return 0.0

    def _extract_channel_labels(self, stream_info: Any) -> List[str]:
        labels: List[str] = []
        try:
            import xml.etree.ElementTree as ET
            xml_text = stream_info.as_xml()
            root = ET.fromstring(xml_text)
            for node in root.findall(".//channels/channel"):
                label = (node.findtext("label") or "").strip()
                if label:
                    labels.append(label)
        except Exception:
            pass

        if labels:
            return labels

        channel_count = self._safe_int(stream_info, "channel_count")
        return [f"channel_{index + 1}" for index in range(max(channel_count, 0))]

    def _sleep_with_stop(self, duration: float) -> None:
        deadline = time.monotonic() + duration
        while not self._stop_event.is_set() and time.monotonic() < deadline:
            time.sleep(0.05)


# ============================================================================
# Flask Application
# ============================================================================

app = Flask(__name__, template_folder="templates")
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", os.urandom(24))
socketio = SocketIO(app, cors_allowed_origins="*")

@app.after_request
def add_no_cache_headers(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

from static import register_static_routes

register_static_routes(app)

stream_manager: Optional[MuseStreamManager] = None


# ----------------------------------------------------------------------------
# HTTP API
# ----------------------------------------------------------------------------


@app.route("/")
def index() -> str:
    return render_template("fypdashboard.html")


@app.route("/api/status")
def get_status():
    mgr = MuseStreamManager.get_instance()
    if mgr is not None:
        return jsonify(mgr.state_snapshot())
    return jsonify({
        "status": "Not initialised",
        "is_running": False,
        "stream_active": False,
    })


@app.route("/api/start", methods=["POST"])
def start_streaming():
    mgr = MuseStreamManager.get_instance()
    if mgr is None:
        return jsonify({"success": False, "message": "Stream manager not initialised"})

    if mgr.is_streaming:
        return jsonify({"success": True, "message": "Stream already active"})

    ok = mgr.start()
    if ok:
        return jsonify({"success": True, "message": "Stream started"})
    return jsonify({"success": False, "message": "Failed to start — check LSL support"})


@app.route("/api/stop", methods=["POST"])
def stop_streaming():
    mgr = MuseStreamManager.get_instance()
    if mgr is None:
        return jsonify({"success": False, "message": "Not initialised"})

    mgr.stop()
    return jsonify({"success": True, "message": "Stream stopped"})


@app.route("/api/sessions")
def get_sessions():
    data_dir = Path(DATA_DIR_NAME)
    if not data_dir.exists():
        return jsonify({"sessions": []})

    sessions = []
    for csv_file in data_dir.glob(f"{CSV_PREFIX}_*.csv"):
        sessions.append({
            "filename": csv_file.name,
            "path": str(csv_file),
            "size": csv_file.stat().st_size,
            "modified": datetime.fromtimestamp(
                csv_file.stat().st_mtime
            ).isoformat(),
        })
    sessions.sort(key=lambda x: x["modified"], reverse=True)
    return jsonify({"sessions": sessions})


@app.route("/api/session/<filename>")
def get_session_data(filename: str):
    data_dir = Path(DATA_DIR_NAME)
    session_file = data_dir / filename

    if not (session_file.exists() and filename.startswith(CSV_PREFIX)):
        return jsonify({"error": "Session not found"}), 404

    records = []
    with session_file.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            records.append(row)

    if len(records) > 1000:
        records = records[-1000:]

    return jsonify({"records": records})


# ----------------------------------------------------------------------------
# Socket.IO handlers
# ----------------------------------------------------------------------------


@socketio.on("connect")
def handle_connect():
    mgr = MuseStreamManager.get_instance()
    if mgr is not None:
        mgr.attach_listener(socketio)
    emit("connected", {"message": "Connected to NeuroDrive"})
    if mgr is not None:
        emit("status_update", {"status": mgr.status})


@socketio.on("disconnect")
def handle_disconnect():
    mgr = MuseStreamManager.get_instance()
    if mgr is not None:
        mgr.detach_listener(socketio)


# ----------------------------------------------------------------------------
# Application bootstrap
# ----------------------------------------------------------------------------


def build_app_paths() -> Tuple[Path, Path]:
    root = Path(__file__).resolve().parent
    return root, root / DATA_DIR_NAME


def check_muse_connection() -> bool:
    if StreamInlet is None or resolve_stream is None:
        print("ERROR: LSL support not available. Please install pylsl.")
        return False

    print("Searching for Muse headband connection...")
    print("This will keep searching until a Muse stream is found. Press Ctrl+C to stop.")

    while True:
        try:
            streams = _resolve_lsl_streams(timeout=STREAM_DISCOVERY_TIMEOUT)
            if not streams:
                print("No Muse headband detected yet. Retrying...")
                print("Make sure it is turned on and streaming with OpenMuse.")
                time.sleep(2.0)
                continue

            for stream in streams:
                if _looks_like_muse_stream(stream):
                    name = str(_stream_value(stream, "name", "Muse EEG stream"))
                    print(f"Found Muse headband stream: {name}")
                    return True

            print("Found LSL streams, but none are from a Muse headband. Retrying...")
            time.sleep(2.0)
        except KeyboardInterrupt:
            raise
        except Exception as e:
            print(f"Error checking for streams: {e}")
            time.sleep(2.0)


def open_dashboard() -> None:
    try:
        webbrowser.open(DASHBOARD_URL)
    except Exception as exc:
        print(f"Could not open browser automatically: {exc}")


def main() -> int:
    global stream_manager

    print("=" * 60)
    print("NEURODRIVE - EEG Anxiety Monitoring System")
    print("=" * 60)
    print()

    skip_muse_check = (
        os.environ.get("NEURODRIVE_SKIP_MUSE_CHECK", "")
        .strip()
        .lower() in {"1", "true", "yes"}
    )

    if not skip_muse_check:
        if not check_muse_connection():
            print()
            print("Cannot start without headband connection")
            print("   Use 'python withouttheadband.py' for simulation mode")
            return 1
    else:
        print("Muse stream was already confirmed by the launcher. Starting server...")

    print()
    print("Headband connected. Starting web server...")
    print()

    root, data_dir = build_app_paths()

    stream_manager = MuseStreamManager(data_dir=data_dir)
    stream_manager.set_socketio(socketio)

    print(f"Dashboard: {DASHBOARD_URL}")
    print("Press Ctrl+C to stop")
    print()

    stream_manager.start()

    threading.Timer(1.0, open_dashboard).start()

    socketio.run(app, host="0.0.0.0", port=5000, debug=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
