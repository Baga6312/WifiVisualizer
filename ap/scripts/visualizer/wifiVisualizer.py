class WiFiVisualizer:
    def __init__(self, input_file, update_interval=1.0, use_beacons=False, use_channels=True):
        self.input_file = input_file
        self.update_interval = update_interval
        self.use_beacons = use_beacons  # Whether to use beacons for positioning
        self.use_channels = use_channels  # Whether to use channel information
        
        # Position update settings - increased for better responsiveness
        self.position_update_factor = 0.8  # How much to update position (0.0-1.0)
        self.rssi_change_threshold = 1     # Minimum RSSI change to update position
        self.beacon_change_threshold = 3   # Minimum beacon count change to update position
        
        # Store AP data with bssid as key
        self.ap_data = defaultdict(dict)
        
        # History tracking for more accurate movement detection
        self.history_len = 3  # Number of readings to keep in history
        self.ap_history = defaultdict(lambda: {'rssi': [], 'beacons': []})
        
        # Test if we can read data initially
        debug_print(f"Testing initial data read from {input_file}")
        initial_aps = parse_aps(input_file)
        debug_print(f"Initial read found {len(initial_aps)} APs")
        
        if len(initial_aps) == 0:
            debug_print("WARNING: No APs found in the initial read")
            debug_print("You may need to check your file format or try the test data option")
            # Enable test data generation if no APs found
            self.use_test_data = True
        else:
            self.use_test_data = False
        
        # Create a figure and axis for plotting
        self.fig, self.ax = plt.subplots(figsize=(5, 8))
        try:
            self.fig.canvas.manager.set_window_title('WiFi Access Point Visualizer')
        except Exception as e:
            debug_print(f"Window title setting error (non-critical): {e}")
        
        # Add observer (you) at center
        self.ax.plot(0, 0, 'ko', markersize=2)
        self.ax.text(0, 0, "YOU", fontsize=2, ha='center', va='bottom', color='black')
        
        # Setup the plot
        self.setup_plot()
        
        # Add keyboard event handling
        self.fig.canvas.mpl_connect('key_press_event', self.on_key_press)
        
        debug_print("Setting up animation")
        # Start the animation
        self.ani = FuncAnimation(self.fig, self.update, interval=int(self.update_interval*1000), 
                                 cache_frame_data=False)
    

    

    
    def detect_trend(self, history):
        """Detect if a value is trending up, down, or stable based on history"""
        if len(history) < 2:
            return 'stable'
        
        # Calculate differences between consecutive readings
        diffs = [history[i] - history[i-1] for i in range(1, len(history))]
        
        # Check if mostly increasing or decreasing
        increasing = sum(1 for d in diffs if d > 0)
        decreasing = sum(1 for d in diffs if d < 0)
        
        if increasing > decreasing and increasing >= len(diffs) / 2:
            return 'increasing'
        elif decreasing > increasing and decreasing >= len(diffs) / 2:
            return 'decreasing'
        else:
            return 'stable'

    def update(self, frame):
        """Update the plot with new data"""
        try:
            debug_print(f"Update at frame {frame}: Reading data from {self.input_file}")
            aps = parse_aps(self.input_file)
            debug_print(f"Found {len(aps)} APs in this update")
    
            # If no APs found, try to generate test data
            if len(aps) == 0 and self.use_test_data:
                debug_print("Generating test data since no APs found")
                aps = self.generate_test_data()
    
            # Clear previous data points but keep the grid and circles
            to_remove = []
            for artist in self.ax.texts + self.ax.collections + self.ax.lines:
                # Keep the observer point, grid lines and circles
                if isinstance(artist, Circle):
                    continue
                if hasattr(artist, 'get_label') and artist.get_label() in ['Excellent (> -50 dBm)', 'Good (-50 to -65 dBm)', 'Fair (-65 to -75 dBm)', 'Poor (< -75 dBm)']:
                    continue
                if isinstance(artist, plt.Text) and artist.get_position() == (0, 0):
                    continue
                to_remove.append(artist)
    
            for artist in to_remove:
                try:
                    artist.remove()
                except Exception as e:
                    debug_print(f"Error removing artist: {e}")
    
            # Re-add observer
            self.ax.plot(0, 0, 'ko', markersize=9)
            self.ax.text(0, 0, "YOU", fontsize=12, ha='center', va='bottom', color='black')
    
            # Track active BSSIDs for removing stale ones
            active_bssids = set()
    
            # Set constant circle size for all APs
            fixed_circle_radius = 1.5  # Fixed radius for all AP circles
    
            for i, (bssid, rssi, essid, beacons, channel) in enumerate(aps):
                debug_print(f"Processing AP {i+1}/{len(aps)}: BSSID={bssid}, RSSI={rssi}, ESSID={essid}, Beacons={beacons}, Channel={channel}")
                active_bssids.add(bssid)
    
                # Update history for this AP
                if len(self.ap_history[bssid]['rssi']) >= self.history_len:
                    self.ap_history[bssid]['rssi'].pop(0)
                    self.ap_history[bssid]['beacons'].pop(0)
                self.ap_history[bssid]['rssi'].append(rssi)
                self.ap_history[bssid]['beacons'].append(beacons)
    
                # Detect movement trends
                rssi_trend = self.detect_trend(self.ap_history[bssid]['rssi'])
                beacon_trend = self.detect_trend(self.ap_history[bssid]['beacons'])
    
                # Calculate new position based on current RSSI or beacon count
                if self.use_beacons:
                    distance = beacons_to_distance(beacons)
                    debug_print(f"Using beacon count ({beacons}) for base distance: {distance:.1f}m")
                else:
                    if self.use_channels:
                        distance = calculate_distance_with_channel(rssi, channel)
                        debug_print(f"Using RSSI ({rssi}) with channel {channel} for distance: {distance:.1f}m")
                    else:
                        distance = rssi_to_distance(rssi)
                        debug_print(f"Using RSSI ({rssi}) for distance: {distance:.1f}m")
    
                # Store current position or generate new one
                if bssid not in self.ap_data:
                    # First time seeing this AP - generate a random angle
                    angle = np.random.uniform(0, 2 * np.pi)
                    new_x, new_y = calculate_xy_position(distance, angle)
    
                    self.ap_data[bssid] = {
                        'x': new_x,
                        'y': new_y,
                        'rssi': rssi,
                        'beacons': beacons,
                        'channel': channel,
                        'essid': essid,
                        'angle': angle,
                        'last_update': time.time()
                        }
                    debug_print(f"New AP: {essid} ({bssid}) at ({new_x:.1f}, {new_y:.1f})")
                else:
                    # Update existing AP position
                    ap_info = self.ap_data[bssid]
                    old_x, old_y = ap_info['x'], ap_info['y']
                    old_rssi = ap_info['rssi']
                    old_beacons = ap_info['beacons']
    
                    # Decide whether to update position based on significant changes
                    should_update = False
    
                    if self.use_beacons:
                        beacon_diff = abs(beacons - old_beacons)
                        if beacon_diff >= self.beacon_change_threshold:
                            should_update = True
                            debug_print(f"Updating position due to beacon change: {old_beacons} -> {beacons}")
                    else:
                        rssi_diff = abs(rssi - old_rssi)
                        if rssi_diff >= self.rssi_change_threshold:
                            should_update = True
                            debug_print(f"Updating position due to RSSI change: {old_rssi} -> {rssi}")
    
                    # If the signal has changed significantly, update position accordingly
                    if should_update:
                        # Calculate new position using existing angle
                        angle = ap_info['angle']
                        new_x, new_y = calculate_xy_position(distance, angle)
    
                        # Use weighted average for smoother transitions
                        weight = self.position_update_factor
    
                        # Adjust update weight based on trend detection for smoother movement
                        if self.use_beacons:
                            if beacon_trend == 'increasing' and beacons > old_beacons:
                                # Stronger weight for confident movement
                                weight = min(1.0, weight * 1.2)
                            elif beacon_trend == 'decreasing' and beacons < old_beacons:
                                weight = min(1.0, weight * 1.2)
                        else:
                            if rssi_trend == 'increasing' and rssi > old_rssi:
                                # AP is likely getting closer - stronger weight
                                weight = min(1.0, weight * 1.2)
                            elif rssi_trend == 'decreasing' and rssi < old_rssi:
                                # AP is likely moving away - stronger weight
                                weight = min(1.0, weight * 1.2)
    
                        # Calculate updated position with weighted average
                        weighted_x = old_x * (1 - weight) + new_x * weight
                        weighted_y = old_y * (1 - weight) + new_y * weight
    
                        # Update the position
                        self.ap_data[bssid]['x'] = weighted_x
                        self.ap_data[bssid]['y'] = weighted_y
                        self.ap_data[bssid]['last_update'] = time.time()
                        debug_print(f"Updated AP: {essid} ({bssid}) from ({old_x:.1f}, {old_y:.1f}) to ({weighted_x:.1f}, {weighted_y:.1f})")
                    else:
                        debug_print(f"No significant change for {essid} ({bssid}), keeping position")
    
                # Update stored values even if position isn't changed
                self.ap_data[bssid]['rssi'] = rssi
                self.ap_data[bssid]['beacons'] = beacons
                self.ap_data[bssid]['essid'] = essid
                self.ap_data[bssid]['channel'] = channel
    
                # Get current position
                x, y = self.ap_data[bssid]['x'], self.ap_data[bssid]['y']
    
                # Use fixed circle radius for all APs instead of variable radius based on RSSI
                radius = fixed_circle_radius
    
                # Plot the AP with fixed circle size
                circle = Circle((x, y), radius, fill=True, alpha=0.7, color=get_rssi_color(rssi))
                self.ax.add_patch(circle)
    
                # Add text for AP name (without MAC address)
                # Only display ESSID, not MAC address
                display_name = essid if essid else "Hidden Network"
    
                # Add channel information to display if channels are being used
                if self.use_channels and channel > 0:
                    freq = channel_to_frequency(channel)
                    freq_band = "2.4GHz" if freq < 5.0 else "5GHz"
                    display_name = f"{display_name} (Ch {channel}, {freq_band})"
    
                # Add AP label
                self.ax.text(x, y + radius + 0.5, display_name,
                           fontsize=9, ha='center', va='bottom',
                           bbox=dict(facecolor='white', alpha=0.7, boxstyle='round,pad=0.2'))
    
                # Plot the actual distance with a dashed line
                self.ax.plot([0, x], [0, y], '--', color=get_rssi_color(rssi), alpha=0.5)
    
                # Add RSSI value next to the AP
                self.ax.text(x, y - radius - 0.5, f"{rssi} dBm",
                           fontsize=8, ha='center', va='top',
                           bbox=dict(facecolor='white', alpha=0.7, boxstyle='round,pad=0.1'))
    
            # Remove stale APs (not seen in this update)
            stale_bssids = set(self.ap_data.keys()) - active_bssids
            for bssid in stale_bssids:
                debug_print(f"Removing stale AP: {bssid}")
                self.ap_data.pop(bssid, None)
                self.ap_history.pop(bssid, None)
    
            # Update title with current mode information
            mode_text = "Beacon-based" if self.use_beacons else "RSSI-based"
            channel_text = "with channel adjustment" if self.use_channels else "without channel adjustment"
            self.ax.set_title(f'WiFi Access Points Real-time Visualization ({mode_text}, {channel_text})')
    
            # Add keyboard shortcut info
            shortcuts = [
                "[+/-] Adjust update sensitivity",
                "[b] Toggle beacon/RSSI mode",
                "[c] Toggle channel adjustment",
                "[r] Reset positions",
                "[]/[] Adjust change threshold"
            ]
            shortcut_text = "\n".join(shortcuts)
            # Add the shortcuts in the bottom left corner
            if hasattr(self, 'shortcut_text'):
                self.shortcut_text.remove()
            self.shortcut_text = self.ax.text(
                0.02, 0.02, shortcut_text,
                transform=self.fig.transFigure,
                fontsize=8, ha='left', va='bottom',
                bbox=dict(facecolor='white', alpha=0.7, boxstyle='round,pad=0.3')
            )
    
            # Adjust plot limits dynamically based on AP positions
            if self.ap_data:
                x_values = [info['x'] for info in self.ap_data.values()]
                y_values = [info['y'] for info in self.ap_data.values()]
    
                if x_values and y_values:
                    max_x = max(abs(min(x_values)), abs(max(x_values)))
                    max_y = max(abs(min(y_values)), abs(max(y_values)))
                    max_dim = max(max_x, max_y) * 1.2  # Add 20% margin
                    max_dim = max(max_dim, 20)  # At least 20m range
    
                    self.ax.set_xlim(-max_dim, max_dim)
                    self.ax.set_ylim(-max_dim, max_dim)
    
                    # Update range circles if needed
                    if max_dim > 20:
                        for patch in self.ax.patches:
                            if isinstance(patch, Circle) and patch.get_radius() in [5, 10, 20]:
                                patch.remove()
    
                        # Add new range circles
                        for radius in [5, 10, 20, int(max_dim * 0.5), int(max_dim * 0.75)]:
                            if radius > 0:
                                circle = Circle((0, 0), radius, fill=False, linestyle='--', alpha=0.3)
                                self.ax.add_patch(circle)
                                self.ax.text(radius, 0, f"{radius}m", fontsize=8, ha='left', va='bottom')
    
            plt.draw()
            debug_print(f"Update completed with {len(active_bssids)} active APs")

        except Exception as e:
            debug_print(f"Error during update: {e}")
            import traceback
            traceback.print_exc()

    def run(self):
        """Run the visualizer"""
        plt.tight_layout()
        plt.show()
