import sys
import click
from wifi_sense.connection import scan_networks, get_current_connection, connect_to_network, disconnect_network
from wifi_sense.sensing import SignalSensingEngine
from wifi_sense.sniffer import NetworkSniffer
from wifi_sense.prober import MediumProber
from wifi_sense.gui import start_gui

@click.group()
def cli():
    """
    Wifi Sense - Network Packet Sniffer and Radio Wave Signal Sensing Suite.
    """
    pass

@cli.command("scan")
def scan_cmd():
    """
    Scans and prints visible WiFi SSIDs, BSSIDs, Signal, and security.
    """
    print("Scanning available networks...")
    networks = scan_networks()
    if not networks:
        print("No networks visible or WiFi adapter disabled.")
        return
        
    print(f"\n{'SSID':<30} | {'Signal':<7} | {'Authentication':<15} | {'BSSID (MAC)':<20} | {'Channel':<7}")
    print("-" * 90)
    for net in networks:
        channels_str = ",".join(str(c) for c in net.get("channels", []))
        # Print main entry
        print(f"{net['ssid'][:30]:<30} | {net['signal']:>5}% | {net['authentication']:<15} | {'':<20} | {channels_str:<7}")
        # Print sub-BSSIDs for full physical details
        for bssid in net.get("bssids", []):
            print(f"{'':<30} | {bssid['signal']:>5}% | {'':<15} | {bssid['mac']:<20} | {bssid['channel']:<7}")
        print("-" * 90)

@cli.command("status")
def status_cmd():
    """
    Displays detailed information about the current connected network.
    """
    print("Reading connected adapter interface status...")
    info = get_current_connection()
    if info.get("status") != "connected":
        print("\nAdapter State: Disconnected")
        return
        
    print("\n" + "=" * 50)
    print("            CURRENT WIFI LINK STATUS")
    print("=" * 50)
    print(f"SSID:        {info.get('ssid')}")
    print(f"BSSID (MAC): {info.get('bssid')}")
    print(f"Signal:      {info.get('signal')}%")
    print(f"Channel:     {info.get('channel')}")
    print(f"Radio Type:  {info.get('radio_type')}")
    print(f"RX Speed:    {info.get('rx_rate')}")
    print(f"TX Speed:    {info.get('tx_rate')}")
    print(f"Adapter:     {info.get('adapter')}")
    print("=" * 50)

@cli.command("connect")
@click.option("--ssid", required=True, help="SSID of the network to join")
@click.option("--password", default=None, help="WiFi password (leave blank for Open network)")
def connect_cmd(ssid, password):
    """
    Connects programmatically to a targeted network.
    """
    success = connect_to_network(ssid, password)
    if not success:
        sys.exit(1)

@cli.command("disconnect")
def disconnect_cmd():
    """
    Disconnects from the active wireless network.
    """
    disconnect_network()

@cli.command("sense")
@click.option("--duration", default=60, help="Duration of sensing in seconds")
@click.option("--interval", default=0.1, help="Polling interval in seconds (default 0.1s / 10Hz)")
@click.option("--window", default=50, help="Size of statistical moving window")
def sense_cmd(duration, interval, window):
    """
    Performs high-frequency sensing of the signal.
    Captures amplitude RSSI and speed RTT variations to detect reflections or physical motion.
    """
    info = get_current_connection()
    if info.get("status") != "connected":
        print("Error: You must be connected to a WiFi network to run sensing operations.", file=sys.stderr)
        print("Use: python run.py connect --ssid <SSID>", file=sys.stderr)
        sys.exit(1)
        
    engine = SignalSensingEngine(target_ssid=info.get("ssid"), poll_interval=interval, window_size=window)
    try:
        engine.run_sensing_loop(duration_seconds=duration)
    except KeyboardInterrupt:
        print("\nSensing terminated by user.")

@cli.command("sniff")
@click.option("--duration", default=30, help="Sniffing capture duration in seconds")
@click.option("--interface", default=None, help="Name of the interface to sniff on")
def sniff_cmd(duration, interface):
    """
    Captures raw packets, decoding source, destination, protocol, and payload details.
    """
    sniffer = NetworkSniffer()
    sniffer.start_sniffing(duration_seconds=duration, interface=interface)

@cli.command("probe")
@click.option("--packets", default=50, help="Number of packets in the injection train")
@click.option("--delay", default=0.05, help="Delay between packet bursts in seconds")
def probe_cmd(packets, delay):
    """
    Stimulates the transmission medium with an active packet burst train.
    Analyzes wave propagation (jitter, delay, loss) under load.
    """
    info = get_current_connection()
    if info.get("status") != "connected":
        print("Error: You must be connected to a network to run active transmission sweeps.", file=sys.stderr)
        sys.exit(1)
        
    engine = SignalSensingEngine()
    prober = MediumProber(gateway_ip=engine.gateway_ip)
    prober.run_injection_probe(packet_count=packets, burst_delay=delay)

@cli.command("gui")
def gui_cmd():
    """
    Launches the live desktop GUI oscilloscope.
    """
    print("Initializing Live Desktop Oscilloscope...")
    start_gui()

if __name__ == "__main__":
    cli()
