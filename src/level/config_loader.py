"""Configuration loader for PCG system."""

import json
import os
from typing import Dict, Any, NamedTuple
import sys

# Add project root to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from src.level.pcg_level_data import PCGConfig


class PCGRuntimeConfig(NamedTuple):
    use_pcg: bool
    seed_mode: str
    seed: int
    selected_class: str
    selected_class: str


def load_pcg_config(config_path: str = "config/pcg_config.json") -> PCGConfig:
    """
    Load PCG configuration from JSON file.
    
    Args:
        config_path: Path to the configuration file
        
    Returns:
        PCGConfig: Loaded configuration
    """
    if not os.path.exists(config_path):
        import logging
        logging.getLogger(__name__).warning("Config file not found: %s, using defaults", config_path)
        return PCGConfig()
    
    try:
        with open(config_path, 'r') as f:
            data = json.load(f)
        
        config_data = data.get('pcg_config', {})
        # Filter only fields that PCGConfig accepts
        allowed_keys = {
            'num_levels', 'rooms_per_level', 'room_width', 'room_height',
            'air_tile_id', 'wall_tile_id', 'add_doors',
            'door_entrance_tile_id', 'door_exit_tile_id',
            'door_exit_1_tile_id', 'door_exit_2_tile_id',
            'ca_smoothing_iterations', 'ca_wall_neighbor_threshold', 'ca_include_diagonals',
            'post_ca_dilation_iterations', 'post_ca_dilation_radius',
        }
        filtered = {k: v for k, v in config_data.items() if k in allowed_keys}
        return PCGConfig(**filtered)
    
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("Error loading config: %s, using defaults", e)
        return PCGConfig()


def load_pcg_runtime_config(config_path: str = "config/pcg_config.json") -> PCGRuntimeConfig:
    """Load runtime PCG toggles (use_pcg, seed_mode, seed, selected_class) with safe defaults."""
    use_pcg = False
    seed_mode = "fixed"
    seed = 12345
    selected_class = "Knight"  # default class

    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                data = json.load(f)
            cfg = data.get('pcg_config', {})
            use_pcg = bool(cfg.get('use_pcg', use_pcg))
            seed_mode = str(cfg.get('seed_mode', seed_mode))
            # normalize seed_mode
            if seed_mode not in ("fixed", "random"):
                seed_mode = "fixed"
            try:
                seed = int(cfg.get('seed', seed))
            except (TypeError, ValueError):
                seed = 12345
            # Load selected class
            selected_class = str(cfg.get('selected_class', selected_class))
            # Validate class is one of the allowed options
            if selected_class not in ("Knight", "Ranger", "Wizard"):
                selected_class = "Knight"
        except Exception:
            # fall back to defaults on any error
            pass

    return PCGRuntimeConfig(use_pcg=use_pcg, seed_mode=seed_mode, seed=seed, selected_class=selected_class)


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
            "door_exit_tile_id": config.door_exit_tile_id,
            "door_exit_1_tile_id": config.door_exit_1_tile_id,
            "door_exit_2_tile_id": config.door_exit_2_tile_id
        }
    }
    
    # Preserve or add runtime fields if present in existing file
    existing = {}
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                existing = json.load(f) or {}
        except Exception:
            existing = {}
    pcg_cfg = existing.get("pcg_config", {})
    for key in ("use_pcg", "seed_mode", "seed", "selected_class"):
        if key in pcg_cfg:
            data["pcg_config"][key] = pcg_cfg[key]

    with open(config_path, 'w') as f:
        json.dump(data, f, indent=2)


def save_pcg_runtime_config(runtime: PCGRuntimeConfig, config_path: str = "config/pcg_config.json") -> None:
    """Persist runtime PCG toggles back into pcg_config.json safely."""
    os.makedirs(os.path.dirname(config_path), exist_ok=True)

    # Load existing full config
    existing = {}
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                existing = json.load(f) or {}
        except Exception:
            existing = {}

    pcg_cfg = existing.get("pcg_config", {})

    pcg_cfg["use_pcg"] = bool(runtime.use_pcg)
    pcg_cfg["seed_mode"] = str(runtime.seed_mode)
    pcg_cfg["seed"] = int(runtime.seed)
    pcg_cfg["selected_class"] = str(runtime.selected_class)

    existing["pcg_config"] = pcg_cfg

    with open(config_path, 'w') as f:
        json.dump(existing, f, indent=2)


if __name__ == "__main__":
    import logging
    logger = logging.getLogger(__name__)
    # Test configuration loading
    config = load_pcg_config()
    logger.info("Loaded config: %d levels, %d rooms each", config.num_levels, config.rooms_per_level)
    logger.info("Config working correctly!")