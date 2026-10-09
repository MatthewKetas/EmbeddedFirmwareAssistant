# Prompt

## System / Context

You are acting as an embedded systems engineer. The task is to design a simple data-acquisition system (DAS) that periodically samples a temperature sensor and reports abnormal readings. The design should be suitable for a small embedded platform or a lightweight software simulation, and should be clear enough to hand off to a firmware or systems engineer for implementation.

## Engineering Objective

Design a system that:

- Samples a temperature sensor at a defined interval.
- Converts raw sensor data into engineering units (°C).
- Evaluates each measurement against defined normal/abnormal thresholds.
- Reports (logs, flags, or alerts on) abnormal measurements in a timely and reliable manner.
- Operates continuously and predictably without manual intervention.

## Assumptions

- A single analog or digital temperature sensor is used.
- The sensor has a known, bounded operating range and accuracy spec.
- Power and communication to the sensor are reliable.
- The system has a real-time clock or counter for consistent sampling intervals.
- “Abnormal” means outside a specified safe operating range.
- A human uses the reports with no autonomous corrective action.

## Input Information

- **Sensor type & interface:** e.g., analog voltage (0–5 V) via ADC, or digital (I2C/SPI/1-Wire).
- **Sampling rate:** e.g., 1 sample per second.
- **Normal operating range:** e.g., 10°C to 40°C.
- **Abnormal thresholds:** e.g., <0°C or >60°C = fault; between normal and fault = warning.
- **Sensor accuracy/tolerance:** e.g., ±0.5°C.
- **Reporting mechanism:** e.g., serial console, log file, LED indicator, network message.

## Constraints

- Must run on limited hardware resources (e.g., low RAM/CPU if embedded).
- Must handle sensor read failures gracefully (no crashes, no false triggers from a single glitch).
- Sampling and reporting must not block or drift the main control loop (deterministic timing).
- Minimal false positives/negatives.
- Should be simple: avoid complex statistical models or over-engineering for this stage.

## Required Reasoning / Task Steps

1. Define the sensor interface and how raw data is acquired (polling vs. interrupt-driven).
2. Define the sampling loop structure (timing mechanism, sample rate).
3. Define the signal conditioning steps (unit conversion, noise filtering/averaging).
4. Define the threshold-comparison logic (normal / warning / fault states).
5. Define how transient vs. sustained abnormal conditions are distinguished (e.g., N consecutive out-of-range samples before reporting).
6. Define the reporting/alerting mechanism and its format.
7. Define error handling for sensor faults (disconnection, out-of-range raw signal, stale data).
8. Summarize the system as a block diagram or state machine description.

## Output Requirements

Provide:

- A short system architecture description (block diagram in words or ASCII).
- A state machine or flowchart describing sampling → evaluation → reporting logic.
- Pseudocode for the main sampling/evaluation loop.
- A table of defined thresholds and corresponding system responses.
- Notes on error handling and edge cases.


# Response
## System Architecture Description

This design outlines a **Deterministic Sampling and Evaluation Unit** suitable for implementation on microcontrollers such as STM32 Cortex-M series or ESP32. The system operates in a single main thread to minimize context switching overhead but utilizes timer interrupts to ensure sampling precision.

### 1. Block Diagram (Conceptual)
```text
+-------------------+       +-----------------------+       +----------------------+
|   Temp Sensor     |-----> |   ADC / Digital I2C   |-----> |   Pre-Filtering     |
|   (I2C/Digital)   |       |   Driver Library      |       |   (Averaging/Fault) |
+-------------------+       +-----------+----------+       +-----------+----------+
                                         |                            |
                                   [ Raw ADC Sample ]           [ Validity Check ]
                                         |                            |
                                         v                            v
                              +-----------------------+       +---------------+
                              |   Threshold Logic     |       |   Alert Log   |
                              |   (Normal/Warning/    |       |   Manager     |
                              |      Fault)            |       +----------+----+
                              +-----------------------+                  |
                                         |                            |
                                         v                            v
                              +-----------------------+       +---------------+
                              |   System State Flag   |----->  |   UART / LED  |
                              |   (0: OK, 1: WARN,   |        |   / Network   |
                              |      2: CRIT)         |       +----------+----+
                              +-----------------------+                  |
                                         ^                            |
                                         |                            v
                              +-----------------------+       +---------------+
                              |   Timer Counter       |       |   Error Log   |
                              |   (Sample Period      |<------+   / Debug     |
                              |    Reset Logic)       |        +---------------+
                              +-----------------------+
```

