🛰️ Wi-Fi Sensor Tracker
[![HACS Validation](https://github.com/5a2v0/HA-WiFi-Sensor-Tracker/actions/workflows/hacs-validation.yml/badge.svg)](https://github.com/5a2v0/HA-WiFi-Sensor-Tracker/actions/workflows/hacs-validation.yml)

Custom integration for Home Assistant that turns your phone’s Wi-Fi connection sensor into a device tracker.
Useful when GPS is unreliable indoors (e.g. inside your home), allowing presence detection based on Wi-Fi connection.


---

✨ Features

Each Wi-Fi sensor becomes a device_tracker entity.
Supports multiple sensors (e.g. multiple phones).
Supports consider_home: delay before marking a device as not_home after Wi-Fi disconnects.
Exposes trackers as device_tracker entities with source_type=router → integrates seamlessly with Home Assistant person entities.

Fully configurable via UI (Config Flow) – no YAML required.



---

⚙️ Installation

1. Copy the folder wifi_sensor_tracker into your Home Assistant custom_components directory.
Final path:

config/custom_components/wifi_sensor_tracker/

2. Restart Home Assistant.
3. Go to Settings → Devices & Services → Add Integration.
4. Search for Wi-Fi Sensor Tracker and configure it.



---

🔧 Configuration

When you add the integration from the UI, you will be asked:
Home Wi-Fi SSID → the SSID that should be considered "home".

Sensors → select one or more Wi-Fi connection sensors (usually created by the HA Companion App, e.g. sensor.myphone_wifi_connection).

Consider Home (seconds) → how long to wait before marking a device as not_home after Wi-Fi disconnects (default: 180).



---

📊 Example

If you configure with:
SSID: My_Home_SSID

Sensors:
sensor.smartphone_tizio_wifi_connection
sensor.smartphone_caio_wifi_connection


You will get these entities:
device_tracker.smartphone_tizio_wifi
device_tracker.smartphone_caio_wifi

Their state will be home when the phone is connected to My_Home_SSID, and not_home otherwise (after consider_home delay).


---

❗ Notes

Old YAML configuration is no longer required.
Removing the integration from UI will also remove the created trackers.
This integration does not require router credentials, it only relies on the phone’s own Wi-Fi sensor.



---


🚀 Future Plans

Planned improvements for next versions:
Multi-SSID / Multi-Zone support → assign different Wi-Fi networks to custom zones (e.g. Home, Work, Second House).
Automatic sensor filtering → only suggest Wi-Fi-related sensors during setup.
