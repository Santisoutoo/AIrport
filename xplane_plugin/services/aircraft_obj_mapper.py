from pathlib import Path

_XPLANE_ROOT = Path(__file__).resolve().parents[6]

_SCENERY = "Resources/default scenery/sim objects/apt_aircraft"

_OBJ_MAP = {
    "A320": {
        "VLG": "jet/A320_VLG/A320_VLG_static.obj",
        "IBE": "jet/A320_AFR/A320_AFR_static.obj",
        "BAW": "jet/A320_BAW/A320_BAW_static.obj",
        "EZY": "jet/A320_EZY/A320_EZY_static.obj",
        "WZZ": "jet/A320_EZY/A320_EZY_static.obj",
        "VOE": "jet/A320_VLG/A320_VLG_static.obj",
        "IBS": "jet/A320_AFR/A320_AFR_static.obj",
        "_default": "jet/A320_VLG/A320_VLG_static.obj",
    },
    "A321": {
        "VLG": "jet/A320_VLG/A320_VLG_static.obj",
        "IBE": "jet/A320_AFR/A320_AFR_static.obj",
        "BAW": "jet/A320_BAW/A320_BAW_static.obj",
        "EZY": "jet/A320_EZY/A320_EZY_static.obj",
        "WZZ": "jet/A320_EZY/A320_EZY_static.obj",
        "IBS": "jet/A320_AFR/A320_AFR_static.obj",
        "_default": "jet/A320_VLG/A320_VLG_static.obj",
    },
    "B738": {
        "RYR": "jet/B738_RYR/B738_RYR_static.obj",
        "AEA": "jet/B738_KLM/B738_KLM_static.obj",
        "_default": "jet/B738_RYR/B738_RYR_static.obj",
    },
    "B737": {
        "RYR": "jet/B738_RYR/B738_RYR_static.obj",
        "AEA": "jet/B738_KLM/B738_KLM_static.obj",
        "_default": "jet/B738_RYR/B738_RYR_static.obj",
    },
    "E190": {
        "AEA": "jet/CRJ1_AUA/CRJ1_AUA_static.obj",
        "ANE": "jet/CRJ1_AUA/CRJ1_AUA_static.obj",
        "_default": "jet/CRJ1_AUA/CRJ1_AUA_static.obj",
    },
    "C172": {"_default": "prop/C172/C172_static.obj"},
    "PA28": {"_default": "prop/C172/C172_static.obj"},
}

_DEFAULT = f"{_SCENERY}/jet/A320_VLG/A320_VLG_static.obj"


def get_obj_path(aircraft_type: str, airline_icao: str | None = None) -> str:
    """Return the absolute path to the .obj for the given aircraft type and airline."""
    type_map = _OBJ_MAP.get(aircraft_type)
    if not type_map:
        return str(_XPLANE_ROOT / _DEFAULT)
    relative = type_map.get(airline_icao, type_map["_default"])
    return str(_XPLANE_ROOT / _SCENERY / relative)
