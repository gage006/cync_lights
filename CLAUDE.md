# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A Home Assistant custom integration for Cync smart home devices (light switches, bulbs, plugs, fans). Distributed via HACS. There is no build step, no test suite, and no CI — changes are validated by deploying the integration into a live Home Assistant instance.

## Development Setup

This integration is a Python package that runs inside Home Assistant. To develop:

1. Copy `custom_components/cync_lights/` into the `custom_components/` directory of a running HA instance (or a dev container using the VS Code HA devcontainer setup).
2. Restart Home Assistant after any Python file change.
3. Use HA's Developer Tools → Template editor and Logs to validate behavior.

There are no lint, test, or build commands in this repo.

## Architecture

### Communication Layer (`cync_hub.py`)

The integration uses a persistent asyncio TCP connection to `cm.gelighting.com` on port `23779` (with SSL fallback to `23778`). This is **not** a local protocol — it routes through Cync's cloud servers.

- The TCP socket runs in a background thread via `asyncio.run()`.
- Inbound packets carry device state updates; the integration parses packet type bytes to dispatch state changes.
- Outbound commands are sent as raw byte payloads. The protocol is reverse-engineered and undocumented.
- A keep-alive ping fires every 180 seconds; a full state refresh also fires every 180 seconds.
- On command failure, the hub retries with 0.5s timeouts cycling through available controllers, up to 5 seconds total.
- TCP reconnection waits 15 seconds before retrying.

### Device Hierarchy

```
Home
└── Room (CyncRoom) — aggregates state from its switches and subgroups
    ├── Switch/Bulb (CyncSwitch) — individual controllable device
    │   └── Element — some devices (type 67) have multiple elements
    └── SubGroup (nested CyncRoom)
```

**Controllers** are WiFi-connected switches. Commands are relayed *through* a controller to reach other mesh devices. `CyncHub` tracks which devices are WiFi-connected and selects an appropriate controller per command.

### Capability System

`cync_hub.py` contains a large static dict (`CYNC_SWITCH_TYPES`) mapping device type IDs to capability flags: `ONOFF`, `BRIGHTNESS`, `COLORTEMP`, `RGB`, `MOTION`, `AMBIENT_LIGHT`, `PLUG`, `FAN`. All feature gating flows from this table. When adding support for a new device type, add an entry here.

### Platform Files

Each HA platform (`light.py`, `switch.py`, `fan.py`, `binary_sensor.py`) defines entity classes that wrap `CyncRoom` or `CyncSwitch` objects. Entities register a callback with their hub object; state-push packets call those callbacks, which call `async_write_ha_state()`.

- Lights (`light.py`): `CyncRoomEntity` (room groups) and `CyncSwitchEntity` (individual devices). Color mode is selected at runtime from the device's capability flags.
- Switches (`switch.py`): `CyncPlugEntity` — simple on/off for plug-type devices.
- Fans (`fan.py`): `CyncFanEntity` — maps HA fan percentage (0–100) to 4-speed device scale via brightness byte.
- Binary sensors (`binary_sensor.py`): Motion and ambient-light sensors. **Only available on 4-wire switches** (flagged in `CYNC_SWITCH_TYPES`).

### Configuration Flow (`config_flow.py`)

Multi-step HA config flow:
1. Collect username + password → POST to `api.gelighting.com` for auth token.
2. If 2FA required, collect email code and re-authenticate.
3. Fetch device list from API → present room/switch/sensor selectors.
4. Store selected devices in HA config entry.

An options flow allows re-authentication and changing the device selection without re-adding the integration.

`CyncUserData` in `cync_hub.py` owns all API calls. It also builds the full in-memory device graph from the API response.

## Key Conventions

- **Async throughout**: all HA-facing methods are `async def`. TCP socket work runs in a separate thread with its own event loop; use `asyncio.run_coroutine_threadsafe` to bridge the two.
- **Packet indices are magic numbers**: the binary protocol has no schema. Comments in `cync_hub.py` describe packet layout where known, but byte offsets are determined empirically.
- **Device type table is the source of truth**: never hard-code capability checks inline — always gate on the flags from `CYNC_SWITCH_TYPES`.
- **No external Python dependencies**: the integration uses only stdlib and HA's built-in libraries. `manifest.json` must stay dependency-free.
- **Translations live in two files**: `strings.json` (key schema) and `translations/en.json` (values). Both must be updated together when adding new config flow steps or error codes.
