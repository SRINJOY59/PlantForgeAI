"""Tennessee Eastman Process — Tag Topology.

Defines all Measured Variables (MV) and Process Variables (PV) with their
unit areas, display names, and physical units. This is the single source
of truth for tag naming across the simulation, gateway, watcher, and UI.
"""
from __future__ import annotations
from dataclasses import dataclass, field

# ─── Unit Areas ────────────────────────────────────────────────────────────
UNIT_AREAS = [
    "REACTOR",
    "CONDENSER",
    "SEPARATOR",
    "STRIPPER",
    "COMPRESSOR",
    "PRODUCT-SPLIT",
]

@dataclass
class TagDef:
    tag_id: str        # e.g. "REACTOR.T"
    display: str       # e.g. "Reactor Temperature"
    unit_area: str     # one of UNIT_AREAS
    phy_unit: str      # e.g. "°C", "kPa", "%", "kmol/h"
    is_mv: bool = False   # True = manipulated variable (actuator)


# ─── Process Variable (PV) Tags ─────────────────────────────────────────────
PV_TAGS: list[TagDef] = [
    # REACTOR
    TagDef("REACTOR.T",       "Reactor Temperature",          "REACTOR",      "°C"),
    TagDef("REACTOR.P",       "Reactor Pressure",             "REACTOR",      "kPa"),
    TagDef("REACTOR.Level",   "Reactor Level",                "REACTOR",      "%"),
    TagDef("REACTOR.xA",      "Reactor Comp A",               "REACTOR",      "mol%"),
    TagDef("REACTOR.xB",      "Reactor Comp B (Inert)",       "REACTOR",      "mol%"),
    TagDef("REACTOR.xC",      "Reactor Comp C",               "REACTOR",      "mol%"),
    TagDef("REACTOR.xD",      "Reactor Comp D",               "REACTOR",      "mol%"),
    TagDef("REACTOR.xE",      "Reactor Comp E",               "REACTOR",      "mol%"),
    TagDef("REACTOR.xF",      "Reactor Comp F (Byproduct)",   "REACTOR",      "mol%"),
    TagDef("REACTOR.xG",      "Reactor Comp G (Product 1)",   "REACTOR",      "mol%"),
    TagDef("REACTOR.xH",      "Reactor Comp H (Product 2)",   "REACTOR",      "mol%"),
    TagDef("REACTOR.CoolT",   "Reactor Coolant Temperature",  "REACTOR",      "°C"),
    TagDef("REACTOR.HeatDuty","Reactor Heat Duty",            "REACTOR",      "kJ/h"),

    # CONDENSER
    TagDef("CONDENSER.T",     "Condenser Temperature",        "CONDENSER",    "°C"),
    TagDef("CONDENSER.P",     "Condenser Pressure",           "CONDENSER",    "kPa"),
    TagDef("CONDENSER.CoolT", "Condenser Coolant Temp",       "CONDENSER",    "°C"),
    TagDef("CONDENSER.HeatDuty","Condenser Heat Duty",        "CONDENSER",    "kJ/h"),

    # SEPARATOR
    TagDef("SEPARATOR.T",     "Separator Temperature",        "SEPARATOR",    "°C"),
    TagDef("SEPARATOR.P",     "Separator Pressure",           "SEPARATOR",    "kPa"),
    TagDef("SEPARATOR.Level", "Separator Level",              "SEPARATOR",    "%"),
    TagDef("SEPARATOR.xG",    "Separator Liq G Fraction",     "SEPARATOR",    "mol%"),
    TagDef("SEPARATOR.xH",    "Separator Liq H Fraction",     "SEPARATOR",    "mol%"),
    TagDef("SEPARATOR.VapFlow","Separator Vapour Outlet",     "SEPARATOR",    "kmol/h"),
    TagDef("SEPARATOR.LiqFlow","Separator Liquid Outlet",     "SEPARATOR",    "kmol/h"),

    # STRIPPER
    TagDef("STRIPPER.T",      "Stripper Temperature",         "STRIPPER",     "°C"),
    TagDef("STRIPPER.P",      "Stripper Pressure",            "STRIPPER",     "kPa"),
    TagDef("STRIPPER.Level",  "Stripper Base Level",          "STRIPPER",     "%"),
    TagDef("STRIPPER.xG",     "Stripper Product G Fraction",  "STRIPPER",     "mol%"),
    TagDef("STRIPPER.xH",     "Stripper Product H Fraction",  "STRIPPER",     "mol%"),
    TagDef("STRIPPER.Flow",   "Stripper Product Flow",        "STRIPPER",     "kmol/h"),

    # COMPRESSOR
    TagDef("COMPRESSOR.Speed","Compressor Speed",             "COMPRESSOR",   "%"),
    TagDef("COMPRESSOR.Power","Compressor Power",             "COMPRESSOR",   "kW"),
    TagDef("COMPRESSOR.RecycleF","Recycle Valve Flow",        "COMPRESSOR",   "kmol/h"),

    # PRODUCT-SPLIT
    TagDef("PRODUCT-SPLIT.xG",  "Product G Fraction",        "PRODUCT-SPLIT","mol%"),
    TagDef("PRODUCT-SPLIT.xH",  "Product H Fraction",        "PRODUCT-SPLIT","mol%"),
    TagDef("PRODUCT-SPLIT.TotalF","Total Product Flow",       "PRODUCT-SPLIT","kmol/h"),
    TagDef("PRODUCT-SPLIT.Purity","Product Purity (G+H)",    "PRODUCT-SPLIT","mol%"),
]

