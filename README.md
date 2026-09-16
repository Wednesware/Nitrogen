> ### Note
> This Document2.0 formatted README.md file was provided by dannywoof, the maintainer of this library. If you have any questions or feedback, feel free to reach out via [bluesky](https://bsky.app/profile/danny.wednesware.org) or [email](mailto:danny@wednesware.org).

[![Wednesware](wednesware.png)](https://wednesware.org)

# Nitrogen



## Installation

> `pip install wwn`

## Dependencies

- Python 3.12+

# Commands

## General

General commands for installing and managing Wednesware publications and packages.

### `get <publication> [release]`

Download a Wednesware publication from GitHub. Publication names can also be written as their chemical symbols, e.g. `mg` for Magnesium, `he` for Helium. If no release is specified, the latest release will be downloaded.

> `n2 get magnesium 26.5`

### `rm <publication> [release]`

Delete one release or all installed releases for a publication. If no release is specified, all installed releases will be deleted.

> `n2 rm magnesium 26.5`

### `install <path> [--name <command>] [--bin <dir>] [--no-deps]`

Install a Nitrogen package from a local directory.

> `n2 install ./my_package --name my_command --bin ./bin --no-deps`

### `install-cache <publication> [release] [--name <command>] [--bin <dir>]`

Install a cached publication from Nitrogen's internal cache as a command without re-downloading.

> `n2 install-cache magnesium 26.5 --name mg --bin ./bin`

### `uninstall <command> [--bin <dir>]`

Uninstall a Nitrogen package by its command name. If the `--bin` option is not specified, the default bin directory will be used.

> `n2 uninstall my_command --bin ./bin`

## Documentation

Read documentation bundled with Nitrogen.

### `readme`

Show the Nitrogen README.

> `n2 readme`

### `license`

Show the Nitrogen license.

> `n2 license`

### `help`

Show the full help message with all commands.

> `n2 help`

# Definitions

## `nitrogen`

Nitrogen can be used as a Python library. You may use any internal functions, but there are also functions specifically meant for use via the library.

### `nitrogen:require(pub: str, rel: str | None = None) -> object`

Load a Wednesware publication from Nitrogen's internal cache. The first run may need internet access to download the publication, but later runs reuse the cached copy locally. Submodules should be provided within the `pub` parameter like `magnesium.color`. Chemical symbols can also be used for publication names, e.g. `mg` for Magnesium, `he` for Helium.

> `Color = require("magnesium.color", "26.5").Color`

### `nitrogen:NitrogenDependencyError`

Raised when a dependency is not already cached locally and the source site cannot be reached or is otherwise unavailable.

### `nitrogen:cleanup() -> None`

Clean up the internal cache directory by removing any unused publications. This is useful for freeing up disk space after installing and using publications. Generally makes programs significantly slower if you use `require`.

> `cleanup()`

### `nitrogen:entrypoint() -> None`

Starts Nitrogen.

> `entrypoint()`