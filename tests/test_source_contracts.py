"""Source normalization is explicit and independent of graph/LLM infrastructure."""

import math

import pytest
from battlefield_ontology import SourceRef, normalize_equipment, stable_hash
from pydantic import ValidationError


def test_source_identity_includes_system_dataset_epoch_and_record_type():
    ref = SourceRef(
        system_id="atcis", dataset_id="demo", epoch_id="e1", record_type="equipment", native_id="1"
    )
    assert ref.key != ref.model_copy(update={"system_id": "knccs"}).key
    assert ref.key != ref.model_copy(update={"epoch_id": "e2"}).key
    assert ref.key != ref.model_copy(update={"record_type": "unit"}).key
    assert ref.key != ref.model_copy(update={"dataset_id": "other"}).key
    with pytest.raises(ValidationError):
        SourceRef(
            system_id="atcis",
            dataset_id="demo",
            epoch_id="",
            record_type="equipment",
            native_id="1",
        )


def test_atcis_codes_and_coordinates_are_not_inferred_from_names():
    item = normalize_equipment(
        "atcis",
        {
            "trackKey": "a",
            "ownerUnitCode": "u",
            "classCode": "TANK",
            "readyCode": "R",
            "sideCode": "F",
            "pos": {"lon": 127, "lat": 38},
            "velocity": {"eastMps": 3, "northMps": 4},
        },
    )
    assert (item.native_id, item.unit_id, item.kind, item.availability) == (
        "a",
        "u",
        "tank",
        "available",
    )
    assert item.position == {"longitude": 127, "latitude": 38}
    assert item.velocity == {"eastMps": 3, "northMps": 4}
    unknown = normalize_equipment(
        "atcis",
        {"trackKey": "a", "classCode": "FUTURE", "readyCode": "?", "label": "available tank"},
    )
    assert (unknown.kind, unknown.availability) == ("unknown", "unknown")
    assert unknown.position is None
    assert unknown.warnings


@pytest.mark.parametrize("course,east,north", [(0, 0, 1), (90, 1, 0), (180, 0, -1), (270, -1, 0)])
def test_knccs_knots_and_north_clockwise_course(course, east, north):
    item = normalize_equipment(
        "knccs",
        {
            "contactNo": "k",
            "platformCategory": "SURFACE",
            "serviceability": "READY",
            "geo": {"latitude": 37, "longitude": 126},
            "motion": {"courseDeg": course, "speedKnots": 1},
        },
    )
    assert item.kind == "naval_vessel"
    assert item.position == {"longitude": 126, "latitude": 37}
    assert item.velocity["eastMps"] == pytest.approx(east * 1852 / 3600, abs=1e-10)
    assert item.velocity["northMps"] == pytest.approx(north * 1852 / 3600, abs=1e-10)


def test_air_is_not_automatically_an_unmanned_aircraft():
    raw = {"contactNo": "k", "platformCategory": "AIR"}
    assert normalize_equipment("knccs", raw).kind == "unknown"
    assert normalize_equipment("knccs", {**raw, "aircraftType": "UNMANNED"}).kind == "uav"
    with pytest.raises(ValueError):
        normalize_equipment("untrusted", raw)


@pytest.mark.parametrize("position", [{"lon": 200, "lat": 38}, {"lon": 127, "lat": math.nan}])
def test_invalid_coordinates_are_not_changed_to_zero(position):
    with pytest.raises(ValueError):
        normalize_equipment("atcis", {"trackKey": "a", "pos": position})


@pytest.mark.parametrize(
    "patch",
    [
        {"velocity": {"eastMps": 1}},
        {"velocity": {"eastMps": 1000, "northMps": 0}},
        {"pos": {"lon": 127}},
    ],
)
def test_malformed_native_geometry_is_rejected_before_simulation(patch):
    with pytest.raises(ValueError):
        normalize_equipment("atcis", {"trackKey": "a", **patch})


def test_stable_hash_ignores_live_data_but_not_identity_scope():
    export = {
        "systemId": "atcis",
        "datasetId": "d",
        "epochId": "e",
        "units": [{"unitId": "u", "parentId": None}],
        "equipment": [
            {
                "nativeId": "a",
                "unitId": "u",
                "kind": "tank",
                "exerciseAssetRef": "X",
                "position": {"longitude": 127, "latitude": 38},
                "availability": "available",
            }
        ],
    }
    changed = {
        **export,
        "sourceTime": "later",
        "equipment": [
            {
                **export["equipment"][0],
                "position": {"longitude": 128, "latitude": 38},
                "availability": "unavailable",
            }
        ],
    }
    assert stable_hash(export) == stable_hash(changed)
    assert stable_hash(export) != stable_hash({**export, "epochId": "e2"})
    assert stable_hash(export) != stable_hash(
        {**export, "equipment": [{**export["equipment"][0], "unitId": "v"}]}
    )
