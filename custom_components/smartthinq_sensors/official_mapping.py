"""Mapping helpers for official ThinQ devices and attributes."""

from __future__ import annotations

from typing import Any, cast

from thinqconnect import DeviceType as OfficialDeviceType
from thinqconnect.devices.const import Property as ThinQProperty
from thinqconnect.integration import ExtendedProperty, PropertyState

from homeassistant.core import HomeAssistant
from homeassistant.util.dt import utcnow

from .runtime_data import get_domain_data, get_lge_devices
from .wideq import DeviceType as CommunityDeviceType

OFFICIAL_DEVICE_LINKS = "official_device_links"

OFFICIAL_TO_COMMUNITY_TYPE = {
    "AIR_CONDITIONER": CommunityDeviceType.AC,
    "AIR_PURIFIER": CommunityDeviceType.AIR_PURIFIER,
    "AIR_PURIFIER_FAN": CommunityDeviceType.AIR_PURIFIER,
    "CEILING_FAN": CommunityDeviceType.FAN,
    "DEHUMIDIFIER": CommunityDeviceType.DEHUMIDIFIER,
    "DISH_WASHER": CommunityDeviceType.DISHWASHER,
    "DRYER": CommunityDeviceType.DRYER,
    "HOOD": CommunityDeviceType.HOOD,
    "MICROWAVE_OVEN": CommunityDeviceType.MICROWAVE,
    "REFRIGERATOR": CommunityDeviceType.REFRIGERATOR,
    "SYSTEM_BOILER": CommunityDeviceType.WATER_HEATER,
    "WASHER": CommunityDeviceType.WASHER,
    "WATER_HEATER": CommunityDeviceType.WATER_HEATER,
}


def normalize_text(value: Any) -> str:
    """Normalize text for stable comparisons."""
    return str(value or "").strip().casefold()


def normalize_bool_like(value: Any) -> Any:
    """Normalize common string boolean values."""
    normalized = normalize_text(value)
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    return value


def value_means_on(value: Any) -> bool | None:
    """Interpret a ThinQ on/off style value."""
    if isinstance(value, bool):
        return value
    if value is None:
        return None

    normalized = str(value).strip().lower()
    if normalized in {"on", "power_on", "run", "running", "active", "open"}:
        return True
    if normalized in {"off", "power_off", "stop", "stopped", "inactive", "closed"}:
        return False
    return None


def get_state_value(state: PropertyState) -> Any:
    """Return the primary value of an official PropertyState."""
    return getattr(state, "value", None)


def get_official_state_value(data: dict[Any, PropertyState], *keys: Any) -> Any:
    """Return the first available official state value for the given keys."""
    for key in keys:
        if key not in data:
            continue
        value = get_state_value(data[key])
        if value is not None:
            return normalize_bool_like(value)
    return None


def get_official_device_type(official_device_type: Any) -> CommunityDeviceType | None:
    """Map ThinQ Connect device types to community device types."""
    type_name = normalize_text(getattr(official_device_type, "name", official_device_type))
    if type_name.startswith("device_"):
        type_name = type_name.removeprefix("device_")
    return OFFICIAL_TO_COMMUNITY_TYPE.get(type_name.upper())


def update_profile_subscription(profile: Any) -> None:
    """Mark a capability profile as subscribed to official updates."""
    profile.mqtt_subscribed = True
    if profile.mqtt_subscription_time is None:
        profile.mqtt_subscription_time = utcnow()


