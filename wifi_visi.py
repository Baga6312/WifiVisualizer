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
                                # Power is typically in field 8 (index 7)
                                power_str = fields[8].strip()
                                
                                # Handle potential errors in integer conversion
                                try:
                                    rssi = int(power_str) if power_str.lstrip('-').isdigit() else -100
                                except ValueError:
                                    debug_print(f"Warning: Could not convert Power to int: '{power_str}' in line: {line}")
                                    rssi = -100  # Default poor signal if can't parse
                                
                                # ESSID is typically in field 13 (index 12)
                                essid = fields[13].strip() if len(fields) > 13 else ""
                                
                                if bssid and bssid != "BSSID":  # Skip if BSSID is empty or header
                                    aps.append((bssid, rssi, essid))
                                    debug_print(f"Added AP: BSSID={bssid}, RSSI={rssi}, ESSID={essid}")
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
                            essid_idx = next((i for i, cell in enumerate(header) if cell and "ESSID" in cell), 13)
                            
                            # Get values
                            if len(row) > max(bssid_idx, power_idx, essid_idx):
                                bssid = row[bssid_idx].strip()
                                power_str = row[power_idx].strip()
                                essid = row[essid_idx].strip() if len(row) > essid_idx else ""
                                
                                try:
                                    rssi = int(power_str) if power_str.lstrip('-').isdigit() else -100
                                except ValueError:
                                    debug_print(f"Warning: Could not convert Power to int: '{power_str}'")
                                    rssi = -100
                                
                                if bssid and bssid != "BSSID":  # Skip if BSSID is empty or header
                                    aps.append((bssid, rssi, essid))
                                    debug_print(f"Added AP: BSSID={bssid}, RSSI={rssi}, ESSID={essid}")
                        except Exception as e:
                            debug_print(f"Error processing row: {e}")
                            debug_print(f"Row data: {row}")
                    else:
                        debug_print("Processing without identified header")
                        # If we can't find a header, try simple format
                        if len(row) >= 3:
                            try:
                                bssid = row[0].strip()
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
                                
                                # Try to find ESSID
                                essid = ""
                                for i, cell in enumerate(row):
                                    if i > 0 and cell.strip() and not cell.strip().startswith('-') and not cell.strip()[0].isdigit():
                                        essid = cell.strip()
                                        break
                                
                                if not essid and len(row) > 13:
                                    essid = row[13].strip()
                                
                                if bssid and bssid != "BSSID":  # Skip if BSSID is empty or header
                                    aps.append((bssid, rssi, essid))
                                    debug_print(f"Added AP (simple format): BSSID={bssid}, RSSI={rssi}, ESSID={essid}")
                            except Exception as e:
                                debug_print(f"Error processing simple format: {e}")
    
    except Exception as e:
        debug_print(f"Error reading file: {e}")
    
    # Remove any duplicate BSSIDs (keep the one with strongest signal)
    unique_aps = {}
    for bssid, rssi, essid in aps:
        if bssid not in unique_aps or rssi > unique_aps[bssid][0]:
            unique_aps[bssid] = (rssi, essid)
    
    result = [(bssid, rssi, essid) for bssid, (rssi, essid) in unique_aps.items()]
    debug_print(f"Returned {len(result)} unique APs")
    
    return result

def rssi_to_distance(rssi, measured_power=-30, path_loss_exponent=3.5):
    """Convert RSSI to estimated distance in meters"""
    return 10 ** ((measured_power - rssi) / (10 * path_loss_exponent))

def rssi_to_xy(rssi, measured_power=-30, path_loss_exponent=3.5):
    """Convert RSSI to X,Y coordinates with random radial distribution"""
    distance = rssi_to_distance(rssi, measured_power, path_loss_exponent)
    theta = np.random.uniform(0, 2 * np.pi)  # Random angle
    return (
        distance * np.cos(theta),  # X
        distance * np.sin(theta)   # Y
    )

