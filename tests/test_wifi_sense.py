import unittest
from unittest.mock import patch, MagicMock
from collections import deque
from wifi_sense.connection import scan_networks, create_wifi_profile_xml
from wifi_sense.sensing import SignalSensingEngine

class TestWifiSense(unittest.TestCase):

    def test_xml_generation(self):
        """
        Verify that WPA2-PSK and Open XML profile templates are correctly constructed.
        """
        wpa_xml = create_wifi_profile_xml("TestHomeSSID", "mypass123")
        self.assertIn("<name>TestHomeSSID</name>", wpa_xml)
        self.assertIn("<authentication>WPA2PSK</authentication>", wpa_xml)
        self.assertIn("<keyMaterial>mypass123</keyMaterial>", wpa_xml)

        open_xml = create_wifi_profile_xml("AirportFreeOpen")
        self.assertIn("<name>AirportFreeOpen</name>", open_xml)
        self.assertIn("<authentication>open</authentication>", open_xml)
        self.assertNotIn("<sharedKey>", open_xml)

    @patch("subprocess.run")
    def test_scan_networks_parsing(self, mock_run):
        """
        Ensure netsh BSSID output is correctly converted into structured network dictionaries.
        """
        mock_output = """
SSID 1 : AntiGravityHome
    Network type            : Infrastructure
    Authentication          : WPA2-Personal
    Encryption              : CCMP
    BSSID 1                 : 00:11:22:33:44:55
         Signal             : 90%
         Radio type         : 802.11ax
         Channel            : 36
         Basic rates (Mbps) : 6 12 24
         Other rates (Mbps) : 9 18 36 48 54
    BSSID 2                 : 00:11:22:33:44:56
         Signal             : 82%
         Radio type         : 802.11ax
         Channel            : 149
"""
        # Configure subprocess mock
        mock_run.return_value = MagicMock(stdout=mock_output, returncode=0)

        nets = scan_networks()
        self.assertEqual(len(nets), 1)
        self.assertEqual(nets[0]["ssid"], "AntiGravityHome")
        self.assertEqual(nets[0]["authentication"], "WPA2-Personal")
        self.assertEqual(len(nets[0]["bssids"]), 2)
        
        bssid1 = nets[0]["bssids"][0]
        self.assertEqual(bssid1["mac"], "00:11:22:33:44:55")
        self.assertEqual(bssid1["signal"], 90)
        self.assertEqual(bssid1["channel"], 36)

    def test_sensing_statistics(self):
        """
        Verify mean, variance, and standard deviation math calculations.
        """
        engine = SignalSensingEngine()
        data = [10, 12, 10, 12, 10, 12] # Mean is 11, variance is 1.2
        mean, std_dev, variance = engine.calculate_stats(data)
        
        self.assertAlmostEqual(mean, 11.0)
        self.assertAlmostEqual(variance, 1.2)
        self.assertAlmostEqual(std_dev, 1.0954451)

    def test_perturbation_anomaly_detector(self):
        """
        Checks that sudden signal deviations are flagged correctly by the STA/LTA logic.
        """
        engine = SignalSensingEngine()
        
        # Populate history with highly stable signal strengths (90%)
        stable_history = deque([90]*50, maxlen=50)
        
        # Baseline check (no deviation)
        ratio, trigger = engine.detect_perturbation(90, stable_history, sta_len=5, lta_len=30)
        self.assertFalse(trigger)
        self.assertAlmostEqual(ratio, 0.0)

        # Abrupt drop simulation (drop to 60%)
        stable_history.append(60)
        stable_history.append(60)
        stable_history.append(60)
        stable_history.append(60)
        stable_history.append(60)
        
        ratio, trigger = engine.detect_perturbation(60, stable_history, sta_len=5, lta_len=30)
        # Drops from ~90 to 60 is a ~33% variance, which exceeds our 8% anomaly threshold
        self.assertTrue(trigger)
        self.assertGreater(ratio, 0.08)

if __name__ == "__main__":
    unittest.main()