# ─── Manipulated Variable (MV) Tags ─────────────────────────────────────────
MV_TAGS: list[TagDef] = [
    TagDef("MV.D-FEED",        "D Feed Valve",              "REACTOR",      "%", is_mv=True),
    TagDef("MV.E-FEED",        "E Feed Valve",              "REACTOR",      "%", is_mv=True),
    TagDef("MV.A-FEED",        "A Feed Valve",              "REACTOR",      "%", is_mv=True),
    TagDef("MV.AC-FEED",       "A/C Feed Valve",            "REACTOR",      "%", is_mv=True),
    TagDef("MV.COMP-RECYCLE",  "Compressor Recycle Valve",  "COMPRESSOR",   "%", is_mv=True),
    TagDef("MV.PURGE",         "Purge Valve",               "COMPRESSOR",   "%", is_mv=True),
    TagDef("MV.SEP-LIQ-OUT",   "Sep Liquid Outlet Valve",   "SEPARATOR",    "%", is_mv=True),
    TagDef("MV.STRIP-LIQ-IN",  "Stripper Inlet Valve",      "STRIPPER",     "%", is_mv=True),
    TagDef("MV.STRIP-STEAM",   "Stripper Steam Valve",      "STRIPPER",     "%", is_mv=True),
    TagDef("MV.REACTOR-COOL",  "Reactor Coolant Valve",     "REACTOR",      "%", is_mv=True),
    TagDef("MV.COND-COOL",     "Condenser Coolant Valve",   "CONDENSER",    "%", is_mv=True),
    TagDef("MV.PRODUCT-SPLIT", "Product Split Valve",       "PRODUCT-SPLIT","%", is_mv=True),
]

ALL_TAGS: list[TagDef] = PV_TAGS + MV_TAGS

# ─── Lookup helpers ──────────────────────────────────────────────────────────
TAG_BY_ID: dict[str, TagDef] = {t.tag_id: t for t in ALL_TAGS}
TAGS_BY_AREA: dict[str, list[TagDef]] = {}
for _t in ALL_TAGS:
    TAGS_BY_AREA.setdefault(_t.unit_area, []).append(_t)

TAG_UNITS: dict[str, str] = {t.tag_id: t.phy_unit for t in ALL_TAGS}

