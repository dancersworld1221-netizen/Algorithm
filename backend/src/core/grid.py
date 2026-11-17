"""Grid-based search environment.

Implements 4-way and 8-way movement, normal/difficult/high-cost terrain, and
an explicit corner-cutting policy. Provides successor generation, heuristics
(Manhattan for 4-way, Octile for 8-way), and validation helpers used by the
algorithms and the API layer.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from .problem import (
    Action,
    Cell,
    Heuristic,
    MovementMode,
    SearchProblem,
    TerrainType,
    TERRAIN_COST,
)


@dataclass
class GridConfig:
    """Configuration for a grid search environment."""
    rows: int
    cols: int
    movement: MovementMode = MovementMode.FOUR_WAY
    corner_cutting: bool = False
    terrain: dict = field(default_factory=dict)  # (row, col) -> TerrainType
    obstacles: list = field(default_factory=list)  # list[Cell]

    def __post_init__(self) -> None:
        if self.rows <= 0 or self.cols <= 0:
            raise ValueError("grid dimensions must be positive")
        if self.rows > 200 or self.cols > 200:
            raise ValueError("grid dimensions too large (max 200x200)")


class GridEnvironment:
    """A rectangular grid search environment with terrain and obstacles."""

    def __init__(self, config: GridConfig) -> None:
        self.config = config
        # Obstacle cells, keyed by Cell.
        self.obstacles: set[Cell] = set()

    def in_bounds(self, cell: Cell) -> bool:
        return 0 <= cell.row < self.config.rows and 0 <= cell.col < self.config.cols

    def is_obstacle(self, cell: Cell) -> bool:
        return cell in self.obstacles

    def terrain_cost(self, cell: Cell) -> float:
        """Cost to enter a cell. Default normal terrain."""
        t = self.config.terrain.get((cell.row, cell.col), TerrainType.NORMAL)
        return TERRAIN_COST[t]

    def add_obstacle(self, cell: Cell) -> None:
        if self.in_bounds(cell):
            self.obstacles.add(cell)

    def remove_obstacle(self, cell: Cell) -> None:
        self.obstacles.discard(cell)

    def clear_obstacles(self) -> None:
        self.obstacles.clear()

    def _diagonal_corner_blocked(
        self, from_cell: Cell, to_cell: Cell
    ) -> bool:
        """True if a diagonal move cuts through a blocked corner.

        For a diagonal move from (r,c) to (r+dr, c+dc), the two adjacent
        orthogonal cells must both be free (or in-bounds and non-obstacle)
        unless corner cutting is enabled.
        """
        if self.config.corner_cutting:
            return False
        dr = to_cell.row - from_cell.row
        dc = to_cell.col - from_cell.col
        if abs(dr) != 1 or abs(dc) != 1:
            return False
        side1 = Cell(from_cell.row + dr, from_cell.col)
        side2 = Cell(from_cell.row, from_cell.col + dc)
        # A side cell is blocking if it's out of bounds or an obstacle.
        blocked1 = (not self.in_bounds(side1)) or self.is_obstacle(side1)
        blocked2 = (not self.in_bounds(side2)) or self.is_obstacle(side2)
        return blocked1 or blocked2

    def successors(self, cell: Cell) -> List[Tuple[Cell, Action]]:
        """Generate legal successor cells with their actions and costs.

        Movement cost = action base cost * terrain cost of the destination cell.
        This respects weighted terrain for all cost-sensitive algorithms.
        """
        if not self.in_bounds(cell) or self.is_obstacle(cell):
            return []

        result: List[Tuple[Cell, Action]] = []
        if self.config.movement == MovementMode.FOUR_WAY:
            directions = [
                (-1, 0, "up", 1.0),
                (1, 0, "down", 1.0),
                (0, -1, "left", 1.0),
                (0, 1, "right", 1.0),
            ]
        else:
            # Eight-way: orthogonal cost 1, diagonal cost sqrt(2) ~ 1.414.
            diag = math.sqrt(2)
            directions = [
                (-1, 0, "up", 1.0),
                (1, 0, "down", 1.0),
                (0, -1, "left", 1.0),
                (0, 1, "right", 1.0),
                (-1, -1, "up_left", diag),
                (-1, 1, "up_right", diag),
                (1, -1, "down_left", diag),
                (1, 1, "down_right", diag),
            ]

        for dr, dc, label, base_cost in directions:
            nxt = Cell(cell.row + dr, cell.col + dc)
            if not self.in_bounds(nxt):
                continue
            if self.is_obstacle(nxt):
                continue
            if abs(dr) == 1 and abs(dc) == 1 and self._diagonal_corner_blocked(cell, nxt):
                continue
            cost = base_cost * self.terrain_cost(nxt)
            result.append((nxt, Action(dr, dc, label, cost)))

        # Deterministic successor ordering: row-major by destination cell.
        result.sort(key=lambda item: (item[0].row, item[0].col))
        return result

    def manhattan_heuristic(self, cell: Cell, goal: Cell) -> float:
        """Manhattan distance heuristic. Admissible for 4-way unit-cost grids."""
        return float(abs(cell.row - goal.row) + abs(cell.col - goal.col))

    def octile_heuristic(self, cell: Cell, goal: Cell) -> float:
        """Octile distance heuristic.

        Admissible and consistent for 8-way movement with diagonal cost
        sqrt(2) and orthogonal cost 1.
        """
        dx = abs(cell.col - goal.col)
        dy = abs(cell.row - goal.row)
        orthogonal = 1.0
        diagonal = math.sqrt(2)
        return diagonal * min(dx, dy) + orthogonal * abs(dx - dy)


def build_problem(
    config: GridConfig,
    start: Cell,
    goal: Cell,
) -> SearchProblem:
    """Build a :class:`SearchProblem` from a grid config, start, and goal.

    Obstacles declared on the config are registered on the environment so they
    are respected by successor generation (and therefore by every algorithm).
    """
    env = GridEnvironment(config)
    for obs in config.obstacles:
        env.add_obstacle(obs)

    def successors(state: Cell) -> List[Tuple[Cell, Action]]:
        return env.successors(state)

    def goal_test(state: Cell) -> bool:
        return state == goal

    heuristic: Optional[Heuristic] = None
    if config.movement == MovementMode.FOUR_WAY:
        heuristic = lambda s: env.manhattan_heuristic(s, goal)  # noqa: E731
    else:
        heuristic = lambda s: env.octile_heuristic(s, goal)  # noqa: E731

    return SearchProblem(
        start=start,
        goal=goal,
        successors=successors,
        goal_test=goal_test,
        heuristic=heuristic,
    )