def _extract_air_conditioner_attributes(
    data: dict[str, PropertyState],
) -> dict[str, Any]:
    aliases: dict[str, Any] = {}
    climate_state = data.get(ExtendedProperty.CLIMATE_AIR_CONDITIONER)
    if climate_state is not None:
        aliases.update(
            {
                "ac.is_on": climate_state.is_on,
                "ac.operation_mode": climate_state.hvac_mode,
                "ac.current_temperature": climate_state.current_temp,
                "ac.target_temperature": climate_state.target_temp,
                "ac.current_humidity": climate_state.humidity,
            }
        )
    aliases.setdefault(
        "ac.is_on",
        value_means_on(
            get_official_state_value(
                data,
                ThinQProperty.AIR_CON_OPERATION_MODE,
                "air_con_operation_mode",
            )
        ),
    )
    aliases.setdefault(
        "ac.operation_mode",
        get_official_state_value(data, ThinQProperty.CURRENT_JOB_MODE, "current_job_mode"),
    )
    temp_unit = normalize_text(
        get_official_state_value(data, ThinQProperty.TEMPERATURE_UNIT, "temperature_unit")
    )
    if temp_unit == "f":
        aliases.setdefault(
            "ac.current_temperature",
            get_official_state_value(data, "current_temperature_f"),
        )
        aliases.setdefault(
            "ac.target_temperature",
            get_official_state_value(data, "target_temperature_f"),
        )
    else:
        aliases.setdefault(
            "ac.current_temperature",
            get_official_state_value(data, "current_temperature_c", "current_temperature"),
        )
        aliases.setdefault(
            "ac.target_temperature",
            get_official_state_value(data, "target_temperature_c", "target_temperature"),
        )
    if power_state := data.get(ThinQProperty.POWER_LEVEL):
        aliases["ac.power_current"] = get_state_value(power_state)
    return aliases


def _extract_refrigerator_attributes(data: dict[str, PropertyState]) -> dict[str, Any]:
    aliases: dict[str, Any] = {}
    aliases["refrigerator.door_open"] = get_official_state_value(
        data, ThinQProperty.DOOR_STATE, "main_door_state"
    )
    aliases["refrigerator.eco_friendly"] = get_official_state_value(
        data,
        ThinQProperty.ECO_FRIENDLY_MODE,
        ThinQProperty.EXPRESS_MODE,
        ThinQProperty.EXPRESS_FRIDGE,
        "eco_friendly_mode",
        "express_mode",
        "express_fridge",
    )
    aliases["refrigerator.fresh_air_filter"] = get_official_state_value(
        data,
        ThinQProperty.FRESH_AIR_FILTER_REMAIN_PERCENT,
        "fresh_air_filter_remain_percent",
    )
    aliases["refrigerator.fridge_temperature"] = get_official_state_value(
        data,
        ThinQProperty.TARGET_TEMPERATURE_C,
        ThinQProperty.TARGET_TEMPERATURE_F,
        "fridge_target_temperature",
        "fridge_target_temperature_c",
        "fridge_target_temperature_f",
        "target_temperature_c",
        "target_temperature_f",
    )
    aliases["refrigerator.freezer_temperature"] = get_official_state_value(
        data,
        ThinQProperty.TARGET_TEMPERATURE_C,
        ThinQProperty.TARGET_TEMPERATURE_F,
        "freezer_target_temperature",
        "freezer_target_temperature_c",
        "freezer_target_temperature_f",
        "target_temperature_c",
        "target_temperature_f",
    )
    aliases["refrigerator.temp_unit"] = get_official_state_value(
        data,
        ThinQProperty.TEMPERATURE_UNIT,
        "fridge_temperature_unit",
        "freezer_temperature_unit",
        "temperature_unit",
    )
    return aliases


def _extract_water_heater_attributes(
    data: dict[str, PropertyState], device_type: OfficialDeviceType
) -> dict[str, Any]:
    aliases: dict[str, Any] = {}
    wh_key = (
        ExtendedProperty.WATER_HEATER
        if device_type == OfficialDeviceType.WATER_HEATER
        else ExtendedProperty.WATER_BOILER
    )
    water_state = data.get(wh_key)
    if water_state is not None:
        aliases.update(
            {
                "water_heater.is_on": water_state.is_on,
                "water_heater.operation_mode": water_state.job_mode,
                "water_heater.current_temperature": water_state.current_temp,
                "water_heater.target_temperature": water_state.target_temp,
            }
        )
    if power_state := data.get(ThinQProperty.POWER_LEVEL):
        aliases["water_heater.power_current"] = get_state_value(power_state)
    return aliases


