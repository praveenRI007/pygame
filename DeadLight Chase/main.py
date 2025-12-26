import pygame
import time
import math
import random
import traceback
from datetime import datetime
from game_utils.pet import Pet
from game_utils.player import Player
from game_utils.deadlight import DeadlightBoss
from game_utils.procedural_gen import Perlin2D
from game_utils.game_util import show_start_screen

# ============================================================================
# GAME SETTINGS AND CONSTANTS
# ============================================================================

# ---------------- Display & Map Settings ----------------
WINDOW_SIZE_H = 1700
WINDOW_SIZE_V = 950
TILE_SIZE = 8
MAP_SIZE_H = WINDOW_SIZE_H
MAP_SIZE_V = WINDOW_SIZE_V
GRID_W = MAP_SIZE_H // TILE_SIZE
GRID_H = MAP_SIZE_V // TILE_SIZE

# ---------------- Visual Settings ----------------
COLOR_FLOOR = (60, 60, 60)
COLOR_WALL = (20, 20, 20)
LIGHT_RADIUS = 200
RAY_STEP = 5
RAY_ANGLE_STEP = 2
SPECIAL_RADIUS = LIGHT_RADIUS // 3
BOUNDARY_WALL_VALUE = 3  # unbreakable perimeter tiles

# ---------------- Phase Settings ----------------
CHASE_PHASE_DURATION = 60.0  # seconds - Deadlight chases player
VULNERABLE_PHASE_DURATION = 60.0  # seconds - Player can chase Deadlight

# ---------------- Enemy Flicker Settings ----------------
FLICKER_CYCLE_CHASE = 1  # seconds - flicker cycle during chase phase
FLICKER_CYCLE_VULNERABLE = 3.0  # seconds - flicker cycle during vulnerable phase

# ---------------- Enemy Teleport Settings ----------------
# Chase phase (enemy searching for player)
TELEPORT_NOT_FOUND_TIME = 7.0  # seconds - teleport if player stays away from enemy's light
TELEPORT_COOLDOWN = 7.0  # seconds - cooldown between enemy teleports
TELEPORT_MIN_DISTANCE = 80.0  # pixels - minimum distance from player
TELEPORT_BUFFER_OUTSIDE_LIGHT = 30.0  # pixels - teleport just outside light radius
TELEPORT_MAX_DISTANCE_FROM_LIGHT = 150.0  # pixels - maximum distance from light edge

# ---------------- Player Teleport Settings ----------------

player_teleport_cost = 40  # special charge cost to teleport to pet during chase phase

# Vulnerable phase (player chasing enemy)
VULNERABLE_TELEPORT_INTERVAL = 5.0  # seconds - deadlight teleports every 5 seconds

# ---------------- Light Overlap Damage Settings ----------------
# When player is in Deadlight's blue light (chase phase)
PLAYER_HEALTH_DRAIN_RATE = 5.0  # player health damage per second
PLAYER_BASE_RADIANCE_DRAIN_RATE = 5.0  # player base_radiance decrease per second

# When Deadlight is in player's light (vulnerable phase)
DEADLIGHT_HEALTH_DRAIN_RATE = 5.0  # deadlight health damage per second
DEADLIGHT_BASE_RADIANCE_DRAIN_RATE = 5.0  # deadlight base_radiance decrease per second

# ---------------- Pet Settings ----------------
PET_BUFF_DISTANCE = 48  # pixels - distance for pet buff
PET_REGEN_MULT = 4.0  # multiplier for regen when pet is near
PET_SPLIT_DURATION = 30.0  # seconds - how long pets stay split
NUM_SPLIT_PETS = 5  # number of pets when split

# ---------------- Combat Settings ----------------
WAVE_RANGE = 120  # pixels - wave attack range
WAVE_ANGLE_DEG = 50  # degrees - wave cone angle
BREAK_COST = 5  # stamina cost to break a tile


# ---------------- Local Map Generation ----------------
def generate_map(seed):
    """Generate map using local GRID_W and GRID_H dimensions."""
    per = Perlin2D(seed)
    grid = [[0] * GRID_W for _ in range(GRID_H)]
    for y in range(GRID_H):
        for x in range(GRID_W):
            # Impenetrable 3-tile-thick boundary that cannot be broken or crossed
            if x < 3 or y < 3 or x >= GRID_W - 3 or y >= GRID_H - 3:
                grid[y][x] = 3
            else:
                v = per.fractal(x * 0.05, y * 0.05)
                grid[y][x] = 1 if v > 0.05 else 0
    return grid


def is_wall(grid, px, py):
    """Check if a position is a wall using local grid dimensions."""
    tx = int(px) // TILE_SIZE
    ty = int(py) // TILE_SIZE
    if tx < 0 or ty < 0 or tx >= GRID_W or ty >= GRID_H:
        return True
    # Treat 1 = generated wall, 2 = player-built wall, 3 = boundary wall as blocking
    return grid[ty][tx] in (1, 2, 3)


def cast_ray(grid, ox, oy, angle, max_distance=None):
    """Cast a ray with local map size bounds."""
    if max_distance is None:
        max_distance = LIGHT_RADIUS
    ang = math.radians(angle)
    dx = math.cos(ang)
    dy = math.sin(ang)
    dist = 0
    while dist < max_distance:
        dist += RAY_STEP
        x = ox + dx * dist
        y = oy + dy * dist
        if x < 0 or y < 0 or x >= MAP_SIZE_H or y >= MAP_SIZE_V:
            return x, y
        if is_wall(grid, x, y):
            # step back a bit so the hit point is slightly before the wall
            return x - dx * 3, y - dy * 3
    return ox + dx * max_distance, oy + dy * max_distance


def spawn_on_floor(grid):
    """Find a random floor tile using the grid's actual dimensions."""
    grid_h = len(grid)
    grid_w = len(grid[0]) if grid_h > 0 else 0
    max_attempts = 512
    for _ in range(max_attempts):
        tx = random.randint(0, grid_w - 1)
        ty = random.randint(0, grid_h - 1)
        if 0 <= tx < grid_w and 0 <= ty < grid_h and grid[ty][tx] == 0:
            px = tx * TILE_SIZE + TILE_SIZE // 2
            py = ty * TILE_SIZE + TILE_SIZE // 2
            return px, py
    # fallback deterministic scan
    for ty in range(grid_h):
        for tx in range(grid_w):
            if grid[ty][tx] == 0:
                px = tx * TILE_SIZE + TILE_SIZE // 2
                py = ty * TILE_SIZE + TILE_SIZE // 2
                return px, py
    # If no floor found, return center
    return MAP_SIZE_H // 2, MAP_SIZE_V // 2


