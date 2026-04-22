from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional, Tuple, Set
import random
import uuid
import math
from enum import Enum

app = FastAPI(title="地鼠潜行游戏", description="角色反转的网格潜行策略游戏")

try:
    app.mount("/static", StaticFiles(directory="static"), name="static")
except:
    pass

class Direction(str, Enum):
    UP = "up"
    DOWN = "down"
    LEFT = "left"
    RIGHT = "right"

class GameStatus(str, Enum):
    PLAYING = "playing"
    WON = "won"
    LOST = "lost"

class CellType(str, Enum):
    EMPTY = "empty"
    CARROT = "carrot"
    ROCK = "rock"
    TRAP = "trap"

class HammerState:
    def __init__(self, x: int, y: int, warning_time: int, strike_time: int):
        self.x = x
        self.y = y
        self.warning_time = warning_time
        self.strike_time = strike_time
        self.has_struck = False

class Farmer:
    def __init__(self, patrol_edges: List[Tuple[int, int]]):
        self.patrol_edges = patrol_edges
        self.current_index = 0
        self.direction = 1
        self.alert_level = 0
        self.target_x: Optional[int] = None
        self.target_y: Optional[int] = None

class Dog:
    def __init__(self, patrol_route: List[Tuple[int, int]]):
        self.patrol_route = patrol_route
        self.current_index = 0
        self.direction = 1

class SoundWave:
    def __init__(self, x: int, y: int, radius: int, created_time: int):
        self.x = x
        self.y = y
        self.radius = radius
        self.created_time = created_time

class MoleSkills:
    def __init__(self):
        self.dash_cooldown = 0
        self.burrow_cooldown = 0
        self.is_burrowed = False
        self.burrow_end_time = 0
        self.is_dashing = False
        self.dash_end_time = 0

