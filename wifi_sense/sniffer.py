import sys
import time
from collections import Counter

# Suppress scapy warnings during import
try:
    import logging
    logging.getLogger("scapy.runtime").setLevel(logging.ERROR)
    from scapy.all import sniff, IP, IPv6, TCP, UDP, ARP, DNS, ICMP, Raw
except ImportError:
    print("Error: scapy is not installed. Please run 'pip install scapy' or install Npcap/WinPcap.", file=sys.stderr)
    sys.exit(1)

class NetworkSniffer:
    def __init__(self, target_ip=None):
        self.target_ip = target_ip
        self.packet_count = 0
        self.protocol_counter = Counter()
        self.ip_traffic = Counter()
        self.dns_queries = []
        self.start_time = None

    def packet_callback(self, pkt):
        """
        Processes a single captured network packet.
        """
        self.packet_count += 1
        proto = "Unknown"
        src_ip = "N/A"
        dst_ip = "N/A"
        info = ""

        # Determine IP protocol and hosts
        if IP in pkt:
            src_ip = pkt[IP].src
            dst_ip = pkt[IP].dst
            self.ip_traffic[src_ip] += len(pkt)
            self.ip_traffic[dst_ip] += len(pkt)
        elif IPv6 in pkt:
            src_ip = pkt[IPv6].src
            dst_ip = pkt[IPv6].dst
            self.ip_traffic[src_ip] += len(pkt)
            self.ip_traffic[dst_ip] += len(pkt)

        # Handle specific application layers
        if ARP in pkt:
            proto = "ARP"
            src_ip = pkt[ARP].psrc or pkt[ARP].hwsrc
            dst_ip = pkt[ARP].pdst or pkt[ARP].hwdst
            info = f"Who has {pkt[ARP].pdst}? Tell {pkt[ARP].psrc}" if pkt[ARP].op == 1 else f"ARP reply: {pkt[ARP].psrc} is at {pkt[ARP].hwsrc}"
        elif TCP in pkt:
            proto = "TCP"
            sport = pkt[TCP].sport
            dport = pkt[TCP].dport
            info = f"Flags={pkt[TCP].flags} | Ports: {sport} -> {dport}"
        elif UDP in pkt:
            proto = "UDP"
            sport = pkt[UDP].sport
            dport = pkt[UDP].dport
            info = f"Ports: {sport} -> {dport}"
            
            # Check DNS
            if pkt.haslayer(DNS) and pkt[DNS].qd:
                proto = "DNS"
                qname = pkt[DNS].qd.qname.decode('utf-8', errors='ignore')
                info = f"DNS Query: {qname}"
                if qname not in self.dns_queries:
                    self.dns_queries.append(qname)
        elif ICMP in pkt:
            proto = "ICMP"
            info = f"Type={pkt[ICMP].type} Code={pkt[ICMP].code}"

        # Increment protocols
        self.protocol_counter[proto] += 1

        # Format output string
        elapsed = time.time() - self.start_time
        packet_size = len(pkt)
        
        # Display packet detail
        print(f"[{elapsed:7.2f}s] {proto:<7} | {src_ip:<35} -> {dst_ip:<35} | Size: {packet_size:<5} B | {info}")

    def start_sniffing(self, duration_seconds=30, interface=None):
        """
        Starts scanning/sniffing real-time traffic using Scapy.
        """
        self.start_time = time.time()
        self.packet_count = 0
        self.protocol_counter.clear()
        self.ip_traffic.clear()
        self.dns_queries.clear()

        print(f"Starting real-time packet sniffer...")
        print(f"Duration: {duration_seconds} seconds")
        if interface:
            print(f"Interface: {interface}")
        else:
            print("Listening on default network interface...")
        print("=" * 110)
        
        try:
            # Native scapy sniffing
            sniff(
                prn=self.packet_callback,
                timeout=duration_seconds,
                iface=interface,
                store=False # Do not store packets in memory to prevent RAM exhaustion
            )
        except KeyboardInterrupt:
            print("\nSniffing stopped by user.")
        except Exception as e:
            print(f"\nError occurred during sniffing: {e}", file=sys.stderr)
            print("Tip: Under Windows, this command requires Administrator privileges and Npcap/WinPcap.", file=sys.stderr)
            return

        self.display_summary()

    def display_summary(self):
        """
        Outputs post-capture breakdown metrics of active hosts and protocols.
        """
        print("\n" + "=" * 50)
        print("             TRAFFIC ANALYSIS SUMMARY             ")
        print("=" * 50)
        print(f"Total Packets Processed: {self.packet_count}")
        
        print("\nProtocol Distribution:")
        for proto, count in self.protocol_counter.most_common():
            pct = (count / self.packet_count * 100) if self.packet_count > 0 else 0
            print(f"  - {proto:<10}: {count:<5} ({pct:.1f}%)")

        print("\nTop Active Hosts (By Transmitted Data Volume):")
        for host, volume in self.ip_traffic.most_common(5):
            print(f"  - {host:<35}: {volume / 1024:.2f} KB")

        if self.dns_queries:
            print("\nDistinct DNS Queries Captured:")
            for q in self.dns_queries[:10]:
                print(f"  - {q}")
            if len(self.dns_queries) > 10:
                print(f"  ... and {len(self.dns_queries) - 10} more.")
        print("=" * 50)
