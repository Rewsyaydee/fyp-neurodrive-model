from __future__ import annotations

import csv
import json
import math
import os
import sys
import threading
import time
import webbrowser
from collections import deque
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
import queue

try:  # pragma: no cover - optional dependency in some environments
    import pylsl

    StreamInlet = getattr(pylsl, "StreamInlet", None)
    resolve_stream = (
        getattr(pylsl, "resolve_stream", None)
        or getattr(pylsl, "resolve_streams", None)
        or getattr(pylsl, "resolve", None)
    )
except Exception:  # pragma: no cover
    StreamInlet = None
    resolve_stream = None

from flask import Flask, render_template, Response, jsonify, request
from flask_socketio import SocketIO, emit
from utils.anxiety_calculator import calculate_anxiety_estimate

APP_NAME = "NeuroDrive"
TARGET_HZ = 20.0  # Display refresh rate
TARGET_INTERVAL = 1.0 / TARGET_HZ
STREAM_DISCOVERY_TIMEOUT = 10.0
STREAM_STALE_SECONDS = 8.0
DATA_DIR_NAME = "data"
CSV_PREFIX = "neurodrive_session"
DASHBOARD_URL = "http://localhost:5000"
ANXIETY_LABEL_SCALE = {
    "low": 0.0,
    "medium": 50.0,
    "high": 100.0,
}

# Improved synchronization parameters
MAX_BUFFER_SIZE = 100  # Maximum samples to buffer
SYNC_WINDOW = 5  # Number of samples to average for display
EMISSION_BATCH_SIZE = 1  # Number of samples to emit at once


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
    channel_count = int(_stream_value(stream_info, "channel_count", 0) or 0)

    if "muse" in name or "muse" in stream_type:
        return True
    if "eeg" in stream_type and channel_count >= 4:
        return True
    return False


