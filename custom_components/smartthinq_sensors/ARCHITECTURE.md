# SmartThinQ Sensors Architecture

## Overview

This integration has two data/control paths that are intentionally kept separate:

1. Community ThinQ path
   - Implemented by the local `wideq` library.
   - Provides the main device inventory, polling, and the long-established control path.
   - This path is required for the integration to function.

2. Official ThinQ Connect path
   - Implemented through `thinqconnect` and wrapped by the custom integration.
   - Provides MQTT-backed updates and supported official control APIs.
   - This path is optional and is enabled by an LG official PAT.

The integration combines both paths into a hybrid runtime so it can prefer fast official updates where they are trustworthy, while still falling back to the community API for completeness and resilience.

## Layering

### 1. Home Assistant Integration Layer

These files are Home Assistant facing and should stay outside `wideq`:

- [`__init__.py`](/workspaces/core/config/custom_components/smartthinq_sensors/__init__.py)
  Entry orchestration, platform setup, unload, and high-level runtime bootstrapping.
- [`config_flow.py`](/workspaces/core/config/custom_components/smartthinq_sensors/config_flow.py)
  Community auth flow plus optional official PAT setup.
- [`repairs.py`](/workspaces/core/config/custom_components/smartthinq_sensors/repairs.py)
  Repair flow for missing optional official PAT.
- Platform files such as [`sensor.py`](/workspaces/core/config/custom_components/smartthinq_sensors/sensor.py), [`switch.py`](/workspaces/core/config/custom_components/smartthinq_sensors/switch.py), [`fan.py`](/workspaces/core/config/custom_components/smartthinq_sensors/fan.py), etc.
  Home Assistant entities and entity-specific behavior.

### 2. Integration Runtime Layer

These files coordinate runtime behavior across the integration:

- [`runtime_data.py`](/workspaces/core/config/custom_components/smartthinq_sensors/runtime_data.py)
  Shared runtime store access helpers around `hass.data[DOMAIN]`.
- [`setup_runtime.py`](/workspaces/core/config/custom_components/smartthinq_sensors/setup_runtime.py)
  Startup helpers, runtime-store initialization, issue handling, unload preservation, and community client bootstrap.
- [`community_setup.py`](/workspaces/core/config/custom_components/smartthinq_sensors/community_setup.py)
  Device discovery, wrapping community devices, and periodic rediscovery.
- [`lge_device.py`](/workspaces/core/config/custom_components/smartthinq_sensors/lge_device.py)
  The integration’s device wrapper around a community `wideq` device.
- [`snapshot_manager.py`](/workspaces/core/config/custom_components/smartthinq_sensors/snapshot_manager.py)
  Shared community snapshot access.
- [`trace.py`](/workspaces/core/config/custom_components/smartthinq_sensors/trace.py)
  In-memory trace timeline for diagnostics.
- [`diagnostics.py`](/workspaces/core/config/custom_components/smartthinq_sensors/diagnostics.py)
  Diagnostics export, including hybrid state and trace output.

### 3. Hybrid Routing Layer

These files decide how community and official data are merged:

- [`capability_registry.py`](/workspaces/core/config/custom_components/smartthinq_sensors/capability_registry.py)
  Tracks known logical attributes, availability, subscriptions, and source timestamps.
- [`data_source_router.py`](/workspaces/core/config/custom_components/smartthinq_sensors/data_source_router.py)
  Chooses which source should win for a logical attribute.
- [`coordinator_hybrid.py`](/workspaces/core/config/custom_components/smartthinq_sensors/coordinator_hybrid.py)
  Per-device coordinator that merges polling and MQTT/official updates and decides when polling can be skipped.
- [`device_helpers.py`](/workspaces/core/config/custom_components/smartthinq_sensors/device_helpers.py)
  Shared helper logic used by entity files when interpreting hybrid state.

### 4. Official ThinQ Connect Layer

These files adapt official ThinQ Connect into the hybrid model:

- [`official_runtime.py`](/workspaces/core/config/custom_components/smartthinq_sensors/official_runtime.py)
  Starts the official runtime, MQTT client, and official device coordinators.
- [`official_bridge.py`](/workspaces/core/config/custom_components/smartthinq_sensors/official_bridge.py)
  Orchestrates official runtime bootstrap, retry, and coordinator listeners.
- [`official_mapping.py`](/workspaces/core/config/custom_components/smartthinq_sensors/official_mapping.py)
  Matches official devices to community devices and extracts official payloads into integration logical attributes.
- [`official_control.py`](/workspaces/core/config/custom_components/smartthinq_sensors/official_control.py)
  Shared helper for official-first control actions with fallback to the community path.

### 5. Community API Library Layer

The `wideq` package is the integration’s community API library:

- [`wideq/core_async.py`](/workspaces/core/config/custom_components/smartthinq_sensors/wideq/core_async.py)
  Low-level API client/session behavior.
- [`wideq/device.py`](/workspaces/core/config/custom_components/smartthinq_sensors/wideq/device.py)
  Base device abstraction.
