#!/usr/bin/env python3
"""
Test script to verify streaming works with the fixed code
"""

import math
import sys
import tempfile
import time
import threading
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

def test_stream_manager():
    """Test the stream manager with simulated data"""
    print("Testing MuseStreamManager...")

    from app import MuseStreamManager

    # Create a test data directory
    test_dir = Path("test_data")
    test_dir.mkdir(exist_ok=True)

    # Create manager
    manager = MuseStreamManager(test_dir)

    # Create a mock socketio
    class MockSocketIO:
        def __init__(self):
            self.events = []

        def emit(self, event, data):
            self.events.append((event, data))
            print(f"Emitted {event}: {data}")

    mock_socketio = MockSocketIO()
    manager.set_socketio(mock_socketio)

    print("✓ Manager created successfully")

    # Test payload creation
    import numpy as np
    from utils.anxiety_calculator import calculate_anxiety_estimate

    # Create simulated sample data
    sample = np.random.randn(5).tolist()
    timestamp = time.time()
    labels = ["TP9", "AF7", "AF8", "TP10", "Right AUX"]

    # Build payload
    payload = manager._build_payload(sample, timestamp, labels)

    print("✓ Payload created successfully")
    print(f"  - Anxiety: {payload['anxiety']:.2f}")
    print(f"  - Label: {payload['anxiety_label']}")

    # Test record creation
    record = manager._record_from_payload(payload)
    print("✓ Record created successfully")

    # Test emission
    manager._emit_metrics(payload)
    print(f"✓ Emitted {len(mock_socketio.events)} events")

    return True


def test_muse2_compatibility():
    """Test Muse 2 / muselsl raw EEG compatibility."""
    print("\nTesting Muse 2 / muselsl compatibility...")

    from app import MuseStreamManager

    class FakeMuse2Stream:
        def name(self):
            return "Muse"

        def type(self):
            return "EEG"

        def channel_count(self):
            return 5

        def nominal_srate(self):
            return 256.0

        def as_xml(self):
            return "<info/>"

    manager = object.__new__(MuseStreamManager)
    score = manager._score_stream(FakeMuse2Stream())
    assert score >= 140, f"Muse 2 LSL stream score is too low: {score}"
    print(f"✓ Muse 2 LSL stream accepted (score {score})")

    with tempfile.TemporaryDirectory() as temp_dir:
        manager = MuseStreamManager(Path(temp_dir))
        manager._sample_rate = 256.0
        manager._stream_name = "Muse"
        manager._stream_type = "EEG"

        labels = ["TP9", "AF7", "AF8", "TP10", "Right AUX"]
        selected = manager._select_eeg_values([1.0, 2.0, 3.0, 4.0, 999.0], labels)
        assert selected == [1.0, 2.0, 3.0, 4.0], selected
        print("✓ Right AUX is ignored for band-power analysis")

        payload = {}
        timestamp = time.time()
        for index in range(300):
            phase = 2.0 * math.pi * 10.0 * (index / 256.0)
            sample = [math.sin(phase)] * 4 + [999.0]
            payload = manager._build_payload(sample, timestamp + index / 256.0, labels)

        assert payload["heart_rate"] == 0.0
        assert payload["alpha"] > 0.0
        assert payload["anxiety_method"] != "insufficient signal"
        print(
            f"✓ Raw EEG converted to bands: alpha={payload['alpha']:.2f}, "
            f"anxiety={payload['anxiety']:.2f}"
        )

    return True


def test_flask_app():
    """Test that Flask app can be imported and configured"""
    print("\nTesting Flask app...")

    from app import app, socketio

    # Test app configuration
    assert app.config['SECRET_KEY'] == 'neurodrive_secret_key'
    print("✓ Flask app configured correctly")

    # Test routes exist
    with app.test_client() as client:
        response = client.get('/')
        assert response.status_code == 200
        assert len(response.data) > 1000, "Dashboard HTML is empty or too small"
        assert b"NEURODRIVE" in response.data, "Dashboard title is missing"
        print("✓ Dashboard route works and returns real HTML")

        response = client.get('/api/status')
        assert response.status_code == 200
        data = response.get_json()
        assert 'status' in data
        print("✓ Status API works")

    return True

def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    print("=" * 60)
    print("NEURODRIVE - Streaming Test Suite")
    print("=" * 60)
    print()

    try:
        # Test stream manager
        if not test_stream_manager():
            print("❌ Stream manager test failed")
            return 1

        # Test Muse 2 / muselsl compatibility
        if not test_muse2_compatibility():
            print("❌ Muse 2 compatibility test failed")
            return 1

        # Test Flask app
        if not test_flask_app():
            print("❌ Flask app test failed")
            return 1

        print("\n✅ All tests passed!")
        print("\nMuse 2 / muselsl compatibility checks passed.")
        print("\nTo test with your Muse headband:")
        print("1. Double-click START_NEURODRIVE.bat (or run: python start.py)")
        print("2. Choose option 1 for Muse 2 (muselsl) or option 2 for Muse S Athena (OpenMuse)")
        print("3. The dashboard should now stream data properly")

        return 0

    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())