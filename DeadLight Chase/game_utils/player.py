import pygame
import math
import time
from .game_util import is_wall, LIGHT_RADIUS


PLAYER_COLOR = (255, 200, 80)

# ---------------- Player Class ----------------
class Player:
    def __init__(self, x, y):
        # position
        self.x = x
        self.y = y

        # movement
        self.speed = 150
        self.dodge_speed = 400
        self.dodge_duration = 0.12
        self.dodge_cooldown = 0.25
        self.is_dodging = False
        self.dodge_timer = 0
        self.last_dodge_time = -1
        self.dodge_vx = 0
        self.dodge_vy = 0

        # resources
        self.stamina = 100
        self.stamina_max = 100
        self.stamina_regen_rate = self.stamina_max / 60
        self.break_cost = 5

        # special attack
        self.special_charge = 0.0
        self.special_charge_max = 100.0
        self.special_regen = 5.0

        # health (radiance is now health-based)
        self.health = 100
        self.health_max = 100
        self.radiance_regen_rate = self.health_max / 60  # health regen per second

        # mutable light radiance (now based on health)
        self.base_radiance = LIGHT_RADIUS
        self.radiance = self.base_radiance  # starts at full health
        self.min_radiance = self.base_radiance * 0.25


    def handle_movement(self, keys, dt, grid):
        """Handle per-frame movement and dodging.

        keys: pygame.key.get_pressed() result
        dt: delta time in seconds
        grid: map grid for wall checks
        """
        vx = 0
        vy = 0
        if keys[pygame.K_w] or keys[pygame.K_UP]: vy -= 1
        if keys[pygame.K_s] or keys[pygame.K_DOWN]: vy += 1
        if keys[pygame.K_a] or keys[pygame.K_LEFT]: vx -= 1
        if keys[pygame.K_d] or keys[pygame.K_RIGHT]: vx += 1

        if vx or vy:
            l = math.hypot(vx, vy)
            if l != 0:
                vx /= l
                vy /= l

        # Dodge (shift)
        if (keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]) and (vx or vy):
            if self.stamina >= 5 and not self.is_dodging and (time.time() - self.last_dodge_time > self.dodge_cooldown):
                self.start_dodge(vx, vy)

        if self.is_dodging:
            self.update_dodge(dt, grid)
            return

        # Normal movement
        if vx or vy:
            nx = self.x + vx * self.speed * dt
            ny = self.y + vy * self.speed * dt
            if not is_wall(grid, nx, ny):
                self.x, self.y = nx, ny

    def start_dodge(self, vx, vy):
        self.is_dodging = True
        self.dodge_timer = self.dodge_duration
        self.last_dodge_time = time.time()
        self.stamina -= 5
        self.dodge_vx = vx
        self.dodge_vy = vy

    def update_dodge(self, dt, grid):
        nx = self.x + self.dodge_vx * self.dodge_speed * dt
        ny = self.y + self.dodge_vy * self.dodge_speed * dt
        if not is_wall(grid, nx, ny):
            self.x, self.y = nx, ny
        self.dodge_timer -= dt
        if self.dodge_timer <= 0:
            self.is_dodging = False

    # Regen
    def regen(self, dt, pet_near=False, pet_mult=1.0):
        self.stamina = min(self.stamina_max, self.stamina + self.stamina_regen_rate * dt)
        self.special_charge = min(self.special_charge_max, self.special_charge + self.special_regen * dt)
        if pet_near:
            bonus = pet_mult - 1.0
            self.stamina = min(self.stamina_max, self.stamina + self.stamina_regen_rate * bonus * dt)
            self.special_charge = min(self.special_charge_max, self.special_charge + self.special_regen * bonus * dt)
            self.recover_radiance(dt * pet_mult)
        else:
            self.recover_radiance(dt)

    def drain_radiance(self, amount):
        """Drain health/radiance (damage). Radiance is now health-based."""
        if amount <= 0:
            return
        # Damage health, which affects radiance
        self.health = max(0.0, self.health - amount)
        # Update radiance based on health
        health_ratio = max(0.0, self.health / max(1.0, self.health_max))
        self.radiance = self.min_radiance + (self.base_radiance - self.min_radiance) * health_ratio

    def recover_radiance(self, dt):
        """Recover health/radiance. Radiance is now health-based.
        Note: Health regeneration is disabled - health only decreases, never increases."""
        # Health regeneration disabled - health only decreases from damage
        # Update radiance based on current health (no regen)
        health_ratio = max(0.0, self.health / max(1.0, self.health_max))
        self.radiance = self.min_radiance + (self.base_radiance - self.min_radiance) * health_ratio

    # Draw
    def draw(self, screen):
        # Camera is always at (0, 0), so world coordinates = screen coordinates
        px = int(self.x)
        py = int(self.y)

        pygame.draw.circle(screen, PLAYER_COLOR, (px, py), 6)
        if self.is_dodging:
            pygame.draw.circle(screen, (200,200,255), (px, py), 12, 2)

        arc_radius = 20
        thickness = 1

        pygame.draw.arc(
            screen, (0,255,0),
            (px-arc_radius-6, py-arc_radius-6, (arc_radius+6)*2, (arc_radius+6)*2),
            -math.pi/2, -math.pi/2 + 2*math.pi*(self.stamina/self.stamina_max),
            thickness
        )

        frac = self.special_charge / max(1.0, self.special_charge_max)
        pygame.draw.arc(
            screen, (0,0,255),
            (px-arc_radius-12, py-arc_radius-12, (arc_radius+12)*2, (arc_radius+12)*2),
            -math.pi/2, -math.pi/2 + 2*math.pi*frac,
            thickness
        )
