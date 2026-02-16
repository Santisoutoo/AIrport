from pathlib import Path

_XPLANE_ROOT = Path(__file__).resolve().parents[6]

_SCENERY = "Resources/default scenery/sim objects/apt_aircraft"

_OBJ_MAP = {
    "A320": f"{_SCENERY}/jet/A320_VLG/A320_VLG_static.obj",
    "A321": f"{_SCENERY}/jet/A320_VLG/A320_VLG_static.obj",
    "B738": f"{_SCENERY}/jet/B738_RYR/B738_RYR_static.obj",
    "B737": f"{_SCENERY}/jet/B738_RYR/B738_RYR_static.obj",
    "E190": f"{_SCENERY}/jet/CRJ1_AFR/CRJ1_AFR_static.obj",
    "C172": f"{_SCENERY}/prop/C172/C172_static.obj",
    "PA28": f"{_SCENERY}/prop/C172/C172_static.obj",
}

_DEFAULT = f"{_SCENERY}/jet/A320_VLG/A320_VLG_static.obj"


def get_obj_path(aircraft_type: str) -> str:
    """Return the absolute path to the .obj for the given aircraft type."""
    relative = _OBJ_MAP.get(aircraft_type, _DEFAULT)
    return str(_XPLANE_ROOT / relative)
