import heapq
from .game_util import TILE_SIZE

# Simple A* on tile grid. grid[y][x] == 0 is walkable, non-zero is wall.
# Returns list of world coordinates (tile centers) from start to goal, or [] if none found.

def neighbors(x, y, grid_w, grid_h):
    for dx, dy in ((1,0),(-1,0),(0,1),(0,-1)):
        nx, ny = x+dx, y+dy
        if 0 <= nx < grid_w and 0 <= ny < grid_h:
            yield nx, ny


def heuristic(ax, ay, bx, by):
    return abs(ax-bx) + abs(ay-by)


def find_path(grid, start_world, goal_world, max_nodes=10000):
    # Get grid dimensions from actual grid
    grid_h = len(grid)
    grid_w = len(grid[0]) if grid_h > 0 else 0
    if grid_w == 0 or grid_h == 0:
        return []
    
    # convert to tile coords
    sx = int(start_world[0]) // TILE_SIZE
    sy = int(start_world[1]) // TILE_SIZE
    gx = int(goal_world[0]) // TILE_SIZE
    gy = int(goal_world[1]) // TILE_SIZE

    # Quick sanity
    if not (0 <= sx < grid_w and 0 <= sy < grid_h and 0 <= gx < grid_w and 0 <= gy < grid_h):
        return []
    # treat any non-zero tile as blocked (1 generated wall, 2 player-built)
    if grid[sy][sx] != 0 or grid[gy][gx] != 0:
        return []

    open_heap = []
    heapq.heappush(open_heap, (0 + heuristic(sx, sy, gx, gy), 0, (sx, sy)))
    came_from = { (sx, sy): None }
    cost_so_far = { (sx, sy): 0 }
    nodes = 0

    while open_heap:
        _, g, current = heapq.heappop(open_heap)
        nodes += 1
        if nodes > max_nodes:
            break
        if current == (gx, gy):
            # reconstruct path
            path = []
            cur = current
            while cur is not None:
                cx, cy = cur
                wx = cx * TILE_SIZE + TILE_SIZE//2
                wy = cy * TILE_SIZE + TILE_SIZE//2
                path.append((wx, wy))
                cur = came_from[cur]
            path.reverse()
            return path

        cx, cy = current
        for nx, ny in neighbors(cx, cy, grid_w, grid_h):
            # skip any non-walkable tile (non-zero means wall or player-built)
            if grid[ny][nx] != 0:
                continue
            new_cost = cost_so_far[current] + 1
            if (nx, ny) not in cost_so_far or new_cost < cost_so_far[(nx, ny)]:
                cost_so_far[(nx, ny)] = new_cost
                priority = new_cost + heuristic(nx, ny, gx, gy)
                heapq.heappush(open_heap, (priority, new_cost, (nx, ny)))
                came_from[(nx, ny)] = current

    return []
