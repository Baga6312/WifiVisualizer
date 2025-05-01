#!/usr/bin/env python3
import sys
import csv
import time
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from matplotlib.patches import Circle
import subprocess
from collections import defaultdict
import os
import math

# Debug mode
DEBUG = True

def debug_print(*args, **kwargs):
    """Print only in debug mode"""
    if DEBUG:
        print("[DEBUG]", *args, **kwargs)

# Define colors for different signal strength ranges
def get_rssi_color(rssi):
    """Return color based on RSSI value"""
    if rssi >= -50:  # Excellent
        return 'green'
    elif rssi >= -65:  # Good
        return 'blue'
    elif rssi >= -75:  # Fair
        return 'orange'
    else:  # Poor
        return 'red'

def parse_aps(filename):
    """Parse AP information from CSV file with improved format handling"""
    aps = []
    try:
        with open(filename, 'r') as f:
            # Print first few lines of file for debugging
            if DEBUG:
                debug_print(f"Opening file: {filename}")
                f.seek(0)  # Go to start of file
                content = f.read(1000)  # Read first 1000 chars for debug view
                debug_print(f"File preview:\n{content[:500]}...")
                f.seek(0)  # Reset to beginning
            
            # Read the file content
            content = f.read()
            
            # Try to identify if this is a standard CSV or airodump-ng output
            if "Station MAC" in content:
                debug_print("Detected airodump-ng output format")
                # Split into AP section and station section
                parts = content.split("Station MAC")
                ap_section = parts[0].strip()
                
                # Process AP section line by line
                lines = ap_section.split('\n')
                header_line = None
                
                for i, line in enumerate(lines):
                    if "BSSID" in line and "First time seen" in line:
                        header_line = i
                        debug_print(f"Found header line at index {i}: {line}")
                        break
                
                if header_line is not None:
                    # Process each AP line after the header
                    for line in lines[header_line + 1:]:
                        line = line.strip()
                        if not line:  # Skip empty lines
                            continue
                            
                        # Split the line by commas and clean up fields
                        fields = [field.strip() for field in line.split(',')]
                        
                        if len(fields) >= 9:  # Need at least BSSID, Power and ESSID fields
                            try:
                                bssid = fields[0].strip()
                                
                                # Extract channel (typically field 3, index 2)
                                channel_str = fields[3].strip() if len(fields) > 3 else "0"
                                try:
                                    channel = int(channel_str) if channel_str.isdigit() else 0
                                except ValueError:
                                    debug_print(f"Warning: Could not convert Channel to int: '{channel_str}' in line: {line}")
                                    channel = 0
                                
                                # Power is typically in field 8 (index 7)
                                power_str = fields[8].strip()
                                
                                # Handle potential errors in integer conversion
                                try:
                                    rssi = int(power_str) if power_str.lstrip('-').isdigit() else -100
                                except ValueError:
                                    debug_print(f"Warning: Could not convert Power to int: '{power_str}' in line: {line}")
                                    rssi = -100  # Default poor signal if can't parse
                                
                                # Extract beacon count (typically field 9, index 8)
                                beacon_str = fields[9].strip() if len(fields) > 9 else "0"
                                try:
                                    beacons = int(beacon_str) if beacon_str.isdigit() else 0
                                except ValueError:
                                    debug_print(f"Warning: Could not convert Beacons to int: '{beacon_str}' in line: {line}")
                                    beacons = 0
                                
                                # ESSID is typically in field 13 (index 12)
                                essid = fields[13].strip() if len(fields) > 13 else ""
                                
                                if bssid and bssid != "BSSID":  # Skip if BSSID is empty or header
                                    aps.append((bssid, rssi, essid, beacons, channel))
                                    debug_print(f"Added AP: BSSID={bssid}, RSSI={rssi}, ESSID={essid}, Beacons={beacons}, Channel={channel}")
                            except Exception as e:
                                debug_print(f"Error processing line: {e}")
                                debug_print(f"Line data: {line}")
                else:
                    debug_print("Could not find header line with BSSID and First time seen")
            else:
                # Try standard CSV parsing
                debug_print("Attempting standard CSV parsing")
                f.seek(0)  # Reset to beginning
                reader = csv.reader(f)
                header = None
                
                for row in reader:
                    if not row or not any(row):  # Skip empty rows
                        continue
                        
                    # Try to identify header row
                    if not header and any(cell and "BSSID" in cell for cell in row):
                        header = row
                        debug_print(f"Found header: {header}")
                        continue
                    
                    # Process data rows
                    if header:
                        try:
                            # Find column indices
                            bssid_idx = next((i for i, cell in enumerate(header) if cell and "BSSID" in cell), 0)
                            power_idx = next((i for i, cell in enumerate(header) if cell and "Power" in cell), 8)
                            beacons_idx = next((i for i, cell in enumerate(header) if cell and "beacons" in cell), 9)
                            essid_idx = next((i for i, cell in enumerate(header) if cell and "ESSID" in cell), 13)
                            channel_idx = next((i for i, cell in enumerate(header) if cell and "channel" in cell), 3)
                            
                            # Get values
                            if len(row) > max(bssid_idx, power_idx, essid_idx):
                                bssid = row[bssid_idx].strip()
                                power_str = row[power_idx].strip()
                                beacon_str = row[beacons_idx].strip() if len(row) > beacons_idx else "0"
                                essid = row[essid_idx].strip() if len(row) > essid_idx else ""
                                channel_str = row[channel_idx].strip() if len(row) > channel_idx else "0"
                                
                                try:
                                    rssi = int(power_str) if power_str.lstrip('-').isdigit() else -100
                                except ValueError:
                                    debug_print(f"Warning: Could not convert Power to int: '{power_str}'")
                                    rssi = -100
                                
                                try:
                                    beacons = int(beacon_str) if beacon_str.isdigit() else 0
                                except ValueError:
                                    debug_print(f"Warning: Could not convert Beacons to int: '{beacon_str}'")
                                    beacons = 0
                                
                                try:
                                    channel = int(channel_str) if channel_str.isdigit() else 0
                                except ValueError:
                                    debug_print(f"Warning: Could not convert Channel to int: '{channel_str}'")
                                    channel = 0
                                
                                if bssid and bssid != "BSSID":  # Skip if BSSID is empty or header
                                    aps.append((bssid, rssi, essid, beacons, channel))
                                    debug_print(f"Added AP: BSSID={bssid}, RSSI={rssi}, ESSID={essid}, Beacons={beacons}, Channel={channel}")
                        except Exception as e:
                            debug_print(f"Error processing row: {e}")
                            debug_print(f"Row data: {row}")
                    else:
                        debug_print("Processing without identified header")
                        # If we can't find a header, try simple format
                        if len(row) >= 3:
                            try:
                                bssid = row[0].strip()
                                # Try to find channel
                                channel = 0
                                if len(row) > 3:
                                    try:
                                        channel = int(row[3].strip())
                                    except ValueError:
                                        channel = 0
                                
                                # Try to find RSSI/Power field
                                power_found = False
                                for i, cell in enumerate(row):
                                    if cell.strip().startswith('-') and cell.strip().lstrip('-').isdigit():
                                        rssi = int(cell.strip())
                                        power_found = True
                                        break
                                        
                                if not power_found and len(row) > 8:
                                    # Try standard position
                                    try:
                                        rssi = int(row[8].strip())
                                    except ValueError:
                                        rssi = -100
                                elif not power_found:
                                    rssi = -100
                                
                                # Try to find beacons
                                beacons = 0
                                if len(row) > 9:
                                    try:
                                        beacons = int(row[9].strip())
                                    except ValueError:
                                        beacons = 0
                                
                                # Try to find ESSID
                                essid = ""
                                for i, cell in enumerate(row):
                                    if i > 0 and cell.strip() and not cell.strip().startswith('-') and not cell.strip()[0].isdigit():
                                        essid = cell.strip()
                                        break
                                
                                if not essid and len(row) > 13:
                                    essid = row[13].strip()
                                
                                if bssid and bssid != "BSSID":  # Skip if BSSID is empty or header
                                    aps.append((bssid, rssi, essid, beacons, channel))
                                    debug_print(f"Added AP (simple format): BSSID={bssid}, RSSI={rssi}, ESSID={essid}, Beacons={beacons}, Channel={channel}")
                            except Exception as e:
                                debug_print(f"Error processing simple format: {e}")
    
    except Exception as e:
        debug_print(f"Error reading file: {e}")
    
    # Remove any duplicate BSSIDs (keep the one with strongest signal)
    unique_aps = {}
    for bssid, rssi, essid, beacons, channel in aps:
        if bssid not in unique_aps or rssi > unique_aps[bssid][0]:
            unique_aps[bssid] = (rssi, essid, beacons, channel)
    
    result = [(bssid, rssi, essid, beacons, channel) for bssid, (rssi, essid, beacons, channel) in unique_aps.items()]
    debug_print(f"Returned {len(result)} unique APs")
    
    return result

