from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel


class Model(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, extra="forbid", allow_inf_nan=False
    )

    def public(self) -> dict:
        return self.model_dump(mode="json", by_alias=True)


class Kind(StrEnum):
    tank = "tank"
    naval_vessel = "naval_vessel"
    armored_vehicle = "armored_vehicle"
    support_vehicle = "support_vehicle"
    uav = "uav"
    unknown = "unknown"


class Affiliation(StrEnum):
    friendly = "friendly"
    hostile = "hostile"
    unknown = "unknown"


class Availability(StrEnum):
    available = "available"
    unavailable = "unavailable"
    unknown = "unknown"


class Position(Model):
    longitude: float = Field(ge=-180, le=180)
    latitude: float = Field(ge=-85, le=85)


class Velocity(Model):
    east_mps: float = Field(default=0, ge=-200, le=200)
    north_mps: float = Field(default=0, ge=-200, le=200)


class Entity(Model):
    entity_id: str = Field(min_length=1, max_length=64)
    kind: Kind = Kind.unknown
    label: str = Field(max_length=120)
    affiliation: Affiliation = Affiliation.unknown
    availability: Availability = Availability.unknown
    availability_reason: str | None = Field(default=None, max_length=300)
    subtype: str | None = Field(default=None, max_length=80)
    unit_id: str | None = Field(default=None, max_length=64)
    zone_id: str | None = Field(default=None, max_length=64)
    maintenance_status: Literal["serviceable", "maintenance", "unknown"] = "unknown"
    observed_at: str | None = Field(default=None, max_length=64)
    source: str | None = Field(default=None, max_length=120)
    position: Position
    velocity: Velocity = Field(default_factory=Velocity)
    status: Literal["active", "inactive", "unknown"] = "active"
    revision: int = 0
    updated_at: str = ""


class EntityPatch(Model):
    velocity: Velocity | None = None
    availability: Availability | None = None
    availability_reason: str | None = Field(default=None, max_length=300)
    status: Literal["active", "inactive", "unknown"] | None = None
    maintenance_status: Literal["serviceable", "maintenance", "unknown"] | None = None

    @model_validator(mode="after")
    def nonnull_values(self):
        for name in self.model_fields_set - {"availability_reason"}:
            if getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        return self


class EntityFilter(Model):
    kind: Kind | None = None
    affiliation: Affiliation | None = None
    availability: Availability | None = None
    status: Literal["active", "inactive", "unknown"] | None = None
    maintenance_status: Literal["serviceable", "maintenance", "unknown"] | None = None
    unit_id: str | None = None
    zone_id: str | None = None
    bbox: Annotated[list[float], Field(min_length=4, max_length=4)] | None = None

    @model_validator(mode="after")
    def valid_bbox(self):
        if self.bbox is not None:
            west, south, east, north = self.bbox
            if not (-180 <= west <= east <= 180 and -85 <= south <= north <= 85):
                raise ValueError("bbox must be west,south,east,north without antimeridian crossing")
        return self

    def matches(self, entity: Entity) -> bool:
        for name in (
            "kind",
            "affiliation",
            "availability",
            "status",
            "maintenance_status",
            "unit_id",
            "zone_id",
        ):
            if getattr(self, name) is not None and getattr(self, name) != getattr(entity, name):
                return False
        if self.bbox:
            west, south, east, north = self.bbox
            return (
                west <= entity.position.longitude <= east
                and south <= entity.position.latitude <= north
            )
        return True
