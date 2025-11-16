"""
Enhanced Animation System for Enemy Entities

This module provides a comprehensive animation system that handles:
- Multiple animation states (idle, walk, attack, skill, death, hurt, etc.)
- Frame-based animation with configurable speed
- Animation transitions and priority
- Looping and one-shot animations
- Sprite flipping based on facing direction
- Integration with combat system (invincibility flicker)
"""

import pygame
from typing import Dict, List, Optional, Tuple, Callable
from dataclasses import dataclass, field
from enum import Enum


class AnimationState(Enum):
    """Standard animation states for enemies"""
    IDLE = "idle"
    WALK = "walk"
    RUN = "run"
    ATTACK = "attack"
    # Ranger bow attack states
    CHARGE = "charge"        # Drawing bow back
    CHARGED = "charged"      # Holding at full draw
    SHOOT = "shoot"          # Releasing arrow
    SKILL_1 = "skill_1"
    SKILL_2 = "skill_2"
    SKILL_3 = "skill_3"
    HURT = "hurt"
    DEATH = "death"
    TELEGRAPH = "telegraph"
    DASH = "dash"
    JUMP = "jump"
    FALL = "fall"
    WALL_SLIDE = "wall_slide"


@dataclass
class AnimationConfig:
    """Configuration for a single animation"""
    frames: List[pygame.Surface] = field(default_factory=list)
    frame_duration: int = 4  # Frames to display each sprite frame
    loop: bool = True  # Whether animation loops
    priority: int = 0  # Higher priority animations override lower ones
    on_complete_callback: Optional[Callable] = None  # Called when animation completes
    next_state: Optional[AnimationState] = None  # Auto-transition after completion
    frame_events: Dict[int, List[Callable]] = field(default_factory=dict)  # Callbacks per frame
    
    def __post_init__(self):
        """Validate configuration"""
        if self.frame_duration < 1:
            self.frame_duration = 1