class GameState:
    def __init__(self, level: int = 1):
        self.game_id = str(uuid.uuid4())[:8]
        self.level = level
        self.grid_size = 10 if level == 1 else 12
        self.score = 0
        self.high_score = 0
        self.carrot_count = 0
        self.status = GameStatus.PLAYING
        self.mole_x = 1
        self.mole_y = 1
        self.is_slowed = False
        self.slow_end_time = 0
        self.consecutive_moves = 0
        self.last_move_time = 0
        self.hammers: List[HammerState] = []
        self.sound_waves: List[SoundWave] = []
        self.grid: List[List[CellType]] = []
        self.farmer: Optional[Farmer] = None
        self.dog: Optional[Dog] = None
        self.skills = MoleSkills()
        self.tick_count = 0
        self._initialize_grid()
        self._initialize_level()

    def _initialize_grid(self):
        self.grid = [[CellType.EMPTY for _ in range(self.grid_size)] for _ in range(self.grid_size)]
        carrot_count = 5 if self.level == 1 else 8
        for _ in range(carrot_count):
            self._place_random_carrot()

    def _initialize_level(self):
        if self.level >= 2:
            self._add_rocks()
            self._initialize_farmer()
        
        if self.level >= 3:
            self._add_traps()
            self._initialize_dog()

    def _add_rocks(self):
        rock_count = 3 if self.level == 2 else 5
        for _ in range(rock_count):
            x, y = self._get_random_empty_cell()
            if x is not None:
                self.grid[y][x] = CellType.ROCK

    def _add_traps(self):
        trap_count = 3
        for _ in range(trap_count):
            x, y = self._get_random_empty_cell()
            if x is not None:
                self.grid[y][x] = CellType.TRAP

    def _initialize_farmer(self):
        edges = []
        for x in range(self.grid_size):
            edges.append((x, 0))
        for y in range(1, self.grid_size):
            edges.append((self.grid_size - 1, y))
        for x in range(self.grid_size - 2, -1, -1):
            edges.append((x, self.grid_size - 1))
        for y in range(self.grid_size - 2, 0, -1):
            edges.append((0, y))
        self.farmer = Farmer(edges)

    def _initialize_dog(self):
        route = []
        for i in range(2, self.grid_size - 2):
            route.append((i, 3))
        for i in range(4, self.grid_size - 3):
            route.append((self.grid_size - 4, i))
        for i in range(self.grid_size - 5, 1, -1):
            route.append((i, self.grid_size - 4))
        for i in range(self.grid_size - 5, 3, -1):
            route.append((2, i))
        self.dog = Dog(route)

    def _place_random_carrot(self):
        x, y = self._get_random_empty_cell()
        if x is not None:
            self.grid[y][x] = CellType.CARROT

    def _get_random_empty_cell(self) -> Tuple[Optional[int], Optional[int]]:
        empty_cells = []
        for y in range(self.grid_size):
            for x in range(self.grid_size):
                if self.grid[y][x] == CellType.EMPTY and not (x == self.mole_x and y == self.mole_y):
                    empty_cells.append((x, y))
        if empty_cells:
            return random.choice(empty_cells)
        return None, None

    def move_mole(self, direction: Direction) -> bool:
        if self.status != GameStatus.PLAYING:
            return False

        dx, dy = 0, 0
        if direction == Direction.UP:
            dy = -1
        elif direction == Direction.DOWN:
            dy = 1
        elif direction == Direction.LEFT:
            dx = -1
        elif direction == Direction.RIGHT:
            dx = 1

        new_x = self.mole_x + dx
        new_y = self.mole_y + dy

        if not (0 <= new_x < self.grid_size and 0 <= new_y < self.grid_size):
            return False

        if self.grid[new_y][new_x] == CellType.ROCK:
            return False

        self.mole_x = new_x
        self.mole_y = new_y

        if self.grid[new_y][new_x] == CellType.CARROT:
            self.score += 10
            self.carrot_count += 1
            self.grid[new_y][new_x] = CellType.EMPTY
            self._place_random_carrot()
            self._create_sound_wave(new_x, new_y, 3)
            self.consecutive_moves = 0
        elif self.grid[new_y][new_x] == CellType.TRAP:
            self.is_slowed = True
            self.slow_end_time = self.tick_count + 5

        self.consecutive_moves += 1
        if self.consecutive_moves >= 3:
            self._create_sound_wave(new_x, new_y, 2)
            self.consecutive_moves = 0

        return True

    def _create_sound_wave(self, x: int, y: int, radius: int):
        if self.level >= 2:
            self.sound_waves.append(SoundWave(x, y, radius, self.tick_count))

    def use_dash(self, direction: Direction) -> bool:
        if self.status != GameStatus.PLAYING:
            return False
        if self.carrot_count < 3:
            return False
        if self.skills.dash_cooldown > self.tick_count:
            return False

        self.carrot_count -= 3
        self.skills.is_dashing = True
        self.skills.dash_end_time = self.tick_count + 2
        self.skills.dash_cooldown = self.tick_count + 10

        dx, dy = 0, 0
        if direction == Direction.UP:
            dy = -1
        elif direction == Direction.DOWN:
            dy = 1
        elif direction == Direction.LEFT:
            dx = -1
        elif direction == Direction.RIGHT:
            dx = 1

        for _ in range(3):
            new_x = self.mole_x + dx
            new_y = self.mole_y + dy
            if 0 <= new_x < self.grid_size and 0 <= new_y < self.grid_size:
                if self.grid[new_y][new_x] != CellType.ROCK:
                    self.mole_x = new_x
                    self.mole_y = new_y
                    if self.grid[new_y][new_x] == CellType.CARROT:
                        self.score += 10
                        self.carrot_count += 1
                        self.grid[new_y][new_x] = CellType.EMPTY
                        self._place_random_carrot()

        return True

    def use_burrow(self) -> bool:
        if self.status != GameStatus.PLAYING:
            return False
        if self.carrot_count < 5:
            return False
        if self.skills.burrow_cooldown > self.tick_count:
            return False

        self.carrot_count -= 5
        self.skills.is_burrowed = True
        self.skills.burrow_end_time = self.tick_count + 3
        self.skills.burrow_cooldown = self.tick_count + 15

        return True

    def tick(self):
        if self.status != GameStatus.PLAYING:
            return

        self.tick_count += 1

        if self.skills.is_burrowed and self.tick_count >= self.skills.burrow_end_time:
            self.skills.is_burrowed = False

        if self.skills.is_dashing and self.tick_count >= self.skills.dash_end_time:
            self.skills.is_dashing = False

        if self.is_slowed and self.tick_count >= self.slow_end_time:
            self.is_slowed = False

        self.sound_waves = [sw for sw in self.sound_waves if self.tick_count - sw.created_time < 5]

        if self.level == 1:
            if self.tick_count % 3 == 0:
                x, y = self._get_random_empty_cell()
                if x is not None:
                    self.hammers.append(HammerState(x, y, self.tick_count, self.tick_count + 3))
        else:
            if self.farmer:
                if self.tick_count % 2 == 0:
                    self.farmer.current_index += self.farmer.direction
                    if self.farmer.current_index >= len(self.farmer.patrol_edges):
                        self.farmer.direction = -1
                        self.farmer.current_index = len(self.farmer.patrol_edges) - 2
                    elif self.farmer.current_index < 0:
                        self.farmer.direction = 1
                        self.farmer.current_index = 1

                fx, fy = self.farmer.patrol_edges[self.farmer.current_index]
                
                if self.sound_waves:
                    for sw in self.sound_waves:
                        dist = math.sqrt((fx - sw.x) ** 2 + (fy - sw.y) ** 2)
                        if dist <= sw.radius + 3:
                            self.farmer.target_x = sw.x
                            self.farmer.target_y = sw.y
                            if self.tick_count % 2 == 0:
                                self.hammers.append(HammerState(sw.x, sw.y, self.tick_count, self.tick_count + 2))
                else:
                    mole_dist = math.sqrt((fx - self.mole_x) ** 2 + (fy - self.mole_y) ** 2)
                    if mole_dist <= 8 and self.tick_count % 4 == 0:
                        target_x = self.mole_x + random.randint(-1, 1)
                        target_y = self.mole_y + random.randint(-1, 1)
                        target_x = max(0, min(target_x, self.grid_size - 1))
                        target_y = max(0, min(target_y, self.grid_size - 1))
                        self.hammers.append(HammerState(target_x, target_y, self.tick_count, self.tick_count + 3))
                    elif self.tick_count % 5 == 0:
                        x, y = self._get_random_empty_cell()
                        if x is not None:
                            self.hammers.append(HammerState(x, y, self.tick_count, self.tick_count + 3))

        if self.level >= 3 and self.dog:
            if self.tick_count % 2 == 0:
                self.dog.current_index += self.dog.direction
                if self.dog.current_index >= len(self.dog.patrol_route):
                    self.dog.direction = -1
                    self.dog.current_index = len(self.dog.patrol_route) - 2
                elif self.dog.current_index < 0:
                    self.dog.direction = 1
                    self.dog.current_index = 1

            dog_x, dog_y = self.dog.patrol_route[self.dog.current_index]
            if dog_x == self.mole_x and dog_y == self.mole_y and not self.skills.is_burrowed:
                self.status = GameStatus.LOST

        for hammer in self.hammers:
            if not hammer.has_struck and self.tick_count >= hammer.strike_time:
                hammer.has_struck = True
                if hammer.x == self.mole_x and hammer.y == self.mole_y:
                    if not self.skills.is_burrowed:
                        self.status = GameStatus.LOST

        self.hammers = [h for h in self.hammers if self.tick_count - h.warning_time < 10]

        if self.score >= 50 and self.level == 1:
            self.status = GameStatus.WON
        elif self.score >= 100 and self.level == 2:
            self.status = GameStatus.WON
        elif self.score >= 200 and self.level == 3:
            self.status = GameStatus.WON

    def to_dict(self):
        grid_data = []
        for y in range(self.grid_size):
            row = []
            for x in range(self.grid_size):
                cell = {
                    "type": self.grid[y][x].value,
                    "is_mole": x == self.mole_x and y == self.mole_y,
                    "is_warning": False,
                    "is_struck": False,
                    "is_farmer": False,
                    "is_dog": False
                }
                for hammer in self.hammers:
                    if hammer.x == x and hammer.y == y:
                        if not hammer.has_struck:
                            cell["is_warning"] = True
                        else:
                            cell["is_struck"] = True
                grid_data.append(cell)

        if self.farmer:
            fx, fy = self.farmer.patrol_edges[self.farmer.current_index]
            if 0 <= fy < self.grid_size and 0 <= fx < self.grid_size:
                idx = fy * self.grid_size + fx
                grid_data[idx]["is_farmer"] = True

        if self.dog:
            dx, dy = self.dog.patrol_route[self.dog.current_index]
            if 0 <= dy < self.grid_size and 0 <= dx < self.grid_size:
                idx = dy * self.grid_size + dx
                grid_data[idx]["is_dog"] = True

        return {
            "game_id": self.game_id,
            "level": self.level,
            "grid_size": self.grid_size,
            "score": self.score,
            "carrot_count": self.carrot_count,
            "status": self.status.value,
            "grid": grid_data,
            "mole_pos": {"x": self.mole_x, "y": self.mole_y},
            "skills": {
                "can_dash": self.carrot_count >= 3 and self.skills.dash_cooldown <= self.tick_count,
                "can_burrow": self.carrot_count >= 5 and self.skills.burrow_cooldown <= self.tick_count,
                "is_burrowed": self.skills.is_burrowed,
                "is_dashing": self.skills.is_dashing,
                "dash_cooldown": max(0, self.skills.dash_cooldown - self.tick_count),
                "burrow_cooldown": max(0, self.skills.burrow_cooldown - self.tick_count)
            },
            "is_slowed": self.is_slowed,
            "tick": self.tick_count
        }

