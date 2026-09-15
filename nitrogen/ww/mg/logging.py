from __future__ import annotations

from .color import Color


class log:
    def __init__(self, text: str) -> None:
        self.text: str = text + Color.reset
        self.parent: "log | None" = None
        self.children: list[log] = []
        self.level: int = 0

    def sublog(self, text: str) -> log:
        sublog: log = self.__class__(text)
        sublog.parent = self
        self.children.append(sublog)
        sublog.level = self.level + 1 if self else 0
        return sublog

    def _format_line(self) -> str:
        if self.parent is None:
            return self.text

        indent = "┃ " * max(0, self.level - 1)
        branch = "┗ " if self is self.parent.children[-1] else "┣ "
        return f"{indent}{branch}{self.text}"

    def print(self) -> None:
        print(self._tree_string())

    def _tree_string(self) -> str:
        lines = [self._format_line()]
        for child in self.children:
            lines.extend(child._collect_lines())
        return "\n".join(lines)

    def _collect_lines(self) -> list[str]:
        lines = [self._format_line()]
        for child in self.children:
            lines.extend(child._collect_lines())
        return lines
    
    def __enter__(self) -> log:
        return self
    def __exit__(self, *_) -> None:
        if not self.parent:
            self.print()
            
class error(log):
    def __init__(self, text: str) -> None:
        super().__init__(f"{Color.red}{text}")
    @classmethod
    def from_exception(cls, exc: Exception) -> error:
        log1: error = error(f"{Color.red}{exc.__class__.__name__}{Color.reset}")
        log1.sublog(f"{Color.red}{str(exc)}{Color.reset}")
        return log1