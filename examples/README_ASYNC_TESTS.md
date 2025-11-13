# Async Motion Test Examples

This directory contains test scripts demonstrating the new async task architecture with real-time cancellation support.

## Prerequisites

1. **Hardware Setup**
   - Suruga Seiki DA1100 controller connected and powered on
   - Z1 axis (axis 3) servo enabled
   - Network connection to ADS address: `5.146.68.190.1.1` (or update in script)

2. **Software Setup**
   ```bash
   # Ensure all dependencies are installed
   pip install -e .
   ```

3. **Safety Check**
   - Ensure 100um movement on Z1 axis is safe for your setup
   - Adjust distance/speed in scripts if needed

## Test Scripts

### 1. Simple Direct Test (Recommended First)

**File:** `test_simple_async_motion_stop.py`

**What it does:**
- Uses controller async methods directly (no task management overhead)
- Starts Z1 axis relative movement: +100um at 50um/s (2 seconds duration)
- Cancels after 0.3 seconds using `asyncio.Event`
- Verifies axis stopped mid-flight

**Run:**
```bash
python examples/test_simple_async_motion_stop.py
```

**Expected output:**
```
======================================================================
Simple Async Motion with Cancellation - Direct Test
======================================================================

[1] Connecting to controller...
SUCCESS: Connected

[2] Checking axis 3 (Z1) initial state...
  Position: 1500.00 um
  Servo on: True

[3] Starting movement: +100.00 um at 50.0 um/s
  Estimated duration: 2.00 seconds
  Starting background movement...
  Waiting 0.3 seconds...
  Position now: 1515.23 um (moved +15.23 um)
  Is moving: True

[4] *** CANCELLING MOVEMENT ***
  Cancelled successfully: Movement cancelled by user

[5] Results:
  Initial position: 1500.00 um
  Final position: 1517.82 um
  Requested distance: +100.00 um
  Actual distance: +17.82 um
  Stopped at: 17.8% of target

✓ SUCCESS: Movement stopped mid-flight!
  Axis stopped after only 17.82 um

[6] Progress updates received: 3
  Update 1: 0% - 1500.0 um
  Update 2: 30% - 1515.0 um
  Update 3: 100% - 1517.82 um

[7] Disconnecting...
Done!
```

**Key indicators of success:**
- ✅ Actual distance < Requested distance (e.g., 17.82um out of 100um)
- ✅ "Movement stopped mid-flight!" message
- ✅ "Cancelled successfully" message
- ✅ Progress updates captured during movement

---

### 2. Full Task System Test

**File:** `test_async_motion_with_stop.py`

**What it does:**
- Uses complete task management system
- Creates task with UUID via `TaskManager`
- Executes via `MotionTaskExecutor`
- Demonstrates full task lifecycle (pending → running → cancelled)
- Shows task status checking

**Run:**
```bash
python examples/test_async_motion_with_stop.py
```

**Expected output:**
```
======================================================================
Async Motion with Immediate Stop - Test Example
======================================================================

[1] Initializing controller...
[2] Connecting to hardware (default ADS address)...
SUCCESS: Connected to controller

[3] Checking axis 3 (Z1) status...
  Current position: 1500.00 um
  Servo on: True
  Is moving: False
  Is error: False

[4] Creating task for relative movement...
  Task created: a1b2c3d4-e5f6-7890-abcd-1234567890ef
  Movement: +100.00 um at 50.0 um/s
  Estimated time: 2.00 seconds

[5] Starting movement in background task...
  Waiting 0.3 seconds for movement to start...
  Current position: 1516.45 um
  Is moving: True

[6] *** CANCELLING MOVEMENT NOW ***
  Cancellation requested for task a1b2c3d4-e5f6-7890-abcd-1234567890ef
  Task status: stopping

[7] Waiting for movement to stop...
  Movement was cancelled: OperationCancelledException: Movement was cancelled: Movement cancelled by user

[8] Checking final state...
  Initial position: 1500.00 um
  Final position: 1518.92 um
  Actual travel: +18.92 um
  Requested travel: +100.00 um
  Is moving: False

SUCCESS: Movement was stopped mid-flight!
  Only traveled 18.92 um out of 100.00 um requested

[9] Final task status:
  Task ID: a1b2c3d4-e5f6-7890-abcd-1234567890ef
  Status: cancelled
  Operation: axis_movement
  Error: Movement was cancelled: Movement cancelled by user

[10] Disconnecting...
Done!
```

