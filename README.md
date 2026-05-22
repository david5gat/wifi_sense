# Wifi Sense

**Wifi Sense** is a low-level wireless packet analyzer and radio wave perturbation sensor written in Python. It provides command-line capabilities for:
1. Programmatically managing and connecting to WiFi networks.
2. Sniffing and dissecting active network packet streams in real-time.
3. Conducting high-frequency radio signal sensing (amplitude & time propagation jitter analysis) to detect wave reflections or environment physical variations.
4. Injecting active burst packets (ping trains) to stimulate and evaluate link stability under synthetic loads.

---

## Technical Concept: Standard Hardware "WiFi Sensing"

In professional environments, true WiFi sensing involves capturing Channel State Information (CSI) phases directly from specialized WiFi adapter chips. Since standard operating systems and network card drivers lock down CSI data access:

**Wifi Sense** utilizes high-fidelity mathematical proxy metrics:
* **High-Frequency RSSI Sampling**: Measures real-time wave amplitude fading. Movement or wave reflection changes the multipath fading profile, causing observable spikes/drops in RSSI.
* **Round-Trip-Time (RTT) Jitter Analysis**: Measures packet time-of-arrival variance. Blockage or reflections in the wave path trigger packets to scatter or retransmit, causing subtle delays in RTT.
* **STA/LTA Anomaly Trigger**: Applies a seismological STA/LTA (Short-Term Average vs Long-Term Average) ratio trigger. If short-term signal parameters deviate rapidly from the long-term running baseline (exceeding a threshold), a **physical disturbance/reflection event** is flagged.

---

## Installation & Requirements

### System Pre-requisites
1. **Windows OS** (optimized for native `netsh wlan` mechanics).
2. **Npcap** or **WinPcap** installed (required by Scapy for packet sniffing). Download Npcap from: https://npcap.com/ (Ensure you select "Install Npcap in WinPcap API-compatible Mode" during installation).

### Installation Steps
Initialize a virtual environment or install the dependencies:
```bash
pip install -r requirements.txt
```

---

## How to Run Commands

The entry point of the application is `run.py`.

### 1. Scan Available Wireless Networks
Obtains a complete listing of surrounding SSIDs, raw signal strengths, channels, and individual BSSIDs (MAC addresses):
```bash
python run.py scan
```

### 2. Connect Programmatically to a Network
Automatically registers a temporary XML connection profile and associates with the targeted wireless endpoint:
```bash
python run.py connect --ssid "YourSSID" --password "YourPassword"
```
*(Leave `--password` empty if the target network is open).*

### 3. Check Current Link Connection Details
Queries the interface adapter to review current connection quality, speed metrics, SSID, MAC, and channel parameters:
```bash
python run.py status
```

### 4. Real-time Packet Sniffer & Dissector
Captures and processes live airwave packet streams, revealing source/destination hosts, protocols, DNS queries, packet sizes, and generates a traffic breakdown:
```bash
python run.py sniff --duration 30
```
*(Requires Administrator rights / Elevation to open raw socket capture interfaces).*

### 5. High-Frequency Signal Sensing & Wave Reflection Analyzer
Starts high-frequency polling to measure wave perturbations and track physical deviations in the surrounding environment:
```bash
python run.py sense --duration 60 --interval 0.1
```

### 6. Active Medium Prober
Injects a high-speed train of ICMP packet bursts to stimulate the physical wireless medium. Resolves link jitter, packet loss rate, and diagnoses channel scattering:
```bash
python run.py probe --packets 100 --delay 0.02
```

---

## Project Structure
```text
wifi_sense/
│
├── wifi_sense/                # Main package folder
│   ├── __init__.py            # Versioning and package initialization
│   ├── connection.py          # WiFi association and netsh interface parser
│   ├── sensing.py             # Signal sensing engine and STA/LTA trigger math
│   ├── sniffer.py             # Scapy packet dissection and statistics collector
│   └── prober.py              # Packet train channel injection and diagnosis
│
├── tests/                     # Verification test modules
│   └── test_wifi_sense.py     # Unit tests verifying scanner, math, and configs
│
├── requirements.txt           # Dependency listings
├── run.py                     # Command-line router (Click subcommands)
└── README.md                  # This documentation file
```
