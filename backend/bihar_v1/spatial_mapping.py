"""Explicit point-to-district mapping for gridded precipitation.

District assignment requires authoritative polygon geometry supplied by the caller.
Boundary semantics follow the GeoJSON point-on-surface convention used here: polygon
outer boundaries are included, hole interiors and hole boundaries are excluded.
Points shared by two district polygons are rejected as ambiguous.
"""
from __future__ import annotations

import json
import math
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
        _validate_geometry(geometry)
    return features


def _validate_ring(ring: list[list[float]]) -> None:
    if not isinstance(ring, list) or len(ring) < 4:
        raise ValueError("Polygon rings must contain at least four coordinate pairs")
    for point in ring:
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            raise ValueError("Polygon coordinates must be [longitude, latitude] pairs")
        lon, lat = float(point[0]), float(point[1])
        if not math.isfinite(lon) or not math.isfinite(lat):
            raise ValueError("Polygon coordinates must be finite")
        if not -180 <= lon <= 180 or not -90 <= lat <= 90:
            raise ValueError("Polygon coordinates are outside longitude/latitude ranges")
    if list(ring[0][:2]) != list(ring[-1][:2]):
        raise ValueError("Polygon rings must be closed")


def _validate_geometry(geometry: dict) -> None:
    kind, coordinates = geometry.get("type"), geometry.get("coordinates")
    polygons = [coordinates] if kind == "Polygon" else coordinates
    if not isinstance(polygons, list) or not polygons:
        raise ValueError("Polygon geometry must contain rings")
    for polygon in polygons:
        if not isinstance(polygon, list) or not polygon:
            raise ValueError("Polygon must contain an exterior ring")
        for ring in polygon:
            _validate_ring(ring)


def _point_on_segment(
    x: float, y: float, a: list[float], b: list[float], eps: float = 1e-10
) -> bool:
    ax, ay = float(a[0]), float(a[1])
    bx, by = float(b[0]), float(b[1])
    cross = (x - ax) * (by - ay) - (y - ay) * (bx - ax)
    scale = max(1.0, abs(bx - ax), abs(by - ay))
    if abs(cross) > eps * scale:
        return False
    return (min(ax, bx) - eps <= x <= max(ax, bx) + eps
            and min(ay, by) - eps <= y <= max(ay, by) + eps)


def _point_in_ring(
    longitude: float, latitude: float, ring: list[list[float]], *, boundary: bool = True
) -> bool:
    """Ray-cast a point against a ring, with explicit deterministic boundary handling."""
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        a, b = ring[j], ring[i]
        if _point_on_segment(longitude, latitude, a, b):
            return boundary
        xi, yi = float(b[0]), float(b[1])
        xj, yj = float(a[0]), float(a[1])
        if (yi > latitude) != (yj > latitude):
            intersection_x = (xj - xi) * (latitude - yi) / (yj - yi) + xi
            if longitude < intersection_x:
                inside = not inside
        j = i
    return inside


def _point_in_geometry(longitude: float, latitude: float, geometry: dict) -> bool:
    kind = geometry.get("type")
    coordinates = geometry.get("coordinates")
    if kind == "Polygon":
        rings = coordinates or []
        if not rings or not _point_in_ring(longitude, latitude, rings[0], boundary=True):
            return False
        # A hole is excluded including its boundary.
        return not any(_point_in_ring(longitude, latitude, hole, boundary=True)
                       for hole in rings[1:])
    if kind == "MultiPolygon":
        return any(_point_in_geometry(
            longitude, latitude, {"type": "Polygon", "coordinates": polygon}
        ) for polygon in (coordinates or []))
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
        if not math.isfinite(latitude) or not math.isfinite(longitude):
            raise ValueError("Record coordinates must be finite")
        if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            raise ValueError("Record coordinates are outside latitude/longitude ranges")
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