**Key indicators of success:**
- ✅ Task created with UUID
- ✅ Task status transitions: pending → running → stopping → cancelled
- ✅ OperationCancelledException raised
- ✅ Axis stopped mid-flight
- ✅ Task error message populated

---

## Troubleshooting

### "Failed to connect to controller"
**Cause:** Hardware not accessible or wrong ADS address

**Fix:**
1. Check hardware is powered on
2. Verify network connection
3. Update ADS address in script if needed:
   ```python
   ads_address = "YOUR.ADS.ADDRESS.HERE"
   ```

### "Servo not enabled"
**Cause:** Axis servo is off

**Fix:**
1. Enable servo via API:
   ```bash
   curl -X POST http://localhost:8000/servo/on \
     -H "Content-Type: application/json" \
     -d '{"axis_id": 3}'
   ```
2. Or use the existing servo enable script

### "Movement completed without cancellation"
**Cause:** Movement too fast, completed before cancellation took effect

**Fix:** Reduce speed or increase distance:
```python
distance = 500.0  # More distance
speed = 50.0      # Slow speed = more time to cancel
```

### "Axis already moving"
**Cause:** Previous movement not completed

**Fix:** Stop axis first:
```bash
curl -X POST http://localhost:8000/move/stop \
  -H "Content-Type: application/json" \
  -d '{"axis_id": 3}'
```

---

## Customization

### Change Axis
Edit in script:
```python
axis_number = 1  # Change to X1, Y1, etc.
```

### Change Movement Parameters
```python
distance = 200.0  # Micrometers
speed = 100.0     # um/s
```

### Change Cancellation Timing
```python
await asyncio.sleep(0.5)  # Wait longer before cancelling
```

### Add More Progress Tracking
```python
def progress_callback(data):
    print(f"Progress: {data}")
    # Log to file, update UI, etc.
```

---

## Understanding the Output

### Position Values
- **Initial position:** Where axis started
- **Final position:** Where axis stopped
- **Actual travel:** How far axis actually moved
- **Requested travel:** How far you asked it to move

### Success Criteria
Movement stopped mid-flight if:
```
Actual travel < 90% of Requested travel
```

Example:
- Requested: 100um
- Actual: 18um
- Percentage: 18%
- Result: ✅ SUCCESS (18% < 90%)

### Progress Updates
Shows how many times the progress callback was invoked:
- **Low count (1-2):** Very fast movement or immediate cancellation
- **Medium count (3-5):** Normal for 0.3s delay @ 50ms polling
- **High count (10+):** Slower movement or longer delay

---

## Next Steps

After verifying these tests work:

1. **Study the code:** See how `cancellation_event` and `progress_callback` work
2. **Try other axes:** Test on X, Y axes with different parameters
3. **Integrate with your application:** Use the same pattern in your own code
4. **Add to REST API:** Update routers to use task system (see ASYNC_ARCHITECTURE.md)

---

## Additional Examples

### Angle Adjustment Test (Coming Soon)
Will demonstrate async cancellation of angle adjustment operations.

### Alignment Test (Coming Soon)
Will demonstrate async cancellation of flat/focus alignment operations.

### Profile Measurement Test (Coming Soon)
Will demonstrate async cancellation of profile scanning operations.

---

## Support

- **Architecture docs:** See `ASYNC_ARCHITECTURE.md`
- **Implementation details:** See `IMPLEMENTATION_SUMMARY.md`
- **API documentation:** See `README.md`
- **Issues:** Report at GitHub repository
