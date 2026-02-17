# Aircraft performance data
AIRCRAFT_DATA = {
    "A320": {"speed": 450, "equipment": "SDE2E3FGHIJ1RWXY", "transponder": "LB1D1", "wtc": "M"},
    "A321": {"speed": 450, "equipment": "SDE2E3FGHIJ1RWXY", "transponder": "LB1D1", "wtc": "M"},
    "B738": {"speed": 460, "equipment": "SDE2E3FGHIJ1RWXY", "transponder": "LB1D1", "wtc": "M"},
    "B737": {"speed": 455, "equipment": "SDE2E3FGHIJ1RWXY", "transponder": "LB1D1", "wtc": "M"},
    "C172": {"speed": 120, "equipment": "SDFGY", "transponder": "S", "wtc": "L"},
    "PA28": {"speed": 110, "equipment": "SDFY", "transponder": "S", "wtc": "L"},
    "E190": {"speed": 470, "equipment": "SDE2E3FGHIJ1RWXY", "transponder": "LB1D1", "wtc": "M"},
}

# Spanish airports with alternates
AIRPORT_DATA = {
    "LEST": {"name": "Santiago", "alternates": ["LECO", "LEVX"], "elevation": 1213},
    "LEBL": {"name": "Barcelona", "alternates": ["LEGE", "LERS"], "elevation": 12},
    "LEMD": {"name": "Madrid Barajas", "alternates": ["LETO", "LECU"], "elevation": 2000},
    "LECO": {"name": "A Coruña", "alternates": ["LEST", "LEVX"], "elevation": 326},
    "LEVX": {"name": "Vigo", "alternates": ["LEST", "LECO"], "elevation": 856},
    "LEGE": {"name": "Girona", "alternates": ["LEBL", "LFMP"], "elevation": 468},
    "LERS": {"name": "Reus", "alternates": ["LEBL", "LEGE"], "elevation": 233},
    "LEPA": {"name": "Palma Mallorca", "alternates": ["LEIB", "LEMH"], "elevation": 27},
    "LEVC": {"name": "Valencia", "alternates": ["LEAL", "LEBL"], "elevation": 240},
    "LEAL": {"name": "Alicante", "alternates": ["LEVC", "LELC"], "elevation": 141},
    "LEZL": {"name": "Sevilla", "alternates": ["LEMG", "LEMD"], "elevation": 112},
    "LEMG": {"name": "Málaga", "alternates": ["LEZL", "LEGR"], "elevation": 52},
}

# Approximate distances between airports (nm)
DISTANCES = {
    ("LEST", "LEBL"): 480,
    ("LEST", "LEMD"): 320,
    ("LEST", "LECO"): 35,
    ("LEBL", "LEMD"): 270,
    ("LEBL", "LEPA"): 130,
    ("LEMD", "LEVC"): 160,
    ("LEMD", "LEZL"): 220,
    ("LEMD", "LEMG"): 260,
    ("LEVC", "LEBL"): 160,
    ("LEAL", "LEBL"): 250,
    ("LEZL", "LEBL"): 500,
}

# Common pilot names for random generation
PILOT_NAMES = [
    "GARCIA MARTINEZ", "RODRIGUEZ LOPEZ", "FERNANDEZ SANCHEZ",
    "GONZALEZ PEREZ", "MARTIN GOMEZ", "RUIZ DIAZ", "HERNANDEZ MUÑOZ",
    "ALVAREZ ROMERO", "JIMENEZ TORRES", "MORENO NAVARRO"
]
