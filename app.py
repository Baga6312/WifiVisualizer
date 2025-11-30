#!/usr/bin/env python3
import os
import json
import time
import math
import numpy as np
from flask import Flask, render_template, jsonify, request
from collections import defaultdict
import threading
import logging

def rssi_to_distance(rssi, measured_power=-30, path_loss_exponent=3.0):
    if rssi >= measured_power:
        return 1.0  
    
    return 10 ** ((measured_power - rssi) / (10 * path_loss_exponent))

def channel_to_frequency(channel):
    if channel <= 0:
        return 2.4  
    
    if 1 <= channel <= 14:
        if channel == 14:  
            return 2.484
        else:
            return 2.407 + 0.005 * channel
    elif 32 <= channel <= 68:  
        return 5.16 + 0.005 * (channel - 32)
    elif 96 <= channel <= 144:  
        return 5.49 + 0.005 * (channel - 96)
    elif 149 <= channel <= 177:  
        return 5.735 + 0.005 * (channel - 149)
    else:
        if 15 <= channel <= 31:
            return 2.4  
        elif channel >= 32:
            return 5.0 + (channel - 32) * 0.005  
        else:
            return 2.4  # Default

def adjust_rssi_by_channel(rssi, channel):
    """
    Adjust RSSI based on channel frequency with improved accuracy
    Higher frequencies (5GHz) attenuate more than 2.4GHz
    """
    freq = channel_to_frequency(channel)
    
    if freq >= 5.7:  
        return rssi + 8
    elif freq >= 5.4:  
        return rssi + 7
    elif freq >= 5.15:  
        return rssi + 6
    elif freq > 2.45:  
        return rssi + 1
    elif freq < 2.425:   
        return rssi - 1
    else:
        return rssi

def calculate_distance_with_channel(rssi, channel):
    adjusted_rssi = adjust_rssi_by_channel(rssi, channel)
    
    freq = channel_to_frequency(channel)
    
    if freq >= 5.7:  
        path_loss = 3.6 
    elif freq >= 5.15:  
        path_loss = 3.5 
    elif freq > 2.45:  
        path_loss = 3.1 
    elif freq < 2.425:  
        path_loss = 2.9 
    else:   
        path_loss = 3.0 
        
    if freq >= 5.15:
        measured_power = -32  
    else:
        measured_power = -30  
        
    return rssi_to_distance(adjusted_rssi, measured_power=measured_power, path_loss_exponent=path_loss)

def beacons_to_distance(beacon_count, max_beacons=1000, min_beacons=10):
    if beacon_count <= 0:
        return 50  
    
    normalized_beacons = min(max_beacons, max(min_beacons, beacon_count))
    log_scale = math.log(normalized_beacons) / math.log(max_beacons)
    
    return max(1, 40 * (1 - log_scale ** 0.7))

def calculate_xy_position(distance, angle=None):
    if angle is None:
        angle = np.random.uniform(0, 2 * np.pi)  
    return (
        distance * np.cos(angle),  
        distance * np.sin(angle)   
    )

def get_rssi_color(rssi):
    if rssi >= -50:  
        return 'green'
    elif rssi >= -65:  
        return 'blue'
    elif rssi >= -75:
        return 'orange'
    else:  
        return 'red'

def parse_aps(filename):
    aps = []
    try:
        with open(filename, 'r') as f:
            content = f.read()
            
            lines = content.split('\n')
            header_line = None
            
            for i, line in enumerate(lines):
                if "BSSID" in line and "Power" in line:
                    header_line = i
                    logging.debug(f"Found header line at index {i}: {line}")
                    break
            
            if header_line is not None:
                for line_index in range(header_line + 1, len(lines)):
                    line = lines[line_index].strip()
                    if not line or line.startswith("Station MAC"):  
                        break
                        
                    fields = [field.strip() for field in line.split(',')]
                    
                    if len(fields) >= 9:  
                        try:
                            bssid = fields[0].strip()
                            
                            channel_str = fields[3].strip() if len(fields) > 3 else "0"
                            try:
                                channel = int(channel_str) if channel_str.isdigit() else 0
                            except ValueError:
                                channel = 0
                            
                            power_str = fields[8].strip()
                            
                            try:
                                rssi = int(power_str) if power_str.lstrip('-').isdigit() else -100
                            except ValueError:
                                rssi = -100  
                            
                            beacon_str = fields[9].strip() if len(fields) > 9 else "0"
                            try:
                                beacons = int(beacon_str) if beacon_str.isdigit() else 0
                            except ValueError:
                                beacons = 0
                            
                            essid = fields[13].strip() if len(fields) > 13 else ""
                            
                            if bssid and bssid != "BSSID":  
                                aps.append((bssid, rssi, essid, beacons, channel))
                                logging.debug(f"Added AP: BSSID={bssid}, RSSI={rssi}, ESSID={essid}, Beacons={beacons}, Channel={channel}")
                        except Exception as e:
                            logging.debug(f"Error processing line: {e}")
            else:
                logging.debug("Could not find header line with BSSID")
    except Exception as e:
        logging.error(f"Error reading file: {e}")
    
    unique_aps = {}
    for bssid, rssi, essid, beacons, channel in aps:
        if bssid not in unique_aps or rssi > unique_aps[bssid][0]:
            unique_aps[bssid] = (rssi, essid, beacons, channel)
    
    result = [(bssid, rssi, essid, beacons, channel) for bssid, (rssi, essid, beacons, channel) in unique_aps.items()]
    logging.debug(f"Returned {len(result)} unique APs")
    
    if not result:
        logging.error(f"No APs found in file: {filename}")
    
    return result



