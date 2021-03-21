"""
Support for LG Smartthinq device.
"""
import uuid

# wash devices features
FEAT_RUN_STATE = "run_state"
FEAT_PRE_STATE = "pre_state"
FEAT_PROCESS_STATE = "process_state"
FEAT_ERROR_MSG = "error_message"
FEAT_TUBCLEAN_COUNT = "tubclean_count"
FEAT_DRYLEVEL = "dry_level"
FEAT_SPINSPEED = "spin_speed"
FEAT_TEMPCONTROL = "temp_control"
FEAT_TIMEDRY = "time_dry"
FEAT_WATERTEMP = "water_temp"

FEAT_CHILDLOCK = "child_lock"
FEAT_CREASECARE = "crease_care"
FEAT_DELAYSTART = "delay_start"
FEAT_DOORCLOSE = "door_close"
FEAT_DOORLOCK = "door_lock"
FEAT_DOOROPEN = "door_open"
FEAT_DUALZONE = "dual_zone"
FEAT_ENERGYSAVER = "energy_saver"
FEAT_HALFLOAD = "half_load"
FEAT_MEDICRINSE = "medic_rinse"
FEAT_NIGHTDRY = "night_dry"
FEAT_PREWASH = "pre_wash"
FEAT_REMOTESTART = "remote_start"
FEAT_STEAM = "steam"
FEAT_STEAMSOFTENER = "steam_softener"
FEAT_RINSEREFILL = "rinse_refill"
FEAT_SALTREFILL = "salt_refill"
FEAT_TURBOWASH = "turbo_wash"

# refrigerator device features
FEAT_ECOFRIENDLY = "eco_friendly"
FEAT_EXPRESSMODE = "express_mode"
FEAT_EXPRESSFRIDGE = "express_fridge"
FEAT_FRESHAIRFILTER = "fresh_air_filter"
FEAT_ICEPLUS = "ice_plus"
FEAT_SMARTSAVINGMODE = "smart_saving_mode"
# FEAT_SMARTSAVING_STATE = "smart_saving_state"
FEAT_WATERFILTERUSED_MONTH = "water_filter_used_month"


def as_list(obj):
    """Wrap non-lists in lists.

    If `obj` is a list, return it unchanged. Otherwise, return a
    single-element list containing it.
    """

    if isinstance(obj, list):
        return obj
    else:
        return [obj]


def gen_uuid():
    return str(uuid.uuid4())