class AnimationManager:
    """
    Manages animations for an enemy entity.
    
    Usage:
        # In enemy __init__:
        self.anim_manager = AnimationManager(self)
        self.anim_manager.load_animation(
            AnimationState.IDLE,
            ["path/to/frame1.png", "path/to/frame2.png"],
            sprite_size=(96, 128),
            frame_duration=8,
            loop=True
        )
        
        # In enemy tick():
        self.anim_manager.update()
        
        # In enemy draw():
        self.anim_manager.draw(surf, camera)
    """
    
    def __init__(self, entity, default_state: AnimationState = AnimationState.IDLE):
        """
        Initialize animation manager.
        
        Args:
            entity: The enemy entity this manager belongs to
            default_state: Default animation state to start with
        """
        self.entity = entity
        self.animations: Dict[AnimationState, AnimationConfig] = {}
        self.current_state: AnimationState = default_state
        self.current_frame_index: int = 0
        self.frame_timer: int = 0
        self.requested_state: Optional[AnimationState] = None
        self.is_playing: bool = True
        
        # Frame event tracking
        self._triggered_events: set = set()  # Track which frame events have fired this animation
        
        # Sprite rendering properties
        self.sprite_offset = (0, 0)  # (x, y) offset from entity rect
        self.sprite_offset_y = 0  # Backward compatibility
    
    def load_animation(
        self,
        state: AnimationState,
        frame_paths: List[str],
        sprite_size: Tuple[int, int] = (96, 128),
        frame_duration: int = 4,
        loop: bool = True,
        priority: int = 0,
        on_complete_callback: Optional[Callable] = None,
        next_state: Optional[AnimationState] = None
    ):
        """
        Load an animation from a list of file paths.
        
        Args:
            state: Animation state this belongs to
            frame_paths: List of paths to animation frame images
            sprite_size: (width, height) to scale frames to
            frame_duration: Frames to display each sprite frame
            loop: Whether animation should loop
            priority: Priority level (higher = more important)
            on_complete_callback: Function to call when animation completes
            next_state: Auto-transition to this state after completion
        """
        frames = []
        for path in frame_paths:
            try:
                frame = pygame.image.load(path).convert_alpha()
                scaled_frame = pygame.transform.scale(frame, sprite_size)
                frames.append(scaled_frame)
            except Exception as e:
                print(f"[AnimationSystem] Failed to load frame {path}: {e}")
        
        if frames:
            config = AnimationConfig(
                frames=frames,
                frame_duration=frame_duration,
                loop=loop,
                priority=priority,
                on_complete_callback=on_complete_callback,
                next_state=next_state
            )
            self.animations[state] = config
            print(f"[AnimationSystem] Loaded {state.value} animation: {len(frames)} frames")
        else:
            print(f"[AnimationSystem] Warning: No frames loaded for {state.value}")
    
    def load_single_frame_animation(
        self,
        state: AnimationState,
        frame_path: str,
        sprite_size: Tuple[int, int] = (96, 128),
        priority: int = 0
    ):
        """
        Load a single-frame animation (useful for idle states).
        
        Args:
            state: Animation state
            frame_path: Path to the single frame image
            sprite_size: (width, height) to scale to
            priority: Priority level
        """
        self.load_animation(
            state,
            [frame_path],
            sprite_size=sprite_size,
            frame_duration=1,
            loop=True,
            priority=priority
        )
    
    def play(self, state: AnimationState, force: bool = False):
        """
        Request to play an animation.
        
        Args:
            state: Animation state to play
            force: If True, interrupt current animation regardless of priority
        """
        if state not in self.animations:
            print(f"[AnimationSystem] Warning: Animation {state.value} not loaded")
            return
        
        current_config = self.animations.get(self.current_state)
        requested_config = self.animations[state]
        
        # Check priority unless forced
        if not force and current_config:
            if requested_config.priority < current_config.priority:
                # Store request for later
                self.requested_state = state
                return
        
        # Switch to new animation
        self.current_state = state
        self.current_frame_index = 0
        self.frame_timer = 0
        self.requested_state = None
        self.is_playing = True
        self._triggered_events.clear()  # Reset triggered events for new animation
    
    def update(self):
        """Update animation state. Call this every frame in enemy tick()."""
        if not self.is_playing:
            return
        
        current_config = self.animations.get(self.current_state)
        if not current_config or not current_config.frames:
            return
        
        # Update frame timer
        self.frame_timer += 1
        
        if self.frame_timer >= current_config.frame_duration:
            self.frame_timer = 0
            self.current_frame_index += 1
            
            # Trigger frame events when entering a new frame
            self._trigger_frame_events()
            
            # Check if animation completed
            if self.current_frame_index >= len(current_config.frames):
                if current_config.loop:
                    # Loop back to start
                    self.current_frame_index = 0
                    self._triggered_events.clear()  # Reset for next loop
                else:
                    # Animation finished
                    self.current_frame_index = len(current_config.frames) - 1
                    self.is_playing = False
                    
                    # Call completion callback
                    if current_config.on_complete_callback:
                        try:
                            current_config.on_complete_callback()
                        except Exception as e:
                            print(f"[AnimationSystem] Callback error: {e}")
                    
                    # Auto-transition to next state
                    if current_config.next_state:
                        self.play(current_config.next_state)
                    elif self.requested_state:
                        # Play requested animation if one was queued
                        self.play(self.requested_state)
    
    def _trigger_frame_events(self):
        """Internal method to trigger events for the current frame."""
        current_config = self.animations.get(self.current_state)
        if not current_config:
            return
        
        # Check if current frame has events and hasn't been triggered yet
        event_key = (self.current_state, self.current_frame_index)
        if event_key in self._triggered_events:
            return  # Already triggered this frame in this animation playthrough
        
        if self.current_frame_index in current_config.frame_events:
            callbacks = current_config.frame_events[self.current_frame_index]
            for callback in callbacks:
                try:
                    callback()
                    self._triggered_events.add(event_key)
                except Exception as e:
                    print(f"[AnimationSystem] Frame event error on {self.current_state.value} frame {self.current_frame_index}: {e}")
    
    def get_current_frame(self) -> Optional[pygame.Surface]:
        """Get the current animation frame surface."""
        current_config = self.animations.get(self.current_state)
        if not current_config or not current_config.frames:
            return None
        
        # Ensure frame index is valid
        frame_idx = min(self.current_frame_index, len(current_config.frames) - 1)
        return current_config.frames[frame_idx]
    
    def draw(self, surf, camera, show_invincibility: bool = True) -> bool:
        """
        Draw the current animation frame.
        
        Args:
            surf: Surface to draw on
            camera: Camera for screen position conversion
            show_invincibility: Whether to apply invincibility flicker effect
        
        Returns:
            True if sprite was drawn, False if no sprite available
        """
        frame = self.get_current_frame()
        if not frame:
            return False
        
        # Calculate sprite position based on entity rect and offset
        sprite_rect = frame.get_rect()
        sprite_rect.midbottom = (
            self.entity.rect.midbottom[0] + self.sprite_offset[0],
            self.entity.rect.midbottom[1] + self.sprite_offset[1] + self.sprite_offset_y
        )
        
        # Calculate screen position
        screen_pos = camera.to_screen(sprite_rect.topleft)
        
        # Flip sprite based on entity facing direction
        facing = getattr(self.entity, 'facing', 1)
        draw_sprite = pygame.transform.flip(frame, facing == -1, False)
        
        # Scale sprite to match camera zoom
        scaled_width = int(draw_sprite.get_width() * camera.zoom)
        scaled_height = int(draw_sprite.get_height() * camera.zoom)
        draw_sprite = pygame.transform.scale(draw_sprite, (scaled_width, scaled_height))
        
        # Create a rect for the scaled sprite and position it correctly
        scaled_sprite_rect = draw_sprite.get_rect()
        scaled_sprite_rect.midbottom = camera.to_screen(sprite_rect.midbottom)
        
        # Apply invincibility flicker if needed
        if show_invincibility and hasattr(self.entity, 'combat'):
            if self.entity.combat.is_invincible():
                temp = draw_sprite.copy()
                temp.set_alpha(150)
                surf.blit(temp, scaled_sprite_rect.topleft)
                return True
        
        surf.blit(draw_sprite, scaled_sprite_rect.topleft)
        return True
    
    def is_animation_complete(self) -> bool:
        """Check if current animation has completed (for non-looping animations)."""
        current_config = self.animations.get(self.current_state)
        if not current_config or current_config.loop:
            return False
        return not self.is_playing
    
    def reset(self):
        """Reset animation to first frame of current state."""
        self.current_frame_index = 0
        self.frame_timer = 0
        self.is_playing = True
    
    def set_sprite_offset(self, x: int = 0, y: int = 0):
        """Set sprite offset from entity rect."""
        self.sprite_offset = (x, y)
    
    def set_sprite_offset_y(self, offset_y: int):
        """Set vertical sprite offset (backward compatibility)."""
        self.sprite_offset_y = offset_y
    
    def set_frame_event(self, state: AnimationState, frame_index: int, callback: Callable):
        """
        Register a callback to be triggered when a specific animation frame is reached.
        
        This is useful for:
        - Spawning attack hitboxes at the right moment in an attack animation
        - Playing sound effects synchronized with animation (e.g., footstep on frame 3)
        - Triggering particle effects at specific frames
        - Item usage effects synchronized with animation
        
        Args:
            state: Animation state to attach event to
            frame_index: Frame number to trigger on (0-based, matches animation frame index)
            callback: Function to call when frame is reached (takes no arguments)
        
        Example:
            # Spawn attack hitbox on frame 5 of 12-frame attack animation
            def spawn_attack():
                hitbox = Hitbox(self.rect.centerx, self.rect.centery, ...)
                hitboxes.append(hitbox)
            
            self.anim_manager.set_frame_event(AnimationState.ATTACK, 5, spawn_attack)
        """
        if state not in self.animations:
            print(f"[AnimationSystem] Warning: Cannot set frame event for unloaded animation {state.value}")
            return
        
        config = self.animations[state]
        if frame_index < 0 or frame_index >= len(config.frames):
            print(f"[AnimationSystem] Warning: Frame index {frame_index} out of range for {state.value} (has {len(config.frames)} frames)")
            return
        
        if frame_index not in config.frame_events:
            config.frame_events[frame_index] = []
        
        config.frame_events[frame_index].append(callback)
        print(f"[AnimationSystem] Registered frame event for {state.value} frame {frame_index}")
    
    def set_attack_frame(self, state: AnimationState, frame_index: int, spawn_hitbox_callback: Callable):
        """
        Convenience method to set the attack frame for an animation.
        This is the frame where the attack hitbox should spawn.
        
        Args:
            state: Attack animation state (typically AnimationState.ATTACK)
            frame_index: Frame where attack should execute (0-based)
            spawn_hitbox_callback: Function that creates and spawns the hitbox
        
        Example:
            def spawn_sword_slash():
                hitbox = Hitbox(
                    self.rect.centerx + (30 * self.facing),
                    self.rect.centery,
                    40, 40,
                    damage=self.attack_damage,
                    owner=self,
                    lifetime=8
                )
                hitboxes.append(hitbox)
            
            # Spawn hitbox on frame 6 of attack animation
            self.anim_manager.set_attack_frame(AnimationState.ATTACK, 6, spawn_sword_slash)
        """
        self.set_frame_event(state, frame_index, spawn_hitbox_callback)
    
    def get_current_frame_index(self) -> int:
        """
        Get the current frame index (0-based).
        Useful for checking which frame of the animation is currently playing.
        
        Returns:
            Current frame index
        """
        return self.current_frame_index
    
    def is_on_frame(self, frame_index: int) -> bool:
        """
        Check if the animation is currently on a specific frame.
        
        Args:
            frame_index: Frame to check (0-based)
        
        Returns:
            True if currently on that frame
        """
        return self.current_frame_index == frame_index