def parse_clients(ap_bssid):
    """Parse client CSV file for a specific AP"""
    clients = []

    # Look for client CSV file for this AP
    client_dir = "ap_clients"
    if not os.path.exists(client_dir):
        return clients

    # Find client file for this AP (matches any filename with the BSSID)
    for filename in os.listdir(client_dir):
        if filename.startswith(ap_bssid.replace(':', '')) or filename.startswith(ap_bssid):
            filepath = os.path.join(client_dir, filename)

            try:
                with open(filepath, 'r') as f:
                    content = f.read()
                    lines = content.split('\n')

                    # Find "Station MAC" header
                    header_line = None
                    for i, line in enumerate(lines):
                        if "Station MAC" in line:
                            header_line = i
                            break

                    if header_line is not None:
                        # Parse client lines
                        for line_index in range(header_line + 1, len(lines)):
                            line = lines[line_index].strip()
                            if not line:
                                break

                            fields = [field.strip() for field in line.split(',')]

                            if len(fields) >= 4:
                                try:
                                    client_mac = fields[0].strip()
                                    power_str = fields[3].strip()

                                    try:
                                        client_rssi = int(power_str) if power_str.lstrip('-').isdigit() else -100
                                    except ValueError:
                                        client_rssi = -100

                                    if client_mac and client_mac != "Station MAC":
                                        clients.append((client_mac, client_rssi))
                                except Exception as e:
                                    logging.debug(f"Error processing client line: {e}")
            except Exception as e:
                logging.error(f"Error reading client file: {e}")

            break  # Found the file, no need to continue

    return clients





