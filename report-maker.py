import json

# --- Konfiguration ---
UPTIME_THRESHOLD_DAYS = 30

# Läs JSON
data = json.load(open("network.devices.json", "r", encoding="utf-8"))

# Basfält
company_name = data.get("company" )
last_updated = data.get("generated_at") or data.get("last_updated")

# Hjälpstrukturer

from collections import defaultdict

router_if_down = []            # (hostname, site, if_name, status)
wan_capacity_by_site = defaultdict(int)   # site -> sum WAN 'up' Mbps
wan_capacity_by_router = []    # (wan_sum_mbps, hostname, site)

type_counter = {}              # typ -> antal
offline_list = []              # "hostname (site)"
warning_list = []              # "hostname (site)"
low_uptime_list = []           # (uptime, hostname, site, type)
loc_stats = {}                 # site -> {"total":..,"online":..,"offline":..,"warning":..}
vlan_set = set()               # unika VLAN (int)
total_devices = 0
switch_usage = []
switch_ports_used = 0
switch_ports_total = 0
   



# Huvudrapport
report = ""

for location in data["locations"]:
    site_name = location["site"]
    devices = location["devices"]
    # Sortera efter status (offline först, sedan warning, sedan online)
    devices.sort(key=lambda d: {"offline": 0, "warning": 1, "online": 2}.get(str(d.get("status", "")).lower(), 3))
    
    city = location.get("city")
    contact = location.get ("contact")

    

    # Summera status per plats
    total_site = len(devices)
    statuses = [str(d.get("status", "unknown")).lower() for d in devices]
    site_online  = sum(1 for s in statuses if s == "online")
    site_offline = sum(1 for s in statuses if s == "offline")
    site_warning = sum(1 for s in statuses if s == "warning")
    online_pct = (site_online / total_site * 100.0) if total_site > 0 else 0.0

    # Platsrubrik + kolumnrubriker
    report += (
        f"\n{site_name} — {total_site} enheter "
        f"(Online: {site_online}, Offline: {site_offline}, Warning: {site_warning}, {online_pct:.0f}% online)\n"
        f"{city}  |  Kontakt: {contact}\n"
    )
    report += "---------------------------------------------------------------------------\n"
    report += "Hostname".ljust(18) + "Typ".ljust(18) + "Status".ljust(10) + "Uptime (dagar)\n"
    report += "-" * 55 + "\n"

    
    # platsstatistik
    if site_name not in loc_stats:
        loc_stats[site_name] = {"total": 0, "online": 0, "offline": 0, "warning": 0}

    # Enheter
    for device in devices:
        hostname = device["hostname"]
        dtype = str(device.get("type", "")).lower()
        status = str(device.get("status", "")).lower()
        uptime_days = float(device.get("uptime_days", 0))

        report += (
            f"{hostname.ljust(18)}{dtype.ljust(18)}{status.ljust(10)}{str(int(uptime_days)).rjust(5)}\n"
        )

        # Statistik
        type_counter[dtype] = type_counter.get(dtype, 0) + 1
        total_devices += 1

        if status == "offline":
            offline_list.append(f"{hostname} ({site_name})")
        elif status == "warning":
            warning_list.append(f"{hostname} ({site_name})")

        loc_stats[site_name]["total"] += 1
        if status in ("online", "offline", "warning"):
            loc_stats[site_name][status] += 1

        if uptime_days < UPTIME_THRESHOLD_DAYS:
            low_uptime_list.append((uptime_days, hostname, site_name, dtype))

        # --- Switch ---
        if dtype == "switch":
            ports = device.get("ports", {}) or {}
            used = int(ports.get("used", 0))
            total = int(ports.get("total", 0))
            pct = (used / total * 100.0) if total > 0 else 0.0

            switch_ports_used  += used
            switch_ports_total += total
            switch_usage.append((hostname, site_name, used, total, pct))

        # --- Router ---
        if dtype == "router":
            ifs = device.get("interfaces", []) or []
            wan_sum = 0
            for iface in ifs:
                name = str(iface.get("name", ""))
                st   = str(iface.get("status", "")).lower()
                bw   = int(iface.get("bandwidth_mbps", 0))
                # WAN-kapacitet: interface med "wan" i namnet och som är up/online
                if "wan" in name.lower() and st in ("up", "online"):
                    wan_sum += bw
                if st not in ("up", "online"):
                    router_if_down.append((hostname, site_name, name, st))

            if wan_sum:
                wan_capacity_by_site[site_name] += wan_sum
                wan_capacity_by_router.append((wan_sum, hostname, site_name))

    # --- VLAN (oavsett typ) ---
    for v in device.get("vlans", []):
        vlan_set.add(int(v))





