[![Wednesware](wednesware.png)](https://wednesware.org)

# Nitrogen

Easy, ultra-lightweight installer for Wednesware publications.

## Installation methods:

### From PyPI via pipx (recommended, global install, run with `n2`):
* `pipx install wwn`

### CURRENTLY NOT WORKING: From AUR via an AUR helper (best for arch linux, endeavouros, manjaro or garuda linux users, global install, run with `n2`):
* `yay -S n2`
* You may alternatively also use `paru`, `pikaur`, or any other AUR helper to install Nitrogen from the AUR instead of `yay`.

### From PyPI via pip (virtual environment or global install, run with `n2`):
* `pip install wwn`
* Note: You may need to create a virtual environment for this method first on some machines. [Learn how to do this here.](https://docs.python.org/3/library/venv.html)

### From GitHub via terminal (local install, run with `python -m nitrogen.nitrogen`):
* `git clone https://github.com/Wednesware/Nitrogen.git nitrogen`

### From Github via browser (local install, run with `python -m nitrogen.nitrogen`):
* [Click here to install the latest Nitrogen release as a zip file](https://github.com/Wednesware/Nitrogen/releases/latest/download/nitrogen.zip) [or click here to browse releases](https://github.com/Wednesware/Nitrogen/releases).
* Unpack using `bsdtar -xf nitrogen.zip`

## Upgrade methods:

### From PyPI
* `pip install wwn --upgrade`

## Usage:

### 

* `n2 get <publication> [release (latest by default)]` - Download a Wednesware publication from GitHub.
  * Example usage: `n2 get magnesium 26.3` (installs Magnesium release 26.3 to `ww/mg26_3`.)
  * Tip: you can use chemical symbols for publications. Example: `n2 get mg 26.3`
* `n2 getlib <project> <publication> [release (latest by default)]` - Download a Wednesware publication to `./<project>/libraries/ww`.
  * Example usage: `n2 getlib app magnesium 26.3` (installs to `./app/libraries/ww/mg26_3`.)
* `n2 rm <publication> [release (all by default)]` - Delete all releases or a specific release of a publication from the current directory.
  * Example usage: `n2 rm magnesium 26.3` (deletes `./ww/magnesium26_3` and `./ww/mg26_3` only if present)
  * Or: `n2 rm magnesium` (deletes all installed versions in `./ww` for both long and short publication names)
  * Tip: you can use chemical symbols here too.
* `n2 getdep [path]` - Search recursively under path for every `.nitrodep` and install dependencies.
* `n2 forcegetdep [path]` - Same as `getdep`, but force reinstall dependencies.
* `n2 updlibs <project>` - Reinstall all libraries found in `./<project>/libraries/ww` by reading installed publication names and versions.
* `n2 stage get <publication> [release]` - Stage a dependency install into `./ww`.
* `n2 stage getlib <project> <publication> [release]` - Stage a library install into `./<project>/libraries/ww`.
* `n2 stage adddep <publication> [release]` - Stage adding a dependency to `./.nitrodep`.
* `n2 stage rmdep <publication> [release]` - Stage removing a dependency from `./.nitrodep`.
* `n2 stage getdep [target]` - Stage running `getdep` at target path (`.` by default).
* `n2 stage forcegetdep [target]` - Stage running `forcegetdep` at target path (`.` by default).
* `n2 stage updlibs [target]` - Stage running `updlibs` at target path (`.` by default).
* `n2 stage rm <publication> [release]` - Stage removal from `./ww`.
* `n2 stage rmlib <project> <publication> [release]` - Stage removal from `./<project>/libraries/ww`.
* `n2 stage compat <publication> [release]` - Stage compatibility rewrite for Wednesware imports in a directory.
* `n2 stage cmd <*cmd>` - Stage a shell command.
* `n2 stage cancel [subcommand|last] [*arguments]` - Cancel staged entries, last entry, or all entries.
* `n2 stage execute` - Run staged actions in the order they were staged.
* `n2 stage commit` - Run staged actions in batched mode for faster installs.
* `n2 help` - Prints a formatted help message to the terminal.
