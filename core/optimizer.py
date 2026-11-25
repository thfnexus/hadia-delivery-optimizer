"""
Route Optimization Engine using Google OR-Tools
Solves the Capacitated Vehicle Routing Problem with Time Windows (CVRPTW).
Allocates deliveries to vehicles subject to capacity and time restrictions.
"""

from typing import List, Dict, Any, Tuple, Optional
import math
from core.distance_matrix import build_distance_and_time_matrices, format_minutes_to_time

# We attempt to import ortools; if still installing or fallback needed, graceful fallback is provided.
try:
    from ortools.constraint_solver import routing_enums_pb2
    from ortools.constraint_solver import pywrapcp
    ORTOOLS_AVAILABLE = True
except ImportError:
    ORTOOLS_AVAILABLE = False


def solve_cvrptw(
    depot: Dict[str, Any],
    vehicles: List[Dict[str, Any]],
    orders: List[Dict[str, Any]],
    time_limit_seconds: int = 5
) -> Dict[str, Any]:
    """
    Main entry point for Route Optimization.
    Assigns deliveries to vehicles subject to:
      1. Vehicle cargo capacity (weight constraint in KG)
      2. Customer delivery time windows [start_time, end_time]
      3. Minimization of total distance and operational cost.

    Returns:
        Dict containing:
            - success: bool
            - routes: List of route stop dictionaries
            - vehicle_routes: Dict[vehicle_id, list of stops]
            - unassigned_orders: List of order IDs that couldn't fit
            - summary: Metric summary dict
    """
    if not orders:
        return {
            "success": False,
            "message": "No customer orders provided for optimization.",
            "routes": [],
            "vehicle_routes": {},
            "unassigned_orders": [],
            "summary": {}
        }

    if not vehicles:
        return {
            "success": False,
            "message": "No delivery vehicles available in fleet.",
            "routes": [],
            "vehicle_routes": {},
            "unassigned_orders": [o["id"] for o in orders],
            "summary": {}
        }

    # Node 0 is Depot, Nodes 1..N are Orders
    all_locations = [depot] + orders
    distance_matrix, duration_matrix = build_distance_and_time_matrices(all_locations)

    num_locations = len(all_locations)
    num_vehicles = len(vehicles)
    depot_index = 0

    vehicle_capacities = [int(v["capacity_kg"]) for v in vehicles]
    demands = [0] + [int(o["package_weight_kg"]) for o in orders]
    service_times = [0] + [int(o.get("service_time_mins", 10)) for o in orders]

    # Time windows [start, end]
    time_windows = [(depot.get("open_time_mins", 480), depot.get("close_time_mins", 1200))]
    for o in orders:
        time_windows.append((int(o["time_window_start"]), int(o["time_window_end"])))

    # Use OR-Tools if available
    if ORTOOLS_AVAILABLE:
        return _solve_with_ortools(
            depot=depot,
            vehicles=vehicles,
            orders=orders,
            all_locations=all_locations,
            distance_matrix=distance_matrix,
            duration_matrix=duration_matrix,
            demands=demands,
            service_times=service_times,
            time_windows=time_windows,
            vehicle_capacities=vehicle_capacities,
            time_limit_seconds=time_limit_seconds
        )
    else:
        # Smart Heuristic Greedy Fallback if OR-Tools is loading
        return _solve_with_greedy_heuristic(
            depot=depot,
            vehicles=vehicles,
            orders=orders,
            all_locations=all_locations,
            distance_matrix=distance_matrix,
            duration_matrix=duration_matrix,
            demands=demands,
            service_times=service_times,
            time_windows=time_windows,
            vehicle_capacities=vehicle_capacities
        )