def _extract_air_purifier_attributes(
    data: dict[str, PropertyState], device_type: OfficialDeviceType
) -> dict[str, Any]:
    aliases: dict[str, Any] = {}
    operation_key = (
        ThinQProperty.AIR_PURIFIER_OPERATION_MODE
        if device_type == OfficialDeviceType.AIR_PURIFIER
        else ThinQProperty.AIR_FAN_OPERATION_MODE
    )
    operation_value = get_official_state_value(
        data,
        operation_key,
        "air_purifier_operation_mode",
        "airPurifierOperationMode",
        "operation.airPurifierOperationMode",
        "air_fan_operation_mode",
        "airFanOperationMode",
        "operation.airFanOperationMode",
    )
    if operation_value is not None:
        aliases["air_purifier.is_on"] = value_means_on(operation_value)
    if job_mode := data.get(ThinQProperty.CURRENT_JOB_MODE):
        aliases["air_purifier.operation_mode"] = get_state_value(job_mode)
    if wind_strength := data.get(ThinQProperty.WIND_STRENGTH):
        aliases["air_purifier.fan_speed"] = get_state_value(wind_strength)
    if humidity_state := data.get(ThinQProperty.HUMIDITY) or data.get(
        ThinQProperty.CURRENT_HUMIDITY
    ):
        aliases["air_purifier.current_humidity"] = get_state_value(humidity_state)
    if pm1_state := data.get(ThinQProperty.PM1) or data.get(ThinQProperty.PM1_LEVEL):
        aliases["air_purifier.pm1"] = get_state_value(pm1_state)
    if pm10_state := data.get(ThinQProperty.PM10) or data.get(ThinQProperty.PM10_LEVEL):
        aliases["air_purifier.pm10"] = get_state_value(pm10_state)
    if pm25_state := data.get(ThinQProperty.PM2) or data.get(ThinQProperty.PM2_LEVEL):
        aliases["air_purifier.pm25"] = get_state_value(pm25_state)
    if filter_state := data.get(ThinQProperty.FILTER_REMAIN_PERCENT):
        aliases["air_purifier.filter.main"] = get_state_value(filter_state)
    else:
        aliases["air_purifier.filter.main"] = get_official_state_value(
            data,
            "filter_lifetime",
            "filterLifetime",
            "filter_info.filter_lifetime",
            "filterInfo.filterLifetime",
        )
    if filter_used_time := get_official_state_value(
        data, "used_time", "usedTime", "filter_info.used_time", "filterInfo.usedTime"
    ):
        aliases["air_purifier.filter.used_time"] = filter_used_time
    if top_filter_state := get_official_state_value(
        data,
        ThinQProperty.TOP_FILTER_REMAIN_PERCENT,
        "top_filter_remain_percent",
        "topFilterRemainPercent",
    ):
        aliases["air_purifier.filter.top"] = top_filter_state
    return aliases


def _extract_dehumidifier_attributes(data: dict[str, PropertyState]) -> dict[str, Any]:
    aliases: dict[str, Any] = {}
    if operation_state := data.get(ThinQProperty.DEHUMIDIFIER_OPERATION_MODE):
        operation_value = get_state_value(operation_state)
        aliases["dehumidifier.is_on"] = value_means_on(operation_value)
    if job_mode := data.get(ThinQProperty.CURRENT_JOB_MODE):
        aliases["dehumidifier.operation_mode"] = get_state_value(job_mode)
    if fan_state := data.get(ThinQProperty.WIND_STRENGTH):
        aliases["dehumidifier.fan_speed"] = get_state_value(fan_state)
    if humidity_state := data.get(ThinQProperty.CURRENT_HUMIDITY):
        aliases["dehumidifier.current_humidity"] = get_state_value(humidity_state)
    if target_humidity := data.get(ThinQProperty.TARGET_HUMIDITY):
        aliases["dehumidifier.target_humidity"] = get_state_value(target_humidity)
    return aliases


def _extract_hood_attributes(data: dict[str, PropertyState]) -> dict[str, Any]:
    aliases: dict[str, Any] = {}
    if hood_state := data.get(ThinQProperty.HOOD_OPERATION_MODE):
        hood_value = get_state_value(hood_state)
        aliases["hood.is_on"] = value_means_on(hood_value)
        aliases["hood.state"] = hood_value
    if fan_speed := data.get(ThinQProperty.FAN_SPEED):
        aliases["hood.vent_speed"] = get_state_value(fan_speed)
    if lamp_brightness := data.get(ThinQProperty.LAMP_BRIGHTNESS):
        aliases["hood.light_mode"] = get_state_value(lamp_brightness)
    return aliases


