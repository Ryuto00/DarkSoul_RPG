"""
Room graph generation for multi-room levels.
"""

import random
from typing import List, Tuple, Dict, Set
from src.level.level_data import LevelData, LevelGenerationConfig, DoorLink
from src.level.procedural_generator import generate_validated_room
from src.level.room_data import GenerationConfig, MovementAttributes


def generate_linear_graph(num_rooms: int) -> Dict[str, List[str]]:
    """
    Generate a simple linear room graph: Room0 -> Room1 -> ... -> RoomN.
    
    Args:
        num_rooms: Number of rooms
    
    Returns:
        Adjacency list dictionary
    """
    graph = {}
    
    for i in range(num_rooms):
        room_id = f"room_{i}"
        
        if i < num_rooms - 1:
            next_room = f"room_{i + 1}"
            graph[room_id] = [next_room]
        else:
            graph[room_id] = []  # Last room has no exits
    
    return graph


def generate_pcg_linear_graph(num_rooms: int, entrance_doors: int = 1, exit_doors: int = 1) -> Dict[str, List[str]]:
    """
    Generate a PCG linear room graph with specified entrance/exit door counts.
    
    For linear levels, entrance_doors and exit_doors should typically be 1 each.
    Each room (except last) connects to exactly one next room.
    
    Args:
        num_rooms: Number of rooms
        entrance_doors: Number of entrance doors per room
        exit_doors: Number of exit doors per room
    
    Returns:
        Adjacency list dictionary
    """
    # For linear levels, we expect 1 entrance and 1 exit door
    # But the graph structure remains the same regardless of door counts
    return generate_linear_graph(num_rooms)