@dataclass
class StreamRecord:
    sequence: int
    timestamp_iso: str
    timestamp_epoch: float
    delta: float
    theta: float
    alpha: float
    beta: float
    gamma: float
    heart_rate: float
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
            f"{self.delta:.6f}",
            f"{self.theta:.6f}",
            f"{self.alpha:.6f}",
            f"{self.beta:.6f}",
            f"{self.gamma:.6f}",
            f"{self.heart_rate:.6f}",
            f"{self.anxiety:.6f}",
            self.anxiety_label,
            self.anxiety_method,
            f"{self.theta_beta_ratio:.6f}",
            f"{self.alpha_sum_ratio:.6f}",
            f"{self.high_freq_ratio:.6f}",
            self.stream_name,
        ]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ImprovedMuseStreamManager:
    def __init__(self, data_dir: Path):
        self._stop_event = threading.Event()
        self._data_dir = data_dir
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._records: List[StreamRecord] = []
        self._current_sequence = 0
        self._latest_payload: Optional[Dict[str, Any]] = None
        self._csv_path: Optional[Path] = None
        self._stream_name = ""
        self._stream_type = ""
        self._is_running = False
        self._socketio = None
        self._status = "Initializing..."

        # Improved buffering for synchronization
        self._sample_buffer = deque(maxlen=MAX_BUFFER_SIZE)
        self._emission_queue = queue.Queue(maxsize=10)
        self._last_emit_time = 0
        self._samples_since_last_emit = 0
        self._raw_eeg_window = deque(maxlen=512)
        self._latest_band_powers = {
            "delta": 0.0,
            "theta": 0.0,
            "alpha": 0.0,
            "beta": 0.0,
            "gamma": 0.0,
        }
        self._sample_rate = 256.0

        # Lock for thread safety
        self._data_lock = threading.Lock()

    def set_socketio(self, socketio):
        self._socketio = socketio

    def start(self) -> None:
        if not self._is_running:
            self._is_running = True
            # Start data processing thread
            threading.Thread(target=self._process_data_thread, daemon=True).start()
            # Start stream capture thread
            threading.Thread(target=self._run, daemon=True).start()

    def stop(self) -> None:
        self._stop_event.set()
        self._is_running = False

    def _process_data_thread(self) -> None:
        """Separate thread for processing and emitting data at controlled rate"""
        while not self._stop_event.is_set():
            payload = None
            try:
                # Wait for data or timeout
                try:
                    payload = self._emission_queue.get(timeout=0.1)
                except queue.Empty:
                    # No new data, emit last known payload if needed
                    with self._data_lock:
                        if self._latest_payload:
                            payload = self._latest_payload
                    if payload and time.time() - self._last_emit_time > TARGET_INTERVAL * 2:
                        self._emit_metrics(payload)
                    continue

                # Emit at controlled rate
                now = time.time()
                if now - self._last_emit_time >= TARGET_INTERVAL:
                    with self._data_lock:
                        if payload:
                            self._latest_payload = payload
                            self._current_sequence += 1
                            payload["sequence"] = self._current_sequence
                            self._records.append(self._record_from_payload(payload))

                    self._emit_metrics(payload)
                    self._last_emit_time = now
                else:
                    # Rate limited, put back in queue if it's a new payload
                    if payload:
                        try:
                            self._emission_queue.put_nowait(payload)
                        except queue.Full:
                            # Queue full, skip this payload
                            pass

            except Exception as e:
                print(f"Error in data processing thread: {e}")
                time.sleep(0.1)

    def _run(self) -> None:
        self._stop_event.clear()
        self._records.clear()
        self._current_sequence = 0
        with self._data_lock:
            self._latest_payload = None
        self._csv_path = None
        self._stream_name = ""
        self._stream_type = ""
        self._raw_eeg_window.clear()
        self._latest_band_powers = {
            "delta": 0.0,
            "theta": 0.0,
            "alpha": 0.0,
            "beta": 0.0,
            "gamma": 0.0,
        }
        self._sample_rate = 256.0
        self._status = "Starting..."

        # Clear buffers
        self._sample_buffer.clear()
        while not self._emission_queue.empty():
            try:
                self._emission_queue.get_nowait()
            except queue.Empty:
                break

        self._emit_status()

        if StreamInlet is None or resolve_stream is None:
            self._status = "LSL support is unavailable because pylsl is not installed."
            self._write_session_csv()
            self._emit_status()
            return

        self._status = "Searching for Muse stream..."
        self._emit_status()

        try:
            while not self._stop_event.is_set():
                stream_info = self._discover_stream()
                if stream_info is None:
                    self._status = "Waiting for Muse stream..."
                    self._emit_status()
                    self._sleep_with_stop(1.0)
                    continue

                self._stream_name = self._safe_call(stream_info, "name") or "Muse Stream"
                self._stream_type = self._safe_call(stream_info, "type") or "LSL"
                self._sample_rate = self._safe_float(stream_info, "nominal_srate") or 256.0
                if self._sample_rate <= 0:
                    self._sample_rate = 256.0
                self._raw_eeg_window.clear()
                self._status = f"Connected to {self._stream_name}"
                self._emit_status()

                try:
                    inlet = StreamInlet(stream_info, max_buflen=8, recover=True)
                    labels = self._extract_channel_labels(stream_info)
                    self._capture_loop(inlet, labels)
                except Exception as exc:
                    self._status = f"Stream interrupted: {exc}"
                    self._emit_status()
                    self._sleep_with_stop(0.75)
        finally:
            self._write_session_csv()
            self._status = "Session closed."
            self._emit_status()

    def _emit_status(self):
        if self._socketio:
            self._socketio.emit('status_update', {'status': self._status})

    def _emit_metrics(self, payload):
        if self._socketio:
            self._socketio.emit('metrics_update', payload)

    def get_latest_payload(self) -> Optional[Dict[str, Any]]:
        with self._data_lock:
            if self._latest_payload is None:
                return None
            return dict(self._latest_payload)

    def _capture_loop(self, inlet: StreamInlet, labels: List[str]) -> None:
        last_sample_seen = time.monotonic()

        # Initialize with a default payload
        default_payload = {
            "timestamp_iso": datetime.now().isoformat(timespec="milliseconds"),
            "timestamp_epoch": time.time(),
            "delta": 0.0,
            "theta": 0.0,
            "alpha": 0.0,
            "beta": 0.0,
            "gamma": 0.0,
            "heart_rate": 0.0,
            "anxiety": 0.0,
            "anxiety_label": "no signal",
            "anxiety_method": "",
            "theta_beta_ratio": 0.0,
            "alpha_sum_ratio": 0.0,
            "high_freq_ratio": 0.0,
            "stream_name": self._stream_name,
            "stream_type": self._stream_type,
        }

        with self._data_lock:
            if self._latest_payload is None:
                self._latest_payload = default_payload

        while not self._stop_event.is_set():
            try:
                sample, timestamp = inlet.pull_sample(timeout=0.01)
            except Exception as exc:
                raise RuntimeError(str(exc)) from exc

            if sample is not None:
                # Process sample immediately
                payload = self._build_payload(sample, timestamp, labels)

                # Add to buffer for smoothing
                self._sample_buffer.append(payload)

                # Create averaged payload for display
                if len(self._sample_buffer) >= SYNC_WINDOW:
                    averaged_payload = self._average_payloads()
                    try:
                        self._emission_queue.put_nowait(averaged_payload)
                    except queue.Full:
                        # Queue full, skip this sample
                        pass
                else:
                    # Send individual samples until buffer is full
                    try:
                        self._emission_queue.put_nowait(payload)
                    except queue.Full:
                        pass

                last_sample_seen = time.monotonic()

            if time.monotonic() - last_sample_seen > STREAM_STALE_SECONDS:
                raise RuntimeError("no samples received for several seconds")

    def _average_payloads(self) -> Dict[str, Any]:
        """Average the last SYNC_WINDOW samples for smoother display"""
        if not self._sample_buffer:
            return {}

        # Get the most recent samples
        recent_samples = list(self._sample_buffer)[-SYNC_WINDOW:]

        # Initialize averaged payload
        averaged = {
            "timestamp_iso": datetime.now().isoformat(timespec="milliseconds"),
            "timestamp_epoch": time.time(),
            "delta": 0.0,
            "theta": 0.0,
            "alpha": 0.0,
            "beta": 0.0,
            "gamma": 0.0,
            "heart_rate": 0.0,
            "anxiety": 0.0,
            "anxiety_label": "",
            "anxiety_method": "",
            "theta_beta_ratio": 0.0,
            "alpha_sum_ratio": 0.0,
            "high_freq_ratio": 0.0,
            "stream_name": self._stream_name,
            "stream_type": self._stream_type,
        }

        # Average numeric values
        count = len(recent_samples)
        for sample in recent_samples:
            for key in ["delta", "theta", "alpha", "beta", "gamma",
                       "heart_rate", "anxiety", "theta_beta_ratio",
                       "alpha_sum_ratio", "high_freq_ratio"]:
                if key in sample and isinstance(sample[key], (int, float)):
                    averaged[key] += sample[key]

        for key in ["delta", "theta", "alpha", "beta", "gamma",
                   "heart_rate", "anxiety", "theta_beta_ratio",
                   "alpha_sum_ratio", "high_freq_ratio"]:
            averaged[key] /= count

        # Use the most recent label and method
        if recent_samples:
            last = recent_samples[-1]
            averaged["anxiety_label"] = last.get("anxiety_label", "")
            averaged["anxiety_method"] = last.get("anxiety_method", "")

        return averaged

    def _discover_stream(self) -> Optional[Any]:
        try:
            streams = _resolve_lsl_streams(timeout=STREAM_DISCOVERY_TIMEOUT)
        except Exception as exc:
            self._status = f"LSL discovery error: {exc}"
            self._emit_status()
            return None

        if not streams:
            return None

        scored: List[Tuple[int, Any]] = []
        for stream in streams:
            score = self._score_stream(stream)
            scored.append((score, stream))

        scored.sort(key=lambda item: item[0], reverse=True)
        best_score, best_stream = scored[0]
        if best_score <= 0:
            return None
        return best_stream

    def _score_stream(self, stream: Any) -> int:
        name = (self._safe_call(stream, "name") or "").lower()
        stream_type = (self._safe_call(stream, "type") or "").lower()
        labels = [label.lower() for label in self._extract_channel_labels(stream)]
        score = 0

        if "muse" in name:
            score += 100
        if "muse" in stream_type:
            score += 60
        if "eeg" in stream_type:
            score += 30
        if any(token in name for token in ("delta", "theta", "alpha", "beta", "gamma", "anxiety", "heart")):
            score += 40
        if any(token in labels for token in ("delta", "theta", "alpha", "beta", "gamma", "hr", "heart rate", "anxiety")):
            score += 80

        channel_count = self._safe_int(stream, "channel_count")
        if channel_count >= 6:
            score += 20
        elif channel_count >= 4:
            score += 10

        return score

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

    def _build_payload(self, sample: Sequence[Any], timestamp: float, labels: Sequence[str]) -> Dict[str, Any]:
        sample_values = [self._coerce_float(value) for value in sample]
        label_map = self._map_sample_values(sample_values, labels)

        band_powers = self._extract_band_powers(sample_values, label_map)
        delta = label_map.get("delta", band_powers.get("delta", 0.0))
        theta = label_map.get("theta", band_powers.get("theta", 0.0))
        alpha = label_map.get("alpha", band_powers.get("alpha", 0.0))
        beta = label_map.get("beta", band_powers.get("beta", 0.0))
        gamma = label_map.get("gamma", band_powers.get("gamma", 0.0))
        heart_rate = label_map.get("heart_rate", self._fallback(sample_values, 4))
        estimate = calculate_anxiety_estimate(
            delta=delta,
            theta=theta,
            alpha=alpha,
            beta=beta,
            gamma=gamma,
        )
        anxiety = estimate.score
        anxiety_label = estimate.label

        timestamp_epoch = float(timestamp if timestamp is not None else time.time())
        timestamp_iso = datetime.now().isoformat(timespec="milliseconds")

        return {
            "timestamp_iso": timestamp_iso,
            "timestamp_epoch": timestamp_epoch,
            "delta": float(delta),
            "theta": float(theta),
            "alpha": float(alpha),
            "beta": float(beta),
            "gamma": float(gamma),
            "heart_rate": float(heart_rate),
            "anxiety": float(anxiety),
            "anxiety_label": anxiety_label,
            "anxiety_method": estimate.method,
            "theta_beta_ratio": float(estimate.theta_beta_ratio),
            "alpha_sum_ratio": float(estimate.alpha_sum_ratio),
            "high_freq_ratio": float(estimate.high_freq_ratio),
            "stream_name": self._stream_name,
            "stream_type": self._stream_type,
        }

    def _extract_band_powers(self, sample_values: Sequence[float], label_map: Dict[str, Any]) -> Dict[str, float]:
        if any(label_map.get(key) is not None for key in ("delta", "theta", "alpha", "beta", "gamma")):
            return dict(self._latest_band_powers)

        eeg_values = [value for value in sample_values if math.isfinite(value)]
        if not eeg_values:
            return dict(self._latest_band_powers)

        self._raw_eeg_window.append(sum(eeg_values) / len(eeg_values))
        if len(self._raw_eeg_window) < max(64, int(self._sample_rate // 2)):
            return dict(self._latest_band_powers)

        try:
            import numpy as np

            values = np.asarray(self._raw_eeg_window, dtype=float)
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

            self._latest_band_powers = powers
            return dict(powers)
        except Exception:
            return dict(self._latest_band_powers)

    def _map_sample_values(self, sample_values: Sequence[float], labels: Sequence[str]) -> Dict[str, Any]:
        normalized: Dict[str, float] = {}
        raw_labels: Dict[str, Any] = {}

        for index, label in enumerate(labels):
            if index >= len(sample_values):
                break
            key = self._normalize_label(label)
            value = sample_values[index]
            if key:
                normalized[key] = value
                raw_labels[key] = value

        mapped: Dict[str, Any] = {}
        mapped["delta"] = self._first_match(normalized, ("delta", "band_delta", "spectral_delta"))
        mapped["theta"] = self._first_match(normalized, ("theta", "band_theta", "spectral_theta"))
        mapped["alpha"] = self._first_match(normalized, ("alpha", "band_alpha", "spectral_alpha"))
        mapped["beta"] = self._first_match(normalized, ("beta", "band_beta", "spectral_beta", "low_beta", "high_beta"))
        mapped["gamma"] = self._first_match(normalized, ("gamma", "band_gamma", "spectral_gamma"))
        mapped["heart_rate"] = self._first_match(normalized, ("heart_rate", "heartrate", "hr", "pulse"))

        anxiety_value = self._first_match(normalized, ("anxiety", "anxiety_score", "stress"))
        if anxiety_value is None:
            anxiety_value = 0.0
        mapped["anxiety"] = anxiety_value

        anxiety_label = ""
        for key in ("anxiety_label", "label", "state", "level"):
            if key in raw_labels:
                anxiety_label = str(raw_labels[key])
                break

        if not anxiety_label:
            for key in ("anxiety", "stress"):
                if key in normalized:
                    anxiety_label = f"{normalized[key]:.2f}"
                    break

        if isinstance(anxiety_value, str):
            lowered = anxiety_value.strip().lower()
            mapped["anxiety"] = ANXIETY_LABEL_SCALE.get(lowered, 0.0)
            anxiety_label = anxiety_value

        if mapped["anxiety"] is None:
            mapped["anxiety"] = 0.0
        if mapped["heart_rate"] is None:
            mapped["heart_rate"] = 0.0
        if mapped["delta"] is None:
            mapped["delta"] = 0.0
        if mapped["theta"] is None:
            mapped["theta"] = 0.0
        if mapped["alpha"] is None:
            mapped["alpha"] = 0.0
        if mapped["beta"] is None:
            mapped["beta"] = 0.0
        if mapped["gamma"] is None:
            mapped["gamma"] = 0.0

        mapped["anxiety_label"] = anxiety_label
        return mapped

    def _first_match(self, mapping: Dict[str, float], keys: Iterable[str]) -> Optional[float]:
        for key in keys:
            if key in mapping:
                return mapping[key]
        return None

    def _record_from_payload(self, payload: Dict[str, Any]) -> StreamRecord:
        return StreamRecord(
            sequence=int(payload["sequence"]),
            timestamp_iso=str(payload["timestamp_iso"]),
            timestamp_epoch=float(payload["timestamp_epoch"]),
            delta=float(payload["delta"]),
            theta=float(payload["theta"]),
            alpha=float(payload["alpha"]),
            beta=float(payload.get("beta", 0.0)),
            gamma=float(payload["gamma"]),
            heart_rate=float(payload["heart_rate"]),
            anxiety=float(payload["anxiety"]),
            anxiety_label=str(payload.get("anxiety_label", "")),
            anxiety_method=str(payload.get("anxiety_method", "")),
            theta_beta_ratio=float(payload.get("theta_beta_ratio", 0.0)),
            alpha_sum_ratio=float(payload.get("alpha_sum_ratio", 0.0)),
            high_freq_ratio=float(payload.get("high_freq_ratio", 0.0)),
            stream_name=str(payload.get("stream_name", "")),
        )

    def _write_session_csv(self) -> None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._csv_path = self._data_dir / f"{CSV_PREFIX}_{timestamp}.csv"
        header = [
            "sequence",
            "timestamp_iso",
            "timestamp_epoch",
            "delta",
            "theta",
            "alpha",
            "beta",
            "gamma",
            "heart_rate",
            "anxiety",
            "anxiety_label",
            "anxiety_method",
            "theta_beta_ratio",
            "alpha_sum_ratio",
            "high_freq_ratio",
            "stream_name",
        ]
        with self._csv_path.open("w", newline="", encoding="utf-8") as file_handle:
            writer = csv.writer(file_handle)
            writer.writerow(header)
            for record in self._records:
                writer.writerow(record.to_row())

    def _fallback(self, values: Sequence[float], index: int) -> float:
        if 0 <= index < len(values):
            return float(values[index])
        return 0.0

    def _normalize_label(self, label: str) -> str:
        token = label.strip().lower().replace("-", "_").replace(" ", "_")
        if token in {"heartrate", "heart_rate", "heart", "hr", "pulse"}:
            return "heart_rate"
        if token in {"anxiety", "anxiety_score", "stress"}:
            return "anxiety"
        if token in {"beta", "band_beta", "spectral_beta", "low_beta", "high_beta", "beta1", "beta_1", "beta2", "beta_2"}:
            return "beta"
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
                lowered = text.lower()
                return ANXIETY_LABEL_SCALE.get(lowered, 0.0)
        return 0.0

    def _safe_call(self, stream_info: Any, method_name: str) -> str:
        try:
            value = getattr(stream_info, method_name)()
            return "" if value is None else str(value)
        except Exception:
            return ""

    def _safe_int(self, stream_info: Any, method_name: str) -> int:
        try:
            value = getattr(stream_info, method_name)()
            return int(value or 0)
        except Exception:
            return 0

    def _safe_float(self, stream_info: Any, method_name: str) -> float:
        try:
            value = getattr(stream_info, method_name)()
            return float(value or 0.0)
        except Exception:
            return 0.0

    def _sleep_with_stop(self, duration: float) -> None:
        deadline = time.monotonic() + duration
        while not self._stop_event.is_set() and time.monotonic() < deadline:
            time.sleep(0.05)


# Use the improved manager
MuseStreamManager = ImprovedMuseStreamManager

# Flask App Initialization
app = Flask(__name__)
app.config['SECRET_KEY'] = 'neurodrive_secret_key'
socketio = SocketIO(app, cors_allowed_origins="*")

# Register static file routes
from static import register_static_routes
register_static_routes(app)

# Global stream manager
stream_manager = None


@app.route('/')
def index():
    """Serve the main dashboard HTML file"""
    return render_template('fypdashboard.html')


@app.route('/api/status')
def get_status():
    """Get current streaming status"""
    if stream_manager:
        return jsonify({
            'status': stream_manager._status,
            'is_running': stream_manager._is_running,
            'stream_name': stream_manager._stream_name,
            'sequence': stream_manager._current_sequence,
            'latest_payload': stream_manager.get_latest_payload()
        })
    return jsonify({'status': 'Not initialized', 'is_running': False})


@app.route('/api/start', methods=['POST'])
def start_streaming():
    """Start the EEG streaming"""
    if stream_manager and not stream_manager._is_running:
        stream_manager.start()
        return jsonify({'success': True, 'message': 'Streaming started'})
    return jsonify({'success': False, 'message': 'Already running or not initialized'})


@app.route('/api/stop', methods=['POST'])
def stop_streaming():
    """Stop the EEG streaming"""
    if stream_manager and stream_manager._is_running:
        stream_manager.stop()
        return jsonify({'success': True, 'message': 'Streaming stopped'})
    return jsonify({'success': False, 'message': 'Not running or not initialized'})


@app.route('/api/sessions')
def get_sessions():
    """Get list of past sessions"""
    data_dir = Path(DATA_DIR_NAME)
    if data_dir.exists():
        sessions = []
        for csv_file in data_dir.glob(f"{CSV_PREFIX}_*.csv"):
            sessions.append({
                'filename': csv_file.name,
                'path': str(csv_file),
                'size': csv_file.stat().st_size,
                'modified': datetime.fromtimestamp(csv_file.stat().st_mtime).isoformat()
            })
        sessions.sort(key=lambda x: x['modified'], reverse=True)
        return jsonify({'sessions': sessions})
    return jsonify({'sessions': []})


@app.route('/api/session/<filename>')
def get_session_data(filename):
    """Get data from a specific session"""
    data_dir = Path(DATA_DIR_NAME)
    session_file = data_dir / filename

    if session_file.exists() and filename.startswith(CSV_PREFIX):
        records = []
        with session_file.open('r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                records.append(row)

        # Limit to last 1000 records for performance
        if len(records) > 1000:
            records = records[-1000:]

        return jsonify({'records': records})
    return jsonify({'error': 'Session not found'}), 404


@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    emit('connected', {'message': 'Connected to NeuroDrive'})


@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    print('Client disconnected')


def build_app_paths() -> Tuple[Path, Path]:
    root = Path(__file__).resolve().parent
    return root, root / DATA_DIR_NAME


def check_muse_connection() -> bool:
    """Check if Muse headband is connected before starting"""
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
            print("Retrying...")
            time.sleep(2.0)

    if StreamInlet is None or resolve_stream is None:
        print("❌ ERROR: LSL support not available. Please install pylsl.")
        return False

    print("🔍 Checking for Muse headband connection...")

    try:
        streams = _resolve_lsl_streams(timeout=STREAM_DISCOVERY_TIMEOUT)

        if not streams:
            print("❌ No Muse headband detected!")
            print()
            print("Please ensure:")
            print("1. Your Muse headband is turned on")
            print("2. Connected via Bluetooth to your computer")
            print("3. Streaming with OpenMuse:")
            print("   OpenMuse stream --address <your-headset-address>")
            print()
            print("Or run without headband: python withouttheadband.py")
            return False

        # Check if any stream is Muse
        for stream in streams:
            name = getattr(stream, 'name', '') or ''
            if 'muse' in name.lower():
                print(f"✅ Found Muse headband: {name}")
                return True

        print("❌ No Muse streams found")
        print("Found streams, but none are from a Muse headband")
        return False

    except Exception as e:
        print(f"❌ Error checking for streams: {e}")
        return False


def open_dashboard() -> None:
    """Open the dashboard in the default browser after the server starts."""
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

    skip_muse_check = os.environ.get("NEURODRIVE_SKIP_MUSE_CHECK", "").strip().lower() in {"1", "true", "yes"}

    if not skip_muse_check:
        # Check for Muse connection first
        if not check_muse_connection():
            print()
            print("❌ Cannot start without headband connection")
            print("   Use 'python withouttheadband.py' for simulation mode")
            return 1
    else:
        print("Muse stream was already confirmed by the launcher. Starting server...")

    print()
    print("✅ Headband connected! Starting web server...")
    print()

    root, data_dir = build_app_paths()
    stream_manager = MuseStreamManager(data_dir=data_dir)
    stream_manager.set_socketio(socketio)

    print(f"Dashboard will be available at: {DASHBOARD_URL}")
    print(f"Press Ctrl+C to stop")
    print()

    # Start streaming
    stream_manager.start()

    threading.Timer(1.0, open_dashboard).start()

    # Run the Flask app
    socketio.run(app, host='0.0.0.0', port=5000, debug=False)


if __name__ == "__main__":
    main()