# OFFLINE
report += "\nEnheter med status OFFLINE\n"
report += "--------------------------\n"
if offline_list:
    for item in offline_list:
        report += f"- {item}\n"
else:
    report += "Inga.\n"

#WARNING
report += "\nEnheter med status WARNING\n"
report += "--------------------------\n"
if warning_list:
    for item in warning_list:
        report += f"- {item}\n"
else:
    report += "Inga.\n"

#Låg uptime
report += f"\nEnheter med mindre än {UPTIME_THRESHOLD_DAYS} dagars uptime\n"
report += "---------------------------------------------\n"
if low_uptime_list:
    low_uptime_list.sort(key=lambda t: t[0])  # minst först
    for uptime, hostname, site_name, dtype in low_uptime_list:
        report += f"- {hostname:<15} {site_name:<12}  {dtype:<12}  {int(uptime):>3} dagar\n"
        # --- WAN-kapacitet per plats (routrar) ---
report += "\nWAN-kapacitet per plats (routrar)\n"
report += "---------------------------------\n"
if wan_capacity_by_site:
    total_wan = sum(wan_capacity_by_site.values())
    for s, cap in sorted(wan_capacity_by_site.items()):
        report += f"- {s:<20} {cap:>6} Mbps (summa WAN up)\n"
    report += f"\nTotalt WAN (alla platser): {total_wan} Mbps\n"
else:
    report += "Ingen WAN-kapacitet hittades.\n"

# --- Routrar: interface nere / avvikande ---
report += "\nRouterinterface nere / avvikande\n"
report += "--------------------------------\n"
if router_if_down:
    for h, s, ifn, st in sorted(router_if_down, key=lambda x: (x[1], x[0], x[2])):
        report += f"- {s:<16} {h:<20} {ifn:<10} status: {st}\n"
else:
    report += "Inga.\n"

# --- Routrar – högst WAN-kapacitet (topp 5) ---
report += "\nRoutrar – högst WAN-kapacitet (topp 5)\n"
report += "--------------------------------------\n"
if wan_capacity_by_router:
    for wan_sum, h, s in sorted(wan_capacity_by_router, reverse=True)[:5]:
        report += f"- {h:<20} {s:<16} {wan_sum:>6} Mbps\n"
else:
    report += "Inga routrar med WAN-up hittades.\n"




# Switchport-användning per switch
report += "\nSwitchport-användning per switch\n"
report += "--------------------------------\n"

# Sortera efter anvädning
switch_usage.sort(key=lambda t: (t[4], t[2]), reverse=True)

# Rubriker 
report += f"{'Switch':<22} {'Plats':<18} {'Anv.':>6}/{ 'Tot.':<6} {'%':>6}\n"
report += f"{'-'*22} {'-'*18} {'-'*13} {'-'*6}\n"

for hostname, site_name, used, total, pct in switch_usage:
    report += f"{hostname:<22} {site_name:<18} {used:>6}/{total:<6} {pct:>5.1f}%\n"



# Översikt per lokation
report += "\nÖversikt per lokation (total/online/offline/warning)\n"
report += "-----------------------------------------------------\n"
report += "Lokation                Totalt  Online  Offline  Warning\n"
report += "----------------------  ------  ------  -------  -------\n"
for site_name in sorted(loc_stats.keys()):
    row = loc_stats[site_name]
    report += (
        f"{site_name.ljust(22)}  "
        f"{str(row['total']).rjust(6)}  "
        f"{str(row['online']).rjust(6)}  "
        f"{str(row['offline']).rjust(7)}  "
        f"{str(row['warning']).rjust(7)}\n"
    )

# Executive Summary (överst)
port_pct = (switch_ports_used / switch_ports_total * 100.0) if switch_ports_total > 0 else 0.0
vlan_list_str = ", ".join(map(str, sorted(vlan_set)))

summary = ""
summary += "Summary\n"
summary += "-----------------\n"
summary += f"Företag: {company_name}\n"
summary += f"Senast uppdaterad: {last_updated}\n"
summary += f"Totalt antal enheter: {total_devices}\n"
summary += (
    f"Offline: {len(offline_list)}  |  Warning: {len(warning_list)}  |  "
    f"Låg uptime (<{UPTIME_THRESHOLD_DAYS} d): {len(low_uptime_list)}\n"
)
summary += f"Switch-portar: {switch_ports_used}/{switch_ports_total} i bruk ({port_pct:.0f}%)\n"
summary += f"Unika VLAN: {len(vlan_set)}\n"
summary += "\n"
summary += f"VLAN-lista: {vlan_list_str}\n"
summary += "\n"

#Sammanfattningen före resten av rapporten & skriv fil
report = summary + report

with open("report.txt", "w", encoding="utf-8") as f:
    f.write(report)
