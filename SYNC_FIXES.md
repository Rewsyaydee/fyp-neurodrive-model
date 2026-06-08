# Stream Synchronization Fixes

This document describes the improvements made to fix the synchronization issues between the Muse headband stream and the NeuroDrive dashboard.

## Problems Identified

1. **Timing Mismatch**: The original code tried to emit data at exactly 20Hz but didn't account for processing delays
2. **Blocking I/O**: The main thread was handling both stream capture and dashboard updates
3. **No Buffer Management**: Samples could be lost during high-frequency streams
4. **Missing Latency Tracking**: No way to monitor sync health

## Solutions Implemented

### 1. Separated Processing Threads

Created two dedicated threads:
- **Stream Capture Thread**: Continuously pulls samples from LSL stream
- **Data Processing Thread**: Handles emissions to dashboard at controlled rate

### 2. Improved Buffering System

- Added a circular buffer (`_sample_buffer`) to hold incoming samples
- Implemented averaging window (`SYNC_WINDOW = 5`) for smoother display
- Used a queue (`_emission_queue`) for thread-safe data passing

### 3. Rate Limiting & Flow Control

- Emissions now occur at precise 20Hz intervals (`TARGET_INTERVAL`)
- Queue prevents buffer overflow with max size limit
- Graceful handling of missed emissions

### 4. Enhanced Dashboard Synchronization

- Added latency calculation based on server timestamps
- Connection status indicator with real-time feedback
- Automatic reconnection with exponential backoff
- Disabled chart animations for better sync

### 5. Thread Safety

- Added locks (`_data_lock`) for shared data access
- Atomic operations for sequence numbers
- Safe queue operations with error handling

## Key Improvements

### In `app.py`:

```python
# Before: Single thread handling everything
def _capture_loop(self, inlet: StreamInlet, labels: List[str]) -> None:
    # Direct emission with potential blocking
    self._emit_metrics(display_payload)

# After: Separated concerns with dedicated thread
def _process_data_thread(self) -> None:
    # Controlled emission at exact rate
    if now - self._last_emit_time >= TARGET_INTERVAL:
        self._emit_metrics(payload)
```

### In Dashboard:

```javascript
// Added latency tracking
socket.on('metrics_update', (data) => {
    const latency = calculateLatency(data.timestamp_epoch);
    if (latency > SYNC_CONFIG.maxLatency) {
        addLog(`High latency detected: ${latency}ms`, 'warn');
    }
});
```

## Configuration Options

You can adjust these parameters in the code:

```python
# In app.py
TARGET_HZ = 20.0  # Display refresh rate
MAX_BUFFER_SIZE = 100  # Maximum samples to buffer
SYNC_WINDOW = 5  # Number of samples to average
```

```javascript
// In dashboard
const SYNC_CONFIG = {
    expectedUpdateRate: 20, // Hz
    maxLatency: 200, // ms
    timeoutMs: 5000, // ms
};
```

## Testing the Fix

1. Start the application with your Muse headband
2. Monitor the connection status indicator (should show "Connected")
3. Check the latency indicator (should be under 200ms)
4. Verify smooth updates in the metrics display
5. Watch for sync warnings in the log

## Troubleshooting

If sync issues persist:

1. **High Latency**: Check network conditions and browser performance
2. **Missed Updates**: Reduce `TARGET_HZ` to 10Hz if needed
3. **Connection Drops**: Ensure stable Bluetooth connection to Muse
4. **Buffer Overflow**: Increase `MAX_BUFFER_SIZE` if samples are lost

## Files Changed

- `app.py` → Improved stream manager with better synchronization
- `templates/fypdashboard.html` → Enhanced dashboard with sync monitoring
- Created backups in `backups/` folder

The synchronization should now be much more stable and responsive!