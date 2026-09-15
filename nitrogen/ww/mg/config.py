from __future__ import annotations

import os

from .logging import error
from .filepath import FilePath


class ObjectNotationError(Exception):
    pass

def rf(path: str) -> str:
    if not os.path.exists(path):
        raise FileNotFoundError(f"File not found: {path}")
    with open(path) as file:
        return file.read()

class ObjectNotation:
    def __init__(self, path: FilePath | str) -> None:
        self.path: FilePath = FilePath(path)
        if not self.path.exists():
            raise ObjectNotationError(f"File not found: {self.path}")
        
        self.data: any = eval(self.path.read(), {"rf": rf})
    def get(self, key: str, else_val: any = None) -> any:
        return self.data.get(key, else_val)
def getconf(key: str, else_value: any = ...) -> any:
    config_file_path: FilePath = FilePath("config.pyon")
    if not config_file_path.exists():
        with error("Configuration file not found: config.pyon, creating one for you.") as error_log:
            config_file_path.write("{}")
            error_log.sublog(f"'{config_file_path.name}' created successfully.")
    if key not in ObjectNotation(config_file_path).data:
        if else_value is not ...:
            return else_value
        raise ObjectNotationError(f"Configuration key not found: {key}")
    return ObjectNotation(config_file_path).get(key)