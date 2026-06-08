from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HEADSET_ADDRESS = os.environ.get("MUSE_HEADSET_ADDRESS", "00:55:DA:BB:C4:8E")
OPENMUSE_CMD = [
    "OpenMuse",
    "stream",
    "--address",
    HEADSET_ADDRESS,
    "--sensors",
    "EEG",
    "ACCGYRO",
]


def wait_for_lsl_stream(timeout: float = 20.0) -> bool:
    try:
        import pylsl
    except Exception as exc:
        print(f"Cannot import pylsl: {exc}")
        return False

    resolve_stream = (
        getattr(pylsl, "resolve_stream", None)
        or getattr(pylsl, "resolve_streams", None)
        or getattr(pylsl, "resolve", None)
    )
    if resolve_stream is None:
        print("No compatible pylsl resolver found.")
        return False

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            try:
                streams = list(resolve_stream(timeout=2.0) or [])
            except TypeError:
                streams = list(resolve_stream(wait_time=2.0) or [])
        except Exception as exc:
            print(f"LSL check failed: {exc}")
            streams = []

        for stream in streams:
            name = stream.name() if callable(getattr(stream, "name", None)) else getattr(stream, "name", "")
            stream_type = stream.type() if callable(getattr(stream, "type", None)) else getattr(stream, "type", "")
            channel_count = (
                stream.channel_count()
                if callable(getattr(stream, "channel_count", None))
                else getattr(stream, "channel_count", 0)
            )
            text = f"{name} {stream_type}".lower()
            if "muse" in text or ("eeg" in text and int(channel_count or 0) >= 4):
                print(f"LSL stream detected: {name} ({stream_type}, {channel_count} channels)")
                return True

        print("Waiting for OpenMuse LSL stream...")

    return False


def run_dashboard_until_stream_stops(openmuse_process: subprocess.Popen) -> int | None:
    environment = os.environ.copy()
    environment["NEURODRIVE_SKIP_MUSE_CHECK"] = "1"
    dashboard_process = subprocess.Popen([sys.executable, str(ROOT / "app.py")], cwd=ROOT, env=environment)

    while dashboard_process.poll() is None:
        openmuse_exit = openmuse_process.poll()
        if openmuse_exit is not None:
            print(f"OpenMuse stopped with exit code {openmuse_exit}. Restarting stream...")
            dashboard_process.terminate()
            try:
                dashboard_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                dashboard_process.kill()
                dashboard_process.wait(timeout=5)
            return None
        time.sleep(1)

    return int(dashboard_process.returncode or 0)


def main() -> int:
    print("Starting OpenMuse with EEG and ACC/GYRO sensors only.")
    print("If Windows has the Muse paired, remove it from Bluetooth settings first.")
    print("Press Ctrl+C to stop.")
    print()

    while True:
        print("Launching:", " ".join(OPENMUSE_CMD))
        process = subprocess.Popen(OPENMUSE_CMD, cwd=ROOT)

        try:
            if wait_for_lsl_stream():
                print("Starting NeuroDrive dashboard...")
                dashboard_exit = run_dashboard_until_stream_stops(process)
                if dashboard_exit is not None:
                    process.terminate()
                    return dashboard_exit

            print("OpenMuse did not publish a usable LSL stream in time.")
        except KeyboardInterrupt:
            print("\nStopping OpenMuse...")
            process.terminate()
            return 1

        exit_code = process.poll()
        if exit_code is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        else:
            print(f"OpenMuse stopped with exit code {exit_code}.")

        print("Retrying in 5 seconds...")
        time.sleep(5)


if __name__ == "__main__":
    raise SystemExit(main())
