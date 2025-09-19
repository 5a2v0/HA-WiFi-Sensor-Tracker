# Wi-Fi Sensor Tracker

This custom integration allows you to use Wi-Fi sensors as `device_tracker` entities in Home Assistant.  
Each Wi-Fi sensor can be treated as a tracker, useful to determine if a person is `home` or `not_home`.

---

## Configuration

In the current version you need to add the configuration in your `configuration.yaml`.  
Specify your **home Wi-Fi SSID** and the list of **Wi-Fi sensors** you want to track.

### Example

```yaml
device_tracker:
  - platform: wifi_sensor_tracker
    home_wifi_ssid: "My_Home_SSID"
    sensors:
      - sensor.smartphone_tizio_wifi_connection
      - sensor.smartphone_caio_wifi_connection
    consider_home: 180
```

home_wifi_ssid: The SSID of your home network.
sensors: List of Wi-Fi sensors (entities) to be used as trackers.
consider_home: (optional) Number of seconds to wait before marking the device as not_home.

Roadmap

In a future release, configuration will be possible through the Home Assistant UI with a Config Flow, including:
Selection of Wi-Fi sensors directly from a list of available entities.
Support for multiple Wi-Fi networks.
Mapping each Wi-Fi network to a specific zone (e.g., home, work, second_home).
