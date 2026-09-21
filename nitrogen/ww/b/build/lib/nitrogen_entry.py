
import os
import runpy
import sys

ROOT = '/home/danny/projects/wednesware/nitrogen/nitrogen/ww/b'
ENTRY = '__main__.py'
PACKAGE_NAME = 'b'
MODULE_PATH = '/home/danny/projects/wednesware/nitrogen/nitrogen/ww/b/__main__.py'


def main() -> None:
    entry_path = os.path.join(ROOT, ENTRY)
    if os.path.isfile(entry_path):
        if os.path.basename(entry_path) == "__main__.py" and os.path.isfile(os.path.join(ROOT, "__init__.py")):
            sys.path.insert(0, os.path.dirname(ROOT))
            runpy.run_module(PACKAGE_NAME, run_name="__main__")
            return
        runpy.run_path(entry_path, run_name="__main__")
        return
    if os.path.isfile(MODULE_PATH):
        sys.path.insert(0, os.path.dirname(ROOT))
        runpy.run_module(PACKAGE_NAME, run_name="__main__")
        return
    raise FileNotFoundError(f"No entry script found for package at {ROOT!r}")
