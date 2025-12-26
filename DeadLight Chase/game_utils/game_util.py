import math
import random
from .procedural_gen import Perlin2D
import pygame

WINDOW_SIZE_H = 1600
WINDOW_SIZE_V = 1000
TILE_SIZE = 8
MAP_SIZE = 3000
GRID_W = MAP_SIZE // TILE_SIZE
GRID_H = MAP_SIZE // TILE_SIZE
LIGHT_RADIUS = 300
RAY_STEP = 5


# ---------------- Collision ----------------
def is_wall(grid, px, py):
    tx = int(px) // TILE_SIZE
    ty = int(py) // TILE_SIZE
    if tx < 0 or ty < 0 or tx >= GRID_W or ty >= GRID_H:
        return True
    # Treat 1 = generated wall, 2 = player-built wall, 3 = boundary wall as blocking
    return grid[ty][tx] in (1, 2, 3)


# ---------------- Raycast ----------------
def cast_ray(grid, ox, oy, angle, max_distance=None):
    # Updated: allow callers to specify max_distance (useful for deadlight/enemy rays).
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
        if x < 0 or y < 0 or x >= MAP_SIZE or y >= MAP_SIZE:
            return x, y
        if is_wall(grid, x, y):
            # step back a bit so the hit point is slightly before the wall
            return x - dx * 3, y - dy * 3
    return ox + dx * max_distance, oy + dy * max_distance


# ---------------- Map ----------------
def generate_map(seed):
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



# ---------------- Spawn ----------------
def spawn_on_floor(grid):
    # try random sampling first, then fall back to a deterministic scan to guarantee a floor tile
    max_attempts = 512
    for _ in range(max_attempts):
        tx = random.randint(0, GRID_W - 1)
        ty = random.randint(0, GRID_H - 1)
        if 0 <= tx < GRID_W and 0 <= ty < GRID_H and grid[ty][tx] == 0:
            px = tx * TILE_SIZE + TILE_SIZE // 2
            py = ty * TILE_SIZE + TILE_SIZE // 2
            return px, py

    # fallback deterministic scan (left-to-right, top-to-bottom)
    for ty in range(GRID_H):
        for tx in range(GRID_W):
            if grid[ty][tx] == 0:
                px = tx * TILE_SIZE + TILE_SIZE // 2
                py = ty * TILE_SIZE + TILE_SIZE // 2
                return px, py

    # If map has no floors (degenerate), return center of map clamped
    return MAP_SIZE // 2, MAP_SIZE // 2


def show_start_screen(screen, clock):
    """Display start screen and wait for start button click."""
    pygame.font.init()
    ui_font = pygame.font.SysFont(None, 24)
    title_font = pygame.font.SysFont(None, 72)
    large_font = pygame.font.SysFont(None, 32)

    waiting = True
    button_rect = None

    while waiting:
        dt = clock.tick(60) / 1000.0

        # Draw screen and get button rect
        button_rect = draw_start_screen(screen, ui_font, title_font, large_font)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            if event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:  # Left click
                    if button_rect and button_rect.collidepoint(event.pos):
                        waiting = False
                        return True
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return False
                if event.key == pygame.K_RETURN or event.key == pygame.K_SPACE:
                    waiting = False
                    return True

        pygame.display.flip()

    return True


def draw_start_screen(screen, ui_font, title_font, large_font):
    """Draw the start screen with title, lore, instructions, and start button."""
    screen.fill((10, 10, 20))

    # Title
    title_surf = title_font.render("DeadLight Pursuit", True, (255, 200, 80))
    title_rect = title_surf.get_rect(center=(WINDOW_SIZE_H // 2, 80))
    screen.blit(title_surf, title_rect)

    # Lore section
    lore_y = 150
    lore_title = large_font.render("The Lore", True, (200, 200, 255))
    screen.blit(lore_title, (WINDOW_SIZE_H // 2 - lore_title.get_width() // 2, lore_y))
    lore_y += 40

    # Player lore
    player_lore = [
        "You are a Lightbearer, one of the last guardians of the fading realm.",
        "Your inner radiance is your life force - as it dims, so does your power.",
        "With your loyal companion by your side, you must survive the eternal hunt."
    ]
    for line in player_lore:
        text_surf = ui_font.render(line, True, (255, 240, 200))
        screen.blit(text_surf, (WINDOW_SIZE_H // 2 - text_surf.get_width() // 2, lore_y))
        lore_y += 30

    lore_y += 20

    # Deadlight lore
    deadlight_lore = [
        "The Deadlight is an ancient entity of consuming darkness,",
        "a predator that feeds on light itself. It hunts in cycles:",
        "when it chases, its blue radiance drains your very essence.",
        "But in its vulnerable moments, you can turn the tables..."
    ]
    for line in deadlight_lore:
        text_surf = ui_font.render(line, True, (150, 200, 255))
        screen.blit(text_surf, (WINDOW_SIZE_H // 2 - text_surf.get_width() // 2, lore_y))
        lore_y += 30

    # Instructions section
    instructions_y = WINDOW_SIZE_V - 350
    inst_title = large_font.render("Controls", True, (255, 255, 255))
    screen.blit(inst_title, (WINDOW_SIZE_H // 2 - inst_title.get_width() // 2, instructions_y))
    instructions_y += 40

    instructions = [
        "WASD / Arrow Keys: Move",
        "Shift + Move: Sprint",
        "T: Teleport (near pet sends to pocket, far teleports to pet)",
        "Q: Split pet into 5 (during chase phase, 30s duration)",
        "H: Pet hints at Deadlight location (during vulnerable phase)",
        "F: Destroy walls (special attack)",
        "C: Command pet to stay/follow"
    ]

    for i, line in enumerate(instructions):
        color = (200, 255, 200) if i < 2 else (220, 220, 220)
        text_surf = ui_font.render(line, True, color)
        screen.blit(text_surf, (WINDOW_SIZE_H // 2 - text_surf.get_width() // 2, instructions_y))
        instructions_y += 28

    # Start button
    button_width = 200
    button_height = 60
    button_x = WINDOW_SIZE_H // 2 - button_width // 2
    button_y = WINDOW_SIZE_V - 80
    button_rect = pygame.Rect(button_x, button_y, button_width, button_height)

    # Button glow effect
    mouse_pos = pygame.mouse.get_pos()
    hover = button_rect.collidepoint(mouse_pos)

    if hover:
        pygame.draw.rect(screen, (100, 150, 255), button_rect, border_radius=10)
        pygame.draw.rect(screen, (150, 200, 255), button_rect, width=3, border_radius=10)
    else:
        pygame.draw.rect(screen, (50, 100, 200), button_rect, border_radius=10)
        pygame.draw.rect(screen, (100, 150, 255), button_rect, width=2, border_radius=10)

    start_text = large_font.render("START", True, (255, 255, 255))
    start_text_rect = start_text.get_rect(center=button_rect.center)
    screen.blit(start_text, start_text_rect)

    return button_rect