def rssi_to_distance(rssi, measured_power=-30, path_loss_exponent=3.0):
    """
    Convert RSSI to estimated distance in meters
    Using improved path loss exponent based on WiFi characteristics
    """
    # Prevent division by zero or negative values that would break the logarithm
    if rssi >= measured_power:
        return 1.0  # Minimum distance
    
    return 10 ** ((measured_power - rssi) / (10 * path_loss_exponent))

def channel_to_frequency(channel):
    """Convert WiFi channel to frequency in GHz with more accurate mapping"""
    if channel <= 0:
        return 2.4  # Default to 2.4 GHz
    
    if 1 <= channel <= 14:
        # 2.4 GHz band
        if channel == 14:  # Special case for channel 14
            return 2.484
        else:
            return 2.407 + 0.005 * channel
    elif 32 <= channel <= 68:  # U-NII-1 and U-NII-2A bands
        return 5.16 + 0.005 * (channel - 32)
    elif 96 <= channel <= 144:  # U-NII-2C band
        return 5.49 + 0.005 * (channel - 96)
    elif 149 <= channel <= 177:  # U-NII-3 band
        return 5.735 + 0.005 * (channel - 149)
    else:
        # Unknown channel - make an educated guess based on channel number
        if 15 <= channel <= 31:
            return 2.4  # Assume 2.4 GHz
        elif channel >= 32:
            return 5.0 + (channel - 32) * 0.005  # Assume 5 GHz with standard spacing
        else:
            return 2.4  # Default

