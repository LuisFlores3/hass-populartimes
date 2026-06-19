# hass-populartimes
[![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg)](https://github.com/custom-components/hacs)


A modern Home Assistant integration that scrapes Google Maps to provide popular times, wait times, and ratings for venues without requiring a Google Maps API Key.

This is an updated version and fork of the original work by [freakshock88](https://github.com/freakshock88/hass-populartimes).

## Features
- **Multi-Sensor Support**: Each venue creates a Device with four sensors:
  - **Popularity**: Current occupancy percentage.
  - **Rating**: Average star rating.
  - **Wait Time**: Estimated time spent waiting for service.
  - **Time Spent**: Average duration of stay.
- **Dynamic Icons**: Intelligent clock icons that change based on the current hour.
  - Filled icons represent **Live** data.
  - Outlined icons represent **Historical** trends when live data is unavailable.
- **Rich Attributes**: Includes geographical coordinates, postal address, and hour-by-hour popularity trends for each day of the week.
- **UI Configurable**: Fully managed via the Integrations dashboard. No YAML required.
- **Customizable**: Adjust update intervals, retry logic, and icons directly in the UI.

## Installation
### Option 1: HACS (Recommended)
1. Open HACS in Home Assistant.
2. Click the three dots in the top-right corner and select **Custom repositories**.
3. Paste this repository's URL (`https://github.com/LuisFlores3/hass-populartimes`) and select **Integration** as the category.
4. Click **Add**, then search for "Popular Times" in HACS and click **Download**.
5. Restart Home Assistant.

### Option 2: Manual
1. Download the repository as a ZIP.
2. Copy `custom_components/populartimes` to your `config/custom_components/` directory.
3. Restart Home Assistant.

## Configuration
1. Go to **Settings** -> **Devices & Services**.
2. Click **+ Add Integration** and search for **Popular Times**.
3. Enter a **Name** (e.g., "The Local Bar") and a **Precise Address**. 
4. The integration will automatically find the venue and create the entities.

### Updating Configuration
To change the address or adjust polling/icon settings:
1. Open the **Popular Times** entry in the Integrations dashboard.
2. Click **Configure** or the **Gear Icon** to modify settings without restarting.

## Auto-Updates & Refresh
Each venue's sensor updates automatically on the configured polling interval
(default: every 10 minutes; adjustable from 1–120 minutes in the options).

To force an immediate update, the integration registers two actions, available
under **Developer Tools → Actions**:

- **`populartimes.refresh`** — Re-fetch data right now for a single entry (pass
  an `entry_id`) or for every Popular Times entry when called with no target.
  Entities stay available during the refresh, unlike a full reload — making it
  ideal for dashboards and automations that need data on demand.
- **`populartimes.update_entry`** — Update an entry's options (name, address,
  icon, update interval) programmatically without opening the UI.

## Data Source
This integration uses the [LivePopularTimes](https://github.com/GrocerCheck/LivePopularTimes) library to fetch data directly from Google Maps. It does **not** use the official Places API, meaning no API keys or billing are required.

## Legacy YAML Support
YAML configuration is deprecated. Any existing YAML config is automatically imported into the UI on startup. Once imported, you can safely remove the `populartimes` block from your `configuration.yaml`.

## Changelog
See [CHANGELOG.md](CHANGELOG.md) for release notes. The latest release (2.1.0)
fixes auto-updates and adds the `populartimes.refresh` service.

## Credits
- Developed by [LuisFlores3](https://github.com/LuisFlores3).
- Forked from [freakshock88/hass-populartimes](https://github.com/freakshock88/hass-populartimes).
- Uses the [LivePopularTimes](https://github.com/GrocerCheck/LivePopularTimes) library (forked from [m-wrzr/populartimes](https://github.com/m-wrzr/populartimes)).

---
> [!NOTE]
> This integration has been modernized and refactored using artificial intelligence to enhance its architecture and performance characteristics.