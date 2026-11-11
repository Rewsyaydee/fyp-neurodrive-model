from __future__ import annotations

import csv
import math
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from PyQt5.QtCore import QObject, QThread, QTimer, QUrl, pyqtSignal, pyqtSlot
from PyQt5.QtWidgets import QApplication, QMainWindow
from PyQt5.QtWebChannel import QWebChannel
from PyQt5.QtWebEngineWidgets import QWebEngineView

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


APP_NAME = "NeuroDrive"
TARGET_HZ = 20.0
TARGET_INTERVAL = 1.0 / TARGET_HZ
STREAM_DISCOVERY_TIMEOUT = 2.0
STREAM_STALE_SECONDS = 8.0
DATA_DIR_NAME = "data"
CSV_PREFIX = "neurodrive_session"
ANXIETY_LABEL_SCALE = {
    "low": 0.0,
    "medium": 50.0,
    "high": 100.0,
}


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


@dataclass
class StreamRecord:
    sequence: int
    timestamp_iso: str
    timestamp_epoch: float
    delta: float
    theta: float
    alpha: float
    gamma: float
    heart_rate: float
    anxiety: float
    anxiety_label: str
    stream_name: str

    def to_row(self) -> List[str]:
        return [
            str(self.sequence),
            self.timestamp_iso,
            f"{self.timestamp_epoch:.6f}",
            f"{self.delta:.6f}",
            f"{self.theta:.6f}",
            f"{self.alpha:.6f}",
            f"{self.gamma:.6f}",
            f"{self.heart_rate:.6f}",
            f"{self.anxiety:.6f}",
            self.anxiety_label,
            self.stream_name,
        ]


class SessionBridge(QObject):
    metricsChanged = pyqtSignal(dict)
    statusChanged = pyqtSignal(str)
    sessionSaved = pyqtSignal(dict)
    sessionEnded = pyqtSignal()

    @pyqtSlot()
    def requestEndSession(self) -> None:
        self.sessionEnded.emit()


class MuseStreamWorker(QThread):
    metricsReady = pyqtSignal(dict)
    statusReady = pyqtSignal(str)
    sessionSaved = pyqtSignal(dict)

    def __init__(self, data_dir: Path, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._stop_event = threading.Event()
        self._data_dir = data_dir
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._records: List[StreamRecord] = []
        self._current_sequence = 0
        self._latest_payload: Optional[Dict[str, Any]] = None
        self._csv_path: Optional[Path] = None
        self._stream_name = ""
        self._stream_type = ""

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        self._stop_event.clear()
        self._records.clear()
        self._current_sequence = 0
        self._latest_payload = None
        self._csv_path = None
        self._stream_name = ""
        self._stream_type = ""

        if StreamInlet is None or resolve_stream is None:
            self.statusReady.emit("LSL support is unavailable because pylsl is not installed.")
            self._write_session_csv()
            return

        self.statusReady.emit("Searching for Muse stream...")

        try:
            while not self._stop_event.is_set():
                stream_info = self._discover_stream()
                if stream_info is None:
                    self.statusReady.emit("Waiting for Muse stream...")
                    self._sleep_with_stop(1.0)
                    continue

                self._stream_name = self._safe_call(stream_info, "name") or "Muse Stream"
                self._stream_type = self._safe_call(stream_info, "type") or "LSL"
                self.statusReady.emit(f"Connected to {self._stream_name}")

                try:
                    inlet = StreamInlet(stream_info, max_buflen=8, recover=True)
                    labels = self._extract_channel_labels(stream_info)
                    self._capture_loop(inlet, labels)
                except Exception as exc:
                    self.statusReady.emit(f"Stream interrupted: {exc}")
                    self._sleep_with_stop(0.75)
        finally:
            self._write_session_csv()

    def _capture_loop(self, inlet: StreamInlet, labels: List[str]) -> None:
        last_sample_seen = time.monotonic()
        next_emit = time.perf_counter()

        while not self._stop_event.is_set():
            try:
                sample, timestamp = inlet.pull_sample(timeout=0.01)
            except Exception as exc:
                raise RuntimeError(str(exc)) from exc

            new_sample = False
            if sample is not None:
                payload = self._build_payload(sample, timestamp, labels)
                self._latest_payload = payload
                last_sample_seen = time.monotonic()
                new_sample = True
            else:
                payload = self._latest_payload

            now = time.perf_counter()
            if payload is not None and now >= next_emit:
                display_payload = dict(payload)
                if new_sample:
                    self._current_sequence += 1
                    display_payload["sequence"] = self._current_sequence
                    self._records.append(self._record_from_payload(display_payload))
                else:
                    display_payload["sequence"] = self._current_sequence
                self.metricsReady.emit(display_payload)
                next_emit = now + TARGET_INTERVAL

            if time.monotonic() - last_sample_seen > STREAM_STALE_SECONDS:
                raise RuntimeError("no samples received for several seconds")

    def _discover_stream(self) -> Optional[Any]:
        try:
            streams = _resolve_lsl_streams()
        except Exception as exc:
            self.statusReady.emit(f"LSL discovery error: {exc}")
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
        if any(token in name for token in ("delta", "theta", "alpha", "gamma", "anxiety", "heart")):
            score += 40
        if any(token in labels for token in ("delta", "theta", "alpha", "gamma", "hr", "heart rate", "anxiety")):
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

        delta = label_map.get("delta", self._fallback(sample_values, 0))
        theta = label_map.get("theta", self._fallback(sample_values, 1))
        alpha = label_map.get("alpha", self._fallback(sample_values, 2))
        gamma = label_map.get("gamma", self._fallback(sample_values, 3))
        heart_rate = label_map.get("heart_rate", self._fallback(sample_values, 4))
        anxiety = label_map.get("anxiety", self._fallback(sample_values, 5))
        anxiety_label = label_map.get("anxiety_label", "")

        timestamp_epoch = float(timestamp if timestamp is not None else time.time())
        timestamp_iso = datetime.now().isoformat(timespec="milliseconds")

        return {
            "sequence": self._current_sequence + 1,
            "timestamp_iso": timestamp_iso,
            "timestamp_epoch": timestamp_epoch,
            "delta": float(delta),
            "theta": float(theta),
            "alpha": float(alpha),
            "gamma": float(gamma),
            "heart_rate": float(heart_rate),
            "anxiety": float(anxiety),
            "anxiety_label": anxiety_label,
            "stream_name": self._stream_name,
            "stream_type": self._stream_type,
        }

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
            gamma=float(payload["gamma"]),
            heart_rate=float(payload["heart_rate"]),
            anxiety=float(payload["anxiety"]),
            anxiety_label=str(payload.get("anxiety_label", "")),
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
            "gamma",
            "heart_rate",
            "anxiety",
            "anxiety_label",
            "stream_name",
        ]
        with self._csv_path.open("w", newline="", encoding="utf-8") as file_handle:
            writer = csv.writer(file_handle)
            writer.writerow(header)
            for record in self._records:
                writer.writerow(record.to_row())

        self.sessionSaved.emit(
            {
                "csv_path": str(self._csv_path),
                "row_count": len(self._records),
                "stream_name": self._stream_name,
            }
        )

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

    def _sleep_with_stop(self, duration: float) -> None:
        deadline = time.monotonic() + duration
        while not self._stop_event.is_set() and time.monotonic() < deadline:
            time.sleep(0.05)


