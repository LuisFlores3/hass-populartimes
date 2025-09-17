# Updated with AI - Not fit for human consumption

# hass-populartimes
[![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg)](https://github.com/custom-components/hacs)

## Description
This is a custom component for Home Assistant.
The component generates a sensor which shows the current popularity for a place which can be found in Google Maps using the Places API.

Sensor attributes are also generated which indicate past popularity at each hour of the day. 

## Updated requirements

Since updating to a new fork of populartimes, a Google Places API key or Places Id is no longer required.

## Installation
Either:
1. Install via HACS
2. Download files as zip and put the contents of the populartimes folder in your home assistant custom_components folder.

## Configure via UI (recommended)
After installing the integration files:

1. In Home Assistant, go to Settings → Devices & Services → Add Integration.
2. Search for "Popular Times".
3. Enter:
  - Name: Friendly name for the sensor (e.g., Charlie Browns)
  - Address: A precise postal address (e.g., "123 Main St, City, State, Country"). The integration will automatically use the Name together with the Address to improve matching.
4. Submit to create the sensor.

Entity ID default for new sensors:
- The entity_id will by default be created as `sensor.bar_{slugified_name}` (for example: `sensor.bar_charlie_browns`).
- You can always manually change the entity ID from the entity settings if desired.


## Configuration

```yaml
sensor:
  platform: populartimes
  name: 'your_sensor_name_here'
  address: 'your_address_here'
```
Address tips:
- Enter the standard postal address. You do not need to include the place name; the integration sends "Name, Address" to Google behind the scenes for better matching.

## YAML → UI migration
- If you already configured this integration via YAML, it will be imported automatically into the UI on the next restart.
- A persistent notification will be shown indicating YAML can be removed.
- After import, the UI config becomes the source of truth; the YAML can be removed from `configuration.yaml`.

## Edit after setup
- To change the sensor Name or Address later, open the Popular Times integration and click the gear icon for the entry, then adjust the fields and save.
- Changing the Name updates the entity's friendly name. Existing entity IDs are not changed automatically; you can rename the entity ID from the entity settings if you want.

## Live vs historical data
Sometimes Google Maps does not provide live popularity data for the place you want to query.
In that case the historical data is used to set the sensor state.
To indicate this, the attribute `popularity_is_live` is set to `false`.

## Links:
[Home Assistant Community Topic](https://community.home-assistant.io/t/google-maps-places-popular-times-component/147362)

## Credits

This component uses the [LivePopularTimes](https://github.com/GrocerCheck/LivePopularTimes) library, which is a fork of the previously used [populartimes](https://github.com/m-wrzr/populartimes) library.