### 2. State Machine / Flow Logic
The system logic follows a **State-Based Sampling Loop**.

*   **IDLE/SAMPLE:** Acquire raw sensor data. Check for communication timeout.
*   **CONVERT:** Map raw register/value to degrees Celsius using calibration offset/scale.
*   **FILTER:** Compare current value against the last $N$ stored values (e.g., 3-sample window) to reject transient noise. If variance is high, discard or average; if stable, proceed.
*   **EVALUATE:** Map temperature to state:
    *   State `NORMAL` (10°C–40°C): Reset fault counters. Log OK status occasionally (e.g., once every 60s).
    *   State `WARNING` (0–10°C or 40–60°C): Increment a warning counter. If continuous > 3 samples, log WARNING.
    *   State `FAULT` (<0°C or >60°C): Increment fault counter. If continuous > 5 samples, send ALERT immediately.
*   **REPORT:** If alert condition is met and timer since last alert allows (rate limiting), push message to UART/Network.
*   **ERROR:** If I2C timeout or ADC invalid code received: Mark `SENSOR_OFFLINE`. Do not trigger Fault logic based on this value; only log the error and wait for recovery.

### 3. Threshold Logic Definition Table

| Temperature Range ($^\circ$C) | State Class | Action / Response |
| :--- | :--- | :--- |
| **Fault Low**: $< -5$ | `CRITICAL_LOW` | Trigger Alert after sustained check (see below). Log immediately. |
| **Warning Low**: $-5 \le T < 10$ | `WARNING_LOW` | Increment warning counter. Log if persistent. |
| **Normal**: $10 \le T \le 40$ | `OK` | System Nominal. Reset Fault/Warning counters. No Alert. |
| **Warning High**: $40 < T \le 60$ | `WARNING_HIGH` | Increment warning counter. Log if persistent. |
| **Fault High**: $T > 60$ | `CRITICAL_HIGH` | Trigger Alert after sustained check. Log immediately. |
| **Sensor Offline** | `SENSOR_OFFLINE` | Do not trigger Fault logic. Log error once per minute to avoid spam. |

*Note: Sustained Check ($N_{sust}$): A condition is considered "real" only if it persists for $N_{sust}$ consecutive valid samples.*
*   **Alert Rate:** Maximum 1 alert per second (debounce the output) to avoid flooding logs with identical lines.

### 4. Pseudocode Implementation

