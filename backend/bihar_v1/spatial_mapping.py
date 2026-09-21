"""Explicit point-to-district mapping for gridded precipitation.

District assignment requires authoritative polygon geometry supplied by the caller.
No hard-coded geographic approximation is used.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable


def load_district_features(path: str | Path) -> list[dict]:
    """Load and validate a GeoJSON FeatureCollection of district polygons."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("type") != "FeatureCollection":
        raise ValueError("District boundary file must be a GeoJSON FeatureCollection")
    features = payload.get("features")
    if not isinstance(features, list) or not features:
        raise ValueError("District boundary file contains no features")
    for feature in features:
        if feature.get("type") != "Feature":
            raise ValueError("District boundary contains a non-Feature entry")
        properties = feature.get("properties") or {}
        if not str(properties.get("district") or "").strip():
            raise ValueError("Every district feature must contain a district property")
        geometry = feature.get("geometry") or {}
        if geometry.get("type") not in {"Polygon", "MultiPolygon"}:
            raise ValueError("District boundary geometry must be Polygon or MultiPolygon")
    return features


def _point_in_ring(longitude: float, latitude: float, ring: list[list[float]]) -> bool:
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i]
        xj, yj = ring[j]
        intersects = ((yi > latitude) != (yj > latitude)) and (
            longitude < (xj - xi) * (latitude - yi) / ((yj - yi) or 1e-15) + xi
        )
        if intersects:
            inside = not inside
        j = i
    return inside


def _point_in_geometry(longitude: float, latitude: float, geometry: dict) -> bool:
    kind = geometry.get("type")
    coordinates = geometry.get("coordinates")
    if kind == "Polygon":
        rings = coordinates or []
        if not rings or not _point_in_ring(longitude, latitude, rings[0]):
            return False
        return not any(_point_in_ring(longitude, latitude, hole) for hole in rings[1:])
    if kind == "MultiPolygon":
        return any(_point_in_geometry(longitude, latitude, {"type": "Polygon", "coordinates": polygon})
                   for polygon in (coordinates or []))
    raise ValueError(f"Unsupported GeoJSON geometry type: {kind}")


def assign_districts(
    records: Iterable[dict],
    district_features: Iterable[dict],
) -> list[dict]:
    """Attach district names to precipitation points using GeoJSON polygons."""
    features = list(district_features)
    output = []
    for record in records:
        latitude = float(record["latitude"])
        longitude = float(record["longitude"])
        matches = []
        for feature in features:
            geometry = feature.get("geometry", {})
            if _point_in_geometry(longitude, latitude, geometry):
                name = feature.get("properties", {}).get("district")
                if name:
                    matches.append(str(name).strip().lower().replace(" ", "_"))
        if len(matches) > 1:
            raise ValueError("Point intersects multiple district polygons")
        item = dict(record)
        item["district"] = matches[0] if matches else None
        output.append(item)
    return output
