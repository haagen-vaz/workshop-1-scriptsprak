import json
import datetime
from collections import defaultdict

# --- Konfiguration ---
UPTIME_THRESHOLD_DAYS = 30
PORT_USAGE_WARN = 80  # procent (pct i koden är 0..100)

# Läs JSON
data = json.load(open("network.devices.json", "r", encoding="utf-8"))

# Basfält
company_name = data.get("company", "Okänt företag")
last_updated = data.get("generated_at") or data.get("last_updated") or "okänt"

# Hjälpstrukturer
router_if_down = []                        # (hostname, site, if_name, status)
wan_capacity_by_router = []                # (wan_sum_mbps, hostname, site)

type_counter = {}              # typ -> antal
offline_list = []              # "hostname (site)"
warning_list = []              # "hostname (site)"
low_uptime_list = []           # (uptime, hostname, site, type)
loc_stats = {}                 # site -> {"total":..,"online":..,"offline":..,"warning":..}

# VLAN
vlan_set = set()               # unika VLAN (int)
vlan_by_site = defaultdict(set)  # {site -> set(VLAN)}

total_devices = 0

# Switch-siffror
switch_usage = []              # (hostname, site_name, used, total, pct)
switch_ports_used = 0
switch_ports_total = 0
high_port_usage_list = []      # (pct, used, total, hostname, site_name)

# --- Detaljrapport (byggs först) ---
report = ""

for location in data.get("locations", []):
    site_name = location.get("site", "okänd_plats")
    devices = list(location.get("devices", []))

    # Sortera efter status (offline först, sedan warning, sedan online)
    devices.sort(key=lambda d: {"offline": 0, "warning": 1, "online": 2}.get(str(d.get("status", "")).lower(), 3))
    
    city = location.get("city", "")
    contact = location.get("contact", "")

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

    # platsstatistik init
    if site_name not in loc_stats:
        loc_stats[site_name] = {"total": 0, "online": 0, "offline": 0, "warning": 0}

    # Enheter
    for device in devices:
        hostname = device.get("hostname", "unknown")
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

            # Flagga switchar med hög portanvändning
            if total > 0 and pct >= PORT_USAGE_WARN:
                high_port_usage_list.append((pct, used, total, hostname, site_name))

        # --- Router ---
        if dtype == "router":
            ifs = device.get("interfaces", []) or []
            port_sum = 0

            for iface in ifs:
                name = str(iface.get("name", ""))
                st   = str(iface.get("status", "")).lower()
                bw   = int(iface.get("bandwidth_mbps", 0))

                # Räkna kapacitet per PORT: ta med alla portar som är up/online
                if st in ("up", "online"):
                    port_sum += bw
                else:
                    router_if_down.append((hostname, site_name, name, st))

            wan_capacity_by_router.append((port_sum, hostname, site_name))

        # --- VLAN ---
        for v in device.get("vlans", []):
            try:
                vid = int(v)
                vlan_set.add(vid)
                vlan_by_site[site_name].add(vid)
            except Exception:
                pass

# -----------------------------
# Sektioner efter enhetsloopen
# -----------------------------

# OFFLINE
report += "\nEnheter med status OFFLINE\n"
report += "--------------------------\n"
if offline_list:
    for item in offline_list:
        report += f"- {item}\n"
else:
    report += "Inga.\n"

# WARNING
report += "\nEnheter med status WARNING\n"
report += "--------------------------\n"
if warning_list:
    for item in warning_list:
        report += f"- {item}\n"
else:
    report += "Inga.\n"

# Låg uptime
report += f"\nEnheter med mindre än {UPTIME_THRESHOLD_DAYS} dagars uptime\n"
report += "---------------------------------------------\n"
if low_uptime_list:
    low_uptime_list.sort(key=lambda t: t[0])
    for uptime, hostname, site_name, dtype in low_uptime_list:
        report += f"- {hostname:<15} {site_name:<12}  {dtype:<12}  {int(uptime):>3} dagar\n"
else:
    report += "Inga.\n"

# Routrar: interface nere / avvikande
report += "\nRouterinterface nere / avvikande\n"
report += "--------------------------------\n"
if router_if_down:
    for h, s, ifn, st in sorted(router_if_down, key=lambda x: (x[1], x[0], x[2])):
        report += f"- {s:<16} {h:<20} {ifn:<10} status: {st}\n"
else:
    report += "Inga.\n"

# Routrar – lägst total portkapacitet
report += "\nRoutrar – lägst total portkapacitet\n"
report += "----------------------------------------------\n"
if wan_capacity_by_router:
    dedup = {}
    for total, h, s in wan_capacity_by_router:
        key = (h, s)
        dedup[key] = max(dedup.get(key, -1), total)

    rows = sorted([(v, h, s) for (h, s), v in dedup.items()])
    for total, h, s in rows[:5]:
        report += f"- {h:<20} {s:<16} {total:>6} Mbps\n"
else:
    report += "Inga.\n"

