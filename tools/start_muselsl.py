from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MUSE_NAME = "Muse-2474"
DEFAULT_MUSE_ADDRESS = "00:55:DA:B8:24:74"
MUSE_NAME = os.environ.get("NEURODRIVE_MUSE_NAME", DEFAULT_MUSE_NAME).strip()
address_override = os.environ.get("NEURODRIVE_MUSE_ADDRESS")
MUSE_ADDRESS = (DEFAULT_MUSE_ADDRESS if address_override is None else address_override).strip()
MUSELSL_MODEL = os.environ.get("NEURODRIVE_MUSELSL_MODEL", "legacy").strip() or "legacy"


def build_muselsl_command() -> list[str] | None:
    if importlib.util.find_spec("muselsl") is not None:
        command = [sys.executable, "-m", "muselsl", "stream"]
    else:
        executable = shutil.which("muselsl")
        if executable is None:
            return None
        command = [executable, "stream"]

    if MUSE_ADDRESS:
        command.extend(["--address", MUSE_ADDRESS])
    elif MUSE_NAME:
        command.extend(["--name", MUSE_NAME])

    command.extend(["--model", MUSELSL_MODEL, "--lsltime"])
    return command


def wait_for_lsl_stream(timeout: float = 30.0) -> bool:
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
            if int(channel_count or 0) >= 4 and ("eeg" in text or "muse" in text):
                print(f"LSL stream detected: {name} ({stream_type}, {channel_count} channels)")
                return True

        print("Waiting for muselsl EEG stream...")

    return False


def run_dashboard_until_stream_stops(stream_process: subprocess.Popen) -> int | None:
    environment = os.environ.copy()
    environment["NEURODRIVE_SKIP_MUSE_CHECK"] = "1"
    environment["PYTHONUTF8"] = "1"
    dashboard_process = subprocess.Popen([sys.executable, str(ROOT / "app.py")], cwd=ROOT, env=environment)

    while dashboard_process.poll() is None:
        stream_exit = stream_process.poll()
        if stream_exit is not None:
            print(f"muselsl stopped with exit code {stream_exit}. Restarting stream...")
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
    command = build_muselsl_command()
    if command is None:
        print("muselsl is not installed or is not importable.")
        print("Install it with:")
        print(f"  {sys.executable} -m pip install muselsl")
        print("Or with pipx: pipx install muselsl")
        return 1

    if MUSE_ADDRESS:
        target = f"address {MUSE_ADDRESS}" + (f" ({MUSE_NAME})" if MUSE_NAME else "")
    else:
        target = f"name {MUSE_NAME or '(first Muse found)'}"
    print(f"Starting muselsl for Muse 2 / legacy Muse ({target}, model {MUSELSL_MODEL}).")
    print("If Windows has the Muse paired, remove it from Bluetooth settings first.")
    print("Do not run OpenMuse at the same time.")
    print("Press Ctrl+C to stop.")
    print()

    while True:
        print("Launching:", " ".join(command))
        try:
            process = subprocess.Popen(command, cwd=ROOT)
        except OSError as exc:
            print(f"Could not start muselsl: {exc}")
            print("Install it with:")
            print(f"  {sys.executable} -m pip install muselsl")
            return 1

        try:
            if wait_for_lsl_stream():
                print("Starting NeuroDrive dashboard...")
                dashboard_exit = run_dashboard_until_stream_stops(process)
                if dashboard_exit is not None:
                    process.terminate()
                    return dashboard_exit

            print("muselsl did not publish a usable EEG stream in time.")
        except KeyboardInterrupt:
            print("\nStopping muselsl...")
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
            print(f"muselsl stopped with exit code {exit_code}.")

        print("Retrying in 5 seconds...")
        time.sleep(5)


if __name__ == "__main__":
    raise SystemExit(main())