# ============================================================================
# Convenience Functions for Quick Setup
# ============================================================================

def create_simple_animation_manager(
    entity,
    idle_path: str,
    attack_paths: Optional[List[str]] = None,
    sprite_size: Tuple[int, int] = (96, 128),
    offset_y: int = 55
) -> AnimationManager:
    """
    Create a simple animation manager with idle and optional attack animation.
    
    Args:
        entity: Enemy entity
        idle_path: Path to idle sprite
        attack_paths: Optional list of paths for attack animation
        sprite_size: Size to scale sprites to
        offset_y: Vertical offset for sprite positioning
    
    Returns:
        Configured AnimationManager
    """
    manager = AnimationManager(entity)
    manager.set_sprite_offset_y(offset_y)
    
    # Load idle animation
    manager.load_single_frame_animation(
        AnimationState.IDLE,
        idle_path,
        sprite_size=sprite_size,
        priority=0
    )
    
    # Load attack animation if provided
    if attack_paths:
        manager.load_animation(
            AnimationState.ATTACK,
            attack_paths,
            sprite_size=sprite_size,
            frame_duration=4,
            loop=False,
            priority=10,
            next_state=AnimationState.IDLE  # Return to idle after attack
        )
    
    return manager


def load_numbered_frames(
    base_path: str,
    start: int,
    end: int,
    extension: str = ".png"
) -> List[str]:
    """
    Generate list of frame paths with numbered sequence.
    
    Example:
        load_numbered_frames("assets/enemy/attack_", 1, 4)
        Returns: ["assets/enemy/attack_1.png", ..., "assets/enemy/attack_4.png"]
    
    Args:
        base_path: Base path without number
        start: Starting number (inclusive)
        end: Ending number (inclusive)
        extension: File extension (default: ".png")
    
    Returns:
        List of frame paths
    """
    return [f"{base_path}{i}{extension}" for i in range(start, end + 1)]
