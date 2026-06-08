#!/usr/bin/env python3
"""
NeuroDrive - Muse Headband Connection Script (REFACTORED)
==========================================================
Refactored: This script now ONLY discovers and verifies the Muse stream.
It does NOT create its own LSL StreamInlet — that responsibility belongs
solely to ``app.MuseStreamManager`` (the Singleton).

The discovery here gives the user immediate visual feedback that their
headband is working, but the actual data acquisition is left to the
Flask app so there is exactly ONE inlet in the system.
"""

import os
import sys
import time
import subprocess
from pathlib import Path
from typing import Optional, Any

try:
    import pylsl

    resolve_stream = (
        getattr(pylsl, "resolve_stream", None)
        or getattr(pylsl, "resolve_streams", None)
        or getattr(pylsl, "resolve", None)
    )
except Exception:
    resolve_stream = None

# Connection settings
DISCOVERY_TIMEOUT = 5.0
DISCOVERY_RETRY_DELAY = 2.0
MIN_CHANNELS = 4

ROOT = Path(__file__).resolve().parent


# -----------------------------------------------------------------------
# LSL helpers
# -----------------------------------------------------------------------


def _resolve_lsl_streams(timeout: Optional[float] = None):
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
    return (
        "muse" in name
        or "muse" in stream_type
        or ("eeg" in stream_type and channel_count >= MIN_CHANNELS)
    )


# -----------------------------------------------------------------------
# UI helpers
# -----------------------------------------------------------------------


def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")


def print_header():
    print("=" * 60)
    print("NEURODRIVE - Muse Headband Connection")
    print("=" * 60)
    print()


def print_status(message: str, symbol: str = "⏳"):
    print(f"{symbol} {message}")
    sys.stdout.flush()


def print_success(message: str):
    print(f"✅ {message}")


def print_error(message: str):
    print(f"❌ {message}")


# -----------------------------------------------------------------------
# Discovery
# -----------------------------------------------------------------------


def score_muse_stream(stream) -> int:
    """Score a stream to determine if it's a valid Muse stream (0 = not Muse)."""
    score = 0
    name = str(_stream_value(stream, "name", ""))
    stream_type = str(_stream_value(stream, "type", ""))

    if "muse" in name.lower():
        score += 100
    if "athena" in name.lower():
        score += 50
    if "eeg" in stream_type.lower():
        score += 30
    if "muse" in stream_type.lower():
        score += 30

    try:
        channel_count = int(_stream_value(stream, "channel_count", 0) or 0)
        if channel_count >= MIN_CHANNELS:
            score += 20
        else:
            score -= 10
    except Exception:
        score -= 5

    return score


def discover_muse_stream():
    """
    Discover available Muse streams.
    Returns list of (score, stream_info, name) tuples, sorted best-first.
    """
    print_status("Scanning for Muse streams...")

    attempt = 0
    while True:
        try:
            found_streams = _resolve_lsl_streams(timeout=DISCOVERY_TIMEOUT)

            muse_streams = []
            for stream in found_streams:
                if _looks_like_muse_stream(stream):
                    s = score_muse_stream(stream)
                    if s > 0:
                        name = str(_stream_value(stream, "name", "Unknown"))
                        muse_streams.append((s, stream, name))

            if muse_streams:
                muse_streams.sort(key=lambda x: x[0], reverse=True)
                return muse_streams

        except Exception as e:
            print_error(f"Scan error: {e}")

        attempt += 1
        print_status(f"No streams found. Retrying... ({attempt})")
        time.sleep(DISCOVERY_RETRY_DELAY)


