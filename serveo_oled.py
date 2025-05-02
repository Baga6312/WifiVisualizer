import subprocess
import requests
import re
import time
from luma.core.interface.serial import i2c
from luma.oled.device import ssd1306
from luma.core.render import canvas

# OLED Setup
serial = i2c(port=1, address=0x3C)
device = ssd1306(serial, width=128, height=32)

# PXL.to Configuration
PXLT_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJqdGkiOiJ5QWFoVmxQQS1FUEdNcWVUNmFZUlMiLCJpYXQiOjE3NDYxODY1NjEuODUyLCJsaW1pdCI6NTAwLCJ0aW1lZnJhbWUiOjg2NDAwLCJvcmdhbmlzYXRpb24iOiIxN2JiYmEwOC1kYWJiLTQ0YTMtYWFjOC1jNTk5NmZlOTQ4YmEiLCJ3b3Jrc3BhY2UiOjM3NDg1LCJ1c2VyIjoxOTg0MywiZXhwIjoxNzUzOTYyNTU1fQ.Q9ZVkdIrjJxRx-oIisDKGt7qGGH6Zm45QcHaz7VyD8k"
HEADERS = {
    "Accept-Encoding": "gzip",
    "Content-Type": "application/json",
    "Authorization": f"Bearer {PXLT_TOKEN}"
}

def shorten_url(long_url):
    try:
        print(f"Attempting to shorten URL: {long_url}")
        response = requests.post(
            "https://api.pxl.to/api/v1/short",
            headers=HEADERS,
            json={"destination": long_url}
        )
        response.raise_for_status()
        
        # Print full response for debugging
        print(f"API Response: {response.text}")
        
        # Extract short URL from response
        result = response.json()
        
        # Print the JSON structure to help debug
        print(f"Response JSON structure: {result}")
        
        # Based on the response structure we got: {"data":{"id":"pxl.to/1falt91",...}}
        if 'data' in result and 'id' in result['data']:
            # The 'id' field contains the shortened URL in format 'pxl.to/1falt91'
            short_id = result['data']['id']
            # Make it a full URL
            if not short_id.startswith('http'):
                short_id = f"https://{short_id}"
            return short_id
        else:
            print("Could not find shortened URL in the expected format")
            return None
    except Exception as e:
        print(f"API Error: {str(e)}")
        print(f"Full Response: {response.text if 'response' in locals() else 'No response'}")
        return None

def display_on_oled(title, url):
    try:
        print(f"Displaying on OLED: {title} - {url}")
        
        # Make sure url is a string
        if not isinstance(url, str):
            url = str(url)
            
        with canvas(device) as draw:
            draw.text((0, 0), title, fill="white")
            display_text = url.replace("https://", "").replace("http://", "")
            draw.text((0, 16), display_text[:20], fill="white")
        print("Successfully displayed on OLED")
    except Exception as e:
        print(f"Error displaying on OLED: {str(e)}")

def run_serveo():
    try:
        print("Starting Serveo tunnel...")
        proc = subprocess.Popen(
            ["ssh", "-o", "StrictHostKeyChecking=no", "-R", "80:localhost:4444", "serveo.net"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )
        
        serveo_url = None
        for line in iter(proc.stdout.readline, ''):
            print(f"Serveo output: {line.strip()}")
            if "Forwarding" in line:
                match = re.search(r'(https?://\S+\.serveo\.net)', line)
                if match:
                    serveo_url = match.group(1)
                    print(f"Found Serveo URL: {serveo_url}")
                    break
        
        if serveo_url:
            # Try to shorten the URL
            print("Attempting to shorten the URL...")
            short_url = shorten_url(serveo_url)
            
            if short_url:
                print(f"Shortened URL: {short_url}")
                # Display the shortened URL on the OLED
                display_on_oled("Public URL:", short_url)
            else:
                # Fallback to Serveo URL
                print("URL shortening failed, using Serveo URL")
                display_on_oled("Serveo URL:", serveo_url)
            
            # Keep the process running
            print("Tunnel active. Press Ctrl+C to stop.")
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                print("Received keyboard interrupt, shutting down...")
        else:
            print("Failed to get Serveo URL!")
    except Exception as e:
        print(f"Error in run_serveo: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        if 'proc' in locals():
            proc.terminate()
            print("Serveo tunnel closed")

if __name__ == "__main__":
    run_serveo()