def _solve_with_ortools(
    depot, vehicles, orders, all_locations,
    distance_matrix, duration_matrix, demands, service_times,
    time_windows, vehicle_capacities, time_limit_seconds
) -> Dict[str, Any]:
    """Uses Google OR-Tools Constraint Programming Routing Engine."""
    num_locations = len(all_locations)
    num_vehicles = len(vehicles)
    depot_index = 0

    manager = pywrapcp.RoutingIndexManager(num_locations, num_vehicles, depot_index)
    routing = pywrapcp.RoutingModel(manager)

    # 1. Distance transit callback
    def distance_callback(from_index, to_index):
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        # Multiply by 100 to work in integer meters
        return int(distance_matrix[from_node][to_node] * 100)

    transit_callback_index = routing.RegisterTransitCallback(distance_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

    # 2. Vehicle Capacity Dimension (Cargo weight in KG)
    def demand_callback(from_index):
        from_node = manager.IndexToNode(from_index)
        return demands[from_node]

    demand_callback_index = routing.RegisterUnaryTransitCallback(demand_callback)
    routing.AddDimensionWithVehicleCapacity(
        demand_callback_index,
        0,  # null capacity slack
        vehicle_capacities,  # vehicle maximum capacities
        True,  # start cumul to zero
        "Capacity"
    )

    # 3. Time Window Dimension (Minutes)
    def time_callback(from_index, to_index):
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        # Travel time + service time at departing node
        return duration_matrix[from_node][to_node] + service_times[from_node]

    time_callback_index = routing.RegisterTransitCallback(time_callback)
    routing.AddDimension(
        time_callback_index,
        180,  # allow up to 180 mins waiting slack
        1440, # maximum horizon (24 hrs in mins)
        False, # don't force start cumul to zero
        "Time"
    )
    time_dimension = routing.GetDimensionOrDie("Time")

    # Add time window constraints for each customer order
    for order_idx, customer_window in enumerate(time_windows):
        if order_idx == 0:
            continue
        index = manager.NodeToIndex(order_idx)
        time_dimension.CumulVar(index).SetRange(customer_window[0], customer_window[1])

    # Add time window constraints for depot start/finish on each vehicle
    depot_open, depot_close = time_windows[0]
    for vehicle_id in range(num_vehicles):
        index = routing.Start(vehicle_id)
        time_dimension.CumulVar(index).SetRange(depot_open, depot_close)

    # Allow dropping orders with penalty if fleet capacity is exceeded
    penalty = 100000
    for node in range(1, num_locations):
        routing.AddDisjunction([manager.NodeToIndex(node)], penalty)

    # Search parameters
    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    )
    search_parameters.local_search_metaheuristic = (
        routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    )
    search_parameters.time_limit.seconds = time_limit_seconds

    # Solve the problem
    solution = routing.SolveWithParameters(search_parameters)

    if not solution:
        # Fallback to heuristic if strict time windows prevent solution
        return _solve_with_greedy_heuristic(
            depot, vehicles, orders, all_locations,
            distance_matrix, duration_matrix, demands, service_times,
            time_windows, vehicle_capacities
        )

    # Extract solution routes
    routes = []
    vehicle_routes = {}
    unassigned_orders = []

    # Check unassigned
    for node in range(1, num_locations):
        if routing.IsStart(manager.NodeToIndex(node)) or routing.IsEnd(manager.NodeToIndex(node)):
            continue
        if solution.Value(routing.NextVar(manager.NodeToIndex(node))) == manager.NodeToIndex(node):
            unassigned_orders.append(orders[node - 1]["id"])

    capacity_dimension = routing.GetDimensionOrDie("Capacity")

    for vehicle_id in range(num_vehicles):
        v_info = vehicles[vehicle_id]
        vehicle_routes[v_info["id"]] = []
        index = routing.Start(vehicle_id)

        seq = 0
        cum_dist = 0.0
        prev_node = 0

        while not routing.IsEnd(index):
            node = manager.IndexToNode(index)
            time_var = time_dimension.CumulVar(index)
            cap_var = capacity_dimension.CumulVar(index)

            arr_min = solution.Min(time_var)
            dep_min = arr_min + service_times[node]
            load_kg = solution.Value(cap_var)

            leg_dist = distance_matrix[prev_node][node] if seq > 0 else 0.0
            cum_dist += leg_dist

            loc_name = depot["name"] if node == 0 else orders[node - 1]["customer_name"]
            ord_id = None if node == 0 else orders[node - 1]["id"]
            lat = all_locations[node]["latitude"]
            lon = all_locations[node]["longitude"]
            addr = all_locations[node]["address"]

            stop_item = {
                "vehicle_id": v_info["id"],
                "vehicle_name": v_info["name"],
                "vehicle_type": v_info["vehicle_type"],
                "stop_sequence": seq,
                "order_id": ord_id,
                "location_name": loc_name,
                "address": addr,
                "latitude": lat,
                "longitude": lon,
                "arrival_mins": arr_min,
                "departure_mins": dep_min,
                "arrival_time_str": format_minutes_to_time(arr_min),
                "departure_time_str": format_minutes_to_time(dep_min),
                "distance_from_prev_km": round(leg_dist, 2),
                "cumulative_distance_km": round(cum_dist, 2),
                "load_carried_kg": load_kg
            }
            routes.append(stop_item)
            vehicle_routes[v_info["id"]].append(stop_item)

            prev_node = node
            index = solution.Value(routing.NextVar(index))
            seq += 1

        # Final return to Depot
        node = manager.IndexToNode(index)
        time_var = time_dimension.CumulVar(index)
        arr_min = solution.Min(time_var)
        leg_dist = distance_matrix[prev_node][0]
        cum_dist += leg_dist

        final_stop = {
            "vehicle_id": v_info["id"],
            "vehicle_name": v_info["name"],
            "vehicle_type": v_info["vehicle_type"],
            "stop_sequence": seq,
            "order_id": None,
            "location_name": f"{depot['name']} (Return)",
            "address": depot["address"],
            "latitude": depot["latitude"],
            "longitude": depot["longitude"],
            "arrival_mins": arr_min,
            "departure_mins": arr_min,
            "arrival_time_str": format_minutes_to_time(arr_min),
            "departure_time_str": format_minutes_to_time(arr_min),
            "distance_from_prev_km": round(leg_dist, 2),
            "cumulative_distance_km": round(cum_dist, 2),
            "load_carried_kg": 0.0
        }
        routes.append(final_stop)
        vehicle_routes[v_info["id"]].append(final_stop)

    return {
        "success": True,
        "solver_used": "Google OR-Tools VRPTW",
        "routes": routes,
        "vehicle_routes": vehicle_routes,
        "unassigned_orders": unassigned_orders
    }