# VLAN i användning
report += "\nVLAN i användning (unika)\n"
report += "-------------------------\n"
if vlan_set:
    vlan_list = sorted(vlan_set)
    line = []
    for i, vid in enumerate(vlan_list, 1):
        line.append(str(vid))
        if i % 20 == 0:
            report += ", ".join(line) + "\n"
            line = []
    if line:
        report += ", ".join(line) + "\n"
else:
    report += "Inga.\n"

# VLAN per plats
report += "\nVLAN per plats\n"
report += "--------------\n"
if vlan_by_site:
    for s in sorted(vlan_by_site.keys()):
        vids = sorted(vlan_by_site[s])
        if vids:
            report += f"{s}:\n"
            line = []
            for i, vid in enumerate(vids, 1):
                line.append(str(vid))
                if i % 20 == 0:
                    report += "  " + ", ".join(line) + "\n"
                    line = []
            if line:
                report += "  " + ", ".join(line) + "\n"
        else:
            report += f"{s}: Inga.\n"
else:
    report += "Inga.\n"

# Switchport-användning per switch
report += "\nSwitchport-användning per switch\n"
report += "--------------------------------\n"
switch_usage.sort(key=lambda t: (t[4], t[2]), reverse=True)
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

# --- EXECUTIVE SUMMARY ---
offline_count = len(offline_list)
low_uptime_count = len(low_uptime_list)
high_port_count = len(high_port_usage_list)

summary = ""
summary += "==============================\n"
summary += "        EXECUTIVE SUMMARY     \n"
summary += "==============================\n"
summary += f"- Offline enheter: {offline_count}\n"
summary += f"- Enheter med låg uptime (< {UPTIME_THRESHOLD_DAYS} dagar): {low_uptime_count}\n"
summary += f"- Switchar med hög portanvändning (≥ {PORT_USAGE_WARN}%): {high_port_count}\n\n"

if offline_list:
    summary += "⚠️  Offline (topp 3):\n"
    summary += "\n".join(f" - {item}" for item in offline_list[:3]) + "\n\n"

if low_uptime_list:
    low_uptime_sorted = sorted(low_uptime_list, key=lambda x: x[0])
    summary += "⚠️  Låg uptime (topp 3):\n"
    for uptime, host, site, typ in low_uptime_sorted[:3]:
        summary += f" - {host} ({site}) – {int(uptime)} dagar, {typ}\n"
    summary += "\n"

if high_port_usage_list:
    port_sorted = sorted(high_port_usage_list, key=lambda x: x[0], reverse=True)
    summary += "⚠️  Hög portanvändning (topp 3):\n"
    for pct, used, total, host, site in port_sorted[:3]:
        summary += f" - {host} ({site}) – {used}/{total} portar ({pct:.0f}%)\n"
    summary += "\n"

# --- RAPPORTHUVUD ---
today = datetime.date.today().strftime("%Y-%m-%d")
switch_pct_total = (switch_ports_used / switch_ports_total * 100.0) if switch_ports_total > 0 else 0.0

header = ""
header += "=================================================\n"
header += f"Rapport för: {company_name}\n"
header += f"Genererad: {today}\n"
header += f"Datakälla senast uppdaterad: {last_updated}\n"
header += "=================================================\n"
header += f"Unika VLAN: {len(vlan_set)}\n"
header += f"Totalt antal enheter: {total_devices}\n"
header += f"Switchportar i bruk: {switch_ports_used}/{switch_ports_total} ({switch_pct_total:.0f}%)\n"
header += "-------------------------------------------------\n\n"

# --- REKOMMENDATIONER ---
recommendations = ""
recommendations += "\n=================================================\n"
recommendations += "                REKOMMENDATIONER                \n"
recommendations += "=================================================\n"

if offline_count > 0:
    recommendations += f"- Kontrollera anslutning och ström till {offline_count} offline-enheter.\n"
if low_uptime_count > 0:
    recommendations += f"- Överväg att uppgradera eller felsöka de {low_uptime_count} enheter med låg uptime (< {UPTIME_THRESHOLD_DAYS} dagar).\n"
if high_port_count > 0:
    recommendations += f"- Öka kapaciteten eller fördela trafiken på switchar med över {PORT_USAGE_WARN}% portanvändning.\n"
if router_if_down:
    recommendations += f"- Granska {len(router_if_down)} routerinterface som är nere eller avvikande.\n"
if not any([offline_count, low_uptime_count, high_port_count, router_if_down]):
    recommendations += "- Inga akuta åtgärder rekommenderas. Systemet ser stabilt ut.\n"

recommendations += "- Se till att VLAN-konfigurationen hålls uppdaterad och undvik oanvända VLAN.\n"
recommendations += "- Granska varningsstatusar för att upptäcka mönster (t.ex. frekvent 'warning' på samma plats).\n"
recommendations += "-------------------------------------------------\n\n"

# --- Slutlig ordning ---
final_report = header + summary + report + recommendations

with open("report.txt", "w", encoding="utf-8") as f:
    f.write(final_report)
