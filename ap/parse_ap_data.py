import sys 
import csv
import numpy as np

def parse_aps(filename):
    aps = []
    with open(filename, 'r') as f:
        reader = csv.reader(f)
        for row in reader:
            # AP rows have >=14 columns, client rows have fewer
            if len(row) >= 14 and row[0].strip() != 'BSSID':
                bssid = row[13].strip()
                rssi = int(row[8].strip())  # <-- FIXED: PWR is column 8
                essid = row[0].strip()
                aps.append((bssid,rssi,essid))
    return aps 

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
    aps = parse_aps(sys.argv[1])
    for ap in aps:
        print(f"AP: {ap[0]} | RSSI: {ap[1]} dBm --> {rssi_to_distance(ap[1]):.1f} <=> X : {rssi_to_xy(ap[1])[0]:.1f} , Y : {rssi_to_xy(ap[1])[1]:.1f} ")
