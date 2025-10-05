# Import the json library so that we can handle json
import json

INPUT_FILE = "network.devices.json"
OUTPUT_FILE = "report.txt"


# Read json from products.json to the variable data
data = json.load(open("network.devices.json","r",encoding = "utf-8"))

# Create a variable that holds our whole text report
report = ""

# loop through the location list 
for location in data["locations"]:
    # add the site/'name' of the location to the report
    report += "\n" + location["site"] + "\n"
    # add a list of the host names of the devices 
    # on the location to the report
    for device in location["devices"]:
      hostname = device["hostname"]
      status = device.get("status", "unknown")
      uptime_days = device.get("uptime_days", 0)
      report += f"  {hostname}  |  Status: {status}  |  Uptime: {uptime_days} dagar\n"

# write the report to text file
with open('report.txt', 'w', encoding='utf-8') as f:
    f.write(report)