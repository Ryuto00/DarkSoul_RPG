"""Level loader utility for integrating PCG levels with the game."""

import os
from typing import Optional, List, Dict
import sys

# Add project root to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from src.level.pcg_level_data import LevelSet, LevelData, RoomData


class LevelLoader:
    """Utility class for loading and accessing PCG-generated levels."""
    
    def __init__(self, levels_file: str = "data/levels/generated_levels.json"):
        """
        Initialize the level loader.
        
        Args:
            levels_file: Path to the JSON file containing generated levels
        """
        self.levels_file = levels_file
        self._level_set: Optional[LevelSet] = None
    
    def load_levels(self) -> LevelSet:
        """
        Load levels from JSON file.
        
        Returns:
            LevelSet: Loaded level data
        """
        if not os.path.exists(self.levels_file):
            raise FileNotFoundError(f"Levels file not found: {self.levels_file}")
        
        self._level_set = LevelSet.load_from_json(self.levels_file)
        return self._level_set
    
    def get_level_set(self) -> Optional[LevelSet]:
        """Get the currently loaded level set."""
        return self._level_set
    
    def get_room(self, level_id: int, room_code: str) -> Optional[RoomData]:
        """
        Get a specific room by level ID and room code.
        
        Args:
            level_id: The level number (1-based)
            room_code: Room code like "1A", "2B", etc.
            
        Returns:
            RoomData if found, None otherwise
        """
        if self._level_set is None:
            self.load_levels()
        
        if self._level_set is not None:
            return self._level_set.get_room(level_id, room_code)
        return None
    
    def get_level(self, level_id: int) -> Optional[LevelData]:
        """
        Get a specific level by ID.
        
        Args:
            level_id: The level number (1-based)
            
        Returns:
            LevelData if found, None otherwise
        """
        if self._level_set is None:
            self.load_levels()
        
        if self._level_set is not None:
            return self._level_set.get_level(level_id)
        return None
    
    def get_room_tiles(self, level_id: int, room_code: str) -> Optional[List[List[int]]]:
        """
        Get just the tile grid for a specific room.
        
        Args:
            level_id: The level number (1-based)
            room_code: Room code like "1A", "2B", etc.
            
        Returns:
            2D list of tile IDs if found, None otherwise
        """
        room = self.get_room(level_id, room_code)
        return room.tiles if room else None
    
    def get_room_exits(self, level_id: int, room_code: str) -> Dict[str, str]:
        """
        Get door exits mapping for a specific room.
        
        Args:
            level_id: The level number (1-based)
            room_code: Room code like "1A", "2B", etc.
            
        Returns:
            Dict mapping "door_exit_1"/"door_exit_2" to target room codes
        """
        room = self.get_room(level_id, room_code)
        return room.door_exits if room else {}
    
    def get_room_entrance_from(self, level_id: int, room_code: str) -> Optional[str]:
        """
        Get which room this room's entrance comes from.
        
        Args:
            level_id: The level number (1-based)
            room_code: Room code like "1A", "2B", etc.
            
        Returns:
            Room code this entrance comes from, or None if no entrance
        """
        room = self.get_room(level_id, room_code)
        return room.entrance_from if room else None
    
    def list_rooms_in_level(self, level_id: int) -> List[str]:
        """
        Get list of room codes for a level.
        
        Args:
            level_id: The level number (1-based)
            
        Returns:
            List of room codes like ["1A", "1B", ...]
        """
        level = self.get_level(level_id)
        if level:
            return [room.room_code for room in level.rooms]
        return []
    
    def get_starting_room(self, level_id: int) -> Optional[RoomData]:
        """
        Get the starting room for a level (first room).
        
        Args:
            level_id: The level number (1-based)
            
        Returns:
            RoomData for the first room if found, None otherwise
        """
        level = self.get_level(level_id)
        if level and level.rooms:
            return level.rooms[0]
        return None


# Global level loader instance
level_loader = LevelLoader()


def get_room_tiles(level_id: int, room_code: str) -> Optional[List[List[int]]]:
    """
    Convenience function to get room tiles.
    
    Args:
        level_id: The level number (1-based)
        room_code: Room code like "1A", "2B", etc.
        
    Returns:
        2D list of tile IDs if found, None otherwise
    """
    return level_loader.get_room_tiles(level_id, room_code)


def get_starting_room(level_id: int) -> Optional[RoomData]:
    """
    Convenience function to get starting room for a level.
    
    Args:
        level_id: The level number (1-based)
        
    Returns:
        RoomData for the first room if found, None otherwise
    """
    return level_loader.get_starting_room(level_id)


def get_room_exits(level_id: int, room_code: str) -> Dict[str, str]:
    """
    Convenience function to get room exits.
    
    Args:
        level_id: The level number (1-based)
        room_code: Room code like "1A", "2B", etc.
        
    Returns:
        Dict mapping "door_exit_1"/"door_exit_2" to target room codes
    """
    return level_loader.get_room_exits(level_id, room_code)


def get_room_entrance_from(level_id: int, room_code: str) -> Optional[str]:
    """
    Convenience function to get room entrance source.
    
    Args:
        level_id: The level number (1-based)
        room_code: Room code like "1A", "2B", etc.
        
    Returns:
        Room code this entrance comes from, or None if no entrance
    """
    return level_loader.get_room_entrance_from(level_id, room_code)


def list_all_levels() -> List[int]:
    """
    Get list of all available level IDs.
    
    Returns:
        List of level IDs
    """
    level_set = level_loader.get_level_set()
    if level_set is None:
        level_loader.load_levels()
        level_set = level_loader.get_level_set()
    
    return [level.level_id for level in level_set.levels] if level_set else []