def generate_pcg_branching_graph(
    num_rooms: int,
    entrance_doors: int = 1,
    exit_doors: int = 2,
    rng: random.Random = random.Random()
) -> Dict[str, List[str]]:
    """
    Generate a PCG branching room graph with specified entrance/exit door counts.
    
    For branching levels, entrance_doors should be 1 and exit_doors should be 1-2.
    Creates a simple branching structure without loops.
    
    Args:
        num_rooms: Number of rooms
        entrance_doors: Number of entrance doors per room
        exit_doors: Number of exit doors per room
        rng: Random number generator
    
    Returns:
        Adjacency list dictionary
    """
    if entrance_doors < 1 or entrance_doors > 2:
        raise ValueError("Branching PCG graphs require entrance_doors = 1-2")
    if exit_doors < 1 or exit_doors > 2:
        raise ValueError("Branching PCG graphs require exit_doors = 1-2")
    
    graph = {}
    room_counter = 0
    
    # Start with main path
    main_path_length = max(2, num_rooms // 2)
    
    # Create main linear path
    for i in range(main_path_length):
        room_id = f"room_{room_counter}"
        room_counter += 1
        
        if i < main_path_length - 1 and room_counter < num_rooms:
            # Connect to next room on main path
            next_room = f"room_{room_counter}"
            graph[room_id] = [next_room]
        elif i == main_path_length - 1:
            # Last room on main path
            graph[room_id] = []
        else:
            # We've reached the room limit
            break
    
    # Add branch rooms if we have exit_doors > 1 and room slots remaining
    if exit_doors > 1 and room_counter < num_rooms:
        # Add branches from some main path rooms
        branch_rooms_added = 0
        max_branches = min(exit_doors - 1, num_rooms - room_counter)  # Limit branches
        
        for i in range(min(main_path_length - 1, len(graph.keys()))):
            if branch_rooms_added >= max_branches:
                break
                
            if rng.random() < 0.5:  # 50% chance to branch at each position
                main_room_id = f"room_{i}"
                branch_room_id = f"room_{room_counter}"
                room_counter += 1
                branch_rooms_added += 1
                
                # Add branch connection
                graph[main_room_id].append(branch_room_id)
                graph[branch_room_id] = []  # Branch rooms are dead ends
    
    return graph


def generate_branching_graph(
    num_rooms: int,
    branch_probability: float,
    rng: random.Random
) -> Dict[str, List[str]]:
    """
    Generate a branching room graph with optional paths.
    
    Strategy:
    - Start with linear path
    - Randomly add branch rooms
    - Some branches reconnect to main path (optional paths)
    
    Args:
        num_rooms: Target number of rooms
        branch_probability: Chance of branching at each room
        rng: Random number generator
    
    Returns:
        Adjacency list dictionary
    """
    graph = {}
    main_path_length = max(3, num_rooms // 2)
    
    # Create main path
    for i in range(main_path_length):
        room_id = f"room_{i}"
        
        if i < main_path_length - 1:
            graph[room_id] = [f"room_{i + 1}"]
        else:
            graph[room_id] = []
    
    # Add branches
    branch_id = main_path_length
    
    for i in range(main_path_length - 1):  # Don't branch from last room
        if rng.random() < branch_probability and branch_id < num_rooms:
            branch_room = f"room_{branch_id}"
            main_room = f"room_{i}"
            
            # Add branch
            graph[main_room].append(branch_room)
            
            # Branch can reconnect or be dead-end
            if rng.random() < 0.5 and i < main_path_length - 2:
                # Reconnect to main path
                reconnect_to = f"room_{i + 2}"
                graph[branch_room] = [reconnect_to]
            else:
                # Dead-end (optional treasure room)
                graph[branch_room] = []
            
            branch_id += 1
    
    return graph


def generate_looping_graph(
    num_rooms: int,
    loop_probability: float,
    rng: random.Random
) -> Dict[str, List[str]]:
    """
    Generate a graph with loops (multiple paths to same room).
    
    Args:
        num_rooms: Number of rooms
        loop_probability: Chance of creating loop connections
        rng: Random number generator
    
    Returns:
        Adjacency list dictionary
    """
    # Start with branching graph
    graph = generate_branching_graph(num_rooms, 0.4, rng)
    
    # Add loop connections
    room_ids = list(graph.keys())
    
    for i in range(len(room_ids) - 2):
        current_room = room_ids[i]
        
        if rng.random() < loop_probability:
            # Create loop to a later room
            target_idx = rng.randint(i + 2, min(i + 4, len(room_ids) - 1))
            target_room = room_ids[target_idx]
            
            if target_room not in graph[current_room]:
                graph[current_room].append(target_room)
    
    return graph


def generate_level_graph(config: LevelGenerationConfig, seed: int) -> Dict[str, List[str]]:
    """
    Generate room graph based on configuration.
    
    Args:
        config: Level generation configuration
        seed: Random seed
    
    Returns:
        Adjacency list dictionary
    """
    rng = random.Random(seed)
    
    if config.layout_type == "linear":
        # Use PCG linear generation with separate entrance/exit door counts
        return generate_pcg_linear_graph(
            config.num_rooms, 
            config.entrance_doors_per_room, 
            config.exit_doors_per_room
        )
    elif config.layout_type == "branching":
        # Use PCG branching generation with separate entrance/exit door counts
        return generate_pcg_branching_graph(
            config.num_rooms,
            config.entrance_doors_per_room,
            config.exit_doors_per_room,
            rng
        )
    elif config.layout_type == "looping":
        return generate_looping_graph(
            config.num_rooms,
            config.loop_probability,
            rng
        )
    else:
        # Default to linear PCG
        return generate_pcg_linear_graph(
            config.num_rooms, 
            config.entrance_doors_per_room, 
            config.exit_doors_per_room
        )


def generate_complete_level(
    room_config: GenerationConfig,
    level_config: LevelGenerationConfig,
    movement_attrs: MovementAttributes,
    seed: int
) -> LevelData:
    """
    Generate a complete multi-room level.
    
    Strategy:
    1. Generate room graph structure
    2. Create each room with appropriate depth/difficulty
    3. Validate that path exists from start to goal
    4. Return complete LevelData
    
    Args:
        room_config: Configuration for individual room generation
        level_config: Configuration for level structure
        movement_attrs: Player movement capabilities
        seed: Random seed for level
    
    Returns:
        Complete LevelData with all rooms and connections
    """
    # Set seed
    level_rng = random.Random(seed)
    
    # Generate room graph
    graph = generate_level_graph(level_config, seed)
    
    # Create LevelData
    level = LevelData(
        internal_graph=graph,
        level_seed=seed
    )
    
    # Identify start and goal
    room_ids = list(graph.keys())
    level.start_room_id = room_ids[0] if room_ids else None
    
    # Goal is room with no exits, or last room
    goal_candidates = [rid for rid, neighbors in graph.items() if not neighbors]
    level.goal_room_id = goal_candidates[-1] if goal_candidates else room_ids[-1]
    
    # Generate each room
    for room_id in room_ids:
        # Calculate depth from start
        depth = level.get_room_depth(room_id)
        if depth == -1:
            depth = 0  # Fallback
        
        # Determine exit door count from graph structure
        neighbor_ids = graph.get(room_id, [])
        exit_doors_count = len(neighbor_ids)  # Number of exits from this room
        
        # Generate a new seed for each room
        room_config.seed = level_rng.randint(0, 2**32 - 1)
        
        # Generate room with appropriate exit door count
        room = generate_validated_room(
            room_config,
            movement_attrs,
            depth_from_start=depth,
            exit_doors=exit_doors_count
        )
        

        level.add_room(room_id, room)
    
    # Create DoorLink objects for each connection using PCG door system
    for from_room_id, neighbor_ids in graph.items():
        from_room = level.get_room(from_room_id)
        
        if not from_room or not from_room.doors:
            continue
        
        for to_room_id in neighbor_ids:
            to_room = level.get_room(to_room_id)
            
            if not to_room or not to_room.doors:
                continue
            
            # Get first available door from each room
            # For linear levels, each room should have exactly 1 door
            from_door_id = next(iter(from_room.doors.keys()))
            to_door_id = next(iter(to_room.doors.keys()))
            
            # Add destination to the from_room's door
            from_door = from_room.doors[from_door_id]
            from_door.add_destination("default", to_room_id)
            
            # Create PCG door link
            door_link = DoorLink(
                from_room_id=from_room_id,
                to_room_id=to_room_id,
                from_door_id=from_door_id,
                to_door_id=to_door_id,
                choice_label="default"
            )
            
            level.door_links.append(door_link)
    
    # Validate level has path to goal
    path = level.get_path_to_goal()
    if not path:
        # No path! Use linear fallback
        print(f"Warning: Generated level has no path to goal, using linear fallback")
        return generate_linear_fallback_level(room_config, level_config, movement_attrs, seed)
    
    return level


def generate_linear_fallback_level(
    room_config: GenerationConfig,
    level_config: LevelGenerationConfig,
    movement_attrs: MovementAttributes,
    seed: int
) -> LevelData:
    """
    Generate a simple linear level as fallback.
    
    Guaranteed to have a path from start to goal.
    """
    room_config.seed = seed
    
    level = LevelData(level_seed=seed)
    
    # Create rooms
    for i in range(level_config.num_rooms):
        room_id = f"room_{i}"
        room = generate_validated_room(room_config, movement_attrs, depth_from_start=i)
        level.add_room(room_id, room)

    # Create connections and door links
    for i in range(level_config.num_rooms):
        if i < level_config.num_rooms - 1:
            from_room_id = f"room_{i}"
            to_room_id = f"room_{i + 1}"
            level.connect_rooms(from_room_id, to_room_id)
            
            from_room = level.get_room(from_room_id)
            to_room = level.get_room(to_room_id)

            if from_room and from_room.doors and to_room and to_room.doors:
                # Get first available door from each room
                from_door_id = next(iter(from_room.doors.keys()))
                to_door_id = next(iter(to_room.doors.keys()))
                
                # Add destination to from_room's door
                from_door = from_room.doors[from_door_id]
                from_door.add_destination("default", to_room_id)
                
                door_link = DoorLink(
                    from_room_id=from_room_id,
                    to_room_id=to_room_id,
                    from_door_id=from_door_id,
                    to_door_id=to_door_id,
                    choice_label="default"
                )
                level.door_links.append(door_link)
    
    level.start_room_id = "room_0"
    level.goal_room_id = f"room_{level_config.num_rooms - 1}"
    
    return level
