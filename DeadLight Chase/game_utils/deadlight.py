import math
import random
import time
import pygame
from .pathfinding import find_path
from .game_util import cast_ray, TILE_SIZE

ANGLE_STEP = 8

# how many consecutive hibernation ticks indicates a trapped enemy (can be tuned)
HIBERNATION_TICKS_THRESHOLD = 5


class DeadlightBoss:
    """Deadlight boss: three white dots radiating blue light.
    - Radiance is health-based (same as player)
    - Uses A* pathfinding to chase player
    - Alternates between chase phase and vulnerable phase
    """

    def __init__(self, x, y, base_radiance=200):
        self.x = float(x)
        self.y = float(y)
        self.base_radiance = base_radiance
        self.alive = True
        # Health = radiance (light radius)
        self.health = float(base_radiance)
        self.health_max = float(base_radiance)
        self.radiance = float(base_radiance)  # radiance is now health
        self.speed = 200.0
        # remember baseline speed & think interval
        self._base_speed = float(self.speed)
        self._min_speed = 300.0
        self._max_speed = 450.0  # max speed when health is very low
        self._target = None
        self._path = []
        self._path_index = 0
        self._think_timer = 0.0
        self._think_interval = 2.5  # reduce frequency to avoid heavy A* calls
        self._base_think_interval = float(self._think_interval)

        # Legacy variables (kept for compatibility, no longer used)
        self._follow_player_mode = False
        self._guard_target = None

        # Chase mode: triggered when enemy is killed, uses simple chase by default, A* only when close
        self._chase_mode = False
        self._chase_timer = 0.0
        self._chase_duration = 60.0  # 60 seconds
        self._chase_path_update_timer = 0.0
        self._chase_path_update_interval = 1.5  # update path every 1.5s when chasing (reduced frequency for performance)
        self._last_player_pos = None  # track last player position to avoid unnecessary recalculations
        self._player_move_threshold = 40.0  # only recalculate if player moved more than this (pixels)
        self._player_teleport_threshold = 200.0  # if player moves more than this, force immediate recalculation (catches teleports)
        self._astar_distance_threshold = float('inf')  # Always use A* pathfinding (no distance limit)

        # Stuck detection for simple chase mode
        self._simple_chase_stuck_timer = 0.0
        self._simple_chase_stuck_threshold = 0.5  # seconds before considering stuck (faster detection)
        self._simple_chase_last_pos = (float(self.x), float(self.y))
        self._simple_chase_stuck_move_epsilon = 4.0  # pixels - if moved less than this, consider stuck

        # Stuck detection for A* path following
        self._astar_stuck_timer = 0.0
        self._astar_stuck_threshold = 0.5  # seconds before considering stuck
        self._astar_last_pos = (float(self.x), float(self.y))
        self._astar_stuck_move_epsilon = 4.0  # pixels

        # Direction smoothing for smooth movement through narrow spaces
        self._preferred_direction = None  # (dx, dy) normalized direction
        self._direction_persistence_timer = 0.0
        self._direction_persistence_duration = 0.15  # seconds to persist direction before trying alternatives
        self._last_successful_direction = None

        # Random search state (for roaming)
        self._random_direction = random.uniform(0, 2 * math.pi)
        self._random_move_timer = 0.0
        self._random_move_duration = 2.0  # change direction every 2 seconds

        # Stuck detection to prevent being trapped in walls
        self._stuck_timer = 0.0
        self._stuck_threshold = 3.0
        self._stuck_move_epsilon = 3.0
        self._last_pos = (self.x, self.y)
        self._stuck_blast_radius_tiles = 8
        self._space_blast_radius_tiles = 12
        self._path_blast_threshold = 3.0
        # Cardinal space monitoring (disabled - Deadlight only needs 1 tile space, same as player)
        self._space_timer = 0.0
        self._space_threshold = 999.0  # effectively disabled - set very high so it never triggers
        self._space_required_tiles = 1  # only need 1 tile (same as physical size)

        # three dots offsets
        self.dots = [(-18, 0), (18, 0), (0, -18)]

        # Escape mode (vulnerable phase - run away from player)
        self._escape_mode = False
        self._escape_speed_multiplier = 1.5  # Speed boost when escaping from player
        self._under_player_light_speed_multiplier = 5.0  # Massive speed boost when under player's light

        # Flicker timer for invisibility effect when outside player's light
        self._flicker_timer = 0.0

    def start_chase(self, extra_time=None):
        """Start (or extend) chase mode. Each call adds to the remaining time."""
        added = float(extra_time) if extra_time is not None else self._chase_duration
        self._chase_mode = True
        self._chase_timer = max(0.0, self._chase_timer) + max(0.0, added)
        self._path = []  # clear any existing path
        self._path_index = 0
        # Reset stuck detection for simple chase
        self._simple_chase_stuck_timer = 0.0
        self._simple_chase_last_pos = (self.x, self.y)
        # Reset stuck detection for A* path following
        self._astar_stuck_timer = 0.0
        self._astar_last_pos = (self.x, self.y)
        # Reset direction smoothing
        self._preferred_direction = None
        self._direction_persistence_timer = 0.0
        self._last_successful_direction = None
        # Reset player position tracking
        self._last_player_pos = None

    def update(self, dt, player_x, player_y, grid, player_radiance=None):
        if not self.alive:
            return
        # Update flicker timer for invisibility effect when outside player's light
        if not hasattr(self, '_flicker_timer'):
            self._flicker_timer = 0.0
        self._flicker_timer += dt
        # Radiance is now health-based (no longer depends on enemy count)
        self.radiance = max(0.0, self.health)
        # Update speed based on health (lower health = higher speed)
        health_ratio = max(0.0, min(1.0, self.health / max(1.0, self.health_max)))
        # Speed increases as health decreases (inverse relationship)
        # When health is 100%: speed = min_speed
        # When health is 0%: speed = max_speed
        speed_factor = 1.0 - health_ratio  # 0.0 at full health, 1.0 at 0 health
        base_speed = self._min_speed + (self._max_speed - self._min_speed) * speed_factor

        # Check if Deadlight is under player's light (will be set by main2.py)
        under_player_light = getattr(self, '_under_player_light', False)

        # Apply speed multipliers
        if hasattr(self, '_escape_mode') and self._escape_mode:
            speed_mult = self._escape_speed_multiplier
            if under_player_light:
                speed_mult *= self._under_player_light_speed_multiplier
            self.speed = base_speed * speed_mult
        else:
            self.speed = base_speed
        self._base_speed = base_speed

        # Update chase timer if in chase mode
        if self._chase_mode:
            self._chase_timer -= dt
            if self._chase_timer <= 0:
                # Chase time expired, return to random search
                self._chase_mode = False
                self._chase_timer = 0.0
                self._path = []
                self._path_index = 0
                # Reset stuck detection for simple chase
                self._simple_chase_stuck_timer = 0.0
                self._simple_chase_last_pos = (self.x, self.y)
                # Reset to random direction
                self._random_direction = random.uniform(0, 2 * math.pi)

        # Priority: Chase mode > Escape mode > Random search
        # Note: chase_mode is now controlled by main2.py's phase system
        if self._chase_mode:
            # CHASE MODE: Hybrid approach - A* for close distances, simple movement for far distances
            dxp = player_x - self.x
            dyp = player_y - self.y
            dist_to_player = math.hypot(dxp, dyp)

            # Always use A* pathfinding for chase (no distance limit)
            if True:  # Always use A* pathfinding
                # Use A* pathfinding (accurate navigation through walls)
                # Update path periodically, but only if needed
                self._chase_path_update_timer += dt

                # Check if we need to recalculate path
                need_recalculate = False
                if not self._path:
                    need_recalculate = True
                elif self._last_player_pos is not None:
                    # Check if player moved significantly (including teleports)
                    dx = player_x - self._last_player_pos[0]
                    dy = player_y - self._last_player_pos[1]
                    player_moved = math.hypot(dx, dy)
                    # If player moved a large distance (teleport), force immediate recalculation
                    if player_moved >= self._player_teleport_threshold:
                        need_recalculate = True
                        self._chase_path_update_timer = self._chase_path_update_interval  # Reset timer
                    # Otherwise, check normal update interval and movement threshold
                    elif self._chase_path_update_timer >= self._chase_path_update_interval:
                        if player_moved >= self._player_move_threshold:
                            need_recalculate = True
                elif self._chase_path_update_timer >= self._chase_path_update_interval:
                    # No last position tracked yet, recalculate
                    need_recalculate = True

                if need_recalculate:
                    self._chase_path_update_timer = 0.0
                    # Path to player position
                    self._path = self._compute_path(grid, (player_x, player_y))
                    self._path_index = 0
                    # Reset stuck detection when recalculating path
                    self._astar_stuck_timer = 0.0
                    self._astar_last_pos = (self.x, self.y)
                    # Update last known player position
                    self._last_player_pos = (player_x, player_y)

                # Follow path if available
                moved_this_frame = False
                if self._path and self._path_index < len(self._path):
                    # Check if path target is still valid (player might have teleported)
                    if self._last_player_pos is not None:
                        # Check if the path's final destination is too far from current player position
                        if len(self._path) > 0:
                            final_target = self._path[-1]
                            dist_to_final = math.hypot(final_target[0] - player_x, final_target[1] - player_y)
                            # If final target is more than 100 pixels from player, path is invalid
                            if dist_to_final > 100.0:
                                # Clear invalid path to force recalculation
                                self._path = []
                                self._path_index = 0
                                self._chase_path_update_timer = self._chase_path_update_interval

                    if self._path and self._path_index < len(self._path):
                        tx, ty = self._path[self._path_index]
                        dx = tx - self.x
                        dy = ty - self.y
                        dist = math.hypot(dx, dy)
                        if dist < 6:
                            self._path_index += 1
                            # Consider it moved if we reached a waypoint
                            moved_this_frame = True
                        else:
                            nx = self.x + (dx / dist) * self.speed * dt
                            ny = self.y + (dy / dist) * self.speed * dt
                            old_x, old_y = self.x, self.y
                            if self._move_if_free(nx, ny, grid):
                                moved_this_frame = (abs(self.x - old_x) > 0.1 or abs(self.y - old_y) > 0.1)

                # Check if stuck while following A* path
                if moved_this_frame:
                    self._astar_stuck_timer = 0.0
                    self._astar_last_pos = (self.x, self.y)
                else:
                    # Check if we actually moved
                    dist_moved = math.hypot(self.x - self._astar_last_pos[0],
                                            self.y - self._astar_last_pos[1])
                    if dist_moved >= self._astar_stuck_move_epsilon:
                        self._astar_stuck_timer = 0.0
                        self._astar_last_pos = (self.x, self.y)
                    else:
                        self._astar_stuck_timer += dt
                        # If stuck for too long, try to recalculate path
                        if self._astar_stuck_timer >= self._astar_stuck_threshold:
                            # Force path recalculation
                            self._chase_path_update_timer = self._chase_path_update_interval
                            self._astar_stuck_timer = 0.0
                            # Try jitter movement as fallback
                            self._attempt_jitter_move(self.speed * dt * 0.5, grid)

                # If no path found, try jitter movement to get unstuck
                if not self._path or self._path_index >= len(self._path):
                    # No valid path - try to move randomly to find a better position
                    self._attempt_jitter_move(self.speed * dt * 0.3, grid)

            self._update_stuck_state(dt, grid)
            self._update_space_state(dt, grid)
            return  # Skip other movement logic when chasing

        # RANDOM SEARCH MODE or ESCAPE MODE:
        # If _escape_mode is True, Deadlight actively runs away from player
        # Otherwise, just random movement
        self._follow_player_mode = False
        self._guard_target = None
        # restore baseline movement parameters
        try:
            self.speed = float(self._base_speed)
            self._think_interval = float(self._base_think_interval)
        except Exception:
            pass

        # Check if we should escape from player (vulnerable phase)
        if hasattr(self, '_escape_mode') and self._escape_mode:
            # ESCAPE MODE: Use A* pathfinding to move to a floor tile just outside player's light area
            dx = self.x - player_x
            dy = self.y - player_y
            dist_to_player = math.hypot(dx, dy)

            # Calculate escape target (floor tile just outside player's light radius)
            if dist_to_player > 0:
                # Normalize direction away from player
                escape_dir_x = dx / dist_to_player
                escape_dir_y = dy / dist_to_player

                # Get player's light radius - use provided value or estimate
                if player_radiance is not None:
                    player_light_radius = player_radiance
                else:
                    # Fallback estimate if not provided
                    player_light_radius = 250

                # Calculate escape target just outside player's light radius
                # Add some buffer to ensure we're clearly outside
                escape_distance = player_light_radius + 150  # Just outside player's light + buffer

                # Target is just outside player's light area in direction away from player
                escape_target_x = player_x + escape_dir_x * escape_distance
                escape_target_y = player_y + escape_dir_y * escape_distance

                # Get map bounds from grid
                grid_h = len(grid) if grid else 0
                grid_w = len(grid[0]) if grid_h > 0 and grid else 0
                map_max_x = grid_w * TILE_SIZE if grid_w > 0 else 1700
                map_max_y = grid_h * TILE_SIZE if grid_h > 0 else 950

                # Clamp target to map bounds
                escape_target_x = max(TILE_SIZE, min(map_max_x - TILE_SIZE, escape_target_x))
                escape_target_y = max(TILE_SIZE, min(map_max_y - TILE_SIZE, escape_target_y))

                # Find nearest floor tile to the escape target
                target_tx = int(escape_target_x // TILE_SIZE)
                target_ty = int(escape_target_y // TILE_SIZE)

                # Check if target is already on a floor tile
                if (0 <= target_tx < grid_w and 0 <= target_ty < grid_h and
                        grid[target_ty][target_tx] == 0):
                    # Target is already on floor, use it
                    final_target_x = target_tx * TILE_SIZE + TILE_SIZE // 2
                    final_target_y = target_ty * TILE_SIZE + TILE_SIZE // 2
                else:
                    # Find nearest floor tile to the target
                    best_floor = None
                    best_dist = float('inf')
                    search_radius = 10  # Search up to 10 tiles away

                    for dy_search in range(-search_radius, search_radius + 1):
                        for dx_search in range(-search_radius, search_radius + 1):
                            check_tx = target_tx + dx_search
                            check_ty = target_ty + dy_search

                            if (0 <= check_tx < grid_w and 0 <= check_ty < grid_h and
                                    grid[check_ty][check_tx] == 0):
                                # Found a floor tile
                                floor_x = check_tx * TILE_SIZE + TILE_SIZE // 2
                                floor_y = check_ty * TILE_SIZE + TILE_SIZE // 2
                                dist_to_target = math.hypot(floor_x - escape_target_x,
                                                            floor_y - escape_target_y)
                                if dist_to_target < best_dist:
                                    best_dist = dist_to_target
                                    best_floor = (floor_x, floor_y)

                    if best_floor:
                        final_target_x, final_target_y = best_floor
                    else:
                        # Fallback: use original target (shouldn't happen, but safety)
                        final_target_x = escape_target_x
                        final_target_y = escape_target_y

                # Update escape path periodically (every 0.8s)
                escape_path_update_interval = 0.8
                self._chase_path_update_timer += dt
                need_path_update = (not self._path or
                                    self._chase_path_update_timer >= escape_path_update_interval or
                                    self._path_index >= len(self._path))

                if need_path_update:
                    self._chase_path_update_timer = 0.0
                    # Use A* to find path to escape target (floor tile)
                    self._path = self._compute_path(grid, (final_target_x, final_target_y))
                    self._path_index = 0

                # Follow A* escape path
                moved_this_frame = False
                if self._path and self._path_index < len(self._path):
                    tx, ty = self._path[self._path_index]
                    dx = tx - self.x
                    dy = ty - self.y
                    dist = math.hypot(dx, dy)
                    if dist < 8:
                        self._path_index += 1
                        moved_this_frame = True
                    else:
                        if dist > 0:
                            old_x, old_y = self.x, self.y
                            nx = self.x + (dx / dist) * self.speed * dt
                            ny = self.y + (dy / dist) * self.speed * dt
                            if self._move_if_free(nx, ny, grid):
                                moved_this_frame = (abs(self.x - old_x) > 0.1 or abs(self.y - old_y) > 0.1)

                # If no path or path following failed, recalculate path
                if not moved_this_frame:
                    # Force path recalculation on next frame
                    self._chase_path_update_timer = escape_path_update_interval
                    # Try jitter movement as temporary measure
                    self._attempt_jitter_move(self.speed * dt * 0.5, grid)

                # Update stuck detection for escape
                if moved_this_frame:
                    self._astar_stuck_timer = 0.0
                    self._astar_last_pos = (self.x, self.y)
                else:
                    dist_moved = math.hypot(self.x - self._astar_last_pos[0],
                                            self.y - self._astar_last_pos[1])
                    if dist_moved >= 4.0:
                        self._astar_stuck_timer = 0.0
                        self._astar_last_pos = (self.x, self.y)
                    else:
                        self._astar_stuck_timer += dt
                        # If stuck, force path recalculation
                        if self._astar_stuck_timer >= 0.3:
                            self._chase_path_update_timer = escape_path_update_interval
                            self._astar_stuck_timer = 0.0
                            self._path = []  # Clear path to force recalculation
        else:
            # RANDOM MOVEMENT MODE
            # Update random direction periodically
            self._random_move_timer += dt
            if self._random_move_timer >= self._random_move_duration:
                self._random_move_timer = 0.0
                self._random_direction = random.uniform(0, 2 * math.pi)

            # Move in random direction
            move_dist = self.speed * dt
            nx = self.x + math.cos(self._random_direction) * move_dist
            ny = self.y + math.sin(self._random_direction) * move_dist

            if not self._move_if_free(nx, ny, grid):
                # Hit a wall, change direction and try once more
                self._random_direction = random.uniform(0, 2 * math.pi)
                nx = self.x + math.cos(self._random_direction) * move_dist
                ny = self.y + math.sin(self._random_direction) * move_dist
                self._move_if_free(nx, ny, grid)

        # Update stuck timer / blast if necessary
        self._update_stuck_state(dt, grid)
        self._update_space_state(dt, grid)

    def player_in_radiance(self, px, py, grid):
        """Return True only if player is within radiance AND line-of-sight (not occluded by walls)."""
        if not self.alive:
            return False
        # Update radiance from health
        self.radiance = max(0.0, self.health)
        dx = px - self.x
        dy = py - self.y
        dist_player = math.hypot(dx, dy)
        if dist_player > self.radiance:
            return False
        # Use raycast to determine occlusion: cast towards player angle and see how far the ray reached
        ang = math.degrees(math.atan2(dy, dx)) % 360
        # ensure raycast respects the Deadlight's radiance
        hit_x, hit_y = cast_ray(grid, self.x, self.y, ang, max_distance=self.radiance)
        dist_hit = math.hypot(hit_x - self.x, hit_y - self.y)
        # If the ray reached at least to the player's distance (with small epsilon), player is visible
        return dist_hit + 1e-6 >= dist_player

    def drain_radiance(self, amount):
        """Drain health/radiance (damage)."""
        if amount <= 0:
            return
        self.health = max(0.0, self.health - amount)
        self.radiance = max(0.0, self.health)
        if self.health <= 0:
            self.alive = False

    def take_blast(self, px, py, blast_radius, all_entities_dead=False):
        """Attempt to kill boss with a special blast. Only kills if all_entities_dead True and within blast_radius"""
        if not self.alive:
            return False
        d = math.hypot(self.x - px, self.y - py)
        if all_entities_dead and d <= blast_radius:
            self.alive = False
            return True
        return False

    def apply_multiplier(self, mult):
        """Apply a multiplier to deadlight aggression: increase speed and lower think interval (more frequent pathing)."""
        try:
            self.speed *= float(mult)
            self._base_speed *= float(mult)
            # make pathfinding more frequent (smaller interval) as it gets angrier
            self._think_interval = max(0.35, self._think_interval / float(mult))
        except Exception:
            pass

    def get_chase_time_remaining(self):
        """Return remaining chase time in seconds, or 0 if not chasing."""
        if self._chase_mode:
            return max(0.0, self._chase_timer)
        return 0.0

    def is_chasing(self):
        """Return True if currently in chase mode."""
        return self._chase_mode

    def draw(self, surface, grid, show_light=True, visible_in_player_light=True, flicker_cycle=0.3):
        """Render the deadlight's occluded light using raycasting (like the player's light).
        show_light: if False, don't draw the blue radiance (used during vulnerable phase)
        visible_in_player_light: if False, draw as black shadow instead of normal colors
        flicker_cycle: flicker cycle duration in seconds (adjustable based on phase)
        """
        if not self.alive:
            return
        # Radiance is synced in check_light_overlap_damage, but ensure it's updated here for drawing
        if hasattr(self, 'min_radiance'):
            health_ratio = max(0.0, self.health / max(1.0, self.health_max))
            self.radiance = self.min_radiance + (self.base_radiance - self.min_radiance) * health_ratio
        else:
            self.radiance = max(0.0, self.health)

        # Only draw blue radiance light during chase phase (when show_light=True) and when visible
        if show_light and self.radiance > 0 and visible_in_player_light:
            # build light polygon via raycasting
            points = []
            for ang in range(0, 360, ANGLE_STEP):
                # cast rays up to the deadlight's radiance to build the light polygon
                wx, wy = cast_ray(grid, self.x, self.y, ang, max_distance=self.radiance)
                dx, dy = wx - self.x, wy - self.y
                dist = math.hypot(dx, dy)
                if dist > self.radiance and dist > 0:
                    scale = self.radiance / dist
                    wx = self.x + dx * scale
                    wy = self.y + dy * scale
                # Camera is always at (0, 0), so world coordinates = screen coordinates
                points.append((int(wx), int(wy)))

            if len(points) >= 3:
                light_surf = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
                # bluish glow polygon
                pygame.draw.polygon(light_surf, (60, 120, 255, 120), points)
                surface.blit(light_surf, (0, 0))

        # draw three dots on top (purely visual - can overlap with blocks, no collision)
        # Camera is always at (0, 0), so world coordinates = screen coordinates
        x = int(self.x)
        y = int(self.y)

        if visible_in_player_light:
            # Normal colors when visible in player's light
            for ox, oy in self.dots:
                pygame.draw.circle(surface, (245, 245, 255), (x + ox, y + oy), 6)
                pygame.draw.circle(surface, (100, 150, 255), (x + ox, y + oy), 8, 2)
        else:
            # Flicker effect: alternate between black shadow and invisible
            # flicker_cycle is passed as parameter (adjustable based on phase)
            flicker_phase = (self._flicker_timer % flicker_cycle) / flicker_cycle
            # Show shadow for first half of cycle, invisible for second half
            if flicker_phase < 0.5:
                # Black shadow when outside player's light (visible phase)
                for ox, oy in self.dots:
                    pygame.draw.circle(surface, (20, 20, 20), (x + ox, y + oy), 6)
                    pygame.draw.circle(surface, (0, 0, 0), (x + ox, y + oy), 8, 2)
            # else: invisible (don't draw anything)

    # ---------------- internal helpers ----------------
    def _move_if_free(self, nx, ny, grid):
        """Check if Deadlight can move to new position. Only checks the center tile (one block size).
        The three lights on top are purely visual and can overlap with blocks without affecting movement."""
        txn, tyn = int(nx) // TILE_SIZE, int(ny) // TILE_SIZE
        if 0 <= tyn < len(grid) and 0 <= txn < len(grid[0]) and grid[tyn][txn] == 0:
            self.x, self.y = nx, ny
            return True
        return False

    def _attempt_jitter_move(self, magnitude, grid):
        angle = random.random() * math.tau
        nx = self.x + math.cos(angle) * magnitude
        ny = self.y + math.sin(angle) * magnitude
        if not self._move_if_free(nx, ny, grid):
            # try opposite direction
            nx = self.x - math.cos(angle) * magnitude
            ny = self.y - math.sin(angle) * magnitude
            self._move_if_free(nx, ny, grid)

    def _simple_chase_move(self, player_x, player_y, grid, dt):
        move_dist = self.speed * dt
        dx = player_x - self.x
        dy = player_y - self.y
        if dx == 0 and dy == 0:
            return

        # Normalize direction toward player
        dist_to_player = math.hypot(dx, dy)
        if dist_to_player == 0:
            return
        target_dir_x = dx / dist_to_player
        target_dir_y = dy / dist_to_player

        # Update direction persistence timer
        self._direction_persistence_timer += dt

        # If we have a preferred direction that's still valid, try it first
        # This prevents jittery movement by persisting direction choices
        if self._preferred_direction is not None and self._direction_persistence_timer < self._direction_persistence_duration:
            pref_x, pref_y = self._preferred_direction
            nx = self.x + pref_x * move_dist
            ny = self.y + pref_y * move_dist
            if self._move_if_free(nx, ny, grid):
                # Success! Keep using this direction
                self._last_successful_direction = self._preferred_direction
                return
            # Preferred direction blocked, but keep trying for a bit longer
            # This helps in narrow spaces where we need to commit to a direction

        # Try direct movement toward player
        nx = self.x + target_dir_x * move_dist
        ny = self.y + target_dir_y * move_dist
        if self._move_if_free(nx, ny, grid):
            # Direct path works, use it and reset preferred direction
            self._preferred_direction = (target_dir_x, target_dir_y)
            self._direction_persistence_timer = 0.0
            self._last_successful_direction = (target_dir_x, target_dir_y)
            return

        # If we had a successful direction recently, try it again (helps in narrow corridors)
        if self._last_successful_direction is not None:
            last_x, last_y = self._last_successful_direction
            nx = self.x + last_x * move_dist
            ny = self.y + last_y * move_dist
            if self._move_if_free(nx, ny, grid):
                self._preferred_direction = self._last_successful_direction
                self._direction_persistence_timer = 0.0
                return

        # Direct path blocked - need to find alternative
        # Only try alternatives if we've persisted the preferred direction long enough
        # or if we don't have a preferred direction
        if self._preferred_direction is None or self._direction_persistence_timer >= self._direction_persistence_duration:
            # Reset persistence timer and find new direction
            self._direction_persistence_timer = 0.0

            # Calculate base direction components
            horiz = -1 if dx < 0 else 1
            vert = -1 if dy < 0 else 1

            # Try directions in order of preference (prioritize directions closer to target)
            alternative_dirs = [
                (horiz, vert),  # Primary diagonal (toward player)
                (horiz, 0),  # Horizontal (toward player)
                (0, vert),  # Vertical (toward player)
                (-horiz, vert),  # Perpendicular diagonal 1
                (horiz, -vert),  # Perpendicular diagonal 2
                (-horiz, 0),  # Opposite horizontal
                (0, -vert),  # Opposite vertical
                (-horiz, -vert),  # Opposite diagonal
            ]

            # Try each alternative direction
            for dirx, diry in alternative_dirs:
                length = math.hypot(dirx, diry) or 1.0
                norm_x = dirx / length
                norm_y = diry / length
                nx = self.x + norm_x * move_dist
                ny = self.y + norm_y * move_dist
                if self._move_if_free(nx, ny, grid):
                    # Found a working direction - set it as preferred
                    self._preferred_direction = (norm_x, norm_y)
                    self._last_successful_direction = (norm_x, norm_y)
                    return

            # If all full-step directions failed, try smaller steps
            for dirx, diry in alternative_dirs:
                length = math.hypot(dirx, diry) or 1.0
                norm_x = dirx / length
                norm_y = diry / length
                nx = self.x + norm_x * move_dist * 0.5
                ny = self.y + norm_y * move_dist * 0.5
                if self._move_if_free(nx, ny, grid):
                    self._preferred_direction = (norm_x, norm_y)
                    self._last_successful_direction = (norm_x, norm_y)
                    return

            # All directions failed - clear preferred direction and try jitter
            self._preferred_direction = None
            self._attempt_jitter_move(move_dist * 0.6, grid)

    def _try_unstick_simple_chase(self, player_x, player_y, grid, dt):
        """When stuck in simple chase mode, try to find nearby free spaces to navigate around obstacles."""
        if grid is None:
            return

        move_dist = self.speed * dt
        tx = int(self.x) // TILE_SIZE
        ty = int(self.y) // TILE_SIZE
        h = len(grid)
        w = len(grid[0]) if h > 0 else 0
        if w == 0:
            return

        # Check nearby tiles in a radius to find free spaces
        # Prioritize spaces that are closer to the player
        best_pos = None
        best_score = float('inf')
        check_radius = 3  # check 3 tiles in each direction

        for dy in range(-check_radius, check_radius + 1):
            for dx in range(-check_radius, check_radius + 1):
                nx = tx + dx
                ny = ty + dy
                if 0 <= nx < w and 0 <= ny < h:
                    # Check if this tile is free
                    if grid[ny][nx] == 0:
                        # Calculate world position of this tile center
                        wx = nx * TILE_SIZE + TILE_SIZE / 2
                        wy = ny * TILE_SIZE + TILE_SIZE / 2

                        # Score: distance to player (lower is better)
                        dist_to_player = math.hypot(wx - player_x, wy - player_y)
                        dist_from_current = math.hypot(wx - self.x, wy - self.y)

                        # Prefer closer tiles that are also closer to player
                        score = dist_to_player + dist_from_current * 0.5
                        if score < best_score:
                            best_score = score
                            best_pos = (wx, wy)

        # If we found a good position, try to move toward it
        if best_pos is not None:
            bx, by = best_pos
            dx = bx - self.x
            dy = by - self.y
            dist = math.hypot(dx, dy)
            if dist > 0:
                # Move toward the best free space
                nx = self.x + (dx / dist) * move_dist
                ny = self.y + (dy / dist) * move_dist
                self._move_if_free(nx, ny, grid)

    def _update_stuck_state(self, dt, grid):
        dist = math.hypot(self.x - self._last_pos[0], self.y - self._last_pos[1])
        if dist >= self._stuck_move_epsilon:
            self._stuck_timer = 0.0
            self._last_pos = (self.x, self.y)
            return
        self._stuck_timer += dt
        if self._stuck_timer >= self._stuck_threshold:
            self._perform_power_blast(grid, self._stuck_blast_radius_tiles)
            self._stuck_timer = 0.0
            self._last_pos = (self.x, self.y)

    def _perform_power_blast(self, grid, radius_tiles):
        if grid is None:
            return
        tx = int(self.x) // TILE_SIZE
        ty = int(self.y) // TILE_SIZE
        h = len(grid)
        w = len(grid[0]) if h > 0 else 0
        if w == 0:
            return
        radius = max(1, int(radius_tiles))
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                nx = tx + dx
                ny = ty + dy
                if 0 <= nx < w and 0 <= ny < h:
                    if grid[ny][nx] in (1, 2):
                        grid[ny][nx] = 0
        # ensure we are positioned on a walkable tile
        self._ensure_on_floor(grid)

    def _ensure_on_floor(self, grid):
        tx = int(self.x) // TILE_SIZE
        ty = int(self.y) // TILE_SIZE
        h = len(grid)
        w = len(grid[0]) if h > 0 else 0
        if w == 0:
            return
        if 0 <= tx < w and 0 <= ty < h and grid[ty][tx] == 0:
            return
        max_radius = 4
        for r in range(1, max_radius + 1):
            for dy in range(-r, r + 1):
                for dx in range(-r, r + 1):
                    nx = tx + dx
                    ny = ty + dy
                    if 0 <= nx < w and 0 <= ny < h and grid[ny][nx] == 0:
                        self.x = nx * TILE_SIZE + TILE_SIZE / 2
                        self.y = ny * TILE_SIZE + TILE_SIZE / 2
                        return

    def _update_space_state(self, dt, grid):
        if grid is None:
            return
        if self._has_cardinal_space(grid):
            self._space_timer = 0.0
            return
        self._space_timer += dt
        if self._space_timer >= self._space_threshold:
            self._perform_power_blast(grid, self._space_blast_radius_tiles)
            self._space_timer = 0.0

    def _has_cardinal_space(self, grid):
        """Check if Deadlight has at least minimal space (1 tile) in any cardinal direction.
        Deadlight only needs 1 tile space since its physical size is just one block."""
        tx = int(self.x) // TILE_SIZE
        ty = int(self.y) // TILE_SIZE
        h = len(grid)
        w = len(grid[0]) if h > 0 else 0
        if w == 0:
            return True
        # Only need 1 tile of space (same as physical size)
        required = 1
        directions = ((0, -1), (0, 1), (-1, 0), (1, 0))
        for dx, dy in directions:
            # Check just the adjacent tile
            nx = tx + dx
            ny = ty + dy
            if 0 <= nx < w and 0 <= ny < h and grid[ny][nx] == 0:
                return True
        return False

    def _compute_path(self, grid, goal):
        if grid is None or goal is None:
            return []
        start_time = time.perf_counter()
        path = []

        # Calculate distance to goal to optimize pathfinding
        dx = goal[0] - self.x
        dy = goal[1] - self.y
        dist_to_goal = math.hypot(dx, dy)

        # For very long distances, use reduced max_nodes to improve performance
        # Scale max_nodes based on distance (closer = more nodes, farther = fewer nodes)
        max_nodes = 2000
        if dist_to_goal > 500:  # Very far away
            max_nodes = 1000  # Reduce search space
        elif dist_to_goal > 1000:  # Extremely far
            max_nodes = 500  # Even more aggressive reduction

        try:
            # Use custom max_nodes for performance
            path = find_path(grid, (self.x, self.y), goal, max_nodes=max_nodes)
            # If pathfinding returns empty, it means no path found - this is valid, return empty
        except Exception:
            path = []
        duration = time.perf_counter() - start_time
        if duration >= self._path_blast_threshold:
            # Pathfinding took too long, blast nearby walls and try again
            self._perform_power_blast(grid, self._stuck_blast_radius_tiles)
            try:
                path = find_path(grid, (self.x, self.y), goal, max_nodes=max_nodes)
            except Exception:
                path = []
        # Return path (may be empty if no path found - caller should handle this)
        return path
