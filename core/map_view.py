"""
Map Visualization Module
Generates interactive OpenStreetMap / Folium maps and Matplotlib route graphs.
No API keys required.
"""

from typing import List, Dict, Any, Optional

# Distinct bright colors for vehicles
VEHICLE_COLORS = [
    "#1E40AF",  # Blue
    "#059669",  # Emerald Green
    "#D97706",  # Amber
    "#7C3AED",  # Purple
    "#DC2626",  # Crimson Red
    "#0891B2",  # Cyan
    "#DB2777",  # Pink
]


def create_folium_route_map(
    depot: Dict[str, Any],
    vehicle_routes: Dict[int, List[Dict[str, Any]]],
    orders: List[Dict[str, Any]]
):
    """
    Builds an interactive Folium map showing depots, stops, and vehicle routes
    using standard OpenStreetMap tiles (100% free, no API key required).
    """
    try:
        import folium
    except ImportError:
        return None

    depot_lat = float(depot.get("latitude", 31.5204))
    depot_lon = float(depot.get("longitude", 74.3587))

    # Create map with NO default tiles, then add OpenStreetMap manually
    # This prevents folium from injecting CartoDB/paid tiles
    fmap = folium.Map(
        location=[depot_lat, depot_lon],
        zoom_start=12,
        tiles=None  # Disable ALL default tiles
    )
    # Add official OpenStreetMap tiles explicitly (100% free, no API key)
    folium.TileLayer(
        tiles="https://tile.openstreetmap.org/{z}/{x}/{y}.png",
        attr="&copy; <a href='https://www.openstreetmap.org/copyright'>OpenStreetMap</a> contributors",
        name="OpenStreetMap",
        control=False
    ).add_to(fmap)

    # 1. Add Depot Marker (Central Warehouse)
    depot_popup = f"""
    <div style='font-family: Arial, sans-serif; min-width: 180px;'>
        <h4 style='margin:0 0 6px 0; color:#1E3A8A;'>🏢 {depot.get('name', 'Depot')}</h4>
        <p style='margin:0; font-size:12px; color:#555;'><b>Address:</b> {depot.get('address', 'N/A')}</p>
        <p style='margin:4px 0 0 0; font-size:12px; color:#555;'><b>Hub Operating Hours:</b> 08:00 AM - 08:00 PM</p>
    </div>
    """
    folium.Marker(
        location=[depot_lat, depot_lon],
        popup=folium.Popup(depot_popup, max_width=300),
        tooltip="🏢 Central Distribution Depot",
        icon=folium.Icon(color="red", icon="home", prefix="fa")
    ).add_to(fmap)

    # 2. Add vehicle routes and stop markers
    color_idx = 0
    for v_id, stops in vehicle_routes.items():
        customer_stops = [s for s in stops if s.get("order_id") is not None]
        if not customer_stops:
            continue

        color = VEHICLE_COLORS[color_idx % len(VEHICLE_COLORS)]
        color_idx += 1

        v_name = stops[0].get("vehicle_name", f"Vehicle #{v_id}")

        # Coordinates path: Depot -> Stop 1 -> Stop 2 ... -> Return Depot
        route_coords = []
        for s in stops:
            lat = s.get("latitude")
            lon = s.get("longitude")
            if lat is not None and lon is not None:
                route_coords.append((float(lat), float(lon)))

        # Draw vehicle polyline
        if len(route_coords) > 1:
            folium.PolyLine(
                locations=route_coords,
                color=color,
                weight=5,
                opacity=0.85,
                tooltip=f"Route: {v_name}"
            ).add_to(fmap)

        # Draw Customer Stop Markers
        for s in stops:
            if s.get("order_id") is None:
                continue  # Skip depot returns

            lat = s.get("latitude")
            lon = s.get("longitude")
            if lat is None or lon is None:
                continue

            seq = s.get("stop_sequence", 1)
            cust_name = s.get("location_name", "Customer")
            addr = s.get("address", "")
            arr_time = s.get("arrival_time_str", "")
            dep_time = s.get("departure_time_str", "")
            load = s.get("load_carried_kg", 0)

            popup_html = f"""
            <div style='font-family: Arial, sans-serif; min-width: 200px;'>
                <div style='background-color:{color}; color:white; padding:4px 8px; border-radius:4px; font-weight:bold;'>
                    Stop #{seq} - {v_name}
                </div>
                <h4 style='margin:8px 0 4px 0; color:#111;'>{cust_name}</h4>
                <p style='margin:0; font-size:12px; color:#666;'>📍 {addr}</p>
                <hr style='margin:6px 0; border:0; border-top:1px solid #ddd;'>
                <p style='margin:2px 0; font-size:12px;'><b>🕒 Scheduled Arrival:</b> {arr_time}</p>
                <p style='margin:2px 0; font-size:12px;'><b>⏱️ Departure:</b> {dep_time}</p>
                <p style='margin:2px 0; font-size:12px;'><b>📦 Current Load:</b> {load} kg</p>
            </div>
            """

            folium.CircleMarker(
                location=[float(lat), float(lon)],
                radius=11,
                color="#ffffff",
                weight=2,
                fill=True,
                fill_color=color,
                fill_opacity=0.95,
                tooltip=f"Stop #{seq}: {cust_name} ({arr_time})",
                popup=folium.Popup(popup_html, max_width=320)
            ).add_to(fmap)

    return fmap


def create_matplotlib_route_plot(
    depot: Dict[str, Any],
    vehicle_routes: Dict[int, List[Dict[str, Any]]]
):
    """
    High-contrast 2D geometric route network graph with custom stop markers.
    """
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        return None

    fig, ax = plt.subplots(figsize=(10, 6), dpi=100)

    depot_lat = float(depot.get("latitude", 31.5204))
    depot_lon = float(depot.get("longitude", 74.3587))

    # Plot depot
    ax.scatter([depot_lon], [depot_lat], c="#DC2626", s=280, marker="s", label=f"Central Depot: {depot.get('name')}", zorder=6, edgecolors="black", linewidths=1.5)

    color_idx = 0
    for v_id, stops in vehicle_routes.items():
        customer_stops = [s for s in stops if s.get("order_id") is not None]
        if not customer_stops:
            continue

        color = VEHICLE_COLORS[color_idx % len(VEHICLE_COLORS)]
        color_idx += 1
        v_name = stops[0].get("vehicle_name", f"Vehicle #{v_id}")

        lons = [float(s["longitude"]) for s in stops]
        lats = [float(s["latitude"]) for s in stops]

        ax.plot(lons, lats, color=color, linewidth=2.5, linestyle="-", label=v_name, alpha=0.9, zorder=3)
        ax.scatter(lons[1:-1], lats[1:-1], color=color, s=110, edgecolors="white", linewidths=1.5, zorder=5)

        for s in customer_stops:
            ax.annotate(
                f" #{s['stop_sequence']}",
                (float(s["longitude"]), float(s["latitude"])),
                fontsize=9,
                fontweight="bold",
                color="#0f172a"
            )

    ax.set_title("Multi-Vehicle Dispatch Network & Trajectories", fontsize=13, fontweight="bold", pad=12)
    ax.set_xlabel("Longitude (GPS)", fontsize=10)
    ax.set_ylabel("Latitude (GPS)", fontsize=10)
    ax.grid(True, linestyle="--", alpha=0.4)
    ax.legend(loc="best", fontsize=9, framealpha=0.9)
    plt.tight_layout()

    return fig