class WiFiVisualizer:
    def __init__(self, input_file, update_interval=1.0):
        self.input_file = input_file
        self.update_interval = update_interval
        
        # Position update settings
        self.position_update_factor = 0.3  # How much to update position (0.0-1.0)
        self.rssi_change_threshold = 2     # Minimum RSSI change to update position
        
        # Store AP data with bssid as key
        self.ap_data = defaultdict(dict)
        
        # Test if we can read data initially
        debug_print(f"Testing initial data read from {input_file}")
        initial_aps = parse_aps(input_file)
        debug_print(f"Initial read found {len(initial_aps)} APs")
        
        if len(initial_aps) == 0:
            debug_print("WARNING: No APs found in the initial read")
            debug_print("You may need to check your file format or try the test data option")
        
        # Create a figure and axis for plotting
        self.fig, self.ax = plt.subplots(figsize=(10, 8))
        try:
            self.fig.canvas.manager.set_window_title('WiFi Access Point Visualizer')
        except Exception as e:
            debug_print(f"Window title setting error (non-critical): {e}")
        
        # Add observer (you) at center
        self.ax.plot(0, 0, 'ko', markersize=10)
        self.ax.text(0, 0, "YOU", fontsize=12, ha='center', va='bottom', color='black')
        
        # Setup the plot
        self.setup_plot()
        
        # Add keyboard event handling for adjusting position_update_factor
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
            self.position_update_factor = max(0.0, self.position_update_factor - 0.1)
            debug_print(f"Decreased position update factor to {self.position_update_factor:.1f}")
        elif event.key == '[':
            # Decrease RSSI change threshold
            self.rssi_change_threshold = max(0, self.rssi_change_threshold - 1)
            debug_print(f"Decreased RSSI change threshold to {self.rssi_change_threshold}")
        elif event.key == ']':
            # Increase RSSI change threshold
            self.rssi_change_threshold = self.rssi_change_threshold + 1
            debug_print(f"Increased RSSI change threshold to {self.rssi_change_threshold}")
        elif event.key == 'r':
            # Reset all AP positions
            debug_print("Resetting all AP positions")
            self.ap_data.clear()

    
    def setup_plot(self):
        """Initialize the plot appearance"""
        self.ax.set_xlim(-30, 30)
        self.ax.set_ylim(-30, 30)
        self.ax.set_xlabel('X Distance (m)')
        self.ax.set_ylabel('Y Distance (m)')
        self.ax.set_title('WiFi Access Points Real-time Visualization')
        self.ax.grid(True)
        
        # Add range circles
        for radius in [5, 10, 20]:
            circle = Circle((0, 0), radius, fill=False, linestyle='--', alpha=0.3)
            self.ax.add_patch(circle)
            self.ax.text(radius, 0, f"{radius}m", fontsize=8, ha='left', va='bottom')
        
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
    
    def update(self, frame):
        """Update the plot with new data"""
        try:
            debug_print(f"Update at frame {frame}: Reading data from {self.input_file}")
            aps = parse_aps(self.input_file)
            debug_print(f"Found {len(aps)} APs in this update")
            
            # If no APs found, try to generate test data
            if len(aps) == 0 and hasattr(self, 'use_test_data') and self.use_test_data:
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
            self.ax.plot(0, 0, 'ko', markersize=10)
            self.ax.text(0, 0, "YOU", fontsize=12, ha='center', va='bottom', color='black')
            
            # Position update smoothing factor (0.0 = no update, 1.0 = full update)
            # This controls how much the position changes based on new RSSI
            position_update_factor = self.position_update_factor
            
            for i, (bssid, rssi, essid) in enumerate(aps):
                debug_print(f"Processing AP {i+1}/{len(aps)}: BSSID={bssid}, RSSI={rssi}, ESSID={essid}")
                
                # Calculate new position based on current RSSI
                new_x, new_y = rssi_to_xy(rssi)
                
                # Store current position or generate new one
                if bssid not in self.ap_data:
                    # First time seeing this AP - use the calculated position
                    self.ap_data[bssid] = {
                        'x': new_x, 
                        'y': new_y, 
                        'rssi': rssi, 
                        'essid': essid,
                        'prev_rssi': rssi
                    }
                    debug_print(f"New AP positioned at ({new_x:.1f}, {new_y:.1f})")
                else:
                    # Calculate smoothed position update based on RSSI change
                    old_x = self.ap_data[bssid]['x']
                    old_y = self.ap_data[bssid]['y']
                    prev_rssi = self.ap_data[bssid]['prev_rssi']
                    
                    # Only update position if RSSI changed significantly (e.g., 2dBm or more)
                    rssi_change = abs(rssi - prev_rssi)
                    if rssi_change >= self.rssi_change_threshold:
                        # Apply smoothing to position update
                        updated_x = old_x * (1 - position_update_factor) + new_x * position_update_factor
                        updated_y = old_y * (1 - position_update_factor) + new_y * position_update_factor
                        
                        debug_print(f"Updating position from ({old_x:.1f}, {old_y:.1f}) to ({updated_x:.1f}, {updated_y:.1f}) - RSSI change: {rssi_change}")
                        
                        self.ap_data[bssid]['x'] = updated_x
                        self.ap_data[bssid]['y'] = updated_y
                    else:
                        debug_print(f"RSSI change too small ({rssi_change}), keeping position: ({old_x:.1f}, {old_y:.1f})")
                    
                    # Update stored RSSI and essid
                    self.ap_data[bssid]['prev_rssi'] = self.ap_data[bssid]['rssi']  # Store previous RSSI
                    self.ap_data[bssid]['rssi'] = rssi
                    self.ap_data[bssid]['essid'] = essid
                
                # Get current position for display
                x = self.ap_data[bssid]['x']
                y = self.ap_data[bssid]['y']
                color = get_rssi_color(rssi)
                
                # Plot the AP
                distance = np.sqrt(x**2 + y**2)
                self.ax.plot(x, y, 'o', color=color, markersize=8, alpha=0.7)
                
                # Add text label
                if essid:
                    label = f"{essid}\n{bssid}\n{rssi} dBm"
                else:
                    label = f"{bssid}\n{rssi} dBm"
                self.ax.text(x, y, label, fontsize=8, ha='center', va='bottom')
                
                # Draw line from center to AP
                self.ax.plot([0, x], [0, y], '--', color=color, alpha=0.3)
            
            # Add timestamp
            self.ax.text(0.02, 0.98, f"Last updated: {time.strftime('%H:%M:%S')}", 
                      transform=self.ax.transAxes, ha='left', va='top')
            
            # Add position update factor info
            self.ax.text(0.02, 0.94, f"Position Update: {position_update_factor:.2f} (Keys: + / -)", 
                      transform=self.ax.transAxes, ha='left', va='top', fontsize=8)
            self.ax.text(0.02, 0.91, f"RSSI Change Threshold: {self.rssi_change_threshold} dBm (Keys: [ / ])", 
                      transform=self.ax.transAxes, ha='left', va='top', fontsize=8)
            
            # Update the plot title with count of APs
            self.ax.set_title(f'WiFi Access Points Real-time Visualization ({len(aps)} APs)')
            
            # Redraw
            self.fig.canvas.draw_idle()
            debug_print(f"Plot updated with {len(aps)} APs")
            
        except Exception as e:
            import traceback
            debug_print(f"Error updating plot: {e}")
            debug_print(traceback.format_exc())
            
    def generate_test_data(self):
        """Generate fake test data for demonstration"""
        debug_print("Generating test data")
        test_aps = [
            ("00:11:22:33:44:55", -65, "TestWiFi-1"),
            ("AA:BB:CC:DD:EE:FF", -75, "TestWiFi-2"),
            ("11:22:33:44:55:66", -55, "TestWiFi-3"),
            ("AA:BB:CC:11:22:33", -85, "TestWiFi-4"),
            ("FF:EE:DD:CC:BB:AA", -45, "TestWiFi-5")
        ]
        
        # Add some randomness to RSSI to simulate changes
        result = []
        for bssid, rssi, essid in test_aps:
            new_rssi = rssi + np.random.randint(-3, 4)  # Add random variation
            result.append((bssid, new_rssi, essid))
        
        return result
    
    def show(self):
        """Show the plot window"""
        plt.tight_layout()
        plt.show()

