import subprocess
import re
import sys
import os
import time

def scan_networks():
    """
    Scans for visible WiFi networks using Windows netsh command.
    Returns a list of dictionaries with SSID, Signal, Security type, and BSSIDs.
    """
    try:
        # Run netsh wlan show networks mode=bssid
        result = subprocess.run(
            ["netsh", "wlan", "show", "networks", "mode=bssid"],
            capture_output=True,
            text=True,
            errors="ignore",
            check=True
        )
        output = result.stdout
    except Exception as e:
        print(f"Error executing netsh wlan: {e}", file=sys.stderr)
        return []

    networks = []
    current_net = {}
    current_bssid = {}

    # Parse netsh wlan show networks output
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue

        # Detect new SSID entry
        ssid_match = re.match(r"^SSID\s+\d+\s*:\s*(.*)$", line)
        if ssid_match:
            if current_net:
                networks.append(current_net)
            ssid_name = ssid_match.group(1).strip()
            current_net = {
                "ssid": ssid_name if ssid_name else "[Hidden Network]",
                "signal": 0,
                "security": "Unknown",
                "authentication": "Unknown",
                "bssids": []
            }
            continue

        if not current_net:
            continue

        # Parse Network Parameters
        if line.startswith("Network type"):
            pass
        elif line.startswith("Authentication"):
            current_net["authentication"] = line.split(":", 1)[1].strip()
        elif line.startswith("Encryption"):
            current_net["security"] = line.split(":", 1)[1].strip()
        elif line.startswith("BSSID"):
            if current_bssid:
                current_net["bssids"].append(current_bssid)
            bssid_mac = line.split(":", 1)[1].strip()
            current_bssid = {"mac": bssid_mac, "signal": 0, "channel": 0}
        elif line.startswith("Signal"):
            sig_str = line.split(":", 1)[1].strip().replace("%", "")
            try:
                sig_val = int(sig_str)
            except ValueError:
                sig_val = 0
            if current_bssid:
                current_bssid["signal"] = sig_val
            # Overall network signal is usually the max of its BSSID signals
            if sig_val > current_net["signal"]:
                current_net["signal"] = sig_val
        elif line.startswith("Channel"):
            chan_str = line.split(":", 1)[1].strip()
            try:
                chan_val = int(chan_str)
            except ValueError:
                chan_val = 0
            if current_bssid:
                current_bssid["channel"] = chan_val
            # Keep track of channels in current_net for summary
            if "channels" not in current_net:
                current_net["channels"] = []
            if chan_val not in current_net["channels"]:
                current_net["channels"].append(chan_val)
        elif line.startswith("Basic rates") or line.startswith("Other rates"):
            # Mark the completion of the current BSSID parsing
            if current_bssid:
                current_net["bssids"].append(current_bssid)
                current_bssid = {}

    # Append the last parsed network
    if current_bssid and current_net:
        current_net["bssids"].append(current_bssid)
    if current_net:
        networks.append(current_net)

    return networks

def get_current_connection():
    """
    Retrieves the current connected WiFi network details.
    """
    try:
        result = subprocess.run(
            ["netsh", "wlan", "show", "interfaces"],
            capture_output=True,
            text=True,
            errors="ignore",
            check=True
        )
        output = result.stdout
    except Exception as e:
        return {"status": "Disconnected", "error": str(e)}

    info = {"status": "Disconnected"}
    for line in output.splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        key, val = [part.strip() for part in line.split(":", 1)]
        if key == "State":
            info["status"] = val
        elif key == "SSID":
            info["ssid"] = val
        elif key == "BSSID":
            info["bssid"] = val
        elif key == "Signal":
            info["signal"] = int(val.replace("%", "").strip())
        elif key == "Radio type":
            info["radio_type"] = val
        elif key == "Channel":
            info["channel"] = int(val)
        elif key == "Receive rate (Mbps)":
            info["rx_rate"] = val
        elif key == "Transmit rate (Mbps)":
            info["tx_rate"] = val
        elif key == "Description":
            info["adapter"] = val

    return info

def create_wifi_profile_xml(ssid, password=None):
    """
    Generates a Windows WLAN Profile XML string for connecting.
    Supports WPA2-PSK and Open networks.
    """
    # Convert SSID to hex
    ssid_hex = ssid.encode('utf-8').hex().upper()
    
    if password:
        security_config = f"""
            <security>
                <authEncryption>
                    <authentication>WPA2PSK</authentication>
                    <encryption>AES</encryption>
                    <useOneX>false</useOneX>
                </authEncryption>
                <sharedKey>
                    <keyType>passPhrase</keyType>
                    <protected>false</protected>
                    <keyMaterial>{password}</keyMaterial>
                </sharedKey>
            </security>"""
    else:
        security_config = """
            <security>
                <authEncryption>
                    <authentication>open</authentication>
                    <encryption>none</encryption>
                    <useOneX>false</useOneX>
                </authEncryption>
            </security>"""

    xml = f"""<?xml version="1.0"?>
<WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1">
    <name>{ssid}</name>
    <SSIDConfig>
        <SSID>
            <hex>{ssid_hex}</hex>
            <name>{ssid}</name>
        </SSID>
    </SSIDConfig>
    <connectionType>ESS</connectionType>
    <connectionMode>manual</connectionMode>
    <MSM>
        {security_config}
    </MSM>
</WLANProfile>"""
    return xml

def connect_to_network(ssid, password=None):
    """
    Programmatically connects to a WiFi network.
    Generates a profile XML, registers it with netsh, and commands a connection.
    """
    xml_content = create_wifi_profile_xml(ssid, password)
    xml_filename = f"temp_wifi_profile_{int(time.time())}.xml"

    try:
        # Write temporary profile file
        with open(xml_filename, "w", encoding="utf-8") as f:
            f.write(xml_content)

        # Add profile to Windows
        add_profile = subprocess.run(
            ["netsh", "wlan", "add", "profile", f"filename={xml_filename}"],
            capture_output=True,
            text=True,
            check=True
        )

        # Connect using the profile
        connect = subprocess.run(
            ["netsh", "wlan", "connect", f"name={ssid}"],
            capture_output=True,
            text=True,
            check=True
        )

        # Give it a few seconds to establish connection
        print(f"Connecting to SSID '{ssid}'...")
        for _ in range(10):
            time.sleep(1)
            conn = get_current_connection()
            if conn.get("status") == "connected" and conn.get("ssid") == ssid:
                print("Successfully connected!")
                return True
            
        print("Connection timed out or failed.", file=sys.stderr)
        return False

    except Exception as e:
        print(f"Error establishing connection: {e}", file=sys.stderr)
        return False
    finally:
        # Cleanup temp file
        if os.path.exists(xml_filename):
            try:
                os.remove(xml_filename)
            except OSError:
                pass

def disconnect_network():
    """
    Disconnects from the current wireless network.
    """
    try:
        result = subprocess.run(
            ["netsh", "wlan", "disconnect"],
            capture_output=True,
            text=True,
            check=True
        )
        print("Disconnected from wireless network.")
        return True
    except Exception as e:
        print(f"Error disconnecting: {e}", file=sys.stderr)
        return False
