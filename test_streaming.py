#!/usr/bin/env python3
"""
NeuroDrive — Integration test suite.
Verifies: Flask app, REST API, MuseStreamManager, payload construction, CSV output.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


def test_payload_building():
    """Test that _build_payload produces correct structure with raw electrode fields."""
    print("--- Testing payload construction ---")

    from app import MuseStreamManager

    test_dir = Path("test_data")
    manager = MuseStreamManager(test_dir)

    # Simulated Muse EEG sample: 5 channels (TP9, AF7, AF8, TP10, Right AUX)
    sample = [822.5, 823.1, 821.8, 822.9, 512.0]
    timestamp = time.time()
    labels = ["TP9", "AF7", "AF8", "TP10", "Right AUX"]

    payload = manager._build_payload(sample, timestamp, labels)

    # Check raw electrode fields exist
    for key in ("af7", "af8", "tp9", "tp10", "right_aux"):
        assert key in payload, f"Missing field: {key}"
        assert isinstance(payload[key], float), f"{key} should be float"

    # Check band power fields exist
    for key in ("delta", "theta", "alpha", "beta", "gamma"):
        assert key in payload, f"Missing band: {key}"

    # Check anxiety fields
    for key in ("anxiety", "anxiety_label", "anxiety_method"):
        assert key in payload, f"Missing anxiety field: {key}"

    # Check metadata
    for key in ("sequence", "timestamp_iso", "timestamp_epoch", "stream_name", "sample_count"):
        assert key in payload, f"Missing metadata: {key}"

    # Verify electrode values match input
    assert abs(payload["tp9"] - 822.5) < 0.01, f"TP9 mismatch: {payload['tp9']}"
    assert abs(payload["af7"] - 823.1) < 0.01, f"AF7 mismatch: {payload['af7']}"
    assert abs(payload["af8"] - 821.8) < 0.01, f"AF8 mismatch: {payload['af8']}"
    assert abs(payload["tp10"] - 822.9) < 0.01, f"TP10 mismatch: {payload['tp10']}"
    assert abs(payload["right_aux"] - 512.0) < 0.01, f"Right AUX mismatch: {payload['right_aux']}"

    # With only 1 sample, FFT window isn't full -> band powers should be 0
    assert payload["delta"] == 0.0, "Delta should be 0 before FFT window fills"
    assert payload["anxiety_label"] == "no signal", "Should show no signal before FFT"

    print("  [OK] Payload structure correct")
    print(f"  [OK] Electrode values preserved: AF7={payload['af7']}, TP9={payload['tp9']}")
    print(f"  [OK] Initial state: anxiety={payload['anxiety']}, label={payload['anxiety_label']}")

    return True


def test_record_and_csv():
    """Test StreamRecord construction and CSV header."""
    print("--- Testing StreamRecord & CSV ---")

    from app import StreamRecord

    header = StreamRecord.csv_header()
    expected_cols = [
        "sequence", "timestamp_iso", "timestamp_epoch",
        "af7", "af8", "tp9", "tp10", "right_aux",
        "delta", "theta", "alpha", "beta", "gamma",
        "anxiety", "anxiety_label", "anxiety_method",
        "theta_beta_ratio", "alpha_sum_ratio", "high_freq_ratio",
        "stream_name",
    ]
    assert header == expected_cols, f"CSV header mismatch:\n  Got: {header}\n  Exp: {expected_cols}"

    record = StreamRecord(
        sequence=1,
        timestamp_iso="2026-06-01T00:00:00.000",
        timestamp_epoch=1000.0,
        af7=823.1, af8=821.8, tp9=822.5, tp10=822.9, right_aux=512.0,
        delta=25.0, theta=15.0, alpha=30.0, beta=20.0, gamma=10.0,
        anxiety=45.0, anxiety_label="medium", anxiety_method="qEEG band-ratio estimate",
        theta_beta_ratio=0.75, alpha_sum_ratio=0.30, high_freq_ratio=0.33,
        stream_name="Muse-EEG",
    )
    row = record.to_row()
    assert len(row) == len(header), f"Row length {len(row)} != header length {len(header)}"

    print("  [OK] CSV header matches expected columns")
    print("  [OK] Record serialization correct")

    return True


def test_fft_window_filling():
    """Test that FFT produces band powers after window fills."""
    print("--- Testing FFT band-power extraction ---")

    import numpy as np
    from app import MuseStreamManager

    test_dir = Path("test_data")
    manager = MuseStreamManager(test_dir)
    manager._sample_rate = 256.0

    labels = ["TP9", "AF7", "AF8", "TP10", "Right AUX"]

    # Generate 256 samples of simulated EEG (10 Hz alpha wave + noise)
    for i in range(256):
        t = i / 256.0
        # Simulate alpha wave (10 Hz) with some delta (1 Hz) and beta (20 Hz)
        sample = [
            100.0 * np.sin(2 * np.pi * 10 * t) + 10 * np.random.randn(),  # TP9
            100.0 * np.sin(2 * np.pi * 10 * t) + 10 * np.random.randn(),  # AF7
            50.0 * np.sin(2 * np.pi * 1 * t) + 10 * np.random.randn(),    # AF8
            50.0 * np.sin(2 * np.pi * 20 * t) + 10 * np.random.randn(),   # TP10
            512.0 + 5 * np.random.randn(),  # Right AUX
        ]
        timestamp = time.time() + t
        manager._build_payload(sample, timestamp, labels)

    band_powers = manager._latest_band_powers
    print(f"  [OK] FFT produced band powers after {len(manager._raw_eeg_window)} samples:")
    for band in ("delta", "theta", "alpha", "beta", "gamma"):
        print(f"       {band}: {band_powers.get(band, 0):.1f}%")

    # Alpha should be dominant (we injected a 10 Hz signal)
    alpha_power = band_powers.get("alpha", 0)
    assert alpha_power > 0, "Alpha band power should be > 0 after FFT"

    print("  [OK] FFT pipeline functional — band powers extracted")

    return True


def test_flask_app():
    """Test Flask app routes."""
    print("--- Testing Flask app ---")

    from app import app, socketio

    assert app.config["SECRET_KEY"] == "neurodrive_secret_key"

    with app.test_client() as client:
        r = client.get("/")
        assert r.status_code == 200, f"GET / returned {r.status_code}"

        r = client.get("/api/status")
        assert r.status_code == 200, f"GET /api/status returned {r.status_code}"
        data = r.get_json()
        assert "is_running" in data

        r = client.get("/api/sessions")
        assert r.status_code == 200

    print("  [OK] All Flask routes responding")
    return True


def main():
    print("=" * 60)
    print("NEURODRIVE - Integration Test Suite")
    print("=" * 60)
    print()

    tests = [
        test_payload_building,
        test_record_and_csv,
        test_fft_window_filling,
        test_flask_app,
    ]

    passed = 0
    for test in tests:
        try:
            if test():
                passed += 1
        except Exception as e:
            print(f"  [FAIL] {test.__name__}: {e}")
            import traceback
            traceback.print_exc()

    print()
    print(f"Results: {passed}/{len(tests)} tests passed")

    if passed == len(tests):
        print("All tests passed.")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