def create_sample_input_file(filename, content=None):
    """Create a sample input file with the provided content or default test content"""
    try:
        with open(filename, 'w') as f:
            if content:
                f.write(content)
            else:
                # Create a default airodump-ng style output
                f.write("""BSSID, First time seen, Last time seen, channel, Speed, Privacy, Cipher, Authentication, Power, # beacons, # IV, LAN IP, ID-length, ESSID, Key
84:D1:5A:40:CD:1D, 2025-04-30 01:04:35, 2025-04-30 01:16:44,  1, 130, WPA2, CCMP TKIP, PSK, -44,      360,       13,   0.  0.  0.  0,  11, Flybox_CD1D, 
A2:A7:3D:F9:80:76, 2025-04-30 01:04:37, 2025-04-30 01:16:43, 11, 180, WPA2, CCMP, PSK, -32,      484,    31915,   0.  0.  0.  0,  11, selmi firas, 
46:F7:CC:DB:2E:59, 2025-04-30 01:04:38, 2025-04-30 01:16:43,  6, 180, WPA2, CCMP, PSK, -42,      290,        0,   0.  0.  0.  0,  11, POCO M4 Pro, 
84:9F:B5:C5:B8:7C, 2025-04-30 01:05:27, 2025-04-30 01:16:44,  1, 130, WPA2, CCMP, PSK, -66,       75,        0,   0.  0.  0.  0,  12, Ooredoo-B87C, 
7C:B2:7D:19:75:F3, 2025-04-30 01:07:58, 2025-04-30 01:10:05, 11,  -1, OPN, ,   ,  -1,        0,       23,   0.  0.  0.  0,   0, , 
Station MAC, First time seen, Last time seen, Power, # packets, BSSID, Probed ESSIDs
5C:61:99:03:68:95, 2025-04-30 01:04:37, 2025-04-30 01:16:43, -24,     4881, A2:A7:3D:F9:80:76,selmi firas
F0:A6:54:DE:CD:C9, 2025-04-30 01:04:37, 2025-04-30 01:16:45, -36,     1578, A2:A7:3D:F9:80:76,selmi firas
""")
        debug_print(f"Created sample input file: {filename}")
    except Exception as e:
        debug_print(f"Error creating sample input file: {e}")

