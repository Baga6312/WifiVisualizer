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
            return 2.4

def adjust_rssi_by_channel(rssi, channel):
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
                    logging.debug(f"Found header line at index {i}")
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
                                logging.debug(f"Added AP: BSSID={bssid}, RSSI={rssi}, ESSID={essid}")
                        except Exception as e:
                            logging.debug(f"Error processing line: {e}")
            else:
                logging.warning("Could not find header line with BSSID")
    except Exception as e:
        logging.error(f"Error reading file: {e}")
    
    unique_aps = {}
    for bssid, rssi, essid, beacons, channel in aps:
        if bssid not in unique_aps or rssi > unique_aps[bssid][0]:
            unique_aps[bssid] = (rssi, essid, beacons, channel)
    
    result = [(bssid, rssi, essid, beacons, channel) for bssid, (rssi, essid, beacons, channel) in unique_aps.items()]
    logging.info(f"✓ Parsed {len(result)} unique APs")
    
    return result

def parse_clients(ap_bssid):
    """Parse client CSV file for a specific AP with detailed logging"""
    clients = []
    client_dir = "scripts/ap_clients"
    
    logging.info(f"🔍 Looking for clients for AP: {ap_bssid}")
    
    if not os.path.exists(client_dir):
        logging.warning(f"❌ Client directory '{client_dir}' does not exist!")
        return clients
    
    # List all files in directory for debugging
    all_files = os.listdir(client_dir)
    logging.debug(f"📂 Files in {client_dir}: {all_files}")
    
    # Try multiple BSSID formats
    bssid_formats = [
        ap_bssid,                          # AA:BB:CC:DD:EE:FF
        ap_bssid.replace(':', ''),         # AABBCCDDEEFF
        ap_bssid.replace(':', '-'),        # AA-BB-CC-DD-EE-FF
        ap_bssid.lower(),                  # aa:bb:cc:dd:ee:ff
        ap_bssid.upper(),                  # AA:BB:CC:DD:EE:FF
    ]
    
    found_file = None
    for filename in all_files:
        if not filename.endswith('_clients.csv'):
            continue
            
        for bssid_format in bssid_formats:
            if bssid_format in filename or bssid_format.replace(':', '') in filename:
                found_file = filename
                break
        if found_file:
            break
    
    if not found_file:
        logging.warning(f"❌ No client file found for AP {ap_bssid}")
        logging.debug(f"   Tried formats: {bssid_formats}")
        return clients
    
    filepath = os.path.join(client_dir, found_file)
    logging.info(f"✓ Found client file: {found_file}")
    
    try:
        with open(filepath, 'r') as f:
            content = f.read()
            
            if not content.strip():
                logging.warning(f"⚠️ Client file is empty: {found_file}")
                return clients
            
            logging.debug(f"📄 File content preview (first 200 chars): {content[:200]}")
            lines = content.split('\n')
            
            # Find "Station MAC" header
            header_line = None
            for i, line in enumerate(lines):
                if "Station MAC" in line:
                    header_line = i
                    logging.info(f"✓ Found 'Station MAC' header at line {i}")
                    break
            
            if header_line is None:
                logging.warning(f"❌ No 'Station MAC' header found in {found_file}")
                return clients
            
            # Parse client lines
            client_count = 0
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
                        
                        # Validate MAC address format
                        if client_mac and ':' in client_mac and len(client_mac) == 17:
                            clients.append((client_mac, client_rssi))
                            client_count += 1
                            logging.debug(f"   ✓ Client #{client_count}: {client_mac} @ {client_rssi} dBm")
                    except Exception as e:
                        logging.debug(f"   ⚠️ Error processing client line: {e}")
    except Exception as e:
        logging.error(f"❌ Error reading client file {found_file}: {e}")
    
    logging.info(f"📊 Total clients found for {ap_bssid}: {len(clients)}")
    return clients

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
        
        # Setup logging
        log_level = logging.DEBUG if os.environ.get('DEBUG') else logging.INFO
        logging.basicConfig(
            level=log_level,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        
        if not self.input_file and not self.use_test_data:
            self.input_file = 'live_aps_aps_only.csv'  
            logging.info(f"Using default AP file: {self.input_file}")
            
            if not os.path.exists(self.input_file):
                logging.warning(f"Default file {self.input_file} not found")
        
        logging.info("=" * 60)
        logging.info("🚀 WiFi Visualizer Started")
        logging.info(f"   AP File: {self.input_file}")
        logging.info(f"   Client Directory: ap_clients/")
        logging.info("=" * 60)
    
    def update_data(self):
        """Update AP data from file"""
        try:
            if not os.path.exists(self.input_file):
                logging.error(f"❌ Input file {self.input_file} does not exist!")
                return
            
            aps = parse_aps(self.input_file)
            
            if not aps:
                logging.warning("⚠️ No APs found in file")
                return
            
            active_bssids = set()
            
            for bssid, rssi, essid, beacons, channel in aps:
                active_bssids.add(bssid)
                
                with self.lock:
                    if self.use_channels:
                        distance = calculate_distance_with_channel(rssi, channel)
                    else:
                        distance = rssi_to_distance(rssi)
                    
                    if bssid not in self.ap_data:
                        # Hash BSSID for consistent angle
                        mac_hash = sum(ord(c) for c in bssid) * 31
                        angle = (mac_hash % 628) / 100.0
                        
                        new_x = distance * np.cos(angle)
                        new_y = distance * np.sin(angle)
                        
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
                        logging.debug(f"📍 New AP: {essid or 'Hidden'} @ ({new_x:.1f}, {new_y:.1f})")
                    else:
                        # Update existing AP
                        self.ap_data[bssid]['rssi'] = rssi
                        self.ap_data[bssid]['beacons'] = beacons
                        self.ap_data[bssid]['essid'] = essid
                        self.ap_data[bssid]['channel'] = channel
                        self.ap_data[bssid]['color'] = get_rssi_color(rssi)
                        self.ap_data[bssid]['distance'] = distance
            
            # Remove stale APs
            with self.lock:
                stale_bssids = set(self.ap_data.keys()) - active_bssids
                for bssid in stale_bssids:
                    self.ap_data.pop(bssid, None)
                    self.ap_history.pop(bssid, None)
            
        except Exception as e:
            logging.error(f"❌ Error updating data: {e}")
            import traceback
            traceback.print_exc()
    
    def get_ap_data(self):
        """Get current AP data with clients"""
        with self.lock:
            data = []
            total_clients = 0
            
            for bssid, ap_info in self.ap_data.items():
                freq = channel_to_frequency(ap_info['channel'])
                freq_band = "2.4GHz" if freq < 5.0 else "5GHz"
                
                # Parse clients for this AP
                clients_list = parse_clients(bssid)
                
                # Calculate client positions
                clients_data = []
                for client_mac, client_rssi in clients_list:
                    client_distance = calculate_distance_with_channel(client_rssi, ap_info['channel'])
                    
                    # Hash client MAC for consistent angle
                    mac_hash = sum(ord(c) for c in client_mac) * 31
                    angle = (mac_hash % 628) / 100.0
                    
                    # Position client relative to AP
                    client_x = ap_info['x'] + client_distance * np.cos(angle) * 0.3
                    client_y = ap_info['y'] + client_distance * np.sin(angle) * 0.3
                    
                    clients_data.append({
                        'mac': client_mac,
                        'rssi': client_rssi,
                        'distance': client_distance,
                        'x': client_x,
                        'y': client_y
                    })
                    total_clients += 1
                
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
                    'clients': clients_data
                })
            
            if total_clients > 0:
                logging.info(f"📡 Returning {len(data)} APs with {total_clients} total clients")
            
            return data