def _solve_with_greedy_heuristic(
    depot, vehicles, orders, all_locations,
    distance_matrix, duration_matrix, demands, service_times,
    time_windows, vehicle_capacities
) -> Dict[str, Any]:
    """
    Robust Capacitated + Time Window Greedy Insertion Heuristic.
    Ensures the system produces an optimized schedule even in constrained scenarios.
    """
    unassigned = [i for i in range(1, len(all_locations))]
    routes = []
    vehicle_routes = {}

    for v_idx, v_info in enumerate(vehicles):
        v_cap = vehicle_capacities[v_idx]
        current_load = 0
        current_time = depot.get("open_time_mins", 480)
        curr_node = 0
        cum_dist = 0.0
        seq = 0

        v_stops = []

        # Start at depot
        depot_start = {
            "vehicle_id": v_info["id"],
            "vehicle_name": v_info["name"],
            "vehicle_type": v_info["vehicle_type"],
            "stop_sequence": 0,
            "order_id": None,
            "location_name": depot["name"],
            "address": depot["address"],
            "latitude": depot["latitude"],
            "longitude": depot["longitude"],
            "arrival_mins": current_time,
            "departure_mins": current_time,
            "arrival_time_str": format_minutes_to_time(current_time),
            "departure_time_str": format_minutes_to_time(current_time),
            "distance_from_prev_km": 0.0,
            "cumulative_distance_km": 0.0,
            "load_carried_kg": 0.0
        }
        v_stops.append(depot_start)
        routes.append(depot_start)
        seq += 1

        while unassigned:
            # Find best candidate: respects capacity and minimizes arrival detour
            best_candidate = None
            best_score = float("inf")
            best_arr_time = current_time

            for node in unassigned:
                demand = demands[node]
                if current_load + demand > v_cap:
                    continue  # Exceeds vehicle capacity

                travel_mins = duration_matrix[curr_node][node]
                arrival = current_time + travel_mins
                win_start, win_end = time_windows[node]

                # If arriving before window, vehicle can wait
                actual_service_start = max(arrival, win_start)

                if actual_service_start <= win_end:
                    dist = distance_matrix[curr_node][node]
                    score = dist + (actual_service_start - current_time) * 0.2
                    if score < best_score:
                        best_score = score
                        best_candidate = node
                        best_arr_time = actual_service_start

            if best_candidate is None:
                # No more orders fit this vehicle
                break

            # Assign candidate
            node = best_candidate
            unassigned.remove(node)
            current_load += demands[node]
            leg_dist = distance_matrix[curr_node][node]
            cum_dist += leg_dist
            dep_time = best_arr_time + service_times[node]

            stop_data = {
                "vehicle_id": v_info["id"],
                "vehicle_name": v_info["name"],
                "vehicle_type": v_info["vehicle_type"],
                "stop_sequence": seq,
                "order_id": orders[node - 1]["id"],
                "location_name": orders[node - 1]["customer_name"],
                "address": orders[node - 1]["address"],
                "latitude": all_locations[node]["latitude"],
                "longitude": all_locations[node]["longitude"],
                "arrival_mins": best_arr_time,
                "departure_mins": dep_time,
                "arrival_time_str": format_minutes_to_time(best_arr_time),
                "departure_time_str": format_minutes_to_time(dep_time),
                "distance_from_prev_km": round(leg_dist, 2),
                "cumulative_distance_km": round(cum_dist, 2),
                "load_carried_kg": current_load
            }
            v_stops.append(stop_data)
            routes.append(stop_data)

            curr_node = node
            current_time = dep_time
            seq += 1

        # Return to depot
        return_dist = distance_matrix[curr_node][0]
        cum_dist += return_dist
        return_time = current_time + duration_matrix[curr_node][0]

        depot_return = {
            "vehicle_id": v_info["id"],
            "vehicle_name": v_info["name"],
            "vehicle_type": v_info["vehicle_type"],
            "stop_sequence": seq,
            "order_id": None,
            "location_name": f"{depot['name']} (Return)",
            "address": depot["address"],
            "latitude": depot["latitude"],
            "longitude": depot["longitude"],
            "arrival_mins": return_time,
            "departure_mins": return_time,
            "arrival_time_str": format_minutes_to_time(return_time),
            "departure_time_str": format_minutes_to_time(return_time),
            "distance_from_prev_km": round(return_dist, 2),
            "cumulative_distance_km": round(cum_dist, 2),
            "load_carried_kg": 0.0
        }
        v_stops.append(depot_return)
        routes.append(depot_return)
        vehicle_routes[v_info["id"]] = v_stops

    unassigned_ids = [orders[node - 1]["id"] for node in unassigned]

    return {
        "success": True,
        "solver_used": "Heuristic VRPTW Engine",
        "routes": routes,
        "vehicle_routes": vehicle_routes,
        "unassigned_orders": unassigned_ids
    }

