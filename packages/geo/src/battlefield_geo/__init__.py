from math import atan2, degrees, hypot

from c4i_contracts import Entity, Position
from pyproj import Geod

GEOD = Geod(ellps="WGS84")


def motion(entity: Entity) -> tuple[float, float]:
    velocity = entity.velocity
    return hypot(velocity.east_mps, velocity.north_mps), degrees(
        atan2(velocity.east_mps, velocity.north_mps)
    ) % 360


def destination(position: Position, bearing: float, distance: float) -> Position:
    longitude, latitude, _ = GEOD.fwd(position.longitude, position.latitude, bearing, distance)
    return Position(longitude=longitude, latitude=latitude)


def advance(entity: Entity, seconds: float) -> Entity:
    if seconds < 0:
        raise ValueError("seconds must be nonnegative")
    speed, bearing = motion(entity)
    if entity.status != "active" or not speed:
        return entity.model_copy(deep=True)
    return entity.model_copy(
        update={"position": destination(entity.position, bearing, speed * seconds)}
    )


def decorate(entity: Entity) -> dict:
    speed, bearing = motion(entity)
    moving = speed > 0 and entity.status == "active"
    return {
        **entity.public(),
        "speedMps": speed,
        "bearingDegrees": bearing if moving else None,
        "displayVector": {
            "horizonSeconds": 30,
            "endPosition": destination(entity.position, bearing, speed * 30).public(),
        }
        if moving
        else None,
    }


def measure(a: Position, b: Position) -> dict:
    bearing, _, distance = GEOD.inv(a.longitude, a.latitude, b.longitude, b.latitude)
    return {
        "distanceMeters": distance,
        "bearingDegrees": bearing % 360,
        "algorithm": "pyproj.Geod/WGS84",
    }