app = Flask(__name__)
wifi_processor = None

def update_thread_function():
    """Background thread to update WiFi data"""
    while True:
        try:
            wifi_processor.update_data()
            time.sleep(2.0)
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

def create_app(input_file=None):
    global wifi_processor
    wifi_processor = WiFiDataProcessor(input_file)
    update_thread = threading.Thread(target=update_thread_function, daemon=True)
    update_thread.start()
    return app

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='WiFi AP Visualizer with Clients')
    parser.add_argument('-i', '--input-file', help='Path to AP CSV file', default='live_aps_aps_only.csv')
    parser.add_argument('-p', '--port', type=int, default=5000, help='Web server port')
    parser.add_argument('-d', '--debug', action='store_true', help='Enable debug mode')
    
    args = parser.parse_args()
    
    if args.debug:
        os.environ['DEBUG'] = '1'
        logging.getLogger().setLevel(logging.DEBUG)
    
    app = create_app(args.input_file)
    
    print("\n" + "=" * 60)
    print("🌐 WiFi Visualizer Server Starting")
    print(f"   URL: http://0.0.0.0:{args.port}")
    print(f"   AP File: {args.input_file}")
    print(f"   Client Directory: ap_clients/")
    print("=" * 60 + "\n")
    
    app.run(host='0.0.0.0', port=args.port, debug=args.debug)
