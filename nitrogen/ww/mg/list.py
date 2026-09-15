from __future__ import annotations

from .group import Group


class ListNav(list):
    def lm(self) -> int:
        return 0
    
    def rm(self) -> int:
        return len(self) - 1

class Selection:
    def __init__(self, l: list, x1: int, x2: int) -> None:
        self.list: list = l
        self.x1: int = x1
        self.x2: int = x2
        self.mxx: int = max(x1, x2)
        self.mnx: int = min(x1, x2)
    
    def set(self, x: int, value: any) -> "Selection":
        self.list[self.mnx + x] = value
        return self
    
    def get(self, x: int) -> any:
        return self.list[self.mnx + x]
    
    def fill(self, value: any) -> "Selection":
        for i in range(self.mnx, self.mxx):
            self.list[i] = value
        return self
    
    def lm(self) -> int:
        return self.x1
    
    def rm(self) -> int:
        return self.x2

class List2D:
    def __init__(self, width: int, height: int, default_value: any = None) -> None:
        self.width: int = width
        self.height: int = height
        self.default_value: any = default_value
        self.data: list[list] = [[default_value for _ in range(width)] for _ in range(height)]
    
    def set(self, x: int, y: int, value: any) -> "List2D":
        if 0 <= x < self.width and 0 <= y < self.height:
            self.data[y][x] = value
        return self
    
    def get(self, x: int, y: int) -> any:
        if 0 <= x < self.width and 0 <= y < self.height:
            return self.data[y][x]
        return None
    
    def fill(self, value: any) -> "List2D":
        for y in range(self.height):
            for x in range(self.width):
                self.data[y][x] = value
        return self
    
    def select(self, x1: int, y1: int, x2: int, y2: int) -> "Selection2D":
        return Selection2D(self, x1, y1, x2, y2)
    
    def print(self) -> "List2D":
        for row in self.data:
            print("".join(str(cell) for cell in row))
        return self
    
    def render(self) -> str:
        return "\n".join("".join(str(cell) for cell in row) for row in self.data)
    
    def sizefit(self) -> int:
        return min(self.width, self.height)
    
    def sizefill(self) -> int:
        return max(self.width, self.height)
    
    def midx(self) -> int:
        return self.width // 2
    
    def midy(self) -> int:
        return self.height // 2
    
    def lm(self) -> int:
        return 0
    
    def rm(self) -> int:
        return self.width
    
    def tm(self) -> int:
        return 0
    
    def bm(self) -> int:
        return self.height

class Tile:
    def __init__(self, value: any, data: dict[str, any] | None = None) -> None:
        self.value: any = value
        self.data: dict[str, any] = data or {}

class Structure:
    def __init__(self, sel2d: Selection2D, label: str, *groups: Group) -> None:
        self.selection2d: Selection2D = sel2d
        self.label: str = label
        self.groups: list[Group] = []
        for gr in groups:
            if gr.member_added(self):
                self.groups.append(gr)

class Selection2D:
    def __init__(self, l2d: List2D, x1: int, y1: int, x2: int, y2: int) -> None:
        self.list2d: List2D = l2d
        self.x1: int = x1
        self.y1: int = y1
        self.x2: int = x2
        self.y2: int = y2
        self.mxx: int = max(x1, x2)
        self.mnx: int = min(x1, x2)
        self.mxy: int = max(y1, y2)
        self.mny: int = min(y1, y2)
    
    def set(self, x: int, y: int, value: any) -> "Selection2D":
        self.list2d.data[self.mny + y][self.mnx + x] = value
        return self
    
    def get(self, x: int, y: int) -> any:
        return self.list2d.data[self.mny + y][self.mnx + x]
    
    def fill(self, value: any) -> "Selection2D":
        for y in range(self.mny, self.mxy):
            for x in range(self.mnx, self.mxx):
                self.list2d.data[y][x] = value
        return self
    
    def print(self) -> "Selection2D":
        for y in range(self.mny, self.mxy):
            row = "".join(str(self.list2d.data[y][x]) for x in range(self.mnx, self.mxx))
            print(row)
        return self
    
    def new(self) -> None:
        if not isinstance(self.list2d, World):
            raise TypeError("can only create structures on worlds.")
        
    
    def sizefit(self) -> int:
        return min(self.x2 - self.x1, self.y2 - self.y1)
    
    def sizefill(self) -> int:
        return max(self.x2 - self.x1, self.y2 - self.y1)
    
    def midx(self) -> int:
        return (self.x2 - self.x1) // 2
    
    def midy(self) -> int:
        return (self.y2 - self.y1) // 2
    
    def lm(self) -> int:
        return self.x1
    
    def rm(self) -> int:
        return self.x2
    
    def tm(self) -> int:
        return self.y1
    
    def bm(self) -> int:
        return self.y2

class World(List2D):
    def __init__(self, width: int = 100, height: int = 100, default_value: any = ".") -> None:
        super().__init__(width, height, default_value)
        self.plan: list[Structure] = []
    
    def setvalue(self, x: int, y: int, value: any) -> "List2D":
        if 0 <= x < self.width and 0 <= y < self.height:
            self.data[y][x].value = value
        return self
    
    def getvalue(self, x: int, y: int) -> any:
        if 0 <= x < self.width and 0 <= y < self.height:
            return self.data[y][x].value
        return None
    
    def setdata(self, x: int, y: int, value: any) -> "List2D":
        if 0 <= x < self.width and 0 <= y < self.height:
            self.data[y][x].data = value
        return self
    
    def getdata(self, x: int, y: int) -> any:
        if 0 <= x < self.width and 0 <= y < self.height:
            return self.data[y][x].data
        return None
    
    def sde(self, x: int, y: int, key: str, value: any) -> "List2D":
        if 0 <= x < self.width and 0 <= y < self.height:
            self.data[y][x].data[key] = value
        return self
    
    def gde(self, x: int, y: int, key: str) -> any:
        if 0 <= x < self.width and 0 <= y < self.height:
            return self.data[y][x].data[key]
        return None
    
def tl(x: int = 0, y: int = 0, size: int = 0, size_x: int = 0, size_y: int = 0) -> tuple[int, int, int, int]:
    return (x, y, x + size + size_x, y + size + size_y)
def tr(x: int = 0, y: int = 0, size: int = 0, size_x: int = 0, size_y: int = 0) -> tuple[int, int, int, int]:
    return (x - size - size_x, y + size + size_y, x, y)
def bl(x: int = 0, y: int = 0, size: int = 0, size_x: int = 0, size_y: int = 0) -> tuple[int, int, int, int]:
    return (x, y - size - size_y, x + size + size_x, y)
def br(x: int = 0, y: int = 0, size: int = 0, size_x: int = 0, size_y: int = 0) -> tuple[int, int, int, int]:
    return (x - size - size_x, y - size - size_y, x, y)