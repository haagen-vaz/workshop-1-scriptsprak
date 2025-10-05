# Import the json library so that we can handle json

import json
data = json.load(open("network.devices.json","r",encoding = "utf-8"))

for location in data ["locations"]:
    print (location["site"])
    for device in location ["devices"]:
        print (device["hostname"])