def _extract_microwave_attributes(data: dict[str, PropertyState]) -> dict[str, Any]:
    aliases: dict[str, Any] = {}
    if current_state := data.get(ThinQProperty.CURRENT_STATE):
        state_value = get_state_value(current_state)
        aliases["microwave.oven_upper_state"] = state_value
        if (is_on := value_means_on(state_value)) is not None:
            aliases["microwave.is_on"] = is_on
    if fan_speed := data.get(ThinQProperty.FAN_SPEED):
        aliases["microwave.vent_speed"] = get_state_value(fan_speed)
    if lamp_brightness := data.get(ThinQProperty.LAMP_BRIGHTNESS):
        aliases["microwave.light_mode"] = get_state_value(lamp_brightness)
    return aliases


def _extract_fan_attributes(data: dict[str, PropertyState]) -> dict[str, Any]:
    aliases: dict[str, Any] = {}
    operation = get_official_state_value(
        data,
        ThinQProperty.CEILING_FAN_OPERATION_MODE,
        ThinQProperty.CURRENT_JOB_MODE,
        ThinQProperty.CURRENT_STATE,
        ThinQProperty.OPERATION_MODE,
        ThinQProperty.AIR_FAN_OPERATION_MODE,
        "ceiling_fan_operation_mode",
        "ceilingfanOperationMode",
        "current_job_mode",
        "current_state",
        "operation_mode",
        "air_fan_operation_mode",
    )
    aliases["fan.is_on"] = value_means_on(operation)
    aliases["fan.operation"] = operation
    aliases["fan.fan_speed"] = get_official_state_value(
        data,
        ThinQProperty.WIND_STRENGTH,
        ThinQProperty.FAN_SPEED,
        "wind_strength",
        "fan_speed",
        "windStrength",
    )
    return aliases


def _extract_laundry_attributes(
    data: dict[str, PropertyState], device_type: OfficialDeviceType
) -> dict[str, Any]:
    aliases: dict[str, Any] = {}

    def _prefixed_keys(*keys: str) -> tuple[str, ...]:
        prefixed: list[str] = []
        for key in keys:
            prefixed.extend((key, f"main_{key}"))
        return tuple(prefixed)

    if device_type == OfficialDeviceType.WASHER:
        prefix = "washer"
        operation_key = ThinQProperty.WASHER_OPERATION_MODE
        operation_keys = (
            operation_key,
            *_prefixed_keys("washer_operation_mode", "washerOperationMode"),
            "operation.washerOperationMode",
        )
    elif device_type == OfficialDeviceType.DRYER:
        prefix = "dryer"
        operation_key = ThinQProperty.DRYER_OPERATION_MODE
        operation_keys = (
            operation_key,
            *_prefixed_keys("dryer_operation_mode", "dryerOperationMode"),
            "operation.dryerOperationMode",
        )
    else:
        prefix = "dishwasher"
        operation_key = ThinQProperty.DISH_WASHER_OPERATION_MODE
        operation_keys = (
            operation_key,
            *_prefixed_keys("dish_washer_operation_mode", "dishWasherOperationMode"),
            "operation.dishWasherOperationMode",
        )

    operation = get_official_state_value(data, *operation_keys)
    current_state = get_official_state_value(
        data,
        ThinQProperty.CURRENT_STATE,
        *_prefixed_keys("current_state", "currentState"),
        "run_state",
        "runState.currentState",
    )
    is_on = value_means_on(operation)
    if is_on is None:
        is_on = value_means_on(current_state)
    if is_on is not None:
        aliases[f"{prefix}.is_on"] = is_on
    if current_state is not None:
        aliases[f"{prefix}.run_state"] = current_state

    if current_job_mode := get_official_state_value(
        data,
        ThinQProperty.CURRENT_JOB_MODE,
        *_prefixed_keys("current_job_mode", "currentJobMode"),
        "airConJobMode.currentJobMode",
    ):
        aliases[f"{prefix}.process_state"] = current_job_mode
    elif operation is not None:
        aliases[f"{prefix}.process_state"] = operation
    if operation is not None:
        aliases[f"{prefix}.operation_mode"] = operation

    if device_type == OfficialDeviceType.WASHER:
        if current_course := get_official_state_value(
            data,
            *_prefixed_keys(
                "current_washing_course",
                "currentWashingCourse",
                "current_course",
                "currentCourse",
            ),
            "washingCourse.currentWashingCourse",
            "washing_course",
            "course",
        ):
            aliases["washer.current_course"] = current_course
    elif device_type == OfficialDeviceType.DRYER:
        if current_course := get_official_state_value(
            data,
            *_prefixed_keys(
                "current_drying_course",
                "currentDryingCourse",
                "current_course",
                "currentCourse",
            ),
            "dryingCourse.currentDryingCourse",
            "drying_course",
            "course",
        ):
            aliases["dryer.current_course"] = current_course
    elif device_type == OfficialDeviceType.DISH_WASHER:
        if current_course := get_official_state_value(
            data,
            ThinQProperty.CURRENT_DISH_WASHING_COURSE,
            *_prefixed_keys("current_dish_washing_course", "currentDishWashingCourse"),
            "dish_washing_course.current_dish_washing_course",
            "dishWashingCourse.currentDishWashingCourse",
        ):
            aliases["dishwasher.current_course"] = current_course

    return aliases


