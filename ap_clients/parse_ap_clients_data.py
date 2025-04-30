#!/usr/bin/env python3
import sys 
import csv
import argparse
import numpy as np 

def extract_connected_clients(filename):

    clients = []
    in_client_section = False
    
    with open(filename, 'r') as f:
        reader = csv.reader(f)
        for row in reader:
            # Detect client section header
            if len(row) > 0 and "Station MAC" in row[0]:
                in_client_section = True
                continue  # Skip header row
                
            if in_client_section and len(row) >= 6:
                # Extract client data
                client_mac = row[0].strip()
                ap_bssid = row[5].strip()
                
                # Skip non-associated clients
                if ap_bssid == "(not associated)":
                    continue
                    
                try:
                    power = int(row[3].strip())
                    packets = int(row[4].strip())
                    clients.append( (client_mac, power, ap_bssid) )
                except (ValueError, IndexError):
                    continue
                    
    return clients













def rssi_to_distance(rssi, measured_power=-30, path_loss_exponent=3.5):
    # measured_power: RSSI at 1 meter (calibrate for your environment)
    return 10 ** ((measured_power - rssi) / (10 * path_loss_exponent))

def rssi_to_xy(rssi, measured_power=-30, path_loss_exponent=3.5):
    """Convert RSSI to X,Y coordinates with random radial distribution"""

    distance = rssi_to_distance(rssi, measured_power, path_loss_exponent)
    theta = np.random.uniform(0, 2 * np.pi)  # Random angle
    return (
        distance * np.cos(theta),  # X
        distance * np.sin(theta)   # Y
    )

if __name__ == "__main__":
    aps = extract_connected_clients(sys.argv[1])
    for ap in aps:
        print(f"AP: {ap[0]} | RSSI: {ap[1]} dBm --> {rssi_to_distance(ap[1]):.1f} <=> X : {rssi_to_xy(ap[1])[0]:.1f} , Y : {rssi_to_xy(ap[1])[1]:.1f} ")
