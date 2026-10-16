from copy import deepcopy
from random import Random

from c4i_contracts import Entity


def legacy_scenario() -> dict:
    return {
        "scenarioId": "west-coast-demo",
        "version": 1,
        "name": "서해안 모의 상황",
        "bounds": [126.0, 36.4, 127.0, 37.3],
        "initialBounds": [126.15, 36.65, 126.85, 37.10],
        "zones": [],
        "synthetic": True,
    }


def border_scenario() -> dict:
    # Illustrative rectangles on a geographic basemap, not operational boundaries.
    zones = [
        ("west-south", "서부 남측 시연", "land", [126.75, 37.77, 126.9, 37.90]),
        ("west-north", "서부 북측 시연", "land", [126.50, 37.95, 126.64, 38.08]),
        ("central-south", "중부 남측 시연", "land", [127.05, 38.02, 127.18, 38.12]),
        ("central-north", "중부 북측 시연", "land", [127.18, 38.35, 127.35, 38.48]),
        ("east-south", "동부 남측 시연", "land", [128.30, 38.28, 128.42, 38.42]),
        ("east-north", "동부 북측 시연", "land", [128.15, 38.62, 128.28, 38.72]),
        ("west-sea", "서부 연안 시연", "sea", [125.50, 37.60, 125.90, 37.90]),
        ("east-sea", "동부 연안 시연", "sea", [129.00, 38.30, 129.30, 38.60]),
    ]
    return {
        "scenarioId": "border-demo",
        "version": 1,
        "name": "남북 접경 전역 모의 상황",
        "bounds": [125.3, 37.4, 129.5, 38.9],
        "initialBounds": [125.3, 37.4, 129.5, 38.9],
        "synthetic": True,
        "zoneNote": "시연용 구역이며 실제 접경선·작전 구역을 나타내지 않음",
        "zones": [
            {"id": key, "name": name, "domain": domain, "bounds": bounds}
            for key, name, domain, bounds in zones
        ],
    }


def border_entities() -> list[Entity]:
    rng = Random(20261016)
    zones = border_scenario()["zones"]
    kinds = (
        ["tank"] * 40
        + ["armored_vehicle"] * 24
        + ["support_vehicle"] * 20
        + ["uav"] * 12
        + ["naval_vessel"] * 24
    )
    result = []
    for index, kind in enumerate(kinds):
        zone = zones[index % 6] if kind != "naval_vessel" else zones[6 + index % 2]
        side = "friendly" if index % 2 == 0 else "hostile"
        if index % 17 == 0:
            side = "unknown"
        west, south, east, north = zone["bounds"]
        result.append(
            Entity.model_validate(
                {
                    "entityId": f"DEMO-{index + 1:03d}",
                    "label": f"모의 {kind} {index + 1:03d}",
                    "kind": kind,
                    "affiliation": side,
                    "availability": "unknown"
                    if side != "friendly" or index % 5 == 0
                    else "unavailable"
                    if index % 7 == 0
                    else "available",
                    "maintenanceStatus": "unknown"
                    if side != "friendly"
                    else "maintenance"
                    if index % 7 == 0
                    else "serviceable",
                    "status": "inactive" if index % 13 == 0 else "active",
                    "unitId": f"DEMO:{zone['id']}:{side}",
                    "zoneId": zone["id"],
                    "subtype": f"synthetic-{kind}",
                    "source": "synthetic-scenario",
                    "position": {
                        "longitude": rng.uniform(west + 0.01, east - 0.01),
                        "latitude": rng.uniform(south + 0.01, north - 0.01),
                    },
                    "velocity": {
                        "eastMps": 0 if index % 4 == 0 else rng.uniform(-6, 6),
                        "northMps": 0 if index % 4 == 0 else rng.uniform(-6, 6),
                    },
                }
            )
        )
    return result


def get_scenario(scenario_id: str) -> dict:
    if scenario_id == "border-demo":
        return deepcopy(border_scenario())
    if scenario_id == "west-coast-demo":
        return deepcopy(legacy_scenario())
    raise ValueError(f"unknown scenario: {scenario_id}")


def initial_entities() -> list[Entity]:
    # Synthetic equipment on a real geographic map; no operational data.
    specs = [
        ("BLU-T01", "tank", "friendly", "available", 126.585, 36.875, 7, 2),
        ("BLU-T02", "tank", "friendly", "available", 126.610, 36.860, 0, 0),
        ("BLU-T03", "tank", "friendly", "unavailable", 126.635, 36.890, 0, 0),
        ("RED-T01", "tank", "hostile", "unknown", 126.735, 36.925, -4, -2),
        ("RED-T02", "tank", "hostile", "unknown", 126.755, 36.900, -3, 1),
        ("RED-T03", "tank", "hostile", "unknown", 126.715, 36.950, 0, -3),
        ("BLU-S01", "naval_vessel", "friendly", "available", 126.290, 36.890, 0, 5),
        ("RED-S01", "naval_vessel", "hostile", "unknown", 126.250, 36.970, 1, -3),
        ("BLU-A01", "armored_vehicle", "friendly", "available", 126.595, 36.855, 3, 1),
        ("BLU-L01", "support_vehicle", "friendly", "unavailable", 126.615, 36.845, 0, 0),
        ("BLU-U01", "uav", "friendly", "available", 126.640, 36.910, 12, 3),
    ]
    return [
        Entity.model_validate(
            {
                "entityId": eid,
                "label": eid,
                "kind": kind,
                "affiliation": side,
                "availability": availability,
                "unitId": "DEMO-BLUE" if side == "friendly" else "DEMO-RED",
                "subtype": "synthetic-" + kind,
                "maintenanceStatus": (
                    "maintenance" if availability == "unavailable" else "serviceable"
                )
                if side == "friendly"
                else "unknown",
                "source": "synthetic-scenario",
                "position": {"longitude": lon, "latitude": lat},
                "velocity": {"eastMps": east, "northMps": north},
            }
        )
        for eid, kind, side, availability, lon, lat, east, north in specs
    ]