```c
// Configuration Constants
#define SAMPLE_INTERVAL_MS    1000    // 1 Hz sampling
#define SUSTAINED_SAMPLES_LOW    5     // Fault threshold duration
#define SUSTAINED_SAMPLES_WARN   3     // Warning threshold duration
#define ADC_SCALE      0.0625         // Example scale for I2C sensor

// Global Variables (Thread/ISR Safe)
uint16_t raw_sample_buffer[4];       // Circular buffer (size 4 for simplicity)
int last_alert_time_ms = 0;          // Prevents log flooding
int consecutive_count_normal = 0;
enum { STATE_OK, STATE_WARN_LOW, STATE_WARN_HIGH, STATE_CRIT_LOW, STATE_CRIT_HIGH } global_state = STATE_OK;

void sensor_sample_task(void) {
    uint32_t current_time_ms = get_system_tick(); // High-res clock
    
    // 1. ACQUIRE & CONVERSION
    int16_t raw_data = read_sensor_register();    // Returns valid value or -1 on I2C timeout
    if (raw_data == -1) {
        set_error_status("SENSOR_COMM_TIMEOUT");
        return; // Skip logic, do not update state counters to avoid glitching
    }

    float temp_c = (float)raw_data * ADC_SCALE;   // Convert to Engineering Units
    
    // 2. FILTERING / NOISE REDUCTION
    // Update a simple running average or check variance if desired. 
    // For simplicity, we apply the sustained logic below directly on the value.

    // 3. THRESHOLD LOGIC
    switch (global_state) {
        case STATE_OK:
            if ((temp_c < 10) || (temp_c > 40)) {
                global_state = (temp_c < 20) ? STATE_WARN_LOW : STATE_WARN_HIGH; 
                consecutive_count_normal = 0; // Break normal streak
            } else {
                consecutive_count_normal++;   // Continue normal streak
            }
            break;

        case STATE_WARN_LOW:
        case STATE_CRIT_LOW:
        case STATE_WARN_HIGH:
        case STATE_CRIT_HIGH:
            if (temp_c < 10 && temp_c >= -5) { global_state = STATE_WARN_LOW; consecutive_count_warn = ++consecutive_count_warn; }
            else if (temp_c > 40 && temp_c <= 60) { global_state = STATE_WARN_HIGH; consecutive_count_warn = ++consecutive_count_warn; }
            else if (temp_c < -5 || temp_c > 60) { global_state = (temp_c < 20) ? STATE_CRIT_LOW : STATE_CRIT_HIGH; consecutive_count_warn = ++consecutive_count_warn; }
            
            // 4. REPORTING & RATE LIMITING
            int fault_duration_check = current_time_ms - last_alert_time_ms; 
            
            if ((global_state == STATE_CRIT_LOW || global_state == STATE_CRIT_HIGH) && (fault_duration_check > SUSTAINED_SAMPLES_WARN * SAMPLE_INTERVAL_MS)) {
                send_alert("CRITICAL: Temp " + to_string(temp_c));
                last_alert_time_ms = current_time_ms; // Reset debounce timer
            } else if ((global_state == STATE_WARN_LOW || global_state == STATE_WARN_HIGH) && (fault_duration_check > SUSTAINED_SAMPLES_LOW * SAMPLE_INTERVAL_MS)) {
                send_warning("WARNING: Temp " + to_string(temp_c)); 
                last_alert_time_ms = current_time_ms; 
            }
            break;

        default: // Initial state handling
            if (consecutive_count_normal > 3) { send_ok_status(); }
    }
}

void error_handling(uint8_t err_code) {
    if (err_code == SENSOR_TIMEOUT) {
        log_message("Sensor not responding");
        // Do NOT update global_state or thresholds to prevent false alarms during power glitch
    }
}
```

### 5. Reporting Format Specification

The system output should be timestamped and include the state classification.

*   **Console/UART:** `[TS:10:30:45] STATUS=OK TEMP=22.4°C`
*   **Warning Alert:** `[TS:10:32:15] ALERT=WARN TEMP=45.2°C`
*   **Critical Fault:** `[TS:10:32:20] ALARM=CRIT TEMP=65.8°C`
*   **Sensor Error:** `[TS:10:32:22] ERROR=SENSOR_OFFLINE`

### 6. Error Handling & Edge Cases Notes

1.  **Sensor Glitch (Transient Noise):**
    *   If a single sample reads `45°C` when the true temp is `25°C`, do not trigger a warning. The filtering logic in step 3 requires sustained time ($N$ samples) before changing the state machine from Normal to Warning.

2.  **Sensor Disconnect (Stale Data):**
    *   If the ADC returns an invalid register or I2C reads a timeout, the system must **ignore** this reading for threshold calculations and log a specific "Offline" status. This prevents reporting a high temperature if the sensor wire is unplugged (which would usually read as max voltage/high digital code).

3.  **Deterministic Timing:**
    *   The `SAMPLE_INTERVAL_MS` delay function should be replaced by a hardware timer ISR in production to avoid jitter caused by blocking calls (e.g., UART send) on the main thread. The provided pseudocode uses a polling model suitable for resource-constrained environments but assumes `get_system_tick()` is available from an RTOS or Tick Timer.

4.  **Memory Protection:**
    *   The state variables (`global_state`, `raw_sample_buffer`) should be atomic if running in multi-tasking (RTOS) environments to prevent race conditions between the timer ISR and the main sampling task.

5.  **Calibration:**
    *   The `ADC_SCALE` and any Offset must be calibrated at manufacturing or startup using a reference temperature source. This calibration should be stored in non-volatile memory (Flash).