def adjust_rssi_by_channel(rssi, channel):
    """
    Adjust RSSI based on channel frequency with improved accuracy
    Higher frequencies (5GHz) attenuate more than 2.4GHz
    """
    freq = channel_to_frequency(channel)
    
    if freq >= 5.7:  # Upper 5GHz band (U-NII-3)
        # Higher 5GHz signals attenuate significantly more
        return rssi + 8
    elif freq >= 5.4:  # Mid 5GHz band (U-NII-2C)
        # Mid 5GHz signals attenuate more
        return rssi + 7
    elif freq >= 5.15:  # Lower 5GHz band (U-NII-1)
        # Lower 5GHz signals attenuate more than 2.4GHz
        return rssi + 6
    elif freq > 2.45:  # Upper 2.4GHz band (channels 10-14)
        # Upper 2.4GHz signals attenuate slightly more
        return rssi + 1
    elif freq < 2.425:  # Lower 2.4GHz band (channels 1-4)
        # Lower 2.4GHz signals attenuate slightly less
        return rssi - 1
    else:
        # Mid 2.4GHz band (channels 5-9)
        return rssi

def calculate_distance_with_channel(rssi, channel):
    """Calculate distance taking into account the channel frequency with improved accuracy"""
    adjusted_rssi = adjust_rssi_by_channel(rssi, channel)
    
    # Use different path loss exponents based on frequency and environment
    freq = channel_to_frequency(channel)
    
    if freq >= 5.7:  # Upper 5GHz band
        path_loss = 3.6  # Higher attenuation
    elif freq >= 5.15:  # Any 5GHz band
        path_loss = 3.5  # High attenuation
    elif freq > 2.45:  # Upper 2.4GHz band
        path_loss = 3.1  # Slightly higher attenuation
    elif freq < 2.425:  # Lower 2.4GHz band
        path_loss = 2.9  # Slightly lower attenuation
    else:  # Mid 2.4GHz band
        path_loss = 3.0  # Standard path loss
        
    # Calculate measured reference power based on frequency
    # Different frequencies have different reference powers at 1m distance
    if freq >= 5.15:
        measured_power = -32  # 5GHz reference
    else:
        measured_power = -30  # 2.4GHz reference
        
    return rssi_to_distance(adjusted_rssi, measured_power=measured_power, path_loss_exponent=path_loss)

