from __future__ import annotations

from pathlib import Path


class FilePath:
    def __init__(self, *parts: any) -> None:
        self.path: Path = Path(*map(str, parts))

    def __str__(self) -> str:
        return str(self.path)

    def __repr__(self) -> str:
        return f"FilePath({self.path!r})"

    def __truediv__(self, other: any) -> FilePath:
        path: FilePath = self
        for part in str(other).split("/"):
            for part2 in part.split("\\"):
                if str(part2) == "..":
                    path = path.parent
                else:
                    path = FilePath(path.path, part2)
        return path

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def stem(self) -> str:
        return self.path.stem

    @property
    def suffix(self) -> str:
        return self.path.suffix

    @property
    def parent(self) -> FilePath:
        return FilePath(self.path.parent)

    def exists(self) -> bool:
        return self.path.exists()

    def is_file(self) -> bool:
        return self.path.is_file()

    def is_dir(self) -> bool:
        return self.path.is_dir()

    def mkdir(
        self,
        parents: bool = True,
        exist_ok: bool = True,
    ) -> None:
        self.path.mkdir(
            parents=parents,
            exist_ok=exist_ok,
        )

    def unlink(
        self,
        missing_ok: bool = False,
    ) -> None:
        self.path.unlink(
            missing_ok=missing_ok,
        )

    def read(
        self,
        encoding: str = "utf-8",
    ) -> str:
        return self.path.read_text(
            encoding=encoding,
        )

    def write(
        self,
        text: str,
        encoding: str = "utf-8",
    ) -> None:
        self.path.write_text(
            text,
            encoding=encoding,
        )

    def read_bytes(self) -> bytes:
        return self.path.read_bytes()

    def write_bytes(
        self,
        data: bytes,
    ) -> None:
        self.path.write_bytes(data)

    def join(
        self,
        *parts: any,
    ) -> FilePath:
        return FilePath(
            self.path,
            *parts,
        )

    def resolve(self) -> FilePath:
        return FilePath(
            self.path.resolve(),
        )

    def absolute(self) -> FilePath:
        return FilePath(
            self.path.absolute(),
        )