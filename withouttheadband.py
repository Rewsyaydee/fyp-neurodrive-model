from __future__ import annotations

import csv
import json
import math
import os
import sys
import threading
import time
import random
import webbrowser
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from flask import Flask, render_template, Response, jsonify, request
from flask_socketio import SocketIO, emit
from utils.anxiety_calculator import calculate_anxiety_estimate

APP_NAME = "NeuroDrive"
TARGET_HZ = 20.0
TARGET_INTERVAL = 1.0 / TARGET_HZ
DATA_DIR_NAME = "data"
CSV_PREFIX = "neurodrive_simulation"
DASHBOARD_URL = "http://localhost:5001"


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


class SimulationStreamManager:
    """Simulated EEG data manager for demonstration without headband"""

    def __init__(self, data_dir: Path):
        self._stop_event = threading.Event()
        self._data_dir = data_dir
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._records: List[StreamRecord] = []
        self._current_sequence = 0
        self._csv_path: Optional[Path] = None
        self._stream_name = "Muse Simulation"
        self._stream_type = "Simulated"
        self._is_running = False
        self._thread: Optional[threading.Thread] = None
        self._socketio = None
        self._status = "Simulation Ready"

        # Simulation parameters
        self._base_anxiety = 30.0
        self._anxiety_variation = 20.0
        self._base_hr = 70.0
        self._hr_variation = 15.0

    def set_socketio(self, socketio):
        self._socketio = socketio

    def start(self) -> None:
        if not self._is_running:
            self._stop_event.clear()
            self._is_running = True
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._is_running = False
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=10.0)
        self._thread = None

    def _run(self) -> None:
        self._records.clear()
        self._current_sequence = 0
        self._csv_path = None
        self._status = "Running simulation..."

        self._emit_status()

        try:
            while not self._stop_event.is_set():
                time.sleep(TARGET_INTERVAL)
                self._simulate_and_emit()
        finally:
            self._write_session_csv()
            self._status = "Simulation ended."
            self._emit_status()

    def _emit_status(self):
        if self._socketio:
            self._socketio.emit('status_update', {'status': self._status})

    def _emit_metrics(self, payload):
        if self._socketio:
            self._socketio.emit('metrics_update', payload)

    def _simulate_and_emit(self):
        """Generate simulated EEG data"""
        # Simulate a hidden arousal driver, then derive the displayed anxiety
        # estimate from EEG band ratios to match the research architecture.
        time_factor = time.time() / 30.0  # Slow variation over 30 seconds
        arousal = self._base_anxiety + self._anxiety_variation * math.sin(time_factor)
        arousal += random.uniform(-5, 5)
        arousal = max(0, min(100, arousal))

        # Simulate heart rate correlated with arousal.
        hr = self._base_hr + (arousal / 100) * 30
        hr += random.uniform(-5, 5)

        # Alpha increases with relaxation; theta and fast-wave power rise
        # during higher arousal/stress states.
        alpha = 10.0 + (100 - arousal) / 10.0 + random.uniform(-2, 2)
        theta = 5.0 + arousal / 20.0 + random.uniform(-1, 1)
        beta = 8.0 + arousal / 12.0 + random.uniform(-1.5, 1.5)
        delta = 3.0 + random.uniform(-0.5, 0.5)
        gamma = 15.0 + arousal / 15.0 + random.uniform(-3, 3)
        estimate = calculate_anxiety_estimate(
            delta=delta,
            theta=theta,
            alpha=alpha,
            beta=beta,
            gamma=gamma,
        )

        # Create payload
        timestamp_epoch = time.time()
        timestamp_iso = datetime.now().isoformat(timespec="milliseconds")

        self._current_sequence += 1

        payload = {
            "sequence": self._current_sequence,
            "timestamp_iso": timestamp_iso,
            "timestamp_epoch": timestamp_epoch,
            "delta": float(delta),
            "theta": float(theta),
            "alpha": float(alpha),
            "beta": float(beta),
            "gamma": float(gamma),
            "heart_rate": float(hr),
            "anxiety": float(estimate.score),
            "anxiety_label": estimate.label,
            "anxiety_method": estimate.method,
            "theta_beta_ratio": float(estimate.theta_beta_ratio),
            "alpha_sum_ratio": float(estimate.alpha_sum_ratio),
            "high_freq_ratio": float(estimate.high_freq_ratio),
            "stream_name": self._stream_name,
            "stream_type": self._stream_type,
        }

        # Save record
        record = StreamRecord(
            sequence=payload["sequence"],
            timestamp_iso=payload["timestamp_iso"],
            timestamp_epoch=payload["timestamp_epoch"],
            delta=payload["delta"],
            theta=payload["theta"],
            alpha=payload["alpha"],
            beta=payload["beta"],
            gamma=payload["gamma"],
            heart_rate=payload["heart_rate"],
            anxiety=payload["anxiety"],
            anxiety_label=payload["anxiety_label"],
            anxiety_method=payload["anxiety_method"],
            theta_beta_ratio=payload["theta_beta_ratio"],
            alpha_sum_ratio=payload["alpha_sum_ratio"],
            high_freq_ratio=payload["high_freq_ratio"],
            stream_name=payload["stream_name"]
        )
        self._records.append(record)

        # Emit to web clients
        self._emit_metrics(payload)

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


