> ### Note
> This Document2.0 formatted README.md file was provided by dannywoof, the maintainer of this library. If you have any questions or feedback, feel free to reach out via [bluesky](https://bsky.app/profile/danny.wednesware.org) or [email](mailto:danny@wednesware.org).

[![Wednesware](wednesware.png)](https://wednesware.org)

# Nitrogen



## Installation

> `pipx install wwn`

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

### `getdep [path]`

Install missing dependencies from a `.nitrodep` file, including nested ones. If no path is specified, the current working directory will be used.

> `n2 getdep my_project`

### `forcegetdep [path]`

Install all dependencies, regardless of whether they are already installed from a `.nitrodep` file, including nested ones, forcing reinstallation of all dependencies. If no path is specified, the current working directory will be used.

> `n2 forcegetdep my_project`

### `install <path> [--name <command>] [--bin <dir>] [--no-deps]`

Install a Nitrogen package from a local directory.

> `n2 install my_project --name my_command --bin ./bin --no-deps`

### `uninstall <command> [--bin <dir>]`

Uninstall a Nitrogen package by its command name. If the `--bin` option is not specified, the default bin directory will be used.

> `n2 uninstall my_command --bin ./bin`

## Helium

Helium support within Nitrogen.

### `getlib <project> <publication> [release]`

Download a Wednesware publication into `<project>/libraries/ww`. Used to download libraries for Helium projects.

> `n2 getlib my_project magnesium 26.5`

### `updlibs <project>`

Reinstall all libraries in `<project>/libraries/ww` from their exact installed versions. Used to update libraries for Helium projects.

> `n2 updlibs my_project`

## Internal

Internal tools for caching and storing publications.

### `getinternal <publication> [release]`

Same as `get`, but installs to `nitrogen/ww` instead of './ww'.

### `rminternal <publication> [release]`

Same as `rm`, but for `nitrogen/ww` instead of './ww'.

### `getdepinternal [path]`

Same as `getdep`, but for `nitrogen/ww` instead of './ww'.

## Compatibility

Compatibility tools for rewriting `from ww...` imports in a directory to match a different import layout.

### `compat <mode> <publication|directory> [custom-phrase]`

Rewrite Wednesware imports in a directory to match the specified compatibility mode.

The following compatibility modes are available:

- `abs` — Use `abs` for packages found in `.`.
- `rel` — Use `rel` for packages found in `<project>`.
- `rel-up1` — Use `rel-up1` for packages found in `<project>/../`.
- `rel-up2` — Use `rel-up2` for packages found in `<project>/../../`.
- `rel-up3` — Use `rel-up3` for packages found in `<project>/../../../`.
- `abs-ww` — Use `abs-ww` for packages found in `./ww`. This is the default compatibility mode.
- `rel-ww` — Use `rel-ww` for packages found in `<project>/ww` with relative imports.
- `rel-libs-ww` — Use `rel-libs-ww` for Helium projects or packages found in `<project>/libraries/ww` with relative imports.
- `custom` — Use `custom` to specify a custom phrase for the import prefix.

> `n2 compat custom my_project ".."`

## Build

Build a Nitrogen project into an archive.

### `build zip [source path(. by default)] [output path(build.zip by default)]`

Build the current Nitrogen project into a zip archive.

> `n2 build zip . build.zip`

### `build targz [source path(. by default)] [output path(build.tar.gz by default)]`

Build the current Nitrogen project into a tar.gz archive.

> `n2 build targz . build.tar.gz`

### `build n2x [source path(. by default)] [output path(build.n2x by default)]`

Build a Nitrogen extension archive from the required extension files.

> `n2 build n2x . build.n2x`

## Documentation

Read documentation bundled with Nitrogen or an installed extension.

### `readme [extension]`

Show the README for an installed extension, or Nitrogen itself if no argument is provided.

> `n2 readme my_extension`

### `license [extension]`

Show the license for an installed extension, or Nitrogen itself if no argument is provided.

> `n2 license my_extension`

### `help`

Show the full help message with all installed commands.

> `n2 help`

## Extensions

Install, trust, and manage Nitrogen extensions.

### `list-ext`

List installed extensions and their local paths.

> `n2 list-ext`

### `trust-ext <extension>`

Trust an extension so it can run without confirmation.

> `n2 trust-ext my_extension`

### `untrust-ext <extension>`

Remove trust for an extension.

> `n2 untrust-ext my_extension`

### `install-ext <extension>`

Install an extension from LEN.

> `n2 install-ext my_extension`

### `uninstall-ext <extension>`

Remove an installed extension.

> `n2 uninstall-ext my_extension`

### `list-len`

List available extensions in LEN.

> `n2 list-len`

### `load-len`

Clone the LEN repository locally.

> `n2 load-len`

### `unload-len`

Remove the local LEN checkout.

> `n2 unload-len`

# Definitions

## `nitrogen`

Nitrogen can be used as a Python library. You may use any internal functions, but there are also functions specifically meant for use via the library.

### `nitrogen:require(pub: str, rel: str | None = None) -> None`

Get a Wednesware publication. Installs to the internal cache directory and persists across sessions. Only downloads the publication if it is not already installed. If a release is specified, that release will be downloaded. If no release is specified, the latest release will be downloaded. Submodules should be provided within the `pub` parameter like `magnesium.color`. Chemical symbols can also be used for publication names, e.g. `mg` for Magnesium, `he` for Helium.

> `Color = require("magnesium.color", "26.5").Color`

### `nitrogen:cleanup() -> None`

Clean up the internal cache directory by removing any unused publications. This is useful for freeing up disk space after installing and using publications. Generally makes programs significantly slower if you use `require`.

> `cleanup()`

### `nitrogen:entrypoint() -> None`

Starts Nitrogen.

> `entrypoint()`