def beacons_to_distance(beacon_count, max_beacons=1000, min_beacons=10):
    """Convert beacon count to distance with improved scaling"""
    if beacon_count <= 0:
        return 50  # Max distance
    
    # Normalize beacon count between min and max
    normalized_beacons = min(max_beacons, max(min_beacons, beacon_count))
    log_scale = math.log(normalized_beacons) / math.log(max_beacons)
    
    # More aggressive scaling for better distance discrimination
    return max(1, 40 * (1 - log_scale ** 0.7))

def calculate_xy_position(distance, angle=None):
    """Convert distance to X,Y coordinates with optional fixed or random angle"""
    if angle is None:
        angle = np.random.uniform(0, 2 * np.pi)  # Random angle
    return (
        distance * np.cos(angle),  # X
        distance * np.sin(angle)   # Y
    )

def generate_test_data(num_aps=5):
    """Generate test data for demonstration when no real data is available"""
    aps = []
    essids = ["HomeWiFi", "Office_Network", "Guest5G", "IoT_Network", "SecurityCam", 
             "Neighbor1", "Neighbor2", "CoffeeShop", "FreeWiFi", "Hidden"]
    
    for i in range(num_aps):
        # Generate a random MAC address
        mac_parts = [format(np.random.randint(0, 255), '02x') for _ in range(6)]
        bssid = ':'.join(mac_parts).upper()
        
        # Generate random RSSI between -30 (excellent) and -90 (poor)
        rssi = -30 - np.random.randint(0, 60)
        
        # Assign random ESSID
        essid = essids[i % len(essids)]
        if i >= len(essids):
            essid += "_" + str(i // len(essids))
            
        # Generate random beacon count
        beacons = np.random.randint(10, 1000)
        
        # Generate random channel (1-13 for 2.4GHz, 36-165 for 5GHz)
        if np.random.random() < 0.6:  # 60% chance for 2.4GHz
            channel = np.random.randint(1, 14)
        else:  # 40% chance for 5GHz
            channels_5g = [36, 40, 44, 48, 52, 56, 60, 64, 100, 104, 108, 112, 116, 
                          120, 124, 128, 132, 136, 140, 144, 149, 153, 157, 161, 165]
            channel = channels_5g[np.random.randint(0, len(channels_5g))]
        
        aps.append((bssid, rssi, essid, beacons, channel))
    
    return aps

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
    
    def on_key_press(self, event):
        """Handle keyboard events for adjusting parameters"""
        if event.key == '+' or event.key == '=':
            # Increase position update factor
            self.position_update_factor = min(1.0, self.position_update_factor + 0.1)
            debug_print(f"Increased position update factor to {self.position_update_factor:.1f}")
        elif event.key == '-' or event.key == '_':
            # Decrease position update factor
            self.position_update_factor = max(0.1, self.position_update_factor - 0.1)
            debug_print(f"Decreased position update factor to {self.position_update_factor:.1f}")
        elif event.key == '[':
            # Decrease RSSI/beacon change threshold
            if self.use_beacons:
                self.beacon_change_threshold = max(0, self.beacon_change_threshold - 1)
                debug_print(f"Decreased beacon change threshold to {self.beacon_change_threshold}")
            else:
                self.rssi_change_threshold = max(0, self.rssi_change_threshold - 1)
                debug_print(f"Decreased RSSI change threshold to {self.rssi_change_threshold}")
        elif event.key == ']':
            # Increase RSSI/beacon change threshold
            if self.use_beacons:
                self.beacon_change_threshold = self.beacon_change_threshold + 1
                debug_print(f"Increased beacon change threshold to {self.beacon_change_threshold}")
            else:
                self.rssi_change_threshold = self.rssi_change_threshold + 1
                debug_print(f"Increased RSSI change threshold to {self.rssi_change_threshold}")
        elif event.key == 'r':
            # Reset all AP positions
            debug_print("Resetting all AP positions")
            self.ap_data.clear()
            self.ap_history.clear()
        elif event.key == 'b':
            # Toggle between RSSI and beacon-based positioning
            self.use_beacons = not self.use_beacons
            debug_print(f"{'Enabled' if self.use_beacons else 'Disabled'} beacon-based positioning")
        elif event.key == 'c':
            # Toggle channel-based adjustments
            self.use_channels = not self.use_channels
            debug_print(f"{'Enabled' if self.use_channels else 'Disabled'} channel-based adjustments")
    
    def setup_plot(self):
        """Initialize the plot appearance"""
        self.ax.set_xlim(-30, 30)
        self.ax.set_ylim(-30, 30)
        self.ax.set_xlabel('X Distance (m)')
        self.ax.set_ylabel('Y Distance (m)')
        self.ax.set_title('WiFi Access Points Real-time Visualization')
        self.ax.grid(True)
        
        # Add range circles
        for radius in [10, 15]:
            circle = Circle((0, 0), radius, fill=False, linestyle='--', alpha=0.5)
            self.ax.add_patch(circle)
            self.ax.text(radius, 0, f"{radius}m", fontsize=10, ha='left', va='bottom')
        
        # Add legend for RSSI color codes
        rssi_levels = [
            ('Excellent (> -50 dBm)', 'green'),
            ('Good (-50 to -65 dBm)', 'blue'),
            ('Fair (-65 to -75 dBm)', 'orange'),
            ('Poor (< -75 dBm)', 'red')
        ]
        for label, color in rssi_levels:
            self.ax.plot([], [], 'o', color=color, label=label)
        self.ax.legend(loc='upper right')
    
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
    
    def generate_test_data(self):
        """Generate test data for demonstration"""
        return generate_test_data()
    
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

def main():
    """Main function to handle command line arguments and run the visualizer"""
    import argparse

    parser = argparse.ArgumentParser(description='Visualize WiFi APs from airodump-ng CSV output')
    parser.add_argument('input_file', nargs='?', default=None,
                        help='Path to CSV file from airodump-ng (default: test data)')
    parser.add_argument('-i', '--interval', type=float, default=1.0,
                        help='Update interval in seconds (default: 1.0)')
    parser.add_argument('-b', '--beacons', action='store_true',
                        help='Use beacon count instead of RSSI for positioning')
    parser.add_argument('-t', '--test', action='store_true',
                        help='Use test data instead of reading from file')
    parser.add_argument('-c', '--channels', action='store_true', default=True,
                        help='Adjust for channel frequency differences (default: True)')
    parser.add_argument('-d', '--debug', action='store_true',
                        help='Enable debug output')

    args = parser.parse_args()

    # Set global debug flag
    global DEBUG
    DEBUG = args.debug

    # Determine input file
    input_file = None
    if args.test:
        debug_print("Using test data mode")
        # Create a temporary file with test data
        import tempfile
        input_file = tempfile.mktemp(suffix='.csv')
        debug_print(f"Created temporary file for test data: {input_file}")

        # Write minimal header to make parse_aps() happy
        with open(input_file, 'w') as f:
            f.write("BSSID, First time seen, Last time seen, Channel, Speed, Privacy, Cipher, Authentication, Power, # beacons, # IV, LAN IP, ID-length, ESSID, Key\n")

    elif args.input_file:
        input_file = args.input_file
        debug_print(f"Using input file: {input_file}")

        # Check if file exists
        if not os.path.exists(input_file):
            print(f"Error: Input file '{input_file}' does not exist.")
            return 1
    else:
        print("Error: Either an input file or --test option must be specified.")
        parser.print_help()
        return 1

    # Create and run the visualizer
    try:
        debug_print("Creating visualizer")
        visualizer = WiFiVisualizer(input_file,
                                   update_interval=args.interval,
                                   use_beacons=args.beacons,
                                   use_channels=args.channels)
        debug_print("Starting visualizer")
        visualizer.run()
    except Exception as e:
        print(f"Error running visualizer: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0

if __name__ == "__main__":
    sys.exit(main())