# ─── IDV Fault Index ─────────────────────────────────────────────────────────
IDV_TABLE: dict[int, str] = {
    1:  "A/C feed ratio, B composition constant (stream 4) — step",
    2:  "B composition, A/C ratio constant (stream 4) — step",
    3:  "D feed temperature (stream 2) — step",
    4:  "Reactor coolant inlet temperature — step",
    5:  "Condenser coolant inlet temperature — step",
    6:  "A feed loss (stream 1) — step",
    7:  "C header pressure loss — step",
    8:  "A, B, C feed composition (stream 4) — random variation",
    9:  "D feed temperature (stream 2) — random variation",
    10: "C feed temperature (stream 4) — random variation",
    11: "Reactor coolant inlet temperature — random variation",
    12: "Condenser coolant inlet temperature — random variation",
    13: "Reaction kinetics — slow drift",
    14: "Reactor coolant valve stuck",
    15: "Condenser coolant valve stuck",
    16: "Unknown fault 16",
    17: "Unknown fault 17",
    18: "Unknown fault 18",
    19: "Unknown fault 19",
    20: "Unknown fault 20",
    21: "Stream 4 valve position constant",
}

# ─── Neo4j topology for seed script ─────────────────────────────────────────
# Each entry: (source_area, target_area, relation, stream_label)
TEP_CONNECTIONS = [
    # Main process flow
    ("REACTOR",      "CONDENSER",    "FEEDS",        "Stream 8: Reactor Vap Out"),
    ("CONDENSER",    "SEPARATOR",    "FEEDS",        "Stream 8c: Condenser Out"),
    ("SEPARATOR",    "COMPRESSOR",   "FEEDS",        "Stream 9: Sep Vap Out"),
    ("SEPARATOR",    "STRIPPER",     "FEEDS",        "Stream 10: Sep Liq Out"),
    ("COMPRESSOR",   "REACTOR",      "FEEDS",        "Stream 5: Recycle/Purge"),
    ("STRIPPER",     "PRODUCT-SPLIT","FEEDS",        "Stream 11: Stripper Product"),
    # Feed streams into reactor
    ("FEED-A",       "REACTOR",      "CONNECTED_TO", "Stream 1: Feed A"),
    ("FEED-D",       "REACTOR",      "CONNECTED_TO", "Stream 2: Feed D"),
    ("FEED-E",       "REACTOR",      "CONNECTED_TO", "Stream 3: Feed E"),
    ("FEED-AC",      "REACTOR",      "CONNECTED_TO", "Stream 4: Feed A/B/C"),
]

# Equipment nodes for Neo4j
TEP_NODES = [
    {"id": "equip:REACTOR",       "tag": "REACTOR",       "type": "Reactor",            "unit": "TEP"},
    {"id": "equip:CONDENSER",     "tag": "CONDENSER",     "type": "Condenser",          "unit": "TEP"},
    {"id": "equip:SEPARATOR",     "tag": "SEPARATOR",     "type": "Separator",          "unit": "TEP"},
    {"id": "equip:STRIPPER",      "tag": "STRIPPER",      "type": "Stripper",           "unit": "TEP"},
    {"id": "equip:COMPRESSOR",    "tag": "COMPRESSOR",    "type": "Compressor",         "unit": "TEP"},
    {"id": "equip:PRODUCT-SPLIT", "tag": "PRODUCT-SPLIT", "type": "Splitter",           "unit": "TEP"},
    {"id": "equip:FEED-A",        "tag": "FEED-A",        "type": "Line",               "unit": "TEP"},
    {"id": "equip:FEED-D",        "tag": "FEED-D",        "type": "Line",               "unit": "TEP"},
    {"id": "equip:FEED-E",        "tag": "FEED-E",        "type": "Line",               "unit": "TEP"},
    {"id": "equip:FEED-AC",       "tag": "FEED-AC",       "type": "Line",               "unit": "TEP"},
]
