import time
import sys
import subprocess
import re
import math
from wifi_sense.sensing import ping_gateway

class MediumProber:
    def __init__(self, gateway_ip):
        self.gateway_ip = gateway_ip

    def run_injection_probe(self, packet_count=50, burst_delay=0.05):
        """
        Sends a high-frequency train of packets (ICMP pings) to stimulate the WiFi channel.
        Analyzes latency patterns (RTT, packet loss, and jitter) to assess physical channel load/interference.
        """
        print(f"Injecting probe train ({packet_count} packets) to gateway: {self.gateway_ip}")
        print(f"Burst interval: {burst_delay * 1000:.0f} ms")
        print("Stimulating channel... Please wait.")
        print("-" * 60)

        rtts = []
        lost_packets = 0

        for i in range(1, packet_count + 1):
            t_start = time.perf_counter()
            rtt = ping_gateway(self.gateway_ip, timeout_ms=250)
            t_elapsed = time.perf_counter() - t_start

            if rtt is not None:
                rtts.append(rtt)
                indicator = "█"
                print(f"Probe {i:03d}: RTT = {rtt:5.1f} ms  {indicator * int(min(rtt/5.0, 30))}")
            else:
                lost_packets += 1
                print(f"Probe {i:03d}: REQUEST TIMEOUT / PACKET DROPPED !!!")

            # Burst rate throttler
            sleep_time = max(0.001, burst_delay - t_elapsed)
            time.sleep(sleep_time)

        # Print statistics
        print("-" * 60)
        print("                  PROBE STIMULATION STATS")
        print("-" * 60)
        
        total_sent = packet_count
        received = len(rtts)
        loss_pct = (lost_packets / total_sent) * 100.0

        print(f"Packets Sent: {total_sent} | Received: {received} | Lost: {lost_packets} ({loss_pct:.1f}% loss)")

        if rtts:
            min_rtt = min(rtts)
            max_rtt = max(rtts)
            avg_rtt = sum(rtts) / len(rtts)
            
            # Compute jitter (average deviation from avg RTT)
            jitter = sum(abs(r - avg_rtt) for r in rtts) / len(rtts)
            
            print(f"Latency  -  Min: {min_rtt:.2f} ms | Max: {max_rtt:.2f} ms | Avg: {avg_rtt:.2f} ms")
            print(f"Jitter   -  {jitter:.2f} ms (Physical medium path dispersion)")
            
            # Diagnostic interpretation
            print("\nChannel Diagnosis:")
            if loss_pct > 10.0:
                print("  [ALERT] Severe packet loss. Extreme multipath fading, heavy wave obstruction, or high radio interference detected.")
            elif jitter > 15.0:
                print("  [WARNING] High Jitter. Signal path fluctuates rapidly. Bouncing/reflections or crowd movement in the environment.")
            elif avg_rtt > 50.0:
                print("  [NOTICE] High Latency. Congested wireless channel or distant access point.")
            else:
                print("  [OK] Channel stable. Low signal scattering, stable wave propagation.")
        else:
            print("\n[CRITICAL] All probe packets were dropped. Wireless link down or highly shielded.")
        print("-" * 60)
