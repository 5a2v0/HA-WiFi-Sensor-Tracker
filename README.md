# 🛰️ Wi-Fi Sensor Tracker

[![HACS Validation](https://github.com/5a2v0/HA-WiFi-Sensor-Tracker/actions/workflows/hacs-validation.yml/badge.svg)](https://github.com/5a2v0/HA-WiFi-Sensor-Tracker/actions/workflows/hacs-validation.yml)
[![Validate with hassfest](https://github.com/5a2v0/HA-WiFi-Sensor-Tracker/actions/workflows/hassfest.yml/badge.svg)](https://github.com/5a2v0/HA-WiFi-Sensor-Tracker/actions/workflows/hassfest.yml)
[![Available in HACS](https://img.shields.io/badge/HACS-Default-blue.svg?logo=homeassistant)](https://hacs.xyz)

---

## 📘 Integration summary

| Field | Value |
|:--|:--|
| **Domain** | `wifi_sensor_tracker` |
| **Type** | Custom Integration |
| **Author** | [5a2v0](https://github.com/5a2v0) |
| **Tested HA Version** | 2025.9 or newer |
| **Config method** | Config Flow (UI only, no YAML) |
| **Current Version** | 2.0.5 |

---
## <img src="https://twemoji.maxcdn.com/v/latest/svg/1f1ec-1f1e7.svg" width="20"/> English 🇬🇧

## Description

**Wi-Fi Sensor Tracker** is a Home Assistant custom integration that turns your phone’s *Wi-Fi connection sensor* into a `device_tracker`.

Unlike native integrations that require a router-specific setup (often limited to certain brands and credentials access), this solution works **independently of the router**:  
it relies on the Wi-Fi sensor exposed by the Home Assistant Companion App on your smartphone.

That means:
✅ No router login, no vendor restrictions  
✅ Works with any phone that has the Wi-Fi connection sensor enabled in the Companion App  
✅ Perfect for indoor presence detection, where GPS is unreliable  

> ℹ️ Make sure the Wi-Fi Connection Status sensor (usually sensor.<device_name>_wifi_connection) is enabled in the Companion App.
---

## ✨ Features

* Each Wi-Fi sensor creates a `device_tracker` entity
* Supports multiple sensors / multiple phones
* Supports `consider_home`: delay before marking as *not_home* after disconnection
* Source type: `router` → integrates directly with *Person* entities
* Fully configurable from the UI (Config Flow) → no YAML required

---

## ⚙️ Installation

**Via HACS (recommended)**

1. Open HACS → Integrations → Search for “Wi-Fi Sensor Tracker”
2. Install and restart Home Assistant
3. Go to **Settings → Devices & Services → Add Integration**
4. Search for *Wi-Fi Sensor Tracker* and fill in the required fields

**Manual installation**
Copy the `wifi_sensor_tracker` folder into: `config/custom_components/`
then restart Home Assistant.

---

## 🔧 Configuration

During setup in the UI, you’ll be asked to provide:

| Field                       | Description                                                                        |
| --------------------------- | ---------------------------------------------------------------------------------- |
| **Home Wi-Fi SSID**         | SSID to be considered as “home”                                                    |
| **Sensors**                 | One or more Wi-Fi sensors (e.g. `sensor.my_phone_wifi_connection`)                 |
| **Consider Home (seconds)** | Tolerance time before switching to *not_home* after disconnection (default: 180 s) |

---

## 📊 Example

Configuration:

SSID: My_Home_SSID
Sensors:
sensor.smartphone_tizio_wifi_connection
sensor.smartphone_caio_wifi_connection

Result — two entities created:

device_tracker.smartphone_tizio_wifi
device_tracker.smartphone_caio_wifi

State = **home** when connected to “My_Home_SSID”
State = **not_home** after disconnection, following the delay defined in `consider_home`

> 💡 Tip: to link trackers to people, go to *Settings → People* and select the corresponding tracker.

---

## 🧩 Notes

* No YAML configuration required
* Removing the integration from the UI will automatically delete its entities
* Doesn’t require network credentials or router access

---

## 🚀 Roadmap / Future development

* 🔹 **Multi-SSID / Multi-Zone support:** map different SSIDs to custom zones (Home, Work, …)
* 🔹 **Automatic sensor filtering:** during setup, only valid Wi-Fi sensors will be suggested

---


## <img src="https://twemoji.maxcdn.com/v/latest/svg/1f1ee-1f1f9.svg" width="20"/> Italiano 🇮🇹

## Descrizione

**Wi-Fi Sensor Tracker** è un’integrazione personalizzata per Home Assistant che trasforma il *sensore Wi-Fi* del tuo smartphone in un’entità `device_tracker`.

A differenza delle integrazioni native che si collegano ai router (ognuna compatibile solo con determinati modelli e richiedendo username + password), questa integrazione **non ha bisogno di accedere al router**:  
si basa unicamente sul sensore del Wi-Fi esposto dall’App Companion di Home Assistant.

✅ Nessuna credenziale del router  
✅ Compatibile con qualsiasi smartphone che espone il sensore Wi-Fi  
✅ Ideale per rilevare la presenza in casa anche dove il GPS non funziona bene  

> ℹ️ Assicurati che nell’App Companion sia abilitato il sensore *Stato connessione Wi-Fi* (di solito `sensor.<nome_dispositivo>_wifi_connection`).

---
## ✨ Caratteristiche

- Ogni sensore Wi-Fi genera un’entità `device_tracker`
- Supporta più sensori / più telefoni
- Supporta `consider_home`: ritardo prima di marcare *not_home* dopo la disconnessione
- Tipo sorgente: `router` → integrazione diretta con le entità *Person*
- Completamente configurabile da UI (Config Flow) → nessun YAML necessario

---

## ⚙️ Installazione

**Tramite HACS (recommandato)**  
1. Apri HACS → Integrations → Cerca “Wi-Fi Sensor Tracker”  
2. Installa e riavvia Home Assistant  
3. Vai su **Settings → Devices & Services → Add Integration**  
4. Cerca *Wi-Fi Sensor Tracker* e configura i campi richiesti  

**Installazione manuale**  
Copia la cartella `wifi_sensor_tracker` in: config/custom_components/
poi riavvia Home Assistant.

---

## 🔧 Configurazione

Durante la configurazione da UI ti verrà chiesto di specificare:

| Field | Description |
|-------|--------------|
| **Home Wi-Fi SSID** | SSID da considerare come “home” |
| **Sensors** | Uno o più sensori Wi-Fi (es. `sensor.mio_telefono_wifi_connection`) |
| **Consider Home (seconds)** | Secondi di tolleranza prima di passare a *not_home* dopo la disconnessione (default 180 s) |

---

## 📊 Esempio

Configurazione:

SSID: My_Home_SSID
Sensors:
sensor.smartphone_tizio_wifi_connection
sensor.smartphone_caio_wifi_connection

Risultato, due entità create:

device_tracker.smartphone_tizio_wifi
device_tracker.smartphone_caio_wifi

Stato = **home** quando connesso a “My_Home_SSID”  
Stato = **not_home** dopo disconnessione, dopo l'eventuale tempo in secondi dichiarato in  'consider_home'

> 💡 Ricorda: per associare i tracker alle persone, vai in *Impostazioni → Persone* e seleziona il tracker corrispondente.

---

## 🧩 Note

- Nessuna configurazione YAML richiesta  
- Rimuovendo l’integrazione dall’interfaccia, le entità vengono eliminate automaticamente  
- Non richiede credenziali di rete o accesso al router  

---

## 🚀 Roadmap / Sviluppi futuri

- 🔹 **Multi-SSID / Multi-Zone support:** mappa diversi SSID a zone personalizzate (Home, Work, …)  
- 🔹 **Automatic sensor filtering:** durante il setup verranno suggeriti solo sensori Wi-Fi validi

---