class MoveRequest(BaseModel):
    game_id: str
    direction: Direction

class SkillRequest(BaseModel):
    game_id: str
    direction: Optional[Direction] = None

games: dict = {}

@app.post("/api/game/new")
async def new_game(level: int = 1):
    game = GameState(level=level)
    games[game.game_id] = game
    return game.to_dict()

@app.post("/api/game/move")
async def move_mole(request: MoveRequest):
    if request.game_id not in games:
        raise HTTPException(status_code=404, detail="Game not found")
    
    game = games[request.game_id]
    if game.is_slowed and game.tick_count % 2 == 0:
        game.tick()
        return game.to_dict()
    
    game.move_mole(request.direction)
    game.tick()
    return game.to_dict()

@app.post("/api/game/dash")
async def use_dash(request: SkillRequest):
    if request.game_id not in games:
        raise HTTPException(status_code=404, detail="Game not found")
    if not request.direction:
        raise HTTPException(status_code=400, detail="Direction required for dash")
    
    game = games[request.game_id]
    success = game.use_dash(request.direction)
    if not success:
        raise HTTPException(status_code=400, detail="Cannot use dash right now")
    
    game.tick()
    return game.to_dict()

@app.post("/api/game/burrow")
async def use_burrow(request: SkillRequest):
    if request.game_id not in games:
        raise HTTPException(status_code=404, detail="Game not found")
    
    game = games[request.game_id]
    success = game.use_burrow()
    if not success:
        raise HTTPException(status_code=400, detail="Cannot use burrow right now")
    
    game.tick()
    return game.to_dict()

@app.post("/api/game/restart")
async def restart_game(game_id: str):
    if game_id not in games:
        raise HTTPException(status_code=404, detail="Game not found")
    
    old_game = games[game_id]
    new_game = GameState(level=old_game.level)
    new_game.high_score = max(old_game.high_score, old_game.score)
    games[new_game.game_id] = new_game
    return new_game.to_dict()

@app.post("/api/game/next-level")
async def next_level(game_id: str):
    if game_id not in games:
        raise HTTPException(status_code=404, detail="Game not found")
    
    old_game = games[game_id]
    new_level = old_game.level + 1
    if new_level > 3:
        new_level = 1
    
    new_game = GameState(level=new_level)
    new_game.high_score = max(old_game.high_score, old_game.score)
    games[new_game.game_id] = new_game
    return new_game.to_dict()

@app.get("/api/game/{game_id}")
async def get_game(game_id: str):
    if game_id not in games:
        raise HTTPException(status_code=404, detail="Game not found")
    
    game = games[game_id]
    return game.to_dict()

@app.get("/")
async def root():
    return FileResponse("static/index.html")