# Flask App Initialization
app = Flask(__name__)
app.config['SECRET_KEY'] = 'neurodrive_simulation_key'
socketio = SocketIO(app, cors_allowed_origins="*")

# Global simulation manager
simulation_manager = None


@app.route('/')
def index():
    """Serve the main dashboard HTML file"""
    return render_template('fypdashboard.html')


@app.route('/api/status')
def get_status():
    """Get current streaming status"""
    if simulation_manager:
        return jsonify({
            'status': simulation_manager._status,
            'is_running': simulation_manager._is_running,
            'stream_name': simulation_manager._stream_name,
            'sequence': simulation_manager._current_sequence,
            'simulation': True
        })
    return jsonify({'status': 'Not initialized', 'is_running': False, 'simulation': True})


@app.route('/api/start', methods=['POST'])
def start_streaming():
    """Start the simulated EEG streaming"""
    if simulation_manager and not simulation_manager._is_running:
        simulation_manager.start()
        return jsonify({'success': True, 'message': 'Simulation started'})
    return jsonify({'success': False, 'message': 'Already running or not initialized'})


@app.route('/api/stop', methods=['POST'])
def stop_streaming():
    """Stop the simulated EEG streaming"""
    if simulation_manager and simulation_manager._is_running:
        simulation_manager.stop()
        return jsonify({'success': True, 'message': 'Simulation stopped'})
    return jsonify({'success': False, 'message': 'Not running or not initialized'})


@app.route('/api/sessions')
def get_sessions():
    """Get list of past sessions"""
    data_dir = Path(DATA_DIR_NAME)
    if data_dir.exists():
        sessions = []

        # Get both real and simulated sessions
        all_csv_files = list(data_dir.glob("neurodrive_*.csv"))

        for csv_file in all_csv_files:
            is_sim = csv_file.name.startswith(CSV_PREFIX)
            sessions.append({
                'filename': csv_file.name,
                'path': str(csv_file),
                'size': csv_file.stat().st_size,
                'modified': datetime.fromtimestamp(csv_file.stat().st_mtime).isoformat(),
                'simulation': is_sim
            })

        sessions.sort(key=lambda x: x['modified'], reverse=True)
        return jsonify({'sessions': sessions})
    return jsonify({'sessions': []})


@app.route('/api/session/<filename>')
def get_session_data(filename):
    """Get data from a specific session"""
    data_dir = Path(DATA_DIR_NAME)
    session_file = data_dir / filename

    if session_file.exists() and (filename.startswith("neurodrive_session") or filename.startswith("neurodrive_simulation")):
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
    emit('connected', {'message': 'Connected to NeuroDrive Simulation'})


@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    print('Client disconnected')


def build_app_paths() -> Tuple[Path, Path]:
    root = Path(__file__).resolve().parent
    return root, root / DATA_DIR_NAME


def open_dashboard() -> None:
    """Open the simulation dashboard in the default browser."""
    if os.environ.get("NEURODRIVE_NO_BROWSER", "").strip().lower() in {"1", "true", "yes"}:
        return
    try:
        webbrowser.open(DASHBOARD_URL)
    except Exception as exc:
        print(f"Could not open browser automatically: {exc}")


def main() -> int:
    global simulation_manager

    root, data_dir = build_app_paths()
    simulation_manager = SimulationStreamManager(data_dir=data_dir)
    simulation_manager.set_socketio(socketio)

    print(f"Starting {APP_NAME} Web Server (Simulation Mode)")
    print("=" * 50)
    print("WARNING: RUNNING IN SIMULATION MODE")
    print("   No real headband connected")
    print("   Data is generated for demonstration")
    print("=" * 50)
    print(f"Dashboard will be available at: {DASHBOARD_URL}")
    print("Press Ctrl+C to stop")
    print()

    # Start simulation automatically
    simulation_manager.start()
    threading.Timer(1.0, open_dashboard).start()

    # Run the Flask app on different port
    try:
        socketio.run(app, host='0.0.0.0', port=5001, debug=False, allow_unsafe_werkzeug=True)
    finally:
        simulation_manager.stop()


if __name__ == "__main__":
    main()