def extract_official_attributes(official_coordinator: Any) -> dict[str, Any]:
    """Extract curated official attributes from a ThinQ coordinator."""
    data: dict[str, PropertyState] = getattr(official_coordinator, "data", {})
    device_type = official_coordinator.api.device.device_type
    if device_type == OfficialDeviceType.AIR_CONDITIONER:
        aliases = _extract_air_conditioner_attributes(data)
    elif device_type == OfficialDeviceType.REFRIGERATOR:
        aliases = _extract_refrigerator_attributes(data)
    elif device_type in (OfficialDeviceType.WATER_HEATER, OfficialDeviceType.SYSTEM_BOILER):
        aliases = _extract_water_heater_attributes(data, device_type)
    elif device_type in (OfficialDeviceType.AIR_PURIFIER, OfficialDeviceType.AIR_PURIFIER_FAN):
        aliases = _extract_air_purifier_attributes(data, device_type)
    elif device_type == OfficialDeviceType.DEHUMIDIFIER:
        aliases = _extract_dehumidifier_attributes(data)
    elif device_type == OfficialDeviceType.HOOD:
        aliases = _extract_hood_attributes(data)
    elif device_type == OfficialDeviceType.MICROWAVE_OVEN:
        aliases = _extract_microwave_attributes(data)
    elif device_type == OfficialDeviceType.CEILING_FAN:
        aliases = _extract_fan_attributes(data)
    elif device_type in (
        OfficialDeviceType.WASHER,
        OfficialDeviceType.DRYER,
        OfficialDeviceType.DISH_WASHER,
    ):
        aliases = _extract_laundry_attributes(data, device_type)
    else:
        aliases = {}
    return {key: value for key, value in aliases.items() if value is not None}


def find_target_device_id(
    hass: HomeAssistant,
    official_coordinator: Any,
) -> str | None:
    """Match an official device/coordinator to the community device id."""
    domain_data = get_domain_data(hass)
    device_links = cast(dict[str, str], domain_data.setdefault(OFFICIAL_DEVICE_LINKS, {}))
    official_keys = [
        getattr(official_coordinator, "device_id", None),
        getattr(official_coordinator, "unique_id", None),
    ]
    for official_key in official_keys:
        if isinstance(official_key, str) and official_key in device_links:
            return device_links[official_key]

    official_device = getattr(getattr(official_coordinator, "api", None), "device", None)
    if official_device is None:
        return None

    community_type = get_official_device_type(getattr(official_device, "device_type", None))
    if community_type is None:
        return None

    candidates = list(get_lge_devices(hass).get(community_type, []))
    if not candidates:
        return None

    official_alias = normalize_text(getattr(official_device, "alias", None))
    official_model = normalize_text(getattr(official_device, "model_name", None))

    exact_matches = [
        device
        for device in candidates
        if normalize_text(device.name) == official_alias
        and normalize_text(device.device.device_info.model_name) == official_model
    ]
    alias_matches = [device for device in candidates if normalize_text(device.name) == official_alias]
    model_matches = [
        device
        for device in candidates
        if normalize_text(device.device.device_info.model_name) == official_model
    ]

    match = None
    if len(exact_matches) == 1:
        match = exact_matches[0]
    elif len(alias_matches) == 1:
        match = alias_matches[0]
    elif len(model_matches) == 1:
        match = model_matches[0]

    if match is None:
        return None

    target_device_id = cast(str, match.device_id)
    for official_key in official_keys:
        if isinstance(official_key, str):
            device_links[official_key] = target_device_id
    return target_device_id
