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

    @patch('wifi_sense.gui.WifiOscilloscopeGUI.setup_ui')
    @patch('wifi_sense.gui.WifiOscilloscopeGUI.start_worker_thread')
    @patch('wifi_sense.gui.WifiOscilloscopeGUI.animate')
    def test_polar_grid_clustering(self, mock_animate, mock_start_thread, mock_setup_ui):
        """
        Verify that Polar Grid-Based Density Clustering (PGDC) correctly groups points and separates noise.
        """
        from wifi_sense.gui import WifiOscilloscopeGUI
        import time
        import math

        root = MagicMock()
        gui = WifiOscilloscopeGUI(root)
        
        # Manually set up reflection_history with points forming a distinct cluster plus some noise
        gui.reflection_history = []
        now = time.time()
        
        # 1. Cluster points (stable echo wall)
        # 15 points clustered close to r = 2.0m, theta = 1.0 rad
        for i in range(15):
            theta = 1.0 + (i - 7) * 0.05  # angular spread from 0.65 to 1.35 rad
            dist = 2.0 + (i % 3 - 1) * 0.05  # distance spread from 1.95m to 2.05m
            gui.reflection_history.append({
                "x": dist * math.cos(theta),
                "y": 0.0,
                "z": dist * math.sin(theta),
                "theta": theta,
                "distance": dist,
                "intensity": 20.0,
                "timestamp": now
            })
            
        # 2. Add some sparse noise points that should not form clusters (threshold is 12)
        # 3 points at distance 4.0 meters, angle 4.0 radians
        for i in range(3):
            theta = 4.0 + i * 0.1
            dist = 4.0
            gui.reflection_history.append({
                "x": dist * math.cos(theta),
                "y": 0.0,
                "z": dist * math.sin(theta),
                "theta": theta,
                "distance": dist,
                "intensity": 10.0,
                "timestamp": now
            })
            
        gui.cluster_reflection_history()
        
        # Assertions
        # There should be exactly 1 detected wall because the noise points are filtered out.
        self.assertEqual(len(gui.detected_walls), 1)
        
        wall = gui.detected_walls[0]
        self.assertAlmostEqual(wall["distance"], 2.0, places=1)
        self.assertEqual(wall["weight"], 15)
        self.assertGreater(len(wall["slices"]), 0)

    @patch('wifi_sense.gui.WifiOscilloscopeGUI.setup_ui')
    @patch('wifi_sense.gui.WifiOscilloscopeGUI.start_worker_thread')
    @patch('wifi_sense.gui.WifiOscilloscopeGUI.animate')
    def test_multi_cluster_differentiation(self, mock_animate, mock_start_thread, mock_setup_ui):
        """
        Verify that multiple distinct echo walls are correctly distinguished as separate clusters.
        """
        from wifi_sense.gui import WifiOscilloscopeGUI
        import time
        import math

        root = MagicMock()
        gui = WifiOscilloscopeGUI(root)
        gui.reflection_history = []
        now = time.time()

        # Cluster A: 15 points at r = 1.5m, theta = 0.5 rad
        for i in range(15):
            theta = 0.5 + (i - 7) * 0.03
            dist = 1.5
            gui.reflection_history.append({
                "x": dist * math.cos(theta),
                "y": 0.0,
                "z": dist * math.sin(theta),
                "theta": theta,
                "distance": dist,
                "intensity": 25.0,
                "timestamp": now
            })

        # Cluster B: 20 points at r = 3.0m, theta = 3.0 rad
        for i in range(20):
            theta = 3.0 + (i - 10) * 0.03
            dist = 3.0
            gui.reflection_history.append({
                "x": dist * math.cos(theta),
                "y": 0.0,
                "z": dist * math.sin(theta),
                "theta": theta,
                "distance": dist,
                "intensity": 25.0,
                "timestamp": now
            })

        gui.cluster_reflection_history()

        # Both clusters are above the min_points_threshold of 12, so there should be 2 detected walls.
        self.assertEqual(len(gui.detected_walls), 2)
        
        # Sort detected walls by distance to verify properties
        walls = sorted(gui.detected_walls, key=lambda w: w["distance"])
        
        self.assertAlmostEqual(walls[0]["distance"], 1.5, places=1)
        self.assertEqual(walls[0]["weight"], 15)
        
        self.assertAlmostEqual(walls[1]["distance"], 3.0, places=1)
        self.assertEqual(walls[1]["weight"], 20)

if __name__ == "__main__":
    unittest.main()
