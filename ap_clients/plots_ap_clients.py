import matplotlib.pyplot as plt
import numpy as np
from ap_clients.parse_ap_clients_data import extract_connected_clients, rssi_to_distance  # Assuming you have a parse_clients function

def plot_clients(csv_file):
    clients = extract_connected_clients(csv_file)
    
    # Your position (origin)
    your_x, your_y = 0, 0

    # Canvas setup
    fig, ax = plt.subplots()
    ax.set_aspect('equal')
    ax.set_xlim(-50, 50)
    ax.set_ylim(-50, 50)
    ax.grid(True)
    ax.plot(your_x, your_y, 'ro', markersize=10, label='You')

    # Plot clients
    for mac, power, ap_bssid in clients:
        distance = rssi_to_distance(power)
        theta = np.random.uniform(0, 2*np.pi)
        client_x = your_x + distance * np.cos(theta)
        client_y = your_y + distance * np.sin(theta)
        
        ax.plot(client_x, client_y, 'g^', markersize=8)  # Green triangle for clients
        ax.text(client_x, client_y, 
                f"{mac[-5:]}\n{distance:.1f}m", 
                fontsize=8, 
                ha='center')

    plt.legend()
    plt.title(f"Client Devices around You\n({csv_file})")
    plt.xlabel("X (meters)")
    plt.ylabel("Y (meters)")
    plt.show()

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python plot_clients.py <client_csv_file>")
        sys.exit(1)
    
    plot_clients(sys.argv[1])
