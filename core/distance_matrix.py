"""
Distance and Time Calculation Module
Computes distance and duration matrices between locations using Haversine formula
with realistic urban road curvature factors (OpenStreetMap compatible).
"""

import math
from typing import List, Tuple, Dict, Any


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculates great-circle distance between two GPS points using the Haversine formula.
    Returns distance in kilometers.
    """
    R = 6371.0  # Earth's radius in km

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (math.sin(delta_phi / 2.0) ** 2 +
         math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2)
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))

    # Road network winding factor (Manhattan/urban grid detour factor ~1.35x)
    straight_line_dist = R * c
    road_dist = straight_line_dist * 1.35
    return round(road_dist, 2)


def build_distance_and_time_matrices(
    locations: List[Dict[str, Any]],
    avg_speed_kmh: float = 35.0
) -> Tuple[List[List[float]], List[List[int]]]:
    """
    Builds NxN distance matrix (in km) and travel duration matrix (in minutes)
    for a list of locations where index 0 is always the Depot.

    Args:
        locations: List of dicts, each containing 'latitude' and 'longitude'.
        avg_speed_kmh: Average fleet velocity in km/h.

    Returns:
        (distance_matrix_km, duration_matrix_minutes)
    """
    n = len(locations)
    distance_matrix = [[0.0 for _ in range(n)] for _ in range(n)]
    duration_matrix = [[0 for _ in range(n)] for _ in range(n)]

    for i in range(n):
        for j in range(n):
            if i == j:
                distance_matrix[i][j] = 0.0
                duration_matrix[i][j] = 0
            else:
                dist = haversine_distance_km(
                    locations[i]["latitude"], locations[i]["longitude"],
                    locations[j]["latitude"], locations[j]["longitude"]
                )
                distance_matrix[i][j] = dist
                # Transit time in minutes: (distance / speed) * 60
                travel_mins = int(math.ceil((dist / avg_speed_kmh) * 60.0))
                # Minimum 3 mins between distinct stops in city traffic
                travel_mins = max(travel_mins, 3) if dist > 0 else 0
                duration_matrix[i][j] = travel_mins

    return distance_matrix, duration_matrix


def format_minutes_to_time(minutes_from_midnight: int) -> str:
    """Converts minutes (e.g. 570) to readable AM/PM string ('09:30 AM')."""
    hours = (minutes_from_midnight // 60) % 24
    mins = minutes_from_midnight % 60
    period = "AM" if hours < 12 else "PM"
    display_hour = hours if 1 <= hours <= 12 else (hours - 12 if hours > 12 else 12)
    return f"{display_hour:02d}:{mins:02d} {period}"