- [`wideq/device_info.py`](/workspaces/core/config/custom_components/smartthinq_sensors/wideq/device_info.py)
  Device metadata parsing.
- [`wideq/model_info.py`](/workspaces/core/config/custom_components/smartthinq_sensors/wideq/model_info.py)
  Model capabilities and metadata parsing.
- [`wideq/factory.py`](/workspaces/core/config/custom_components/smartthinq_sensors/wideq/factory.py)
  Device construction.
- [`wideq/devices/*`](/workspaces/core/config/custom_components/smartthinq_sensors/wideq/devices)
  Device-type specific community API support and control methods.

The key rule is:

- `wideq` talks to LG.
- The integration root turns LG behavior into Home Assistant behavior.

## Runtime Flow

### Startup

1. [`__init__.py`](/workspaces/core/config/custom_components/smartthinq_sensors/__init__.py) validates Home Assistant version and config entry shape.
2. [`setup_runtime.py`](/workspaces/core/config/custom_components/smartthinq_sensors/setup_runtime.py) prepares runtime state and authenticates the community ThinQ client.
3. [`community_setup.py`](/workspaces/core/config/custom_components/smartthinq_sensors/community_setup.py) discovers devices and wraps them as [`LGEDevice`](/workspaces/core/config/custom_components/smartthinq_sensors/lge_device.py).
4. Entity platforms are forwarded.
5. [`official_bridge.py`](/workspaces/core/config/custom_components/smartthinq_sensors/official_bridge.py) attempts to start the optional official runtime.
6. Periodic rediscovery is scheduled for newly added devices.

### Community Polling

1. Each [`LGEDevice`](/workspaces/core/config/custom_components/smartthinq_sensors/lge_device.py) owns a hybrid-aware coordinator.
2. Community state updates are recorded into the capability registry as polling data.
3. Entity files read either native community state or hybrid logical values, depending on the entity.

### Official MQTT Updates

1. [`official_runtime.py`](/workspaces/core/config/custom_components/smartthinq_sensors/official_runtime.py) receives updates through ThinQ Connect.
2. [`official_bridge.py`](/workspaces/core/config/custom_components/smartthinq_sensors/official_bridge.py) listens for official coordinator changes.
3. [`official_mapping.py`](/workspaces/core/config/custom_components/smartthinq_sensors/official_mapping.py) converts official payload fields into logical attributes such as:
   - `ac.current_temperature`
   - `fan.fan_speed`
   - `washer.run_state`
4. [`coordinator_hybrid.py`](/workspaces/core/config/custom_components/smartthinq_sensors/coordinator_hybrid.py) merges those values and updates listeners immediately.
5. When appropriate, the hybrid coordinator stretches or skips community polling.

### Control Flow

1. Entity service calls start in the platform files.
2. If the entity supports official control, it tries [`official_control.py`](/workspaces/core/config/custom_components/smartthinq_sensors/official_control.py) first.
3. If official control is unavailable or rejected, the entity falls back to the community `wideq` control path.
4. State is reconciled through official MQTT, community polling, or both.

## Hybrid Model

The integration does not merge raw payloads directly into entities. It first translates them into logical attributes.

Examples:

- `refrigerator.freezer_temperature`
- `fan.is_on`
- `washer.run_state`
- `dishwasher.current_course`

This gives the router a stable vocabulary for:

- deciding whether official or community data is fresher
- suppressing unnecessary polling when official MQTT is healthy
- preferring community data for attributes where official data is incomplete or misleading

## Availability and Offline Handling

Offline handling is modeled explicitly in the hybrid layer:

- powered-off or disconnected devices can be marked unavailable
- diagnostics record `offline_reason` and `offline_since`
- official “no data” from a known offline device is not treated as a mapping bug
- polling cadence can slow down for known-offline devices

## Diagnostics and Trace

Diagnostics are intended to be the primary debugging surface.

The diagnostics payload includes:

- runtime configuration
- hybrid profile/source state
- coordinator health and skip counts
- official runtime status and retry timing
- recent trace events

The trace buffer is especially useful for confirming:

- MQTT arrival
- official-to-community bridging
- poll skips
- official control usage and fallback
- offline transitions

## What Belongs in `wideq`

Good candidates for `wideq`:

- raw protocol helpers
- request/response normalization tied to LG payloads
- device command implementations
- model metadata parsing

Bad candidates for `wideq`:

- Home Assistant entities
- config entries, repairs, and flows
- coordinators
- hybrid routing policy
- diagnostics and trace
- Home Assistant-specific logical alias mapping

## Current Design Intent

The design is aiming for:

- community API as the stable base layer
- official ThinQ Connect as the fast-path enhancement layer
- Home Assistant entities reading from a hybrid logical model instead of raw payloads
- optional official runtime failure never breaking the whole integration

That keeps the integration useful when the official API is unavailable, while still benefiting from MQTT and official control where it is supported.
