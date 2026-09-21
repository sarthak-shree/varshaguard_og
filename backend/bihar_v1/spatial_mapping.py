"""Explicit point-to-district mapping for gridded precipitation.

District assignment requires authoritative polygon geometry supplied by the caller.
No hard-coded geographic approximation is used.
"""
from __future__ import annotations

from typing import Iterable


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
        return bool(rings) and _point_in_ring(longitude, latitude, rings[0])
    if kind == "MultiPolygon":
        return any(
            polygon and _point_in_ring(longitude, latitude, polygon[0])
            for polygon in (coordinates or [])
        )
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
