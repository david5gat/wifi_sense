import tkinter as tk
from tkinter import ttk
import threading
import queue
import time
import math
import random
import sys
from wifi_sense.connection import get_current_connection
from wifi_sense.sensing import SignalSensingEngine

class WifiOscilloscopeGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Wifi Sense - 3D Radar & Wave Oscilloscope")
        self.root.geometry("1200x700")
        self.root.configure(bg="#0b0c10")
        self.root.resizable(True, True)

        # Telemetry & Threading Queues
        self.data_queue = queue.Queue()
        self.running = True
        self.paused = False

        # Oscilloscope Telemetry States
        self.time_step = 0.0
        self.current_rssi = 80
        self.current_rtt = 2.0
        self.current_jitter = 1.0
        self.current_perturbation = 0.0
        self.reflection_detected = False
        self.ssid = "Scanning..."
        self.channel = 0
        
        # HUD Borders Flasher
        self.flash_counter = 0

        # Camera & 3D Projection Settings
        self.points_3d = []  # List of dicts: {"x", "y", "z", "intensity", "distance"}
        self.max_points = 250
        self.yaw = 0.0  # Rotation angle around Y-axis
        self.pitch = 0.45  # Viewing elevation angle (radians)
        self.camera_dist = 350.0  # Camera focal distance
        self.zoom = 1.0  # Camera zoom scaling factor
        self.pan_x = 0.0  # X-axis camera pan offset
        self.pan_y = 0.0  # Y-axis camera pan offset
        self.auto_rotate = True  # Enable automatic yaw sweeping

        # Signal Calibration Parameters
        self.sensing_hz = 17.0
        self.alpha_val = 0.25
        self.sensing_engine = None

        # Mouse Drag Tracking
        self.last_mouse_x = 0
        self.last_mouse_y = 0
        
        self.setup_ui()
        self.start_worker_thread()
        self.animate()

    def setup_ui(self):
        """
        Builds a multi-display glassmorphic console layout.
        """
        # Outer border frame for glow alarm signals
        self.outer_frame = tk.Frame(self.root, bg="#0b0c10", bd=4, relief="flat")
        self.outer_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # 1. Title/Header Panel
        self.header = tk.Frame(self.outer_frame, bg="#0b0c10")
        self.header.pack(fill="x", pady=(0, 10))

        title_label = tk.Label(
            self.header, 
            text="WIFI SENSE // 3D MULTIPATH REFLECTION RADAR & OSCILLOSCOPE", 
            font=("Space Mono", 14, "bold"), 
            bg="#0b0c10", 
            fg="#66fcf1"
        )
        title_label.pack(side="left")

        self.status_label = tk.Label(
            self.header, 
            text="STATUS: RADAR SWEEP ACTIVE", 
            font=("Space Mono", 9, "bold"), 
            bg="#0b0c10", 
            fg="#45a29e"
        )
        self.status_label.pack(side="right", pady=5)

        # 2. Main Workspace Row (Left: Waves, Center: 3D Radar, Right: Controls & Meters)
        self.workspace = tk.Frame(self.outer_frame, bg="#0b0c10")
        self.workspace.pack(fill="both", expand=True)
        self.workspace.columnconfigure(0, weight=2)  # Oscilloscope Canvas
        self.workspace.columnconfigure(1, weight=2)  # 3D Radar Canvas
        self.workspace.columnconfigure(2, weight=1)  # Side panel HUD
        self.workspace.rowconfigure(0, weight=1)

        # DISPLAY 1: 2D Electromagnetic Oscilloscope (Left Canvas)
        self.canvas_wave_container = tk.Frame(self.workspace, bg="#1f2833", bd=2, relief="sunken")
        self.canvas_wave_container.grid(row=0, column=0, sticky="nsew", padx=(0, 5))

        self.lbl_wave_title = tk.Label(self.canvas_wave_container, text="[WAVE PROPAGATION CARRIER]", font=("Space Mono", 8, "bold"), bg="#1f2833", fg="#45a29e")
        self.lbl_wave_title.pack(anchor="w", padx=5, pady=2)

        self.canvas_wave = tk.Canvas(self.canvas_wave_container, bg="#000000", highlightthickness=0)
        self.canvas_wave.pack(fill="both", expand=True, padx=2, pady=2)

        # DISPLAY 2: 3D Multipath Radar Point Cloud (Center Canvas)
        self.canvas_radar_container = tk.Frame(self.workspace, bg="#1f2833", bd=2, relief="sunken")
        self.canvas_radar_container.grid(row=0, column=1, sticky="nsew", padx=(5, 10))

        self.lbl_radar_title = tk.Label(self.canvas_radar_container, text="[3D WAVE REFLECTION CLOUD]", font=("Space Mono", 8, "bold"), bg="#1f2833", fg="#45a29e")
        self.lbl_radar_title.pack(anchor="w", padx=5, pady=2)

        self.canvas_radar = tk.Canvas(self.canvas_radar_container, bg="#000000", highlightthickness=0)
        self.canvas_radar.pack(fill="both", expand=True, padx=2, pady=2)

        # Bind configurations for clean resizing grid draws
        self.canvas_wave.bind("<Configure>", lambda e: self.draw_oscilloscope_grid())
        self.canvas_radar.bind("<Configure>", lambda e: self.draw_radar_grid())

        # Mouse bindings for direct 3D interactive navigation
        self.canvas_radar.bind("<ButtonPress-1>", self.on_radar_click)
        self.canvas_radar.bind("<B1-Motion>", self.on_radar_drag_rotate)
        self.canvas_radar.bind("<ButtonPress-3>", self.on_radar_click)
        self.canvas_radar.bind("<B3-Motion>", self.on_radar_drag_pan)
        self.canvas_radar.bind("<MouseWheel>", self.on_radar_scroll_zoom)

        # DISPLAY 3: Interactive Controls & HUD (Right Panel)
        self.side_panel = tk.Frame(self.workspace, bg="#0b0c10")
        self.side_panel.grid(row=0, column=2, sticky="nsew")

        # Digital Telemetry Readouts (Compact 2x2 Grid)
        self.readout_container = tk.LabelFrame(
            self.side_panel, 
            text=" TELEMETRY HUD ", 
            font=("Space Mono", 9, "bold"), 
            bg="#0b0c10", 
            fg="#45a29e", 
            bd=2, 
            relief="groove"
        )
        self.readout_container.pack(fill="x", pady=(0, 5))
        self.readout_container.columnconfigure(0, weight=1)
        self.readout_container.columnconfigure(1, weight=1)

        # Digital Meters (2x2 Structure)
        self.create_led_card(self.readout_container, "RSSI (AMPLITUDE)", "rssi_val", "80%", "#1f2833", "#00ffcc", 0, 0)
        self.create_led_card(self.readout_container, "RTT GATEWAY", "rtt_val", "2.0 ms", "#1f2833", "#00ccff", 0, 1)
        self.create_led_card(self.readout_container, "JITTER (SCATTER)", "jitter_val", "1.0 ms", "#1f2833", "#ffcc00", 1, 0)
        self.create_led_card(self.readout_container, "PERTURBATION", "pert_val", "0.0%", "#1f2833", "#ff0055", 1, 1)

        # Camera & 3D Navigation Controls
        self.view_container = tk.LabelFrame(
            self.side_panel, 
            text=" 3D VIEW & CAMERA ", 
            font=("Space Mono", 9, "bold"), 
            bg="#0b0c10", 
            fg="#45a29e", 
            bd=2, 
            relief="groove"
        )
        self.view_container.pack(fill="x", pady=(0, 5))

        self.var_auto_rotate = tk.BooleanVar(value=True)
        self.cb_auto_rotate = tk.Checkbutton(
            self.view_container,
            text="Auto-Rotate Sweep",
            variable=self.var_auto_rotate,
            font=("Space Mono", 8),
            bg="#0b0c10",
            fg="#c5c6c7",
            selectcolor="#0b0c10",
            activebackground="#0b0c10",
            activeforeground="#66fcf1",
            command=self.update_auto_rotate
        )
        self.cb_auto_rotate.pack(anchor="w", padx=10, pady=4)

        btn_row = tk.Frame(self.view_container, bg="#0b0c10")
        btn_row.pack(fill="x", padx=10, pady=4)
        
        self.btn_zoom_in = tk.Button(
            btn_row, text="ZOOM +", font=("Space Mono", 8, "bold"),
            bg="#1f2833", fg="#66fcf1", bd=1, relief="solid",
            activebackground="#45a29e", activeforeground="#0b0c10",
            padx=5, pady=2, command=self.zoom_in
        )
        self.btn_zoom_in.pack(side="left", expand=True, fill="x", padx=(0, 2))
        
        self.btn_zoom_out = tk.Button(
            btn_row, text="ZOOM -", font=("Space Mono", 8, "bold"),
            bg="#1f2833", fg="#66fcf1", bd=1, relief="solid",
            activebackground="#45a29e", activeforeground="#0b0c10",
            padx=5, pady=2, command=self.zoom_out
        )
        self.btn_zoom_out.pack(side="left", expand=True, fill="x", padx=(2, 2))
        
        self.btn_reset_view = tk.Button(
            btn_row, text="RESET VIEW", font=("Space Mono", 8, "bold"),
            bg="#1f2833", fg="#66fcf1", bd=1, relief="solid",
            activebackground="#45a29e", activeforeground="#0b0c10",
            padx=5, pady=2, command=self.reset_view
        )
        self.btn_reset_view.pack(side="left", expand=True, fill="x", padx=(2, 0))

        # Signal Tuning Controls
        self.signal_container = tk.LabelFrame(
            self.side_panel, 
            text=" SIGNAL CALIBRATION ", 
            font=("Space Mono", 9, "bold"), 
            bg="#0b0c10", 
            fg="#45a29e", 
            bd=2, 
            relief="groove"
        )
        self.signal_container.pack(fill="x", pady=(0, 5))

        lbl_hz = tk.Label(self.signal_container, text="Sensing Rate: 17 Hz", font=("Space Mono", 8), bg="#0b0c10", fg="#c5c6c7")
        lbl_hz.pack(anchor="w", padx=10, pady=(4, 0))
        
        self.slider_hz = tk.Scale(
            self.signal_container,
            from_=5, to=50,
            orient="horizontal",
            bg="#0b0c10", fg="#66fcf1",
            troughcolor="#1f2833",
            activebackground="#45a29e",
            highlightthickness=0,
            showvalue=False,
            command=lambda val: self.update_sensing_hz(val, lbl_hz)
        )
        self.slider_hz.set(17)
        self.slider_hz.pack(fill="x", padx=10, pady=(0, 4))

        lbl_alpha = tk.Label(self.signal_container, text="Noise Filter (EMA Alpha): 0.25", font=("Space Mono", 8), bg="#0b0c10", fg="#c5c6c7")
        lbl_alpha.pack(anchor="w", padx=10, pady=(4, 0))
        
        self.slider_alpha = tk.Scale(
            self.signal_container,
            from_=0.05, to=1.00,
            resolution=0.05,
            orient="horizontal",
            bg="#0b0c10", fg="#66fcf1",
            troughcolor="#1f2833",
            activebackground="#45a29e",
            highlightthickness=0,
            showvalue=False,
            command=lambda val: self.update_filter_alpha(val, lbl_alpha)
        )
        self.slider_alpha.set(0.25)
        self.slider_alpha.pack(fill="x", padx=10, pady=(0, 8))

        # Main Flow Play/Pause Frame
        self.control_container = tk.LabelFrame(
            self.side_panel, 
            text=" WAVE CAPTURE ", 
            font=("Space Mono", 9, "bold"), 
            bg="#0b0c10", 
            fg="#45a29e", 
            bd=2, 
            relief="groove"
        )
        self.control_container.pack(fill="x", pady=(0, 5))

        self.btn_pause = tk.Button(
            self.control_container,
            text="PAUSE CAPTURE",
            font=("Space Mono", 10, "bold"),
            bg="#ff0055",
            fg="#ffffff",
            activebackground="#ff3377",
            activeforeground="#ffffff",
            bd=0,
            padx=10,
            pady=8,
            command=self.toggle_pause
        )
        self.btn_pause.pack(fill="x", padx=10, pady=8)

        # WiFi Node Information Footer
        self.footer = tk.Frame(self.side_panel, bg="#1f2833", bd=1, relief="solid")
        self.footer.pack(fill="x")

        self.details_label = tk.Label(
            self.footer, 
            text="SSID: Scanning...\nChannel: 0\nAdapter: Checking...",
            font=("Space Mono", 8),
            justify="left",
            anchor="w",
            bg="#1f2833",
            fg="#c5c6c7"
        )
        self.details_label.pack(fill="x", padx=10, pady=10)

    def create_led_card(self, parent, label_text, var_name, init_val, bg, fg, row, column):
        """
        Generates clean compact fluorescent LED panels in the grid.
        """
        card = tk.Frame(parent, bg="#0b0c10")
        card.grid(row=row, column=column, sticky="ew", padx=5, pady=4)

        lbl = tk.Label(card, text=label_text, font=("Space Mono", 7, "bold"), bg="#0b0c10", fg="#45a29e")
        lbl.pack(anchor="w")

        led_frame = tk.Frame(card, bg=bg, bd=1, relief="solid")
        led_frame.pack(fill="x", pady=2)

        led_val = tk.Label(
            led_frame, 
            text=init_val, 
            font=("Space Mono", 12, "bold"), 
            bg="#000000", 
            fg=fg,
            padx=5,
            pady=4
        )
        led_val.pack(fill="x")
        setattr(self, var_name, led_val)

    def toggle_pause(self):
        """
        Toggles the global play/pause state.
        """
        self.paused = not self.paused
        if self.paused:
            self.btn_pause.configure(text="RESUME CAPTURE", bg="#00ffcc", fg="#000000", activebackground="#33ffdd")
            self.status_label.configure(text="STATUS: RADAR SWEEP PAUSED", fg="#ffcc00")
        else:
            self.btn_pause.configure(text="PAUSE CAPTURE", bg="#ff0055", fg="#ffffff", activebackground="#ff3377")
            self.status_label.configure(text="STATUS: RADAR SWEEP ACTIVE", fg="#45a29e")

    def update_auto_rotate(self):
        self.auto_rotate = self.var_auto_rotate.get()

    def zoom_in(self):
        self.zoom *= 1.2
        self.zoom = min(10.0, self.zoom)

    def zoom_out(self):
        self.zoom /= 1.2
        self.zoom = max(0.1, self.zoom)

    def reset_view(self):
        self.zoom = 1.0
        self.pan_x = 0.0
        self.pan_y = 0.0
        self.yaw = 0.0
        self.pitch = 0.45
        self.var_auto_rotate.set(True)
        self.auto_rotate = True

    def update_sensing_hz(self, val, label):
        hz = float(val)
        label.configure(text=f"Sensing Rate: {int(hz)} Hz")
        self.sensing_hz = hz
        if hasattr(self, 'sensing_engine') and self.sensing_engine is not None:
            self.sensing_engine.poll_interval = 1.0 / hz

    def update_filter_alpha(self, val, label):
        alpha = float(val)
        label.configure(text=f"Noise Filter (EMA Alpha): {alpha:.2f}")
        self.alpha_val = alpha

    def on_radar_click(self, event):
        self.last_mouse_x = event.x
        self.last_mouse_y = event.y

    def on_radar_drag_rotate(self, event):
        dx = event.x - self.last_mouse_x
        dy = event.y - self.last_mouse_y
        
        # Stop auto-rotation when dragging manually
        self.var_auto_rotate.set(False)
        self.auto_rotate = False
        
        self.yaw += dx * 0.007
        self.pitch += dy * 0.007
        self.pitch = max(-math.pi/2 + 0.1, min(math.pi/2 - 0.1, self.pitch))
        
        self.last_mouse_x = event.x
        self.last_mouse_y = event.y

    def on_radar_drag_pan(self, event):
        dx = event.x - self.last_mouse_x
        dy = event.y - self.last_mouse_y
        
        self.pan_x += dx
        self.pan_y += dy
        
        self.last_mouse_x = event.x
        self.last_mouse_y = event.y

    def on_radar_scroll_zoom(self, event):
        if event.delta > 0:
            self.zoom *= 1.1
        else:
            self.zoom /= 1.1
        self.zoom = max(0.1, min(10.0, self.zoom))

    def draw_oscilloscope_grid(self):
        """
        Draws 2D grid guidelines for the waves.
        """
        self.canvas_wave.delete("grid")
        w = self.canvas_wave.winfo_width()
        h = self.canvas_wave.winfo_height()
        mid_y = h // 2

        self.canvas_wave.create_line(0, mid_y, w, mid_y, fill="#0f1923", width=2, tags="grid")
        self.canvas_wave.create_line(w//2, 0, w//2, h, fill="#0f1923", width=2, tags="grid")

        for y in range(0, h, 40):
            if y != mid_y:
                self.canvas_wave.create_line(0, y, w, y, fill="#070b10", dash=(2, 4), tags="grid")
        for x in range(0, w, 40):
            if x != w//2:
                self.canvas_wave.create_line(x, 0, x, h, fill="#070b10", dash=(2, 4), tags="grid")

    def draw_radar_grid(self):
        """
        Base static radar sweep overlays.
        Grid concentric circles will be drawn dynamically in 3D projection,
        so we only draw radial sweep markings here.
        """
        self.canvas_radar.delete("grid")
        w = self.canvas_radar.winfo_width()
        h = self.canvas_radar.winfo_height()
        cx, cy = w // 2, h // 2

        # Draw cross axes
        self.canvas_radar.create_line(0, cy, w, cy, fill="#0c141e", width=1, tags="grid")
        self.canvas_radar.create_line(cx, 0, cx, h, fill="#0c141e", width=1, tags="grid")

    def project_3d_point(self, x, y, z, cx, cy):
        """
        Applies a mathematical 3D-to-2D Perspective Projection matrix.
        Rotates coordinates around the Y-axis (yaw) and X-axis (pitch),
        then projects them based on camera distance parameters, zoom, and pan offsets.
        """
        # 1. Rotate Y-axis (Yaw)
        cos_y, sin_y = math.cos(self.yaw), math.sin(self.yaw)
        x1 = x * cos_y - z * sin_y
        z1 = x * sin_y + z * cos_y

        # 2. Rotate X-axis (Pitch)
        cos_p, sin_p = math.cos(self.pitch), math.sin(self.pitch)
        y2 = y * cos_p - z1 * sin_p
        z2 = y * sin_p + z1 * cos_p

        # Avoid zero division
        depth = z2 + self.camera_dist
        if depth <= 10.0:
            depth = 10.0

        # Apply zoom scaling
        scaled_x = x1 * self.zoom
        scaled_y = y2 * self.zoom

        # 3. Perspective formula + pan offsets
        proj_x = cx + self.pan_x + (scaled_x * self.camera_dist) / depth
        proj_y = cy + self.pan_y + (scaled_y * self.camera_dist) / depth
        
        return proj_x, proj_y, depth

    def draw_3d_concentric_rings(self, cx, cy):
        """
        Draws concentric range circles at 1m, 2m, 3m, and 5m scaled in 3D projection.
        Includes readable text markers showing actual distances.
        """
        # Distance rings defined in meters, scaled to GUI projection sizes (1 meter = 40 coordinate units)
        rings_meters = [1.0, 2.0, 3.0, 5.0]
        
        for r_m in rings_meters:
            pts = []
            radius = r_m * 40.0
            
            # Form a circle of 36 points in 3D horizontal plane (Y = 0)
            for i in range(37):
                angle = (i * 10) * (math.pi / 180.0)
                x = radius * math.cos(angle)
                z = radius * math.sin(angle)
                y = 0.0 # flat floor plane
                
                px, py, _ = self.project_3d_point(x, y, z, cx, cy)
                pts.append((px, py))
            
            # Renders concentric projected circle
            if len(pts) > 1:
                self.canvas_radar.create_line(pts, fill="#0f1f2e", width=1, dash=(1, 3), tags="radar_ring")
                
                # Draw visual text markers for actual range thresholds
                px_text, py_text, _ = self.project_3d_point(radius, 0.0, 0.0, cx, cy)
                self.canvas_radar.create_text(
                    px_text, py_text - 8,
                    text=f"{r_m:.1f}m",
                    font=("Space Mono", 7),
                    fill="#3f586b",
                    tags="radar_ring"
                )

    def generate_3d_points_from_telemetry(self):
        """
        Converts real-time WiFi telemetry (RSSI, RTT, Jitter) into 3D physical coordinates.
        Each RTT spike acts as an environmental reflection bounce.
        """
        if self.paused:
            return

        # Distance derived directly from RTT delay spread
        # Base scale: 1ms RTT ~ 0.8 meters
        base_distance = max(0.5, self.current_rtt * 0.7)
        
        # Add random scattering to represent multi-path dispersion
        scatter_dist = random.uniform(-0.15, 0.15)
        dist_m = base_distance + scatter_dist
        
        # Map physical meters to coordinate system
        radius = dist_m * 40.0
        
        # Direction angles (Horizontal theta, Vertical phi)
        # Create continuous sweeping angles to simulate physical space sweeps
        sweep_angle = (time.time() * 2.5) % (2.0 * math.pi)
        
        # Add angular spread based on jitter/perturbations
        jitter_angle_spread = random.uniform(-self.current_jitter*0.1, self.current_jitter*0.1)
        theta = sweep_angle + jitter_angle_spread
        phi = random.uniform(-0.15, 0.15)  # Slightly offset from horizontal plane
        
        # Convert polar coordinates (radius, theta, phi) to Cartesian 3D (X, Y, Z)
        # Center of WiFi node is at (0, 0, 0)
        x = radius * math.cos(theta) * math.cos(phi)
        y = radius * math.sin(phi)
        z = radius * math.sin(theta) * math.cos(phi)

        # Intensity is mapped from Jitter and Signal strength
        intensity = self.current_perturbation + (self.current_rssi / 10.0)

        # Push to point cloud buffer
        self.points_3d.append({
            "x": x,
            "y": y,
            "z": z,
            "intensity": intensity,
            "distance": dist_m,
            "timestamp": time.time()
        })

        # Produce a denser cascade of reflection points when a perturbation event is active!
        if self.reflection_detected:
            for _ in range(4):
                # Extra scatter points representing physical wave echoes bouncing off walls/objects
                ref_dist = base_distance * random.uniform(0.9, 1.25)
                ref_radius = ref_dist * 40.0
                ref_theta = theta + random.uniform(-0.4, 0.4)
                ref_phi = random.uniform(-0.3, 0.3)
                
                ref_x = ref_radius * math.cos(ref_theta) * math.cos(ref_phi)
                ref_y = ref_radius * math.sin(ref_phi)
                ref_z = ref_radius * math.sin(ref_theta) * math.cos(ref_phi)
                
                self.points_3d.append({
                    "x": ref_x,
                    "y": ref_y,
                    "z": ref_z,
                    "intensity": intensity * 1.5,
                    "distance": ref_dist,
                    "timestamp": time.time()
                })

        # Prune old points to maintain memory buffers
        while len(self.points_3d) > self.max_points:
            self.points_3d.pop(0)

    def animate(self):
        """
        Core 30 FPS display loop.
        Projects and draws 2D waves & 3D rotating particle clouds.
        """
        if not self.running:
            return

        # 1. Consume Telemetry Queue (only if not paused)
        if not self.paused:
            while not self.data_queue.empty():
                try:
                    stats = self.data_queue.get_nowait()
                    
                    # Apply Exponential Moving Average (EMA) smoothing to filter out high-frequency system/network noise
                    alpha = self.alpha_val  # Adjustable smoothing factor (lower = smoother, higher = more responsive to raw jitter)
                    self.current_rssi = alpha * stats.get("current_rssi", self.current_rssi) + (1.0 - alpha) * self.current_rssi
                    self.current_rtt = alpha * stats.get("current_rtt", self.current_rtt) + (1.0 - alpha) * self.current_rtt
                    self.current_jitter = alpha * stats.get("rtt_jitter", self.current_jitter) + (1.0 - alpha) * self.current_jitter
                    self.current_perturbation = alpha * stats.get("perturbation_index", self.current_perturbation) + (1.0 - alpha) * self.current_perturbation
                    
                    self.reflection_detected = stats.get("reflection_detected", False)
                    self.ssid = stats.get("ssid", self.ssid)
                    self.channel = stats.get("channel", self.channel)
                    
                    # Update digital LED readouts
                    self.rssi_val.configure(text=f"{int(self.current_rssi)}%")
                    self.rtt_val.configure(text=f"{self.current_rtt:.1f} ms")
                    self.jitter_val.configure(text=f"{self.current_jitter:.2f} ms")
                    self.pert_val.configure(text=f"{self.current_perturbation:.1f}%")
                    
                    self.details_label.configure(
                        text=f"SSID: {self.ssid}\nChannel: {self.channel}\nGateway: {stats.get('gateway', 'Unknown')}"
                    )
                    
                    # Convert this new telemetry sample into a physical 3D bounce point
                    self.generate_3d_points_from_telemetry()

                except queue.Empty:
                    break

        # 2. Glowing Alarm Hud pulse (red alerts)
        if self.reflection_detected and not self.paused:
            self.flash_counter += 1
            glow = int(120 + 120 * math.sin(self.flash_counter * 0.45))
            color_hex = f"#{glow:02x}0025"
            self.outer_frame.configure(bg=color_hex)
            self.status_label.configure(text="STATUS: OBSTRUCTION / MOVEMENT DETECTED!", fg="#ff0055")
        else:
            self.flash_counter = 0
            self.outer_frame.configure(bg="#0b0c10")
            if not self.paused:
                self.status_label.configure(text="STATUS: RADAR SWEEP ACTIVE", fg="#45a29e")

        # ----------------------------------------------------
        # DRAW DISPLAY 1: 2D WAVE OSCILLOSCOPE
        # ----------------------------------------------------
        self.canvas_wave.delete("wave")
        w_wave = self.canvas_wave.winfo_width()
        h_wave = self.canvas_wave.winfo_height()
        mid_y = h_wave // 2

        # Draw grid lines if deleted during configure
        if not self.canvas_wave.find_withtag("grid"):
            self.draw_oscilloscope_grid()

        if not self.paused:
            self.time_step += 0.12

        # Carrier Wave (Teal)
        pts_a = []
        amp_a = (self.current_rssi / 100.0) * (h_wave * 0.25)
        freq_a = 0.02
        speed_a = self.time_step

        for x in range(0, w_wave, 5):
            y = mid_y + amp_a * math.sin(freq_a * x - speed_a)
            pts_a.append((x, y))

        if len(pts_a) > 1:
            self.canvas_wave.create_line(pts_a, fill="#00ffcc", width=2, smooth=True, tags="wave")

        # Multipath Reflection Wave (Fucsia/Cyan)
        pts_b = []
        amp_b = amp_a * 0.6
        freq_b = 0.03
        speed_b = self.time_step * 1.45
        
        # Noise magnitude modulates by RTT jitter
        noise_val = max(1.0, self.current_jitter * 2.2 + self.current_perturbation * 0.3)

        for x in range(0, w_wave, 5):
            phase_scat = math.sin(x * 0.006 + self.time_step * 0.6) * (noise_val * 0.4)
            hashing = 0.0
            if (self.reflection_detected or self.current_jitter > 3.0) and not self.paused:
                hashing = (random.random() - 0.5) * noise_val * 1.8
                
            y = mid_y + amp_b * math.sin(freq_b * x - speed_b + phase_scat) + hashing
            pts_b.append((x, y))

        if len(pts_b) > 1:
            wave_b_color = "#ff0055" if self.reflection_detected else "#00ccff"
            self.canvas_wave.create_line(pts_b, fill=wave_b_color, width=1, smooth=True, tags="wave")

        # ----------------------------------------------------
        # DRAW DISPLAY 2: 3D ROTATING RADAR POINT CLOUD
        # ----------------------------------------------------
        self.canvas_radar.delete("radar")
        self.canvas_radar.delete("radar_ring")
        
        w_rad = self.canvas_radar.winfo_width()
        h_rad = self.canvas_radar.winfo_height()
        cx, cy = w_rad // 2, h_rad // 2

        # Auto-rotate 3D space around Y-axis (Yaw)
        if self.auto_rotate and not self.paused:
            self.yaw += 0.015

        # Render 3D concentric distance circles (1m, 2m, 3m, 5m target rings)
        self.draw_3d_concentric_rings(cx, cy)

        # Draw Central WiFi Transmitting Hub Node (0,0,0)
        hub_x, hub_y, _ = self.project_3d_point(0, 0, 0, cx, cy)
        self.canvas_radar.create_oval(
            hub_x - 6, hub_y - 6, hub_x + 6, hub_y + 6,
            fill="#00ffcc", outline="#ffffff", width=1, tags="radar"
        )
        self.canvas_radar.create_text(
            hub_x, hub_y + 14,
            text="WIFI_NODE",
            font=("Space Mono", 7, "bold"),
            fill="#00ffcc",
            tags="radar"
        )

        # Renders each active multipath bounce point in perspective 3D
        for pt in self.points_3d:
            px, py, depth = self.project_3d_point(pt["x"], pt["y"], pt["z"], cx, cy)

            # Cull particles drawn behind camera plane
            if depth <= 20.0:
                continue

            # RTT Distance & intensity
            dist = pt["distance"]
            intensity = pt["intensity"]

            # Dynamic glowing color mapping
            if pt["intensity"] > 25.0:
                color = "#ff0055"  # High perturbation alarm
            elif dist < 2.0:
                color = "#00ffcc"  # Close stable node (teal)
            elif dist < 3.5:
                color = "#00ccff"  # Medium distance reflection (blue)
            else:
                color = "#8b5cf6"  # Distant scattering (purple)

            # Fade older points based on age
            age = time.time() - pt["timestamp"]
            opacity_ratio = max(0.1, 1.0 - (age / 12.0)) # fade out over 12 seconds
            
            # Map size: points closer to the camera (smaller depth) appear physically larger
            point_radius = max(1, min(6, int((150.0 / depth) * (1.0 + intensity*0.05))))

            # Render point bubble
            self.canvas_radar.create_oval(
                px - point_radius, py - point_radius, px + point_radius, py + point_radius,
                fill=color, outline="", tags="radar"
            )

            # Draw subtle distance line from node origin to target reflection particle
            if pt["intensity"] > 18.0:
                self.canvas_radar.create_line(
                    hub_x, hub_y, px, py,
                    fill=color, width=1, stipple="gray25", tags="radar"
                )

        # 30 FPS redraw callback (~33ms)
        self.root.after(33, self.animate)

    def start_worker_thread(self):
        """
        Saves GUI performance from synchronous blocking operations.
        Runs scanning engines in daemon threads.
        """
        self.worker_thread = threading.Thread(target=self.sensing_worker, daemon=True)
        self.worker_thread.start()

    def sensing_worker(self):
        """
        Independent daemon telemetry acquisition.
        Pushes parsed state arrays into the thread-safe queue.
        """
        conn = get_current_connection()
        ssid = conn.get("ssid", "Active Interface")
        
        # High frequency scanner - polled dynamically based on user controls
        init_interval = 1.0 / self.sensing_hz
        self.sensing_engine = SignalSensingEngine(target_ssid=ssid, poll_interval=init_interval, window_size=50)
        
        def push_to_gui(stats):
            stats["gateway"] = self.sensing_engine.gateway_ip
            # When paused, discard telemetry to keep the queue clean
            if not self.paused:
                self.data_queue.put(stats)

        try:
            self.sensing_engine.run_sensing_loop(duration_seconds=999999, callback=push_to_gui)
        except Exception as e:
            print(f"Error in sensing background worker: {e}", file=sys.stderr)

    def close(self):
        """
        Graceful destruction.
        """
        self.running = False
        self.root.destroy()

def start_gui():
    """
    Called by run.py CLI script command router.
    """
    root = tk.Tk()
    app = WifiOscilloscopeGUI(root)
    root.protocol("WM_DELETE_WINDOW", app.close)
    root.mainloop()
