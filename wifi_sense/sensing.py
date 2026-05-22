import time
import sys
import math
import subprocess
import re
from collections import deque
from wifi_sense.connection import get_current_connection

def ping_gateway(gateway_ip, timeout_ms=500):
    """
    Measures RTT (Round Trip Time) to the gateway in milliseconds.
    Uses native Windows ping command for standard compatibility.
    """
    try:
        # Run a single quick ping
        start = time.perf_counter()
        result = subprocess.run(
            ["ping", "-n", "1", "-w", str(timeout_ms), gateway_ip],
            capture_output=True,
            text=True,
            errors="ignore",
            check=True
        )
        end = time.perf_counter()
        
        # Parse output for time=XXms
        match = re.search(r"time[=<](\d+)ms", result.stdout)
        if match:
            return float(match.group(1))
        else:
            # Fallback to python performance counter if output matches successful execution but time parsing fails
            if "TTL=" in result.stdout:
                return (end - start) * 1000.0
            return None
    except Exception:
        return None

class SignalSensingEngine:
    def __init__(self, target_ssid=None, poll_interval=0.1, window_size=50):
        self.target_ssid = target_ssid
        self.poll_interval = poll_interval
        self.window_size = window_size
        
        # Double-ended queues to store sliding window samples
        self.rssi_history = deque(maxlen=window_size)
        self.rtt_history = deque(maxlen=window_size)
        
        # Detect gateway IP for active wave latency probing
        self.gateway_ip = self._detect_gateway()
        
    def _detect_gateway(self):
        """
        Attempts to parse default gateway from route print or ipconfig.
        """
        try:
            result = subprocess.run(
                ["ipconfig"],
                capture_output=True,
                text=True,
                errors="ignore"
            )
            gateways = re.findall(r"Default Gateway.*:\s*([\d\.]+)", result.stdout)
            for gw in gateways:
                if gw != "0.0.0.0" and gw.strip():
                    return gw.strip()
        except Exception:
            pass
        return "192.168.1.1" # Fallback typical home gateway

    def calculate_stats(self, data):
        """
        Computes mean, standard deviation, and variance of a sample queue.
        """
        if len(data) < 2:
            return 0.0, 0.0, 0.0
        
        mean = sum(data) / len(data)
        variance = sum((x - mean) ** 2 for x in data) / (len(data) - 1)
        std_dev = math.sqrt(variance)
        return mean, std_dev, variance

    def detect_perturbation(self, current_val, history, sta_len=5, lta_len=30):
        """
        Applies a STA/LTA (Short-Term Average over Long-Term Average) algorithm.
        This is a classic signal processing method to detect abrupt wave reflections/deviations.
        """
        if len(history) < lta_len:
            return 1.0, False
        
        # Calculate Short-Term and Long-Term Averages
        list_hist = list(history)
        sta = sum(list_hist[-sta_len:]) / sta_len
        lta = sum(list_hist[-lta_len:]) / lta_len
        
        if lta == 0:
            return 1.0, False
            
        # The deviation ratio represents amplitude/phase perturbation
        ratio = abs(sta - lta) / (lta if lta != 0 else 1)
        
        # If signal changes by more than 8% suddenly, trigger anomaly
        is_perturbed = ratio > 0.08
        return ratio, is_perturbed

    def run_sensing_loop(self, duration_seconds=60, callback=None):
        """
        Executes high-frequency RSSI and RTT sampling loop.
        Fires callback(stats_dict) on every sample.
        """
        print(f"Starting WiFi Sensing Engine [SSID: {self.target_ssid or 'Active Interface'}]")
        print(f"Sampling frequency: {1.0 / self.poll_interval:.1f} Hz (every {self.poll_interval}s)")
        print(f"Gateway target for RTT Wave Reflection: {self.gateway_ip}")
        print("Press Ctrl+C to terminate sensing.\n")

        start_time = time.time()
        
        # Warmup loop to populate some baseline values
        for _ in range(5):
            conn = get_current_connection()
            if conn.get("status") == "connected":
                self.rssi_history.append(conn.get("signal", 100))
            rtt = ping_gateway(self.gateway_ip, timeout_ms=300)
            if rtt is not None:
                self.rtt_history.append(rtt)
            time.sleep(self.poll_interval)

        while (time.time() - start_time) < duration_seconds:
            loop_start = time.perf_counter()
            
            # 1. Fetch current signal strength
            conn = get_current_connection()
            if conn.get("status") != "connected":
                print("\n[WARNING] WiFi Disconnected during sensing! Retrying connection...", file=sys.stderr)
                time.sleep(1)
                continue
                
            rssi = conn.get("signal", 0)
            self.rssi_history.append(rssi)
            
            # 2. Measure wave RTT latency
            rtt = ping_gateway(self.gateway_ip, timeout_ms=200)
            if rtt is not None:
                self.rtt_history.append(rtt)
            
            # 3. Calculate statistics
            rssi_mean, rssi_std, rssi_var = self.calculate_stats(self.rssi_history)
            rtt_mean, rtt_std, rtt_var = self.calculate_stats(self.rtt_history)
            
            # 4. Run detection heuristic
            rssi_ratio, rssi_perturb = self.detect_perturbation(rssi, self.rssi_history)
            rtt_ratio, rtt_perturb = self.detect_perturbation(rtt or rtt_mean, self.rtt_history)
            
            # Combine triggers (movement/reflections affect either amplitude or speed of wave arrival)
            perturbation_index = max(rssi_ratio * 100.0, rtt_ratio * 50.0)
            reflection_detected = rssi_perturb or rtt_perturb

            stats_block = {
                "timestamp": time.time() - start_time,
                "current_rssi": rssi,
                "rssi_variance": rssi_var,
                "current_rtt": rtt if rtt is not None else 0.0,
                "rtt_jitter": rtt_std,
                "perturbation_index": perturbation_index,
                "reflection_detected": reflection_detected,
                "ssid": conn.get("ssid"),
                "channel": conn.get("channel", 0)
            }
            
            if callback:
                callback(stats_block)
            else:
                # Default simple text visualizer
                indicator = "!!!" if reflection_detected else "   "
                bar = "#" * int(min(perturbation_index * 2, 40))
                print(f"[{stats_block['timestamp']:06.2f}s] RSSI: {rssi}% (Var: {rssi_var:5.2f}) | RTT: {stats_block['current_rtt']:5.1f}ms (Jitter: {rtt_std:5.2f}) | Perturbation: {perturbation_index:5.1f}% {bar:<40} {indicator}")

            # Precise execution rate timing
            elapsed = time.perf_counter() - loop_start
            sleep_time = max(0.001, self.poll_interval - elapsed)
            time.sleep(sleep_time)
            
        print("\nSensing run completed successfully.")