def generate_test_data(num_aps=5):
    """Generate test data for demonstration when no real data is available"""
    aps = []
    essids = ["HomeWiFi", "Office_Network", "Guest5G", "IoT_Network", "SecurityCam", 
             "Neighbor1", "Neighbor2", "CoffeeShop", "FreeWiFi", "Hidden"]
    
    for i in range(num_aps):
        mac_parts = [format(np.random.randint(0, 255), '02x') for _ in range(6)]
        bssid = ':'.join(mac_parts).upper()
        
        rssi = -30 - np.random.randint(0, 60)
        
        essid = essids[i % len(essids)]
        if i >= len(essids):
            essid += "_" + str(i // len(essids))
            
        beacons = np.random.randint(10, 1000)
        
        if np.random.random() < 0.6:  
            channel = np.random.randint(1, 14)
        else:  
            channels_5g = [36, 40, 44, 48, 52, 56, 60, 64, 100, 104, 108, 112, 116, 
                          120, 124, 128, 132, 136, 140, 144, 149, 153, 157, 161, 165]
            channel = channels_5g[np.random.randint(0, len(channels_5g))]
        
        aps.append((bssid, rssi, essid, beacons, channel))
    
    return aps

class WiFiDataProcessor:
    def __init__(self, input_file=None, use_test_data=False, use_beacons=False, use_channels=True):
        self.input_file = input_file
        self.use_test_data = use_test_data
        self.use_beacons = use_beacons
        self.use_channels = use_channels
        self.position_update_factor = 0.8
        self.rssi_change_threshold = 1
        self.beacon_change_threshold = 3
        self.ap_data = defaultdict(dict)
        self.history_len = 3
        self.ap_history = defaultdict(lambda: {'rssi': [], 'beacons': []})
        self.lock = threading.Lock()  
        
        logging.basicConfig(level=logging.DEBUG if os.environ.get('DEBUG') else logging.INFO,
                           format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        
        if not self.input_file and not self.use_test_data:
            self.input_file = 'live_clients-01.csv'  
            logging.info(f"No input file specified, using default: {self.input_file}")
            
            if not os.path.exists(self.input_file):
                logging.warning(f"Default file {self.input_file} not found. Create a minimal file.")
                with open(self.input_file, 'w') as f:
                    f.write("BSSID, First time seen, Last time seen, Channel, Speed, Privacy, Cipher, Authentication, Power, # beacons, # IV, LAN IP, ID-length, ESSID, Key\n")
        
    def detect_trend(self, history):
        """Detect if a value is trending up, down, or stable based on history"""
        if len(history) < 2:
            return 'stable'
        
        diffs = [history[i] - history[i-1] for i in range(1, len(history))]
        
        increasing = sum(1 for d in diffs if d > 0)
        decreasing = sum(1 for d in diffs if d < 0)
        
        if increasing > decreasing and increasing >= len(diffs) / 2:
            return 'increasing'
        elif decreasing > increasing and decreasing >= len(diffs) / 2:
            return 'decreasing'
        else:
            return 'stable'
    
    def update_data(self):
        """Update AP data from file or generate test data"""
        try:
            if self.use_test_data:
                aps = generate_test_data(num_aps=8)
                logging.debug("Generated test data")
            else:
                if not os.path.exists(self.input_file):
                    logging.error(f"Input file {self.input_file} does not exist!")
                    aps = generate_test_data(num_aps=8)
                    logging.debug("Input file not found, using generated test data")
                else:
                    aps = parse_aps(self.input_file)
                    logging.debug(f"Read {len(aps)} APs from {self.input_file}")
                    
                    if not aps:
                        aps = generate_test_data(num_aps=8)
                        logging.debug("No APs found in file, using generated test data")
            
            active_bssids = set()
            
            for bssid, rssi, essid, beacons, channel in aps:
                active_bssids.add(bssid)
                
                with self.lock:  
                    if len(self.ap_history[bssid]['rssi']) >= self.history_len:
                        self.ap_history[bssid]['rssi'].pop(0)
                        self.ap_history[bssid]['beacons'].pop(0)
                    self.ap_history[bssid]['rssi'].append(rssi)
                    self.ap_history[bssid]['beacons'].append(beacons)
                    
                    rssi_trend = self.detect_trend(self.ap_history[bssid]['rssi'])
                    beacon_trend = self.detect_trend(self.ap_history[bssid]['beacons'])
                    
                    if self.use_beacons:
                        distance = beacons_to_distance(beacons)
                    else:
                        if self.use_channels:
                            distance = calculate_distance_with_channel(rssi, channel)
                        else:
                            distance = rssi_to_distance(rssi)
                    
                    if bssid not in self.ap_data:
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
                            'last_update': time.time(),
                            'color': get_rssi_color(rssi),
                            'distance': distance
                        }
                    else:
                        ap_info = self.ap_data[bssid]
                        old_x, old_y = ap_info['x'], ap_info['y']
                        old_rssi = ap_info['rssi']
                        old_beacons = ap_info['beacons']
                        
                        should_update = False
                        
                        if self.use_beacons:
                            beacon_diff = abs(beacons - old_beacons)
                            if beacon_diff >= self.beacon_change_threshold:
                                should_update = True
                        else:
                            rssi_diff = abs(rssi - old_rssi)
                            if rssi_diff >= self.rssi_change_threshold:
                                should_update = True
                        
                        if should_update:
                            angle = ap_info['angle']
                            new_x, new_y = calculate_xy_position(distance, angle)
                            
                            weight = self.position_update_factor
                            
                            if self.use_beacons:
                                if beacon_trend == 'increasing' and beacons > old_beacons:
                                    weight = min(1.0, weight * 1.2)
                                elif beacon_trend == 'decreasing' and beacons < old_beacons:
                                    weight = min(1.0, weight * 1.2)
                            else:
                                if rssi_trend == 'increasing' and rssi > old_rssi:
                                    weight = min(1.0, weight * 1.2)
                                elif rssi_trend == 'decreasing' and rssi < old_rssi:
                                    weight = min(1.0, weight * 1.2)
                            
                            weighted_x = old_x * (1 - weight) + new_x * weight
                            weighted_y = old_y * (1 - weight) + new_y * weight
                            
                            self.ap_data[bssid]['x'] = weighted_x
                            self.ap_data[bssid]['y'] = weighted_y
                            self.ap_data[bssid]['last_update'] = time.time()
                        
                        self.ap_data[bssid]['rssi'] = rssi
                        self.ap_data[bssid]['beacons'] = beacons
                        self.ap_data[bssid]['essid'] = essid
                        self.ap_data[bssid]['channel'] = channel
                        self.ap_data[bssid]['color'] = get_rssi_color(rssi)
                        self.ap_data[bssid]['distance'] = distance
            
            with self.lock:
                stale_bssids = set(self.ap_data.keys()) - active_bssids
                for bssid in stale_bssids:
                    self.ap_data.pop(bssid, None)
                    self.ap_history.pop(bssid, None)
            
        except Exception as e:
            logging.error(f"Error updating data: {e}")
            import traceback
            traceback.print_exc()
    
    def get_ap_data(self):
        with self.lock:
             data = []
             for bssid, ap_info in self.ap_data.items():
                 freq = channel_to_frequency(ap_info['channel'])
                 freq_band = "2.4GHz" if freq < 5.0 else "5GHz"

                 # Parse clients for this AP
                 clients_list = parse_clients(bssid)

                 # Calculate client positions relative to AP
                 clients_data = []
                 for client_mac, client_rssi in clients_list:
                     # Calculate client distance from AP
                     client_distance = calculate_distance_with_channel(client_rssi, ap_info['channel'])

                     # Generate consistent angle based on client MAC hash
                     mac_hash = sum(ord(c) for c in client_mac) * 31
                     angle = (mac_hash % 628) / 100.0  # 0 to 2π

                     # Calculate client position relative to AP
                     # Client is positioned around the AP
                     client_x = ap_info['x'] + client_distance * np.cos(angle) * 0.3
                     client_y = ap_info['y'] + client_distance * np.sin(angle) * 0.3

                     clients_data.append({
                         'mac': client_mac,
                         'rssi': client_rssi,
                         'distance': client_distance,
                         'x': client_x,
                         'y': client_y
                     })

                 data.append({
                     'bssid': bssid,
                     'essid': ap_info['essid'] if ap_info['essid'] else "Hidden Network",
                     'x': ap_info['x'],
                     'y': ap_info['y'],
                     'rssi': ap_info['rssi'],
                     'channel': ap_info['channel'],
                     'color': ap_info['color'],
                     'beacons': ap_info['beacons'],
                     'distance': ap_info['distance'],
                     'freq_band': freq_band,
                     'clients': clients_data  # Add clients to AP data
                 })
             return data
    
    def set_options(self, options):
        """Update processor options from frontend"""
        with self.lock:
            if 'use_beacons' in options:
                self.use_beacons = options['use_beacons']
            if 'use_channels' in options:
                self.use_channels = options['use_channels']
            if 'position_update_factor' in options:
                self.position_update_factor = options['position_update_factor']
            if 'rssi_change_threshold' in options:
                self.rssi_change_threshold = options['rssi_change_threshold']
            if 'beacon_change_threshold' in options:
                self.beacon_change_threshold = options['beacon_change_threshold']
        
        return self.get_options()
    
    def get_options(self):
        """Get current processor options"""
        with self.lock:
            return {
                'use_beacons': self.use_beacons,
                'use_channels': self.use_channels,
                'position_update_factor': self.position_update_factor,
                'rssi_change_threshold': self.rssi_change_threshold,
                'beacon_change_threshold': self.beacon_change_threshold
            }

app = Flask(__name__)

wifi_processor = None

def update_thread_function():
    """Function to periodically update WiFi data"""
    while True:
        try:
            wifi_processor.update_data()
            time.sleep(1.0)  
        except Exception as e:
            logging.error(f"Error in update thread: {e}")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/data')
def get_data():
    try:
        data = wifi_processor.get_ap_data()
        return jsonify(data)
    except Exception as e:
        logging.error(f"Error getting data: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/options', methods=['GET', 'POST'])
def handle_options():
    try:
        if request.method == 'POST':
            options = request.json
            return jsonify(wifi_processor.set_options(options))
        else:
            return jsonify(wifi_processor.get_options())
    except Exception as e:
        logging.error(f"Error handling options: {e}")
        return jsonify({'error': str(e)}), 500

def create_app(input_file=None, use_test_data=False):
    global wifi_processor
    
    wifi_processor = WiFiDataProcessor(input_file, use_test_data)
    
    update_thread = threading.Thread(target=update_thread_function, daemon=True)
    update_thread.start()
    
    return app

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='WiFi AP Visualizer Web Server')
    parser.add_argument('-i', '--input-file', help='Path to airodump-ng CSV file')
    parser.add_argument('-t', '--test', action='store_true', help='Use test data')
    parser.add_argument('-p', '--port', type=int, default=5000, help='Web server port')
    parser.add_argument('-d', '--debug', action='store_true', help='Enable debug mode')
    
    args = parser.parse_args()
    
    if args.debug:
        os.environ['DEBUG'] = '1'
        logging.getLogger().setLevel(logging.DEBUG)
    
    app = create_app(args.input_file, args.test)
    
    host = '0.0.0.0'
    port = args.port
    
    print(f"WiFi Visualizer running at http://{host}:{port}")
    print(f"Access from other devices using your computer's IP address")
    
    app.run(host=host, port=port, debug=args.debug)