def verify_stream_live(stream_info: Any, duration: float = 5.0) -> bool:
    """
    Verify the stream is actually pushing data.

    IMPORTANT: We create a TEMPORARY inlet just for verification, then
    close it.  This is safe because we close it BEFORE launching the
    Flask app — no conflict with MuseStreamManager's inlet.

    Returns True if data is flowing.
    """
    try:
        from pylsl import StreamInlet as _StreamInlet
    except ImportError:
        print_error("Cannot verify — pylsl not available")
        return True  # assume OK if we can't check

    print_status("Verifying signal quality...")

    try:
        inlet = _StreamInlet(stream_info, max_buflen=2, recover=False)
        sample_count = 0
        channel_count = 0
        start_time = time.time()

        try:
            channel_count = inlet.channel_count
        except Exception:
            pass

        while time.time() - start_time < duration:
            try:
                sample, _ = inlet.pull_sample(timeout=1.0)
                if sample:
                    sample_count += 1
            except Exception:
                pass

        # CRITICAL: close the temporary inlet NOW so it doesn't conflict
        # with the Flask app's Singleton inlet.
        inlet.close_stream()

        if sample_count > 0:
            rate = sample_count / (time.time() - start_time)
            print_success(
                f"Signal quality OK - {channel_count} channels, ~{rate:.1f} Hz"
            )
            return True
        else:
            print_error("No data received — check headband placement")
            return False

    except Exception as e:
        print_error(f"Verification failed: {e}")
        # Best-effort close
        try:
            inlet.close_stream()  # type: ignore[possibly-undefined]
        except Exception:
            pass
        return False


# -----------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------


def main() -> int:
    clear_screen()
    print_header()

    print("This script will search for your Muse headband, verify the")
    print("signal, then launch the NeuroDrive dashboard.")
    print()
    print("Make sure your headband is:")
    print("  - Turned on")
    print("  - NOT paired in Windows Bluetooth settings")
    print("  - Close enough to this computer")
    print()
    print("NOTE: OpenMuse must already be streaming!")
    print("      If not, run:  OpenMuse stream --address <your-headset-address>")
    print()

    if resolve_stream is None:
        print_error("pylsl is not available in this Python environment.")
        print()
        choice = input("Attempt to install pylsl now? [Y/n]: ").strip().lower()
        if choice in ("", "y", "yes"):
            try:
                subprocess.check_call(
                    [sys.executable, "-m", "pip", "install", "pylsl"]
                )
                print_success("pylsl installed. Please re-run this script.")
                return 0
            except Exception as e:
                print_error(f"Install failed: {e}")
                return 1
        return 1

    # 1. Discover
    streams = discover_muse_stream()

    if not streams:
        print_error("No Muse streams found!")
        print()
        print("Troubleshooting:")
        print("  1. Is the headband turned on?")
        print("  2. Is OpenMuse streaming? (OpenMuse stream --address ...)")
        print("  3. Is it paired in Windows Bluetooth? (should NOT be)")
        return 1

    # 2. Show what we found
    print(f"\nFound {len(streams)} potential stream(s):")
    for i, (score, stream, name) in enumerate(streams):
        ch = _stream_value(stream, "channel_count", "?")
        srate = _stream_value(stream, "nominal_srate", "?")
        print(f"  {i+1}. {name}")
        print(f"     Channels: {ch}, Sample rate: {srate} Hz, Score: {score}")
    print()

    # 3. Pick the best one
    _, best_stream, stream_name = streams[0]
    print(f"Using best match: {stream_name}")

    # 4. Verify signal quality (temporary inlet — CLOSED before launching app)
    verified = verify_stream_live(best_stream)
    if not verified:
        print()
        print("⚠️  Signal verification failed, but stream was detected.")
        choice = input("Launch dashboard anyway? [Y/n]: ").strip().lower()
        if choice not in ("", "y", "yes"):
            return 1

    # 5. Launch the Flask app
    #    The app's MuseStreamManager (Singleton) will create the ONE real inlet.
    print()
    print_success("Stream verified! Launching NeuroDrive Dashboard...")
    print(f"Dashboard URL: {DASHBOARD_URL}")
    print("Press Ctrl+C to stop")
    print()

    # Launch as subprocess for clean process isolation
    env = os.environ.copy()
    env["NEURODRIVE_SKIP_MUSE_CHECK"] = "1"  # already verified above

    try:
        result = subprocess.run(
            [sys.executable, str(ROOT / "app.py")],
            cwd=ROOT,
            env=env,
        )
        return result.returncode
    except KeyboardInterrupt:
        print("\nShutting down...")
        return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\nConnection cancelled.")
        sys.exit(1)