def main():
    if len(sys.argv) < 2:
        print("Usage: python wifi_visualizer.py <input_csv_file> [update_interval] [--test] [--create-sample]")
        print("Options:")
        print("  <input_csv_file>   CSV file with WiFi scan data")
        print("  [update_interval]  Update interval in seconds (default: 1.0)")
        print("  [--test]           Use test data if no APs detected")
        print("  [--create-sample]  Create a sample input file if it doesn't exist")
        print("")
        print("Example file format expected (airodump-ng output):")
        print("BSSID, First time seen, Last time seen, channel, Speed, Privacy, Cipher, Authentication, Power, # beacons, # IV, LAN IP, ID-length, ESSID, Key")
        print("00:11:22:33:44:55, 2023-01-01 12:00:00, 2023-01-01 12:05:00, 1, 130, WPA2, CCMP, PSK, -65, 30, 0, 0.0.0.0, 7, TestWiFi,")
        sys.exit(1)
    
    input_file = sys.argv[1]
    update_interval = 1.0  # default update interval in seconds
    use_test_data = False
    create_sample = False
    
    # Parse additional arguments
    for i in range(2, len(sys.argv)):
        arg = sys.argv[i]
        if arg == "--test":
            use_test_data = True
            print("Test data mode enabled - will generate sample data if no APs found")
        elif arg == "--create-sample":
            create_sample = True
            print(f"Will create sample input file {input_file} if it doesn't exist")
        elif arg.startswith("--"):
            print(f"Unknown option: {arg}")
        else:
            try:
                update_interval = float(arg)
                print(f"Update interval set to {update_interval} seconds")
            except ValueError:
                print(f"Invalid update interval: {arg}. Using default 1.0 seconds.")
    
    # Create sample file if requested and file doesn't exist
    if not os.path.exists(input_file) and create_sample:
        print(f"File {input_file} not found, creating sample file")
        create_sample_input_file(input_file)
    
    try:
        visualizer = WiFiVisualizer(input_file, update_interval)
        if use_test_data:
            visualizer.use_test_data = True
        visualizer.show()
    except Exception as e:
        import traceback
        print(f"Error starting visualizer: {e}")
        print(traceback.format_exc())

if __name__ == "__main__":
    main()