class SessionController(QObject):
    def __init__(self, bridge: SessionBridge, data_dir: Path, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.bridge = bridge
        self.worker = MuseStreamWorker(data_dir=data_dir)
        self._ending = False
        self._saved = False
        self._status = "Starting..."

        self.worker.metricsReady.connect(self._on_metrics_ready)
        self.worker.statusReady.connect(self._on_status_ready)
        self.worker.sessionSaved.connect(self._on_session_saved)
        self.bridge.sessionEnded.connect(self.end_session)

    def start(self) -> None:
        if not self.worker.isRunning():
            self.worker.start()

    @pyqtSlot()
    def end_session(self) -> None:
        if self._ending:
            return
        self._ending = True
        self.bridge.statusChanged.emit("Ending session and writing CSV...")
        self.worker.stop()
        self.worker.wait(10000)
        self._saved = True
        self.bridge.statusChanged.emit("Session closed.")

    @pyqtSlot(dict)
    def _on_metrics_ready(self, payload: Dict[str, Any]) -> None:
        self.bridge.metricsChanged.emit(payload)

    @pyqtSlot(str)
    def _on_status_ready(self, message: str) -> None:
        self._status = message
        self.bridge.statusChanged.emit(message)

    @pyqtSlot(dict)
    def _on_session_saved(self, payload: Dict[str, Any]) -> None:
        self.bridge.sessionSaved.emit(payload)


class WebDashboardWindow(QMainWindow):
    def __init__(self, html_path: Path, bridge: SessionBridge, controller: SessionController) -> None:
        super().__init__()
        self._bridge = bridge
        self._controller = controller
        self.setWindowTitle(APP_NAME)
        self.resize(1560, 980)

        self._view = QWebEngineView(self)
        self.setCentralWidget(self._view)

        channel = QWebChannel(self._view.page())
        channel.registerObject("bridge", self._bridge)
        self._view.page().setWebChannel(channel)
        self._view.load(QUrl.fromLocalFile(str(html_path)))

    def closeEvent(self, event) -> None:  # type: ignore[override]
        if self._controller.worker.isRunning() and not self._controller._ending:
            self._controller.end_session()
        event.accept()


def build_app_paths() -> Tuple[Path, Path]:
    root = Path(__file__).resolve().parent
    return root, root / "index.html"


def main() -> int:
    QApplication.setApplicationName(APP_NAME)
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setQuitOnLastWindowClosed(True)

    root, html_path = build_app_paths()
    bridge = SessionBridge()
    controller = SessionController(bridge=bridge, data_dir=root / DATA_DIR_NAME)
    window = WebDashboardWindow(html_path=html_path, bridge=bridge, controller=controller)

    def safe_quit() -> None:
        if controller.worker.isRunning():
            controller.end_session()

    app.aboutToQuit.connect(safe_quit)
    controller.start()
    window.show()

    sigint_timer = QTimer()
    sigint_timer.setInterval(250)
    sigint_timer.timeout.connect(lambda: None)
    sigint_timer.start()
    app._sigint_timer = sigint_timer  # type: ignore[attr-defined]

    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