def perform_special_attack(grid, px, py, break_effects, floor_overlays):
    destroyed = 0
    gen_broken = 0
    player_broken = 0
    min_tx = max(0, int((px - SPECIAL_RADIUS) // TILE_SIZE))
    max_tx = min(GRID_W - 1, int((px + SPECIAL_RADIUS) // TILE_SIZE))
    min_ty = max(0, int((py - SPECIAL_RADIUS) // TILE_SIZE))
    max_ty = min(GRID_H - 1, int((py + SPECIAL_RADIUS) // TILE_SIZE))
    for ty in range(min_ty, max_ty + 1):
        for tx in range(min_tx, max_tx + 1):
            t_cx = tx * TILE_SIZE + TILE_SIZE / 2
            t_cy = ty * TILE_SIZE + TILE_SIZE / 2
            if math.hypot(t_cx - px, t_cy - py) <= SPECIAL_RADIUS:
                # allow player to destroy generated walls (1) and player-built walls (2) but never boundary walls (3)
                if grid[ty][tx] != 0 and grid[ty][tx] != BOUNDARY_WALL_VALUE:
                    if grid[ty][tx] == 1:
                        gen_broken += 1
                    else:
                        player_broken += 1
                    grid[ty][tx] = 0
                    destroyed += 1
                    break_effects.append([tx, ty, 0.0])
                    floor_overlays.append([tx, ty, 0.0])
    return destroyed, gen_broken, player_broken


# Helper: check if lights overlap and apply damage
def check_light_overlap_damage(player, deadlight, dt, phase, grid):
    """Check if player is in deadlight's light area or deadlight is in player's light area.
    Uses raycasting to check if entities are actually within the light area (considering walls).
    phase: 'chase' (deadlight chases player) or 'vulnerable' (player chases deadlight)
    Returns True if Deadlight was hit by player's light, False otherwise.
    """
    if not deadlight or not deadlight.alive:
        return False

    # Ensure radiance is synced with health (for accurate radius calculations)
    # Use same formula for both player and Deadlight
    # Initialize Deadlight's min_radiance if not set
    if not hasattr(deadlight, 'min_radiance'):
        deadlight.min_radiance = deadlight.base_radiance * 0.25

    player_health_ratio = max(0.0, player.health / max(1.0, player.health_max))
    player.radiance = player.min_radiance + (player.base_radiance - player.min_radiance) * player_health_ratio

    deadlight_health_ratio = max(0.0, deadlight.health / max(1.0, deadlight.health_max))
    deadlight.radiance = deadlight.min_radiance + (
            deadlight.base_radiance - deadlight.min_radiance) * deadlight_health_ratio

    dx = player.x - deadlight.x
    dy = player.y - deadlight.y
    dist = math.hypot(dx, dy)

    if dist <= 0:
        return False

    player_radius = player.radiance
    deadlight_radius = deadlight.radiance

    # Check if player is within deadlight's blue light area (only during chase phase)
    if phase == 'chase' and deadlight_radius > 0:
        if dist <= deadlight_radius:
            # Check if deadlight's light can actually reach player (raycast check)
            # Calculate angle from deadlight to player
            ang_to_player = math.degrees(math.atan2(dy, dx)) % 360
            hit_x, hit_y = cast_ray(grid, deadlight.x, deadlight.y, ang_to_player, max_distance=deadlight_radius)
            hit_dist = math.hypot(hit_x - deadlight.x, hit_y - deadlight.y)
            if hit_dist + 1e-6 >= dist:  # Deadlight's light reaches player
                # Player is under deadlight's blue light - drain player's health and base_radiance
                # Use same logic as Deadlight for consistency
                health_drain = PLAYER_HEALTH_DRAIN_RATE * dt
                player.health = max(0.0, player.health - health_drain)
                # Also reduce base_radiance (maximum possible light radius) - permanent reduction
                base_radiance_drain = PLAYER_BASE_RADIANCE_DRAIN_RATE * dt
                player.base_radiance = max(player.min_radiance + 1.0, player.base_radiance - base_radiance_drain)
                # Update min_radiance proportionally (keep it at 25% of base_radiance)
                player.min_radiance = player.base_radiance * 0.25
                # Update radiance immediately to reflect the reduced base
                health_ratio = max(0.0, player.health / max(1.0, player.health_max))
                player.radiance = player.min_radiance + (player.base_radiance - player.min_radiance) * health_ratio
                return False  # Player was hit, not Deadlight

    # Check if deadlight is within player's light area (only during vulnerable phase)
    elif phase == 'vulnerable' and player_radius > 0:
        if dist <= player_radius:
            # Check if player's light can actually reach deadlight (raycast check)
            ang_to_deadlight = math.degrees(math.atan2(dy, dx)) % 360
            hit_x, hit_y = cast_ray(grid, player.x, player.y, ang_to_deadlight, max_distance=player_radius)
            hit_dist = math.hypot(hit_x - player.x, hit_y - player.y)
            if hit_dist + 1e-6 >= dist:  # Player's light reaches deadlight
                # Deadlight is under player's light - use same logic as player for consistency
                # Drain health (same rate as player)
                health_drain = DEADLIGHT_HEALTH_DRAIN_RATE * dt
                deadlight.health = max(0.0, deadlight.health - health_drain)
                # Also reduce base_radiance (permanent reduction, same rate as player)
                base_radiance_drain = DEADLIGHT_BASE_RADIANCE_DRAIN_RATE * dt
                # Ensure Deadlight has min_radiance (same as player)
                if not hasattr(deadlight, 'min_radiance'):
                    deadlight.min_radiance = deadlight.base_radiance * 0.25
                deadlight.base_radiance = max(deadlight.min_radiance + 1.0,
                                              deadlight.base_radiance - base_radiance_drain)
                # Update min_radiance proportionally (keep it at 25% of base_radiance, same as player)
                deadlight.min_radiance = deadlight.base_radiance * 0.25
                # Update health_max to match base_radiance
                deadlight.health_max = deadlight.base_radiance
                # Update radiance using SAME formula as player
                health_ratio = max(0.0, deadlight.health / max(1.0, deadlight.health_max))
                deadlight.radiance = deadlight.min_radiance + (
                        deadlight.base_radiance - deadlight.min_radiance) * health_ratio

                # Return True to indicate Deadlight was hit (for teleport tracking)
                return True

    # No hit occurred
    return False


# ============================================================================
# MAIN GAME LOOP
# ============================================================================

def main():
    pygame.init()
    pygame.mixer.init()
    screen = pygame.display.set_mode((WINDOW_SIZE_H, WINDOW_SIZE_V))
    clock = pygame.time.Clock()
    pygame.font.init()
    ui_font = pygame.font.SysFont(None, 22)
    MESSAGE_TIME = 1.0

    # Show start screen first
    if not show_start_screen(screen, clock):
        pygame.quit()
        return

    # Load background music files
    MUSIC_VOLUME = 0.2  # Moderate volume
    chase_music = "music\Dr.Rick Trager-Chase theme.mp3"
    doom_music = "music\Doom Eternal OST - The Only Thing They Fear Is You (Mick Gordon) [Doom Eternal Theme].mp3"

    # Set music volume
    pygame.mixer.music.set_volume(MUSIC_VOLUME)

    # Helper to create/reset all runtime state so we can restart cleanly
    def reset_state():
        grid = generate_map(int(time.time()))
        spawn_x, spawn_y = spawn_on_floor(grid)
        player = Player(spawn_x, spawn_y)
        pet = Pet(player.x + 28, player.y + 8)
        saved_pet = None
        # place Deadlight on a floor tile so it doesn't spawn inside walls
        dlx, dly = spawn_on_floor(grid)
        # avoid placing too close to player
        tries = 0
        while math.hypot(dlx - player.x, dly - player.y) < 200 and tries < 50:
            dlx, dly = spawn_on_floor(grid)
            tries += 1
        deadlight = DeadlightBoss(dlx, dly, base_radiance=200)
        # Initialize min_radiance for Deadlight (same as player logic)
        deadlight.min_radiance = deadlight.base_radiance * 0.25
        break_effects = []
        floor_overlays = []
        wave_effects = []
        special_effects = []
        messages = []
        phase_timer = 0.0  # tracks time in current phase
        current_phase = 'chase'  # 'chase' or 'vulnerable'
        game_frozen = False  # Freeze all actions when player or enemy is defeated
        player_not_found_timer = 0.0  # Timer for when player is not in enemy's light zone during chase phase
        enemy_teleport_cooldown = 0.0  # Cooldown timer for enemy teleport during chase phase
        vulnerable_teleport_timer = 0.0  # Timer for deadlight teleport during vulnerable phase (every 10 seconds)
        flash_effects = []  # Flash effects for enemy teleports [x, y, time]
        split_pets = []  # List of split pets (when Q is pressed during vulnerable phase)
        split_pets_timer = 0.0  # Timer for split pets duration
        split_pets_active = False  # Whether pets are currently split
        split_pets_teleport_index = 0  # Current index for circular queue teleport
        return dict(grid=grid, player=player, pet=pet, saved_pet=saved_pet,
                    deadlight=deadlight, break_effects=break_effects,
                    floor_overlays=floor_overlays, wave_effects=wave_effects,
                    special_effects=special_effects,
                    messages=messages,
                    phase_timer=phase_timer, current_phase=current_phase,
                    game_frozen=game_frozen, player_not_found_timer=player_not_found_timer,
                    enemy_teleport_cooldown=enemy_teleport_cooldown,
                    vulnerable_teleport_timer=vulnerable_teleport_timer,
                    flash_effects=flash_effects,
                    split_pets=split_pets, split_pets_timer=split_pets_timer,
                    split_pets_active=split_pets_active, split_pets_teleport_index=split_pets_teleport_index)

    # initialize
    state = reset_state()
    # Start deadlight chase at beginning
    if state['deadlight'] and state['deadlight'].alive and state['current_phase'] == 'chase':
        state['deadlight'].start_chase(extra_time=CHASE_PHASE_DURATION)
    # Start chase music at game start
    try:
        pygame.mixer.music.load(chase_music)
        pygame.mixer.music.play(-1)  # Loop indefinitely
    except Exception:
        pass  # Silently fail if music file not found
    game_over = False
    game_over_msg = ""
    fatal_error = None

    running = True
    while running:
        dt = clock.tick(60) / 1000.0

        # --- Per-frame event handling, update & draw inside try/except to avoid abrupt crash ---
        try:
            # always process quit events and game-over restart keys
            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    running = False
                # If game over (error or player death), allow quick restart or quit
                if game_over:
                    if e.type == pygame.KEYDOWN:
                        if e.key in (pygame.K_r,):
                            # restart
                            pygame.mixer.music.stop()
                            state = reset_state()
                            game_over = False
                            game_over_msg = ""
                            fatal_error = None
                            state['game_frozen'] = False
                            # Restart chase music
                            try:
                                pygame.mixer.music.load(chase_music)
                                pygame.mixer.music.play(-1)  # Loop indefinitely
                            except Exception:
                                pass  # Silently fail if music file not found
                        if e.key in (pygame.K_ESCAPE, pygame.K_q):
                            running = False
                    continue

                # --- Normal Event Handling ---
                if e.type == pygame.KEYDOWN:
                    if e.key == pygame.K_ESCAPE: running = False
                    if e.key == pygame.K_q:
                        # Q key: Split pet into 5 pets (only during vulnerable phase)
                        if state['current_phase'] == 'vulnerable' and not state['split_pets_active']:
                            if state['pet']:
                                # Save original pet position
                                original_pet = state['pet']
                                state['split_pets'] = []

                                # Create 5 pets at different locations across the map
                                for i in range(NUM_SPLIT_PETS):
                                    # Distribute pets around the map
                                    angle = (2 * math.pi * i) / NUM_SPLIT_PETS
                                    # Place pets in a circle around map center, or near player
                                    center_x = WINDOW_SIZE_H // 2
                                    center_y = WINDOW_SIZE_V // 2
                                    radius = min(WINDOW_SIZE_H, WINDOW_SIZE_V) // 3

                                    pet_x = center_x + math.cos(angle) * radius
                                    pet_y = center_y + math.sin(angle) * radius

                                    # Ensure pet is on a floor tile
                                    pet_tx = int(pet_x) // TILE_SIZE
                                    pet_ty = int(pet_y) // TILE_SIZE

                                    # Find nearest floor tile
                                    found_floor = False
                                    search_r = 5
                                    for dy in range(-search_r, search_r + 1):
                                        for dx in range(-search_r, search_r + 1):
                                            check_tx = pet_tx + dx
                                            check_ty = pet_ty + dy
                                            if (0 <= check_tx < GRID_W and 0 <= check_ty < GRID_H and
                                                    state['grid'][check_ty][check_tx] == 0):
                                                pet_x = check_tx * TILE_SIZE + TILE_SIZE // 2
                                                pet_y = check_ty * TILE_SIZE + TILE_SIZE // 2
                                                found_floor = True
                                                break
                                        if found_floor:
                                            break

                                    if not found_floor:
                                        # Fallback to spawn_on_floor
                                        pet_x, pet_y = spawn_on_floor(state['grid'])

                                    # Create new pet at this location
                                    new_pet = Pet(pet_x, pet_y)
                                    new_pet.state = 'sit'  # Pets don't follow when split
                                    state['split_pets'].append(new_pet)

                                # Hide original pet
                                state['saved_pet'] = original_pet
                                state['pet'] = None
                                state['split_pets_active'] = True
                                state['split_pets_timer'] = PET_SPLIT_DURATION
                                state['split_pets_teleport_index'] = 0
                                state['messages'].append(
                                    [f"Pet split into {NUM_SPLIT_PETS} pets for {int(PET_SPLIT_DURATION)}s!",
                                     MESSAGE_TIME])
                            else:
                                state['messages'].append(["No pet to split!", MESSAGE_TIME])
                        elif state['current_phase'] != 'vulnerable':
                            state['messages'].append(["Pet split only available when chasing Deadlight!", MESSAGE_TIME])
                        elif state['split_pets_active']:
                            state['messages'].append(["Pets already split!", MESSAGE_TIME])
                    if e.key == pygame.K_t:
                        # Check if pets are split (during vulnerable phase) - free teleport
                        if state['split_pets_active'] and len(state['split_pets']) > 0:
                            # Teleport to split pets in circular queue fashion (FREE during split period)
                            target_pet = state['split_pets'][state['split_pets_teleport_index']]
                            state['player'].x, state['player'].y = target_pet.x, target_pet.y
                            # Move to next pet in circular queue
                            state['split_pets_teleport_index'] = (state['split_pets_teleport_index'] + 1) % len(
                                state['split_pets'])
                            state['messages'].append(
                                [f"Teleported to pet {state['split_pets_teleport_index'] + 1}/{len(state['split_pets'])}! (Free)",
                                 MESSAGE_TIME])
                        # Teleport during chase phase (costs teleport_cost - special_charge)
                        elif state['current_phase'] == 'chase' and state[
                            'player'].special_charge >= player_teleport_cost:
                            if state['pet']:
                                dist_to_pet = math.hypot(state['pet'].x - state['player'].x,
                                                         state['pet'].y - state['player'].y)
                                allow_dist = max(PET_BUFF_DISTANCE, state['pet'].radius * 2)

                                if dist_to_pet <= allow_dist:
                                    state['saved_pet'] = state['pet']
                                    state['pet'] = None
                                    state['messages'].append(["Pet sent to pocket-dimension", MESSAGE_TIME])
                                else:
                                    state['player'].x, state['player'].y = state['pet'].x, state['pet'].y
                                    state['messages'].append(["Teleported to pet!", MESSAGE_TIME])
                                # Consume cost
                                state['player'].special_charge = max(0.0, state[
                                    'player'].special_charge - player_teleport_cost)
                            elif state['saved_pet']:
                                state['pet'] = state['saved_pet']
                                state['saved_pet'] = None
                                state['pet'].x = state['player'].x + 28
                                state['pet'].y = state['player'].y + 8
                                state['messages'].append(["Pet returned from pocket-dimension", MESSAGE_TIME])
                                # Consume cost
                                state['player'].special_charge = max(0.0, state[
                                    'player'].special_charge - player_teleport_cost)
                            else:
                                state['pet'] = Pet(state['player'].x + 28, state['player'].y + 8)
                                state['messages'].append(["Pet spawned", MESSAGE_TIME])
                                # Consume cost
                                state['player'].special_charge = max(0.0, state[
                                    'player'].special_charge - player_teleport_cost)
                        elif state['current_phase'] == 'chase':
                            # Not enough special charge during chase phase
                            pct = int((state['player'].special_charge / state['player'].special_charge_max) * 100)
                            state['messages'].append(
                                [f"Not enough special charge! (Need 20, have {pct}%)", MESSAGE_TIME])
                        else:
                            # Teleport not available during vulnerable phase (unless split pets are active)
                            state['messages'].append(
                                ["Teleport only available when enemy is chasing or pets are split!", MESSAGE_TIME])
                    if e.key == pygame.K_f:
                        if state['player'].special_charge >= state['player'].special_charge_max // 2:
                            destroyed, gen_broken, player_broken = perform_special_attack(state['grid'],
                                                                                          state['player'].x,
                                                                                          state['player'].y,
                                                                                          state['break_effects'],
                                                                                          state['floor_overlays'])
                            state['special_effects'].append([state['player'].x, state['player'].y, 0.0])
                            state['player'].special_charge -= 50
                            if destroyed > 0:
                                msg = f"Special obliterated {destroyed} blocks!"
                                if gen_broken > 0 or player_broken > 0:
                                    msg += f" ({gen_broken} gen, {player_broken} player-built)"
                                state['messages'].append([msg, MESSAGE_TIME])
                            else:
                                state['messages'].append([f"Special used - no blocks in radius", MESSAGE_TIME])
                        else:
                            pct = int((state['player'].special_charge / state['player'].special_charge_max) * 100)
                            state['messages'].append([f"Special not ready ({pct}%)", MESSAGE_TIME])
                    if e.key == pygame.K_c:
                        if state['pet']:
                            if hasattr(state['pet'], 'state') and state['pet'].state == 'follow':
                                state['pet'].command('sit')
                                state['messages'].append(["Pet will stay in place", MESSAGE_TIME])
                            elif hasattr(state['pet'], 'state') and state['pet'].state == 'sit':
                                state['pet'].command('follow')
                                state['messages'].append(["Pet resumes following", MESSAGE_TIME])
                    if e.key == pygame.K_h:
                        # Hint only works during vulnerable phase (player chasing enemy)
                        if state['current_phase'] == 'vulnerable':
                            # Hint costs 25 stamina
                            if state['player'].stamina >= 25:
                                # Pet should point to Deadlight
                                if state['pet'] and state['deadlight'] and state['deadlight'].alive:
                                    dx = state['deadlight'].x - state['pet'].x
                                    dy = state['deadlight'].y - state['pet'].y
                                    dist = math.hypot(dx, dy)
                                    ang = math.degrees(math.atan2(dy, dx))
                                    state['pet'].point_at(state['deadlight'].x, state['deadlight'].y, duration=3.0)
                                    # Consume cost: reduce stamina by 25
                                    state['player'].stamina = max(0.0, state['player'].stamina - 25)
                                    state['messages'].append(
                                        [f"Pet points to Deadlight at {int(dist)}px ({int(ang)}deg)", MESSAGE_TIME])
                                else:
                                    state['messages'].append(["No pet or Deadlight to hint!", MESSAGE_TIME])
                            else:
                                state['messages'].append(["Not enough stamina! (Need 25)", MESSAGE_TIME])
                        else:
                            state['messages'].append(
                                ["Hint only available when Deadlight is vulnerable!", MESSAGE_TIME])

            # ========== GAME LOGIC UPDATE ==========
            if not state['game_frozen']:
                # --- Player Movement & Regeneration ---
                keys = pygame.key.get_pressed()
                state['player'].handle_movement(keys, dt, state['grid'])
                pet_dist = math.hypot(state['pet'].x - state['player'].x, state['pet'].y - state['player'].y) if state[
                    'pet'] else 999999
                pet_near = pet_dist <= PET_BUFF_DISTANCE
                state['player'].regen(dt, pet_near, PET_REGEN_MULT)

                # --- Pet Updates ---
                if state['pet']:
                    state['pet'].update(state['player'].x, state['player'].y, state['grid'], dt)
                    state['pet'].update_pointing(dt)

                # Split pets update (they don't follow, just stay in place)
                if state['split_pets_active']:
                    for split_pet in state['split_pets']:
                        split_pet.update_pointing(dt)

                # --- Phase Management ---
                state['phase_timer'] += dt
                if state['current_phase'] == 'chase':
                    if state['phase_timer'] >= CHASE_PHASE_DURATION:
                        # Switch to vulnerable phase
                        state['current_phase'] = 'vulnerable'
                        state['phase_timer'] = 0.0
                        state['messages'].append(["Deadlight is vulnerable! Chase it now!", MESSAGE_TIME])
                        # Stop chase music and play doom music
                        pygame.mixer.music.stop()
                        try:
                            pygame.mixer.music.load(doom_music)
                            pygame.mixer.music.play(-1)  # Loop indefinitely
                        except Exception:
                            pass  # Silently fail if music file not found
                        # Stop deadlight chase
                        if state['deadlight'] and state['deadlight'].alive:
                            state['deadlight']._chase_mode = False
                            state['deadlight']._chase_timer = 0.0
                        # Reset chase phase teleport tracking
                        state['player_not_found_timer'] = 0.0
                        state['enemy_teleport_cooldown'] = 0.0
                        # Reset vulnerable phase teleport timer
                        state['vulnerable_teleport_timer'] = 0.0
                elif state['current_phase'] == 'vulnerable':
                    if state['phase_timer'] >= VULNERABLE_PHASE_DURATION:
                        # Switch back to chase phase
                        state['current_phase'] = 'chase'
                        state['phase_timer'] = 0.0
                        state['messages'].append(["Deadlight is hunting you again!", MESSAGE_TIME])
                        # Stop doom music and play chase music
                        pygame.mixer.music.stop()
                        try:
                            pygame.mixer.music.load(chase_music)
                            pygame.mixer.music.play(-1)  # Loop indefinitely
                        except Exception:
                            pass  # Silently fail if music file not found
                        # Restart deadlight chase
                        if state['deadlight'] and state['deadlight'].alive:
                            state['deadlight'].start_chase(extra_time=CHASE_PHASE_DURATION)
                            # Disable escape mode
                            state['deadlight']._escape_mode = False
                        # Reset chase phase teleport tracking
                        state['player_not_found_timer'] = 0.0
                        state['enemy_teleport_cooldown'] = 0.0
                        # Reset vulnerable phase teleport timer
                        state['vulnerable_teleport_timer'] = 0.0
                        # Clean up split pets if phase changes
                        if state['split_pets_active']:
                            state['split_pets'] = []
                            state['split_pets_active'] = False
                            state['split_pets_timer'] = 0.0
                            if state['saved_pet']:
                                state['pet'] = state['saved_pet']
                                state['saved_pet'] = None
                                state['pet'].x = state['player'].x + 28
                                state['pet'].y = state['player'].y + 8

                # Update split pets timer and cleanup
                if state['split_pets_active']:
                    state['split_pets_timer'] -= dt
                    if state['split_pets_timer'] <= 0:
                        # Time's up - keep only one pet, remove others
                        if len(state['split_pets']) > 0:
                            # Keep the first pet, remove others
                            state['pet'] = state['split_pets'][0]
                            state['pet'].state = 'follow'  # Resume following
                            state['split_pets'] = []
                        state['split_pets_active'] = False
                        state['split_pets_timer'] = 0.0
                        state['split_pets_teleport_index'] = 0
                        state['messages'].append(["Pets merged back into one!", MESSAGE_TIME])

                # --- Deadlight AI & Behavior ---
                if state['deadlight'] and state['deadlight'].alive:
                    # Update deadlight based on current phase
                    if state['current_phase'] == 'chase':
                        # Deadlight chases player - start chase if not already chasing
                        if not state['deadlight'].is_chasing():
                            state['deadlight'].start_chase(extra_time=CHASE_PHASE_DURATION)
                        # Disable escape mode during chase phase
                        state['deadlight']._escape_mode = False
                        state['deadlight'].update(dt, state['player'].x, state['player'].y, state['grid'],
                                                  player_radiance=state['player'].radiance)

                        # Check if player is in enemy's light zone during chase phase
                        player_in_enemy_light = state['deadlight'].player_in_radiance(
                            state['player'].x, state['player'].y, state['grid'])

                        # Update teleport cooldown
                        if state['enemy_teleport_cooldown'] > 0:
                            state['enemy_teleport_cooldown'] -= dt

                        if player_in_enemy_light:
                            # Player found - reset timer
                            state['player_not_found_timer'] = 0.0
                        else:
                            # Player not found - increment timer
                            state['player_not_found_timer'] += dt

                            # Teleport if player stays away from enemy's light for 10 seconds AND cooldown is ready
                            if (state['player_not_found_timer'] >= TELEPORT_NOT_FOUND_TIME and
                                    state['enemy_teleport_cooldown'] <= 0):
                                # Find floor tile NEAR player, just outside light radius (not too close)
                                player_x = state['player'].x
                                player_y = state['player'].y
                                player_radiance = state['player'].radiance

                                # Target distance: just outside light radius, but not too close
                                # Ensure minimum distance from player to avoid spawning too close
                                min_dist = max(player_radiance + TELEPORT_BUFFER_OUTSIDE_LIGHT, TELEPORT_MIN_DISTANCE)
                                max_dist = player_radiance + TELEPORT_MAX_DISTANCE_FROM_LIGHT

                                best_floor = None
                                best_score = float('inf')  # Lower is better (closer to min_dist)
                                search_radius = 25  # Search up to 25 tiles away

                                # Start from player's tile position
                                player_tx = int(player_x) // TILE_SIZE
                                player_ty = int(player_y) // TILE_SIZE

                                for dy_search in range(-search_radius, search_radius + 1):
                                    for dx_search in range(-search_radius, search_radius + 1):
                                        check_tx = player_tx + dx_search
                                        check_ty = player_ty + dy_search

                                        # Check if tile is valid and is a floor tile
                                        if (0 <= check_tx < GRID_W and 0 <= check_ty < GRID_H and
                                                state['grid'][check_ty][check_tx] == 0):
                                            # Calculate tile center coordinates
                                            floor_x = check_tx * TILE_SIZE + TILE_SIZE // 2
                                            floor_y = check_ty * TILE_SIZE + TILE_SIZE // 2

                                            # Calculate distance from player
                                            dist_to_player_tile = math.hypot(floor_x - player_x, floor_y - player_y)

                                            # Only consider tiles in the sweet spot: just outside light, not too close, not too far
                                            if min_dist <= dist_to_player_tile <= max_dist:
                                                # Score: how close to the ideal distance (min_dist)
                                                score = abs(dist_to_player_tile - min_dist)
                                                if score < best_score:
                                                    best_score = score
                                                    best_floor = (floor_x, floor_y)

                                # If no tile in sweet spot, find nearest tile outside light (but still close, not too close)
                                if not best_floor:
                                    best_floor = None
                                    best_dist = float('inf')
                                    for dy_search in range(-search_radius, search_radius + 1):
                                        for dx_search in range(-search_radius, search_radius + 1):
                                            check_tx = player_tx + dx_search
                                            check_ty = player_ty + dy_search

                                            if (0 <= check_tx < GRID_W and 0 <= check_ty < GRID_H and
                                                    state['grid'][check_ty][check_tx] == 0):
                                                floor_x = check_tx * TILE_SIZE + TILE_SIZE // 2
                                                floor_y = check_ty * TILE_SIZE + TILE_SIZE // 2
                                                dist_to_player_tile = math.hypot(floor_x - player_x, floor_y - player_y)

                                                # Accept tiles outside light, not too close, within reasonable distance
                                                if (dist_to_player_tile >= TELEPORT_MIN_DISTANCE and
                                                        dist_to_player_tile > player_radiance and
                                                        dist_to_player_tile < max_dist * 2):
                                                    if dist_to_player_tile < best_dist:
                                                        best_dist = dist_to_player_tile
                                                        best_floor = (floor_x, floor_y)

                                if best_floor:
                                    # Teleport enemy to location near player, just outside light
                                    teleport_x, teleport_y = best_floor
                                    state['deadlight'].x = float(teleport_x)
                                    state['deadlight'].y = float(teleport_y)

                                    # Add flash effect at teleport location
                                    state['flash_effects'].append([teleport_x, teleport_y, 0.0])

                                    # Reset timer and set cooldown
                                    state['player_not_found_timer'] = 0.0
                                    state['enemy_teleport_cooldown'] = TELEPORT_COOLDOWN

                                    # Clear path to force recalculation
                                    state['deadlight']._path = []
                                    state['deadlight']._path_index = 0

                                    state['messages'].append(
                                        ["Deadlight teleported near you!", MESSAGE_TIME])
                                else:
                                    # Fallback: find any floor tile near player OUTSIDE light zone (expand search radius)
                                    best_floor_fallback = None
                                    best_dist_fallback = float('inf')
                                    expanded_search_radius = 40  # Much larger search radius

                                    for dy_search in range(-expanded_search_radius, expanded_search_radius + 1):
                                        for dx_search in range(-expanded_search_radius, expanded_search_radius + 1):
                                            check_tx = player_tx + dx_search
                                            check_ty = player_ty + dy_search

                                            if (0 <= check_tx < GRID_W and 0 <= check_ty < GRID_H and
                                                    state['grid'][check_ty][check_tx] == 0):
                                                floor_x = check_tx * TILE_SIZE + TILE_SIZE // 2
                                                floor_y = check_ty * TILE_SIZE + TILE_SIZE // 2
                                                dist_to_player_tile = math.hypot(floor_x - player_x, floor_y - player_y)

                                                # CRITICAL: Only accept tiles OUTSIDE player's light zone
                                                if dist_to_player_tile > player_radiance and dist_to_player_tile < best_dist_fallback:
                                                    best_dist_fallback = dist_to_player_tile
                                                    best_floor_fallback = (floor_x, floor_y)

                                    if best_floor_fallback:
                                        fallback_x, fallback_y = best_floor_fallback
                                        state['deadlight'].x = float(fallback_x)
                                        state['deadlight'].y = float(fallback_y)
                                        state['flash_effects'].append([fallback_x, fallback_y, 0.0])
                                        state['player_not_found_timer'] = 0.0
                                        state['enemy_teleport_cooldown'] = TELEPORT_COOLDOWN
                                        state['deadlight']._path = []
                                        state['deadlight']._path_index = 0
                                        state['messages'].append(
                                            ["Deadlight teleported near you!", MESSAGE_TIME])
                                    else:
                                        # Last resort: keep searching further until we find a tile outside light zone
                                        # Don't teleport if we can't find a valid location outside light
                                        state['messages'].append(
                                            ["Could not find safe teleport location!", MESSAGE_TIME])
                    elif state['current_phase'] == 'vulnerable':
                        # Deadlight runs away from player (escape mode)
                        if state['deadlight'].is_chasing():
                            # Stop chasing
                            state['deadlight']._chase_mode = False
                            state['deadlight']._chase_timer = 0.0
                        # Enable escape mode
                        state['deadlight']._escape_mode = True
                        state['deadlight'].update(dt, state['player'].x, state['player'].y, state['grid'],
                                                  player_radiance=state['player'].radiance)

                    # Check if Deadlight is under player's light (for speed boost)
                    if state['current_phase'] == 'vulnerable':
                        dx = state['deadlight'].x - state['player'].x
                        dy = state['deadlight'].y - state['player'].y
                        dist = math.hypot(dx, dy)
                        player_radiance = state['player'].radiance

                        under_light = False
                        if dist <= player_radiance:
                            # Check line of sight
                            ang_to_deadlight = math.degrees(math.atan2(dy, dx)) % 360
                            hit_x, hit_y = cast_ray(state['grid'], state['player'].x, state['player'].y,
                                                    ang_to_deadlight, max_distance=player_radiance)
                            hit_dist = math.hypot(hit_x - state['player'].x, hit_y - state['player'].y)
                            if hit_dist + 1e-6 >= dist:
                                under_light = True

                        state['deadlight']._under_player_light = under_light
                    else:
                        state['deadlight']._under_player_light = False

                    # Check light overlap damage (pass grid for raycasting)
                    deadlight_hit = check_light_overlap_damage(state['player'], state['deadlight'], dt,
                                                               state['current_phase'], state['grid'])

                    # Timer-based teleport during vulnerable phase (every 10 seconds, regardless of hits)
                    if state['current_phase'] == 'vulnerable':
                        state['vulnerable_teleport_timer'] += dt

                        # Teleport every 10 seconds (no limit)
                        if state['vulnerable_teleport_timer'] >= VULNERABLE_TELEPORT_INTERVAL:
                            # Teleport Deadlight to random floor location
                            if state['deadlight'] and state['deadlight'].alive:
                                new_x, new_y = spawn_on_floor(state['grid'])
                                state['deadlight'].x = float(new_x)
                                state['deadlight'].y = float(new_y)

                                # Add flash effect at teleport location
                                state['flash_effects'].append([new_x, new_y, 0.0])

                                # Reset timer for next teleport
                                state['vulnerable_teleport_timer'] = 0.0

                                # Clear path to force recalculation
                                state['deadlight']._path = []
                                state['deadlight']._path_index = 0

                                state['messages'].append(["Deadlight teleported away!", MESSAGE_TIME])

            # ========== GAME STATE CHECKS ==========
            # Check defeat conditions (check even when frozen to set game_over)
            if state['deadlight'] and state['deadlight'].alive:
                if state['deadlight'].health <= 0 or state['deadlight'].radiance <= 0:
                    if not state['game_frozen']:
                        state['game_frozen'] = True
                        pygame.mixer.music.stop()  # Stop music when game ends
                    game_over = True
                    game_over_msg = "You defeated the Deadlight! Press R to restart or Q to quit."

            # Check if player is defeated (radiance/health depleted)
            if state['player'].radiance <= 0 or state['player'].health <= 0:
                if not state['game_frozen']:
                    state['game_frozen'] = True
                    pygame.mixer.music.stop()  # Stop music when game ends
                game_over = True
                game_over_msg = "Your light has been extinguished... Press R to restart or Q to quit."

            # ========== RENDERING ==========
            screen.fill((0, 0, 0))
            start_tx = 0
            end_tx = GRID_W
            start_ty = 0
            end_ty = GRID_H
            for ty in range(start_ty, end_ty):
                for tx in range(start_tx, end_tx):
                    if 0 <= tx < GRID_W and 0 <= ty < GRID_H:
                        color = COLOR_WALL if state['grid'][ty][tx] else COLOR_FLOOR
                        sx, sy = tx * TILE_SIZE, ty * TILE_SIZE
                        pygame.draw.rect(screen, color, (sx, sy, TILE_SIZE, TILE_SIZE))

            # Player light - sync radiance for drawing
            player_health_ratio = max(0.0, state['player'].health / max(1.0, state['player'].health_max))
            state['player'].radiance = state['player'].min_radiance + (
                    state['player'].base_radiance - state['player'].min_radiance) * player_health_ratio
            points = []
            player_radiance = max(16, int(state['player'].radiance))
            for ang in range(0, 360, RAY_ANGLE_STEP):
                wx, wy = cast_ray(state['grid'], state['player'].x, state['player'].y, ang,
                                  max_distance=player_radiance)
                points.append((int(wx), int(wy)))
            light_mask = pygame.Surface((WINDOW_SIZE_H, WINDOW_SIZE_V), pygame.SRCALPHA)
            light_mask.fill((0, 0, 0, 230))
            pygame.draw.polygon(light_mask, (0, 0, 0, 0), points)
            pygame.draw.circle(light_mask, (0, 0, 0, 0),
                               (int(state['player'].x), int(state['player'].y)), 10)
            screen.blit(light_mask, (0, 0))

            # break effects
            new_effects = []
            for bx, by, t in state['break_effects']:
                t += dt
                sx, sy = bx * TILE_SIZE, by * TILE_SIZE
                alpha = int(255 * max(0, 1.0 - t / 0.6))
                surf = pygame.Surface((TILE_SIZE, TILE_SIZE), pygame.SRCALPHA)
                surf.fill((255, 220, 80, alpha))
                screen.blit(surf, (sx, sy))
                if t < 0.6: new_effects.append([bx, by, t])
            state['break_effects'] = new_effects

            # floor overlays
            new_overlays = []
            for fx, fy, t in state['floor_overlays']:
                t += dt
                sx, sy = fx * TILE_SIZE, fy * TILE_SIZE
                pygame.draw.rect(screen, COLOR_FLOOR, (sx, sy, TILE_SIZE, TILE_SIZE))
                if t < 0.6: new_overlays.append([fx, fy, t])
            state['floor_overlays'] = new_overlays

            # wave effects
            new_waves = []
            for ox, oy, ang, t in state['wave_effects']:
                t += dt
                radius = int(120 * (0.6 + 0.4 * (t / 0.25)))
                cx, cy = int(ox), int(oy)
                a_rad = math.radians(ang)
                ha = math.radians(50 / 2)
                p1 = (cx, cy)
                p2 = (cx + math.cos(a_rad - ha) * radius, cy + math.sin(a_rad - ha) * radius)
                p3 = (cx + math.cos(a_rad + ha) * radius, cy + math.sin(a_rad + ha) * radius)
                surf = pygame.Surface((WINDOW_SIZE_H, WINDOW_SIZE_V), pygame.SRCALPHA)
                alpha = int(120 * max(0.0, 1.0 - t / 0.35))
                pygame.draw.polygon(surf, (80, 160, 255, alpha), [p1, p2, p3])
                screen.blit(surf, (0, 0))
                if t < 0.35: new_waves.append([ox, oy, ang, t])
            state['wave_effects'] = new_waves

            # special effects
            new_specials = []
            for ox, oy, t in state['special_effects']:
                t += dt
                cx, cy = int(ox), int(oy)
                frac = min(1.0, t / 0.8)
                radius = int(SPECIAL_RADIUS * (0.2 + 0.8 * frac))
                alpha = int(180 * max(0.0, 1.0 - frac))
                surf = pygame.Surface((WINDOW_SIZE_H, WINDOW_SIZE_V), pygame.SRCALPHA)
                pygame.draw.circle(surf, (255, 120, 40, alpha), (int(cx), int(cy)), radius)
                screen.blit(surf, (0, 0))
                if t < 0.8: new_specials.append([ox, oy, t])

            state['special_effects'] = new_specials

            # flash effects (enemy teleport)
            new_flashes = []
            for fx, fy, t in state['flash_effects']:
                t += dt
                cx, cy = int(fx), int(fy)
                # Flash effect: bright white circle that fades quickly
                frac = min(1.0, t / 0.5)  # Flash lasts 0.5 seconds
                radius = int(60 * (1.0 - frac * 0.5))  # Starts at 60px, shrinks to 30px
                alpha = int(255 * max(0.0, 1.0 - frac))  # Fades from 255 to 0
                surf = pygame.Surface((WINDOW_SIZE_H, WINDOW_SIZE_V), pygame.SRCALPHA)
                # Bright white flash with slight blue tint
                pygame.draw.circle(surf, (255, 255, 255, alpha), (cx, cy), radius)
                pygame.draw.circle(surf, (150, 200, 255, alpha // 2), (cx, cy), radius + 10)
                screen.blit(surf, (0, 0))
                if t < 0.5: new_flashes.append([fx, fy, t])
            state['flash_effects'] = new_flashes

            # pet (normal pet)
            if state['pet']:
                psx, psy = int(state['pet'].x), int(state['pet'].y)
                pygame.draw.circle(screen, state['pet'].color, (psx, psy), state['pet'].radius)
                pygame.draw.circle(screen, (200, 160, 120), (psx - 1, psy - 1),
                                   max(1, state['pet'].radius // 3))
                # draw pointing indicator if set
                if getattr(state['pet'], 'point_target', None):
                    tx, ty = state['pet'].point_target
                    t_sx, t_sy = int(tx), int(ty)
                    # draw a line and arrow from pet to target
                    pygame.draw.line(screen, (120, 200, 255), (psx, psy), (t_sx, t_sy), 2)
                    # small arrowhead
                    ax = t_sx
                    ay = t_sy
                    pygame.draw.circle(screen, (120, 200, 255), (ax, ay), 5)

            # split pets (during vulnerable phase)
            if state['split_pets_active'] and len(state['split_pets']) > 0:
                for i, split_pet in enumerate(state['split_pets']):
                    psx, psy = int(split_pet.x), int(split_pet.y)
                    # Draw pet with slightly different color to distinguish
                    pygame.draw.circle(screen, split_pet.color, (psx, psy), split_pet.radius)
                    pygame.draw.circle(screen, (200, 160, 120), (psx - 1, psy - 1),
                                       max(1, split_pet.radius // 3))
                    # Draw number indicator
                    if i == state['split_pets_teleport_index']:
                        # Highlight current teleport target
                        pygame.draw.circle(screen, (255, 255, 0), (psx, psy), split_pet.radius + 3, 2)

            # player
            state['player'].draw(screen)

            # Phase timer HUD
            phase_time_left = CHASE_PHASE_DURATION - state['phase_timer'] if state[
                                                                                 'current_phase'] == 'chase' else VULNERABLE_PHASE_DURATION - \
                                                                                                                  state[
                                                                                                                      'phase_timer']
            phase_name = "Deadlight Chasing" if state['current_phase'] == 'chase' else "Deadlight Vulnerable"
            phase_color = (255, 100, 100) if state['current_phase'] == 'chase' else (100, 255, 100)
            phase_surf = ui_font.render(f"{phase_name}: {int(phase_time_left)}s", True, phase_color)
            screen.blit(phase_surf, (WINDOW_SIZE_H - phase_surf.get_width() - 12, 8))

            # draw deadlight (always draw, but as shadow when outside player's light)
            if state['deadlight'] and state['deadlight'].alive:
                # Check if Deadlight is within player's light radius
                dx = state['deadlight'].x - state['player'].x
                dy = state['deadlight'].y - state['player'].y
                dist = math.hypot(dx, dy)
                player_radiance = state['player'].radiance

                deadlight_visible = False
                if dist <= player_radiance:
                    # Check line of sight using raycasting
                    ang_to_deadlight = math.degrees(math.atan2(dy, dx)) % 360
                    hit_x, hit_y = cast_ray(state['grid'], state['player'].x, state['player'].y,
                                            ang_to_deadlight, max_distance=player_radiance)
                    hit_dist = math.hypot(hit_x - state['player'].x, hit_y - state['player'].y)
                    # If ray reached at least to Deadlight's distance, it's visible
                    if hit_dist + 1e-6 >= dist:
                        deadlight_visible = True

                # Always draw Deadlight - as shadow if not visible, normal if visible
                show_light = True  # Always show blue light when visible in player's light
                # Use different flicker rates based on phase
                flicker_cycle = FLICKER_CYCLE_CHASE if state['current_phase'] == 'chase' else FLICKER_CYCLE_VULNERABLE
                state['deadlight'].draw(screen, state['grid'], show_light=show_light,
                                        visible_in_player_light=deadlight_visible,
                                        flicker_cycle=flicker_cycle)

            # messages
            new_msgs = []
            y_off = 8
            for txt, tleft in state['messages']:
                tleft -= dt
                surf = ui_font.render(txt, True, (255, 255, 255))
                screen.blit(surf, (8, y_off))
                y_off += surf.get_height() + 4
                if tleft > 0: new_msgs.append([txt, tleft])
            state['messages'] = new_msgs

            # If game over due to crash or death, overlay message
            if game_over:
                overlay = pygame.Surface((WINDOW_SIZE_H, WINDOW_SIZE_V), pygame.SRCALPHA)
                overlay.fill((0, 0, 0, 160))
                screen.blit(overlay, (0, 0))
                msg = game_over_msg if game_over_msg else ("A fatal error occurred. Press R to restart or Q to quit.")
                lines = msg.split('\n')
                y = WINDOW_SIZE_V // 2 - (len(lines) * 20) // 2
                for line in lines:
                    surf = ui_font.render(line, True, (255, 220, 100))
                    screen.blit(surf, (WINDOW_SIZE_H // 2 - surf.get_width() // 2, y))
                    y += 28

            pygame.display.flip()
        except BaseException as _e:
            # Catch everything (including SystemExit / KeyboardInterrupt) to avoid abrupt termination.
            try:
                fatal_error = traceback.format_exc()
            except Exception:
                fatal_error = str(_e)
            ts = datetime.now().isoformat()
            try:
                with open('crash_log.txt', 'a', encoding='utf-8') as f:
                    f.write('\n==== CRASH at ' + ts + ' ====\n')
                    f.write(fatal_error)
            except Exception:
                pass
            # Put game into an overlay state instead of exiting
            game_over = True
            game_over_msg = "A runtime error occurred. Crash log written to crash_log.txt. Press R to restart or Q to quit."


pygame.quit()

if __name__ == '__main__':
    try:
        main()
    except BaseException as _e:
        # top-level crash protection: catch everything (including SystemExit) and log
        import traceback as _tb, datetime as _dt

        ts = _dt.datetime.now().isoformat()
        try:
            with open('crash_log.txt', 'a', encoding='utf-8') as f:
                f.write('\n==== TOP-LEVEL CRASH at ' + ts + ' ====\n')
                f.write(_tb.format_exc())
        except Exception:
            pass
        print('A fatal error occurred during startup. See crash_log.txt for details.')
