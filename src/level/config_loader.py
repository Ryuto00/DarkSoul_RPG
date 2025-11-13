"""Configuration loader for PCG system."""

import json
import os
from typing import Dict, Any
import sys

# Add project root to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from src.level.pcg_level_data import PCGConfig


def load_pcg_config(config_path: str = "config/pcg_config.json") -> PCGConfig:
    """
    Load PCG configuration from JSON file.
    
    Args:
        config_path: Path to the configuration file
        
    Returns:
        PCGConfig: Loaded configuration
    """
    if not os.path.exists(config_path):
        print(f"Config file not found: {config_path}, using defaults")
        return PCGConfig()
    
    try:
        with open(config_path, 'r') as f:
            data = json.load(f)
        
        config_data = data.get('pcg_config', {})
        return PCGConfig(**config_data)
    
    except Exception as e:
        print(f"Error loading config: {e}, using defaults")
        return PCGConfig()


def save_pcg_config(config: PCGConfig, config_path: str = "config/pcg_config.json"):
    """
    Save PCG configuration to JSON file.
    
    Args:
        config: Configuration to save
        config_path: Path to save the configuration file
    """
    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    
    data = {
        "pcg_config": {
            "num_levels": config.num_levels,
            "rooms_per_level": config.rooms_per_level,
            "room_width": config.room_width,
            "room_height": config.room_height,
            "air_tile_id": config.air_tile_id,
            "wall_tile_id": config.wall_tile_id,
            "add_doors": config.add_doors,
            "door_entrance_tile_id": config.door_entrance_tile_id,
            "door_exit_tile_id": config.door_exit_tile_id
        }
    }
    
    with open(config_path, 'w') as f:
        json.dump(data, f, indent=2)





if __name__ == "__main__":
    # Test configuration loading
    config = load_pcg_config()
    print(f"Loaded config: {config.num_levels} levels, {config.rooms_per_level} rooms each")
    print("Config working correctly!")