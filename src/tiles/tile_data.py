from dataclasses import dataclass, field
from typing import Optional, Dict, List, Tuple
from .tile_types import TileType


@dataclass
class CollisionProperties:
    """Collision properties for a tile."""
    collision_type: str = "none"  # "none", "top_only", "full", "one_way"
    collision_box_offset: Tuple[float, float] = (0.0, 0.0)
    collision_box_size: Optional[Tuple[float, float]] = None  # None = use tile size
    can_walk_on: bool = False
    can_climb: bool = False
    can_pass_through: bool = False
    damage_on_contact: int = 0
    push_force: float = 0.0


@dataclass
class VisualProperties:
    """Visual properties for a tile."""
    base_color: Tuple[int, int, int] = (255, 255, 255)
    sprite_path: Optional[str] = None
    animation_frames: List[str] = field(default_factory=list)
    animation_speed: float = 0.1
    border_radius: int = 0
    particle_effects: Dict[str, str] = field(default_factory=dict)
    render_border: bool = False
    border_color: Optional[Tuple[int, int, int]] = None


@dataclass
class PhysicalProperties:
    """Physical properties for a tile."""
    friction: float = 1.0
    bounciness: float = 0.0
    movement_speed_modifier: float = 1.0
    is_sticky: bool = False
    is_slippery: bool = False
    density: float = 1.0


@dataclass
class InteractionProperties:
    """Interaction properties for a tile."""
    breakable: bool = False
    health_points: int = 1
    climbable: bool = False
    interactable: bool = False
    collectible: bool = False
    is_trigger: bool = False
    resistance: float = 1.0  # Resistance to damage/tools
    prompt: str = ""  # Text to show when in range (e.g. "Press E to enter")
    requires_proximity: bool = False
    proximity_radius: float = 24.0
    on_interact_id: str = ""  # Identifier for routing interaction logic
    is_spawn_point: bool = False  # Marks entrance tiles for spawning


@dataclass
class AudioProperties:
    """Audio properties for a tile."""
    footstep_sound: Optional[str] = None
    contact_sound: Optional[str] = None
    break_sound: Optional[str] = None
    ambient_sound: Optional[str] = None
    sound_volume: float = 1.0


@dataclass
class LightingProperties:
    """Lighting properties for a tile."""
    emits_light: bool = False
    light_color: Tuple[int, int, int] = (255, 255, 255)
    light_radius: float = 0.0
    blocks_light: bool = False
    transparency: float = 1.0
    casts_shadows: bool = True
    reflection_intensity: float = 0.0


@dataclass
class TileData:
    """Complete data for a tile type."""
    tile_type: TileType
    name: str
    collision: CollisionProperties = field(default_factory=CollisionProperties)
    visual: VisualProperties = field(default_factory=VisualProperties)
    physics: PhysicalProperties = field(default_factory=PhysicalProperties)
    interaction: InteractionProperties = field(default_factory=InteractionProperties)
    audio: AudioProperties = field(default_factory=AudioProperties)
    lighting: LightingProperties = field(default_factory=LightingProperties)

    def __post_init__(self):
        """Set default collision box size to tile size if not specified."""
        if self.collision.collision_box_size is None:
            self.collision.collision_box_size = (24, 24)  # Default tile size

    @property
    def is_walkable(self) -> bool:
        """Check if tile can be walked on."""
        return self.collision.can_walk_on

    @property
    def has_collision(self) -> bool:
        """Check if tile has any collision."""
        return self.collision.collision_type != "none"

    @property
    def is_destructible(self) -> bool:
        """Check if tile can be destroyed."""
        return self.interaction.breakable

    def get_damage(self) -> int:
        """Get damage dealt by tile on contact."""
        return self.collision.damage_on_contact

    def get_friction(self) -> float:
        """Get friction coefficient."""
        return self.physics.friction

    def get_bounciness(self) -> float:
        """Get bounciness/restitution."""
        return self.physics.bounciness