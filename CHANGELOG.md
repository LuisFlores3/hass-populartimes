# Changelog

All notable changes to this project are documented in this file. The format is
based on [Keep a Changelog](https://keepachangelog.com/), and this project
adheres to [Semantic Versioning](https://semver.org/).

## [2.1.0] - 2026-06-19

### Fixed
- **Sensors no longer freeze after the initial setup fetch.**
  `PopularTimesSensor.async_added_to_hass()` overrode the base method but never
  called `await super().async_added_to_hass()`. That `super()` call is how
  `CoordinatorEntity` subscribes the entity to the coordinator (via
  `async_add_listener`). A `DataUpdateCoordinator` only schedules its periodic
  refresh once it has at least one listener, so without the subscription:
  (1) polling never started, and (2) `_handle_coordinator_update()` never fired,
  so refreshes were not propagated to the entity. Values therefore updated only
  when the config entry was reloaded. The `super()` call has been restored, so
  polling now starts automatically and updates flow through to the sensor.

### Added
- **New `populartimes.refresh` service.** Triggers an immediate re-fetch for a
  single config entry (`entry_id`) or for every Popular Times entry when called
  with no target. Unlike reloading the entry (`reload_config_entry`), entities
  stay available during the refresh. Exposed in Developer Tools → Actions.

## [2.0.0]

- v2.0 baseline: branding, localization, and options cleanup.
- Modern Home Assistant `DataUpdateCoordinator` architecture; legacy YAML drop.
- HACS compliance (icon/logo, manifest metadata).
