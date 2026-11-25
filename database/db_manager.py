"""
Database Manager for Delivery Scheduling and Cost Optimizer
Handles SQLite database connection, tables creation, and sample data seeding.
"""

import sqlite3
import os
import pandas as pd
from typing import List, Dict, Any, Optional

DB_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(DB_DIR, "delivery.db")


def get_connection() -> sqlite3.Connection:
    """Returns a SQLite connection with row factory enabled."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initializes all database tables if they do not exist."""
    conn = get_connection()
    cursor = conn.cursor()

    # Depot / Warehouse Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS depot (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            address TEXT NOT NULL,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            open_time_mins INTEGER DEFAULT 480,   -- 08:00 AM in minutes from midnight (8*60)
            close_time_mins INTEGER DEFAULT 1200  -- 08:00 PM in minutes from midnight (20*60)
        )
    """)

    # Fleet / Vehicles Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS vehicles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            vehicle_type TEXT NOT NULL,          -- Bike, Delivery Van, Small Truck
            capacity_kg REAL NOT NULL,          -- Max cargo weight in KG
            fuel_avg_kmpl REAL NOT NULL,        -- KM per Litre of fuel
            fuel_price_per_litre REAL DEFAULT 280.0, -- Default fuel price (PKR)
            fixed_daily_cost REAL DEFAULT 1500.0,    -- Driver day-wage + vehicle maintenance (PKR)
            speed_kmh REAL DEFAULT 35.0         -- Average urban travel speed
        )
    """)

    # Customer Orders Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_name TEXT NOT NULL,
            phone TEXT NOT NULL,
            address TEXT NOT NULL,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            package_weight_kg REAL NOT NULL,
            time_window_start INTEGER NOT NULL,  -- e.g. 540 = 09:00 AM
            time_window_end INTEGER NOT NULL,    -- e.g. 720 = 12:00 PM
            service_time_mins INTEGER DEFAULT 10, -- Time spent at customer stop
            status TEXT DEFAULT 'Pending'        -- Pending, Assigned, Delivered
        )
    """)

    # Optimization History / Summary Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS optimization_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            total_vehicles_used INTEGER,
            total_orders_scheduled INTEGER,
            total_distance_km REAL,
            total_fuel_cost REAL,
            total_fixed_cost REAL,
            total_cost REAL,
            baseline_unoptimized_cost REAL,
            cost_savings_amount REAL,
            cost_savings_pct REAL,
            late_delivery_count INTEGER,
            on_time_delivery_rate REAL
        )
    """)

    # Scheduled Route Stops Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS route_stops (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER,
            vehicle_id INTEGER,
            vehicle_name TEXT,
            stop_sequence INTEGER,
            order_id INTEGER,                   -- NULL if depot stop
            location_name TEXT,
            arrival_mins INTEGER,
            departure_mins INTEGER,
            arrival_time_str TEXT,
            departure_time_str TEXT,
            distance_from_prev_km REAL,
            cumulative_distance_km REAL,
            load_carried_kg REAL,
            FOREIGN KEY (run_id) REFERENCES optimization_runs(id)
        )
    """)

    conn.commit()
    conn.close()


def seed_sample_data(force: bool = False):
    """Populates realistic courier data if tables are empty."""
    init_db()
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM depot")
    depot_count = cursor.fetchone()[0]

    if depot_count == 0 or force:
        if force:
            cursor.execute("DELETE FROM route_stops")
            cursor.execute("DELETE FROM optimization_runs")
            cursor.execute("DELETE FROM orders")
            cursor.execute("DELETE FROM vehicles")
            cursor.execute("DELETE FROM depot")

        # 1. Central Distribution Hub (Lahore Gulberg Depot)
        cursor.execute("""
            INSERT INTO depot (name, address, latitude, longitude, open_time_mins, close_time_mins)
            VALUES (?, ?, ?, ?, ?, ?)
        """, ("Central Courier Hub", "Gulberg III, Main Boulevard, Lahore", 31.5204, 74.3587, 480, 1200))

        # 2. Vehicle Fleet
        vehicles = [
            ("Van-01 (Swift Cargo)", "Delivery Van", 350.0, 11.0, 280.0, 2500.0, 35.0),
            ("Van-02 (City Hauler)", "Delivery Van", 400.0, 10.5, 280.0, 2500.0, 35.0),
            ("Bike-01 (Express Rider)", "Courier Bike", 40.0, 42.0, 280.0, 1200.0, 40.0),
            ("Bike-02 (Flash Courier)", "Courier Bike", 45.0, 40.0, 280.0, 1200.0, 40.0),
            ("Truck-01 (Heavy Freight)", "Small Truck", 1200.0, 7.5, 280.0, 4000.0, 30.0),
        ]
        cursor.executemany("""
            INSERT INTO vehicles (name, vehicle_type, capacity_kg, fuel_avg_kmpl, fuel_price_per_litre, fixed_daily_cost, speed_kmh)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, vehicles)

        # 3. Customer Orders with real coordinates across the city + time windows
        # Note: Minutes from midnight:
        # 540 = 09:00 AM, 660 = 11:00 AM, 720 = 12:00 PM, 840 = 02:00 PM, 960 = 04:00 PM, 1080 = 06:00 PM
        sample_orders = [
            ("Ahmad Logistics Corp", "0300-1122334", "DHA Phase 5, Sector C", 31.4697, 74.4025, 45.0, 540, 720, 15),
            ("Zubair Pharmacy", "0321-4455667", "Model Town, C-Block", 31.4880, 74.3214, 15.0, 570, 750, 10),
            ("Nexus Electronics", "0333-8899001", "Mall Road, Commercial Area", 31.5580, 74.3270, 85.0, 600, 780, 20),
            ("Fatima Boutique", "0302-3344556", "MM Alam Road, Gulberg II", 31.5120, 74.3520, 12.0, 540, 690, 10),
            ("Khaadi Retail Outlet", "0312-5566778", "Packages Mall, Walton Road", 31.4740, 74.3590, 110.0, 660, 840, 25),
            ("Al-Rehman Book Depot", "0345-9988776", "Urdu Bazaar, Anarkali", 31.5710, 74.3120, 30.0, 600, 780, 15),
            ("Dr. Sana Dental Clinic", "0301-7766554", "Johar Town, Phase 1", 31.4680, 74.2750, 8.0, 720, 900, 10),
            ("Metro Hypermarket", "0322-2233445", "Thokar Niaz Baig", 31.4720, 74.2380, 220.0, 600, 840, 30),
            ("Crescent Textile Mills", "0304-4455112", "Kot Lakhpat Industrial Area", 31.4460, 74.3380, 180.0, 660, 900, 25),
            ("Gourmet Foods Kitchen", "0331-6677889", "Faisal Town, Block B", 31.4810, 74.3050, 25.0, 540, 720, 15),
            ("Innovatech Solutions", "0313-1122998", "Cavalry Ground, Commercial", 31.5030, 74.3720, 18.0, 690, 870, 10),
            ("CareFirst Diagnostic Lab", "0324-7788990", "Shadman Market, Sector A", 31.5380, 74.3290, 5.0, 540, 660, 10),
        ]
        cursor.executemany("""
            INSERT INTO orders (customer_name, phone, address, latitude, longitude, package_weight_kg, time_window_start, time_window_end, service_time_mins)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, sample_orders)

        conn.commit()

    conn.close()


def get_depot() -> Dict[str, Any]:
    """Fetches central depot info."""
    init_db()
    conn = get_connection()
    row = conn.execute("SELECT * FROM depot LIMIT 1").fetchone()
    conn.close()
    return dict(row) if row else {}


def get_all_vehicles() -> List[Dict[str, Any]]:
    """Returns list of active vehicles."""
    init_db()
    conn = get_connection()
    rows = conn.execute("SELECT * FROM vehicles").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_orders(status_filter: Optional[str] = None) -> List[Dict[str, Any]]:
    """Returns list of orders, optionally filtered by status."""
    init_db()
    conn = get_connection()
    if status_filter:
        rows = conn.execute("SELECT * FROM orders WHERE status = ?", (status_filter,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM orders").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_order(customer_name: str, phone: str, address: str, lat: float, lon: float,
              weight_kg: float, start_mins: int, end_mins: int, service_time: int = 10) -> int:
    """Inserts a new customer order."""
    init_db()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO orders (customer_name, phone, address, latitude, longitude, package_weight_kg, time_window_start, time_window_end, service_time_mins)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (customer_name, phone, address, lat, lon, weight_kg, start_mins, end_mins, service_time))
    order_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return order_id


def delete_order(order_id: int):
    """Deletes an order by id."""
    conn = get_connection()
    conn.execute("DELETE FROM orders WHERE id = ?", (order_id,))
    conn.commit()
    conn.close()


def add_vehicle(name: str, vtype: str, capacity_kg: float, fuel_avg: float,
                fuel_price: float = 280.0, fixed_cost: float = 2000.0, speed_kmh: float = 35.0) -> int:
    """Adds a new delivery vehicle to fleet."""
    init_db()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO vehicles (name, vehicle_type, capacity_kg, fuel_avg_kmpl, fuel_price_per_litre, fixed_daily_cost, speed_kmh)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (name, vtype, capacity_kg, fuel_avg, fuel_price, fixed_cost, speed_kmh))
    vid = cursor.lastrowid
    conn.commit()
    conn.close()
    return vid


def delete_vehicle(vehicle_id: int):
    """Removes a vehicle by id."""
    conn = get_connection()
    conn.execute("DELETE FROM vehicles WHERE id = ?", (vehicle_id,))
    conn.commit()
    conn.close()


def save_optimization_run(summary: Dict[str, Any], routes: List[Dict[str, Any]]) -> int:
    """Saves complete optimization run results to database."""
    init_db()
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO optimization_runs (
            total_vehicles_used, total_orders_scheduled, total_distance_km,
            total_fuel_cost, total_fixed_cost, total_cost,
            baseline_unoptimized_cost, cost_savings_amount, cost_savings_pct,
            late_delivery_count, on_time_delivery_rate
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        summary.get("total_vehicles_used", 0),
        summary.get("total_orders_scheduled", 0),
        summary.get("total_distance_km", 0.0),
        summary.get("total_fuel_cost", 0.0),
        summary.get("total_fixed_cost", 0.0),
        summary.get("total_cost", 0.0),
        summary.get("baseline_unoptimized_cost", 0.0),
        summary.get("cost_savings_amount", 0.0),
        summary.get("cost_savings_pct", 0.0),
        summary.get("late_delivery_count", 0),
        summary.get("on_time_delivery_rate", 100.0),
    ))
    run_id = cursor.lastrowid

    # Insert individual stops
    for stop in routes:
        cursor.execute("""
            INSERT INTO route_stops (
                run_id, vehicle_id, vehicle_name, stop_sequence, order_id,
                location_name, arrival_mins, departure_mins, arrival_time_str,
                departure_time_str, distance_from_prev_km, cumulative_distance_km, load_carried_kg
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            run_id,
            stop.get("vehicle_id"),
            stop.get("vehicle_name"),
            stop.get("stop_sequence"),
            stop.get("order_id"),
            stop.get("location_name"),
            stop.get("arrival_mins"),
            stop.get("departure_mins"),
            stop.get("arrival_time_str"),
            stop.get("departure_time_str"),
            stop.get("distance_from_prev_km", 0.0),
            stop.get("cumulative_distance_km", 0.0),
            stop.get("load_carried_kg", 0.0),
        ))

    conn.commit()
    conn.close()
    return run_id


def get_latest_run_summary() -> Optional[Dict[str, Any]]:
    """Returns the most recent optimization run summary."""
    init_db()
    conn = get_connection()
    row = conn.execute("SELECT * FROM optimization_runs ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    return dict(row) if row else None


def get_run_stops(run_id: int) -> List[Dict[str, Any]]:
    """Returns all stops recorded for a specific run."""
    init_db()
    conn = get_connection()
    rows = conn.execute("SELECT * FROM route_stops WHERE run_id = ? ORDER BY vehicle_id, stop_sequence", (run_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

