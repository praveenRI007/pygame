import math
from .game_util import is_wall

# ---------------- Pet class ----------------
class Pet:
    """Simple pet that follows the player. Brown dot.
    Designed to be extended with more behaviors (sit, fetch, etc.).
    """
    def __init__(self, x, y, color=(150, 90, 40), radius=6, speed=140):
        self.x = float(x)
        self.y = float(y)
        self.color = color
        self.radius = radius
        self.speed = speed
        self.state = 'follow'  # placeholder for future states
        self.stay_pos = (self.x, self.y)
        # pointing state
        self.point_target = None
        self.point_timer = 0.0

    def update(self, owner_x, owner_y, grid, dt):
        """Move towards the owner (player). Simple collision avoidance using is_wall.
        - owner_x/owner_y: world coords of player
        - grid: map grid for wall checks
        - dt: seconds since last frame
        """

        if self.state == 'sit':
            # stay at the stay_pos
            self.x, self.y = self.stay_pos
            return

        # if very close, do nothing
        dx = owner_x - self.x
        dy = owner_y - self.y
        dist = math.hypot(dx, dy)
        if dist <= 18:  # stop when near the player (pixels)
            return
        # normalized direction
        vx = dx / dist
        vy = dy / dist
        # propose movement
        move_dist = self.speed * dt
        nx = self.x + vx * move_dist
        ny = self.y + vy * move_dist
        # collision checks: try full move, then axis-aligned fallbacks
        if not is_wall(grid, nx, ny):
            self.x, self.y = nx, ny
        else:
            # try x-only
            if not is_wall(grid, nx, self.y):
                self.x = nx
            # try y-only
            elif not is_wall(grid, self.x, ny):
                self.y = ny
            # else can't move this frame

    # Future behavior hooks
    def sit(self):
        self.state = 'sit'
        self.stay_pos = (self.x, self.y)

    def follow(self):
        self.state = 'follow'

    def command(self, cmd):
        """Placeholder to receive commands (e.g., 'sit', 'stay', 'fetch')."""
        if cmd == 'sit':
            self.sit()
        elif cmd == 'follow':
            self.follow()
        elif cmd == 'point':
            # cmd can be ('point', x, y)
            pass
        else:
            pass

    # ---------------- Helper utilities for hints/alerts ----------------
    def get_nearest_deadlight_direction(self, deadlight):
        """Return (angle_degrees, distance) to deadlight, or (None, None) if none."""
        if not deadlight or not hasattr(deadlight, 'alive') or not deadlight.alive:
            return None, None
        dx = deadlight.x - self.x
        dy = deadlight.y - self.y
        d = math.hypot(dx, dy)
        ang = math.degrees(math.atan2(dy, dx))
        return ang, d

    def point_at(self, tx, ty, duration=2.0):
        """Tell the pet to point toward (tx,ty) for a short duration (used when user presses H)."""
        self.point_target = (tx, ty)
        self.point_timer = float(duration)

    def update_pointing(self, dt):
        if self.point_timer > 0 and self.point_target:
            self.point_timer -= dt
            if self.point_timer <= 0:
                self.point_target = None
                self.point_timer = 0.0
