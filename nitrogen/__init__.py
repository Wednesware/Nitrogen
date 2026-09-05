import sys, zipfile, shutil, os, urllib.error, subprocess, traceback, tarfile, asyncio, re, importlib, types, json, sysconfig
from dataclasses import dataclass
from urllib.request import urlretrieve


VERSION: str = "26.52"
CLI_RESET: str = "\033[0m"
CLI_BOLD: str = "\033[1m"
CLI_DIM: str = "\033[90m"
CLI_INFO: str = "\033[94m"
CLI_SUCCESS: str = "\033[92m"
CLI_WARNING: str = "\033[93m"
CLI_ERROR: str = "\033[91m"

PUBLICATION_CACHE: dict[str, str] = {
    "n": "nitrogen",
    "mg": "magnesium",
    "he": "helium",
    "na": "sodium",
    "kr": "krypton",
    "o": "oxygen",
    "li": "lithium",
    "h": "hydrogen",
    "i": "iodine",
    "in": "indium",
    "ne": "neon",
    "c": "carbon",
    "b": "boron",
    "f": "fluorine",
    "s": "sulfur",
    "p": "phosphorus",
    "cl": "chlorine",
    "ar": "argon",
    "k": "potassium",
    "ca": "calcium",
    "sc": "scandium",
    "ti": "titanium",
    "v": "vanadium",
    "cr": "chromium",
    "mn": "manganese",
    "fe": "iron",
    "co": "cobalt",
    "ni": "nickel",
    "cu": "copper",
    "zn": "zinc",
    "ga": "gallium",
    "ge": "germanium",
    "as": "arsenic",
    "se": "selenium",
    "br": "bromine",
    "rb": "rubidium",
    "sr": "strontium",
    "y": "yttrium",
    "zr": "zirconium",
    "nb": "niobium",
    "mo": "molybdenum",
    "tc": "technetium",
    "ru": "ruthenium",
    "rh": "rhodium",
    "pd": "palladium"
}
REVERSE_PUBLICATION_CACHE: dict[str, str] = {v: k for k, v in PUBLICATION_CACHE.items()}
EXTENSIONS_DIR: str = os.path.join(os.path.dirname(__file__), "extensions")
TRUSTED_EXTENSIONS_FILE: str = os.path.join(os.path.dirname(__file__), ".TRUSTED_EXTENSIONS")
LEN_PATH: str = os.path.join(os.path.dirname(__file__), "ww", "len")
# "internal" installs live inside the nitrogen package itself (not the cwd), so commands like
INTERNAL_WW_DIR: str = os.path.join(os.path.dirname(__file__), "ww")
INTERNAL_TEMP_DIR: str = os.path.join(INTERNAL_WW_DIR, "temp")

running_installs: dict[tuple[str, str, str], asyncio.Task] = {}


def _default_bin_dir() -> str:
    user_home = os.path.expanduser("~")
    candidates: list[str] = []
    scripts_dir = sysconfig.get_path("scripts") if "sysconfig" in globals() else None
    if scripts_dir:
        candidates.append(scripts_dir)
    if os.name == "nt":
        candidates.extend([
            os.path.join(sys.prefix, "Scripts"),
            os.path.join(user_home, "AppData", "Local", "Programs", "Python", "Scripts"),
            os.path.join(user_home, "AppData", "Roaming", "Python", "Scripts"),
            os.path.join(user_home, "bin"),
        ])
    else:
        candidates.extend([
            os.path.join(sys.prefix, "bin"),
            os.path.join(user_home, ".local", "bin"),
            os.path.join(user_home, "bin"),
            "/usr/local/bin",
            "/usr/bin",
        ])
    seen: set[str] = set()
    ordered: list[str] = []
    for candidate in candidates:
        resolved = os.path.abspath(candidate)
        if resolved not in seen:
            seen.add(resolved)
            ordered.append(resolved)
    for candidate in ordered:
        if candidate and os.access(candidate, os.W_OK):
            return candidate
    if os.name == "nt":
        return os.path.join(user_home, "AppData", "Local", "Programs", "Python", "Scripts")
    return os.path.join(user_home, ".local", "bin")


def _load_nitropkg(path: str) -> dict:
    pkg_dir = os.path.abspath(path)
    if not os.path.isdir(pkg_dir):
        raise ValueError(f"Only directories can be installed: {path}")
    pkg_file = os.path.join(pkg_dir, ".nitropkg")
    if not os.path.isfile(pkg_file):
        raise ValueError(f"Only package directories with a JSON .nitropkg file can be installed: {path}")
    try:
        with open(pkg_file, "r", encoding="utf-8") as handle:
            metadata = json.load(handle)
    except json.JSONDecodeError as exc:
        raise ValueError(f".nitropkg is not valid JSON: {pkg_file}") from exc
    if not isinstance(metadata, dict):
        raise ValueError(f".nitropkg must contain a JSON object: {pkg_file}")
    return metadata


def _resolve_nitropkg_entry(path: str, metadata: dict) -> str:
    entry = metadata.get("entry") or metadata.get("main") or metadata.get("script")
    if entry:
        target = os.path.join(path, entry)
        if os.path.isfile(target):
            return target
    for candidate in ("__main__.py", "main.py", "app.py", "run.py"):
        target = os.path.join(path, candidate)
        if os.path.isfile(target):
            return target
    raise ValueError(f"No valid entry script found in package directory '{path}'")


def _as_path_list(root: str) -> list[str]:
    entries = [root]
    for relative in (".ww", "ww", "libraries", os.path.join("libraries", "ww")):
        candidate = os.path.join(root, relative)
        if os.path.isdir(candidate):
            entries.append(candidate)
    return entries


def _write_bin_script(bin_dir: str, command_name: str, target: str, root: str) -> str:
    os.makedirs(bin_dir, exist_ok=True)
    script_path = os.path.join(bin_dir, command_name)
    if os.name == "nt":
        script_path += ".cmd"
        pythonpath = os.pathsep.join(_as_path_list(root))
        script_content = (
            "@echo off\r\n"
            "setlocal\r\n"
            "rem nitropkg-managed\r\n"
            f"rem nitropkg-root={root}\r\n"
            f"set \"PYTHONPATH={pythonpath};%PYTHONPATH%\"\r\n"
            f'"{sys.executable}" "{target}" %*\r\n'
        )
        with open(script_path, "w", encoding="utf-8", newline="") as handle:
            handle.write(script_content)
        return script_path

    script_content = "#!/usr/bin/env sh\n"
    script_content += "set -eu\n"
    script_content += "# nitropkg-managed\n"
    script_content += f"# nitropkg-root={root}\n"
    script_content += f"export PYTHONPATH='{os.pathsep.join(_as_path_list(root))}:$PYTHONPATH'\n"
    script_content += f'exec "{sys.executable}" "{target}" "$@"\n'
    with open(script_path, "w", encoding="utf-8") as handle:
        handle.write(script_content)
    os.chmod(script_path, os.stat(script_path).st_mode | 0o111)
    return script_path


async def install_target(path: str, bin_dir: str | None = None, command_name: str | None = None, no_deps: bool = False) -> dict:
    pkg_dir = os.path.abspath(path)
    metadata = _load_nitropkg(pkg_dir)
    resolved_name = command_name or metadata.get("name") or metadata.get("command") or os.path.basename(pkg_dir)
    target = _resolve_nitropkg_entry(pkg_dir, metadata)
    target_bin_dir = bin_dir or _default_bin_dir()
    script_path = _write_bin_script(target_bin_dir, resolved_name, target, pkg_dir)

    dep_file = os.path.join(pkg_dir, ".nitrodep")
    if not no_deps and os.path.isfile(dep_file):
        if "getdep" in globals() and callable(getdep):
            await getdep(dep_file, install_root=os.path.join(pkg_dir, ".ww"), work_dir=pkg_dir, log=True, force=False)
    return {
        "command_name": resolved_name,
        "source_path": pkg_dir,
        "root": pkg_dir,
        "target": target,
        "bin_dir": os.path.abspath(target_bin_dir),
        "bin_path": os.path.abspath(script_path),
        "metadata": metadata,
    }


def uninstall_target(command_name: str, bin_dir: str | None = None) -> dict:
    target_bin_dir = bin_dir or _default_bin_dir()
    candidates = [
        os.path.join(target_bin_dir, command_name),
        os.path.join(target_bin_dir, command_name + ".cmd"),
        os.path.join(target_bin_dir, command_name + ".exe"),
    ]
    for candidate in candidates:
        if os.path.exists(candidate):
            try:
                with open(candidate, "r", encoding="utf-8") as handle:
                    content = handle.read(512)
            except Exception:
                content = ""
            if "nitropkg-managed" not in content.lower() and "nitropkg-root" not in content.lower():
                return {
                    "command_name": command_name,
                    "bin_dir": os.path.abspath(target_bin_dir),
                    "removed": False,
                    "path": os.path.abspath(candidate),
                    "reason": "refusing to remove a non-nitropkg command",
                }
            os.remove(candidate)
            return {
                "command_name": command_name,
                "bin_dir": os.path.abspath(target_bin_dir),
                "removed": True,
                "path": os.path.abspath(candidate),
            }
    return {
        "command_name": command_name,
        "bin_dir": os.path.abspath(target_bin_dir),
        "removed": False,
        "path": None,
        "reason": "wrapper not found",
    }




@dataclass(slots=True)
class InstallResult:
    status: str
    lines: list[str]
    exit_code: int = 0


def _cli(text: str, color: str = "", bold: bool = False) -> str:
    prefix: str = f"{CLI_BOLD if bold else ''}{color}"
    return f"{prefix}{text}{CLI_RESET if prefix else ''}"


def _print_status(label: str, message: str, tone: str = "info") -> None:
    palette: dict[str, str] = {
        "info": CLI_INFO,
        "success": CLI_SUCCESS,
        "warning": CLI_WARNING,
        "error": CLI_ERROR,
        "muted": CLI_DIM
    }
    color: str = palette.get(tone, "")
    print(f"{_cli(f'[{label}]', color, bold=True)} {message}")


def _print_section(title: str) -> None:
    print(_cli(title, CLI_BOLD))


def _print_command(signature: str, description: str) -> None:
    print(f"  {_cli(signature, CLI_INFO)} {_cli('-', CLI_DIM)} {description}")

def _print_help() -> None:
    print(_cli(f"Nitrogen v{VERSION}", CLI_INFO, bold=True))
    print(_cli("Quick installer for Wednesware publications", CLI_DIM))
    print()
    _print_section("Usage")
    print("  n2 <command> [args]")
    print()
    _print_section("General")
    _print_command("get <publication> [release]", "Download a Wednesware publication from GitHub.")
    _print_command("getlib <project> <publication> [release]", "Download a Wednesware publication into '<project>/libraries/ww'.")
    _print_command("rm <publication> [release]", "Delete one release or all installed releases for a publication.")
    _print_command("getdep [path]", "Install missing dependencies from a .nitrodep file, including nested ones.")
    _print_command("forcegetdep [path]", "Install all dependencies, regardless of whether they are already installed from a .nitrodep file, including nested ones, forcing reinstallation of all dependencies.")
    _print_command("install <path> [--name <command>] [--bin <dir>] [--no-deps]", "Install a Nitrogen package from a local directory.")
    _print_command("uninstall <command> [--bin <dir>]", "Remove an installed Nitrogen package.")
    print()
    _print_section("Helium")
    _print_command("updlibs <project>", "Reinstall all libraries in '<project>/libraries/ww' from their exact installed versions.")
    print()
    _print_section("Internal")
    _print_command("getinternal <publication> [release]", "Same as `get` into `nitrogen/ww` instead of './ww'.")
    _print_command("rminternal <publication> [release]", "Same as `rm` but for `nitrogen/ww`.")
    _print_command("getdepinternal [path]", "Same as `getdep` but for `nitrogen/ww` instead of './ww'.")
    print()
    _print_section("Compatibility")
    _print_command("compat <mode> <publication|directory> [custom-phrase]", "Rewrite Wednesware imports in a directory to match the specified compatibility mode.")
    _print_command("compat abs <publication|directory>", "Use 'abs' for packages found in '.'. ")
    _print_command("compat rel <publication|directory>", "Use 'rel' for packages found in '<project>'.")
    _print_command("compat rel-up1 <publication|directory>", "Use 'rel-up1' for packages found in '<project>/../'.")
    _print_command("compat rel-up2 <publication|directory>", "Use 'rel-up2' for packages found in '<project>/../../'.")
    _print_command("compat rel-up3 <publication|directory>", "Use 'rel-up3' for packages found in '<project>/../../../'.")
    _print_command("compat abs-ww <publication|directory>", "Use 'abs-ww' for packages found in './ww'. Default compat mode.")
    _print_command("compat rel-ww <publication|directory>", "Use 'rel-ww' for packages found in '<project>/ww' with relative imports.")
    _print_command("compat rel-libs-ww <publication|directory>", "Use 'rel-libs-ww' for Helium projects or packages found in '<project>/libraries/ww' with relative imports.")
    _print_command("compat custom <publication|directory> <custom-phrase>", "Use 'custom' to specify a custom phrase for the import prefix.")
    print()
    print()
    _print_section("Build")
    _print_command("build zip [source path(. by default)] [output path(build.zip by default)]", "Build the current Nitrogen project into a zip archive.")
    _print_command("build targz [source path(. by default)] [output path(build.tar.gz by default)]", "Build the current Nitrogen project into a tar.gz archive.")
    _print_command("build n2x [source path(. by default)] [output path(build.n2x by default)]", "Build a Nitrogen extension archive from the required extension files.")
    print()
    _print_section("Documentation")
    _print_command("readme [extension]", "Show the README for Nitrogen or an installed extension.")
    _print_command("license [extension]", "Show the license for Nitrogen or an installed extension.")
    _print_command("help", "Show this help message.")
    print()
    _print_section("Extensions")
    _print_command("list-ext", "List installed extensions and their local paths.")
    _print_command("trust-ext <extension>", "Trust an extension so it can run without confirmation.")
    _print_command("untrust-ext <extension>", "Remove trust for an extension.")
    _print_command("install-ext <extension>", "Install an extension from LEN.")
    _print_command("uninstall-ext <extension>", "Remove an installed extension.")
    _print_command("list-len", "List available extensions in LEN.")
    _print_command("load-len", "Clone the LEN repository locally.")
    _print_command("unload-len", "Remove the local LEN checkout.")


def _print_installed_extensions() -> None:
    _print_section("Installed extensions")
    sent: bool = False
    for ext_filename in [item for item in os.listdir(EXTENSIONS_DIR) if item.endswith(".n2x")]:
        print(f"  {_cli(ext_filename, CLI_INFO)} {_cli('->', CLI_DIM)} {os.path.join(EXTENSIONS_DIR, ext_filename)}")
        sent = True
    if not sent:
        _print_status("empty", "No extensions were detected.", "warning")


def _print_len_extensions() -> None:
    _print_section("Available extensions")
    printed: bool = False
    for ext_filename in [item for item in os.listdir(LEN_PATH) if item.endswith(".n2x")]:
        print(f"  {_cli(ext_filename, CLI_INFO)} {_cli('->', CLI_DIM)} https://github.com/Wednesware/LEN/blob/main/{ext_filename}")
        printed = True
    if not printed:
        _print_status("empty", "No extensions were detected in the LEN repository.", "warning")


def _print_extension_commands() -> None:
    _print_section("Custom commands")
    printed: bool = False
    for ext_path in [item for item in os.listdir(EXTENSIONS_DIR) if item.endswith(".n2x")]:
        print(f"  {_cli(ext_path.removesuffix('.n2x'), CLI_INFO)} {_cli('-', CLI_DIM)} Provided by '{ext_path}' at '{os.path.join(EXTENSIONS_DIR, ext_path)}'")
        printed = True
    if not printed:
        print(f"  {_cli('(none installed)', CLI_DIM)}")

def parsepub(pub: str) -> str:
    if pub.lower() in PUBLICATION_CACHE:
        return PUBLICATION_CACHE[pub.lower()]
    return pub


def _publication_dirname(pub: str, rel: str, root: str = "ww") -> str:
    return os.path.join(root, _publication_leaf(pub, rel))


def _publication_leaf(pub: str, rel: str) -> str:
    pub_key: str = REVERSE_PUBLICATION_CACHE.get(pub.lower(), pub.lower())
    if rel == "latest":
        return pub_key
    return f"{pub_key}{rel.replace('.', '_').replace('-', '_')}"


def _release_token(rel: str) -> str:
    return rel.replace(".", "_").replace("-", "_")


def _dependency_file_path(path: str) -> str:
    if path.endswith(".nitrodep"):
        return path
    return os.path.join(path, ".nitrodep")


def _print_install_result(result: InstallResult, color: bool = True) -> None:
    labels: dict[str, str] = {
        "info": "skip",
        "success": "done",
        "error": "fail",
    }
    palette: dict[str, str] = {
        "info": CLI_INFO,
        "success": CLI_SUCCESS,
        "error": CLI_ERROR,
    }
    prefix: str = palette.get(result.status, "") if color else ""
    label: str = labels.get(result.status, "info")
    for line in result.lines:
        if prefix:
            print(f"{_cli(f'[{label}]', prefix, bold=True)} {line}")
        else:
            print(f"[{label}] {line}")


def _find_nitrodep_files(root_path: str) -> list[str]:
    if root_path.endswith(".nitrodep") and os.path.isfile(root_path):
        return [root_path]
    found: list[str] = []
    for current_root, _, files in os.walk(root_path):
        if ".nitrodep" in files:
            found.append(os.path.join(current_root, ".nitrodep"))
    return sorted(found)


def _read_nitrodep_entries(dep_path: str) -> list[tuple[str, str]]:
    if not os.path.isfile(dep_path):
        return []

    entries: list[tuple[str, str]] = []
    with open(dep_path) as file:
        for raw_line in file:
            line: str = raw_line.strip()
            if not line:
                continue
            parts: list[str] = line.split()
            publication: str = parsepub(parts[0]).lower()
            release: str = parts[1] if len(parts) > 1 else "latest"
            entries.append((publication, release))
    return entries


def _write_nitrodep_entries(dep_path: str, entries: list[tuple[str, str]]) -> None:
    parent: str = os.path.dirname(dep_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(dep_path, "w") as file:
        if entries:
            file.write("\n".join(f"{pub} {rel}" if rel != "latest" else pub for pub, rel in entries) + "\n")


def _add_nitrodep_dependency(path: str, pub: str, rel: str) -> bool:
    dep_path: str = _dependency_file_path(path)
    dep_key: tuple[str, str] = (parsepub(pub).lower(), rel)
    entries: list[tuple[str, str]] = _read_nitrodep_entries(dep_path)
    if dep_key in entries:
        return False
    entries.append(dep_key)
    _write_nitrodep_entries(dep_path, entries)
    return True


def _remove_nitrodep_dependency(path: str, pub: str, rel: str) -> bool:
    dep_path: str = _dependency_file_path(path)
    if not os.path.isfile(dep_path):
        return False

    dep_key: tuple[str, str] = (parsepub(pub).lower(), rel)
    entries: list[tuple[str, str]] = _read_nitrodep_entries(dep_path)
    filtered: list[tuple[str, str]] = [entry for entry in entries if entry != dep_key]
    if len(filtered) == len(entries):
        return False
    _write_nitrodep_entries(dep_path, filtered)
    return True


COMPAT_TAG: str = "#COMPAT"
# Each compat mode is pure data: a prefix plus a join strategy, so adding a new mode never
# requires touching the transform logic below - just add an entry here.
#   "dot"      -> collapse the boundary between a trailing "." on the prefix and the sub-path's
#                 leading "." into a single "." (namespace-style prefixes, e.g. "ww.", ".ww.")
#   "raw"      -> concatenate prefix and sub-path verbatim, no collapsing (every "." is
#                 meaningful, e.g. "up N levels" relative prefixes)
#   "strip"    -> drop the sub-path's own leading "." entirely (plain absolute imports)
#   "identity" -> the sub-path is already in canonical form; only the empty-path fallback is used
COMPAT_MODES: dict[str, tuple[str, str]] = {
    "abs-ww": ("ww.", "dot"),
    "abs": ("", "strip"),
    "rel": (".", "identity"),
    "rel-up1": ("..", "raw"),
    "rel-up2": ("...", "raw"),
    "rel-up3": ("....", "raw"),
    "rel-ww": (".ww.", "dot"),
    "rel-libs-ww": (".libraries.ww.", "dot"),
}
_COMPAT_LINE_RE = re.compile(r'^(\s*)from\s+(?:\.?(?:libraries\.)?)ww(\.[^\s]*|)(\s+import\s+.*)$')
_COMPAT_TAGGED_LINE_RE = re.compile(r'^(\s*)from\s+(\S+)(\s+import\s+.*)$')

def _compat_join(prefix: str, rest: str, join: str) -> str | None:
    if join == "identity":
        return rest if rest else prefix
    if join == "strip":
        sub: str = rest[1:] if rest.startswith(".") else rest
        return sub or None
    if join == "raw":
        return prefix + rest
    # join == "dot": collapse a trailing "." on the prefix with the sub-path's leading "."
    if not rest:
        return prefix[:-1] if prefix.endswith(".") else prefix
    if prefix.endswith(".") and rest.startswith("."):
        return prefix[:-1] + rest
    return prefix + rest

def _compat_new_path(mode: str, custom_phrase: str, rest: str) -> str | None:
    if mode == "custom":
        return _compat_join(custom_phrase, rest, "raw")
    config: tuple[str, str] | None = COMPAT_MODES.get(mode)
    if config is None:
        return None
    prefix, join = config
    return _compat_join(prefix, rest, join)

def _compat_rest_from_tagged_path(path: str, custom_phrase: str) -> str:
    # recover the canonical (dot-prefixed) sub-path from a path already rewritten by any mode,
    # so switching modes on a previously-tagged line works even without knowing which mode built it
    def _is_canonical(candidate: str) -> bool:
        return candidate == "" or candidate.startswith(".")

    raw_prefixes: list[str] = sorted(
        (prefix for prefix, join in COMPAT_MODES.values() if join == "raw"), key=len, reverse=True
    )
    if custom_phrase:
        raw_prefixes.insert(0, custom_phrase)
    for prefix in raw_prefixes:
        if path.startswith(prefix) and _is_canonical(path[len(prefix):]):
            return path[len(prefix):]

    dot_prefixes: list[str] = sorted(
        (prefix for prefix, join in COMPAT_MODES.values() if join == "dot"), key=len, reverse=True
    )
    for prefix in dot_prefixes:
        base: str = prefix[:-1] if prefix.endswith(".") else prefix
        if path == base:
            return ""
        if path.startswith(base + "."):
            return path[len(base):]

    if path in ("", "."):
        return ""
    return path if path.startswith(".") else "." + path

def _compat_transform_line(line: str, mode: str, custom_phrase: str) -> str | None:
    ending: str = "\n" if line.endswith("\n") else ""
    body: str = line[:-1] if ending else line
    stripped: str = body.strip()
    is_tagged: bool = stripped.endswith(COMPAT_TAG)
    if not (stripped.startswith("from ww") or is_tagged):
        return None
    working: str = body
    if working.rstrip().endswith(COMPAT_TAG):
        tag_index: int = working.rstrip().rfind(COMPAT_TAG)
        working = working[:tag_index].rstrip()

    if is_tagged:
        tagged_match: re.Match | None = _COMPAT_TAGGED_LINE_RE.match(working)
        if tagged_match is None:
            return None
        leading_ws, path, import_clause = tagged_match.group(1), tagged_match.group(2), tagged_match.group(3)
        rest: str = _compat_rest_from_tagged_path(path, custom_phrase)
    else:
        match: re.Match | None = _COMPAT_LINE_RE.match(working)
        if match is None:
            return None
        leading_ws, rest, import_clause = match.group(1), match.group(2), match.group(3)

    new_path: str | None = _compat_new_path(mode, custom_phrase, rest)
    if new_path is None:
        return None
    new_body: str = f"{leading_ws}from {new_path}{import_clause}  {COMPAT_TAG}"
    if new_body == body:
        return None
    return new_body + ending

def _iter_python_files(root: str):
    if os.path.isfile(root):
        if root.endswith(".py"):
            yield root
        return
    for dirpath, _dirnames, filenames in os.walk(root):
        for filename in filenames:
            if filename.endswith(".py"):
                yield os.path.join(dirpath, filename)

def _apply_compat(directory: str, mode: str, custom_phrase: str) -> tuple[int, int]:
    files_changed: int = 0
    lines_changed: int = 0
    for path in _iter_python_files(directory):
        with open(path) as file:
            lines: list[str] = file.readlines()
        changed: bool = False
        for i, line in enumerate(lines):
            new_line: str | None = _compat_transform_line(line, mode, custom_phrase)
            if new_line is not None:
                lines[i] = new_line
                changed = True
                lines_changed += 1
        if changed:
            with open(path, "w") as file:
                file.writelines(lines)
            files_changed += 1
    return files_changed, lines_changed


def _remove_publication_versions(install_root: str, pub: str, rel: str | None = None) -> int:
    if not os.path.isdir(install_root):
        return 0

    resolved_pub: str = parsepub(pub).lower()
    symbol: str = REVERSE_PUBLICATION_CACHE.get(resolved_pub, resolved_pub)
    prefixes: set[str] = {resolved_pub, symbol}
    deleted: int = 0

    expected_names: set[str] = set()
    if rel is not None:
        expected_names = {prefix + _release_token(rel) for prefix in prefixes}
        if rel == "latest":
            expected_names |= prefixes

    for path in os.listdir(install_root):
        full_path: str = os.path.join(install_root, path)
        if not os.path.isdir(full_path):
            continue

        path_lower: str = path.lower()
        should_delete: bool
        if rel is None:
            should_delete = any(path_lower.startswith(prefix) for prefix in prefixes)
        else:
            should_delete = path_lower in expected_names

        if should_delete:
            shutil.rmtree(full_path)
            deleted += 1

    return deleted


def _parse_installed_publication_dir(dirname: str) -> tuple[str, str] | None:
    directory_name: str = dirname.lower()
    candidates: list[tuple[str, str]] = []
    for symbol, publication in PUBLICATION_CACHE.items():
        candidates.append((symbol, publication))
    for publication in REVERSE_PUBLICATION_CACHE:
        candidates.append((publication, publication))

    seen: set[str] = set()
    ordered_candidates: list[tuple[str, str]] = []
    for prefix, publication in sorted(candidates, key=lambda item: len(item[0]), reverse=True):
        if prefix in seen:
            continue
        seen.add(prefix)
        ordered_candidates.append((prefix, publication))

    for prefix, publication in ordered_candidates:
        if not directory_name.startswith(prefix):
            continue
        suffix: str = directory_name[len(prefix):]
        if not suffix:
            return publication, "latest"
        if not all(char.isalnum() or char == "_" for char in suffix):
            continue
        release: str = suffix.replace("_", ".")
        return publication, release
    return None


def _queue_install_to_root(pub: str, rel: str, install_root: str, reinstall: bool = True, work_dir: str = ".", emit: bool = True) -> asyncio.Task:
    resolved_pub: str = parsepub(pub)
    key: tuple[str, str, str] = (resolved_pub.lower(), rel, os.path.realpath(install_root))
    if key in running_installs:
        if emit:
            _print_status("wait", f"Already queued {resolved_pub.lower()} {rel} -> {install_root}", "muted")
        return running_installs[key]

    if emit:
        _print_status("queue", f"{resolved_pub.lower()} {rel} -> {install_root}", "info")
    task: asyncio.Task = asyncio.create_task(asyncio.to_thread(_install_publication_to_root, resolved_pub, rel, install_root, reinstall, work_dir, emit))
    running_installs[key] = task

    def cleanup(completed_task: asyncio.Task, install_key: tuple[str, str, str] = key) -> None:
        if running_installs.get(install_key) is completed_task:
            running_installs.pop(install_key, None)

    task.add_done_callback(cleanup)
    return task


async def _reinstall_project_libraries(project: str) -> None:
    install_root: str = os.path.join(project, "libraries", "ww")
    if not os.path.isdir(install_root):
        _print_status("miss", f"No library directory found at '{install_root}'.", "warning")
        raise SystemExit(1)

    entries: list[str] = [item for item in os.listdir(install_root) if os.path.isdir(os.path.join(install_root, item))]
    if not entries:
        _print_status("info", f"No installed libraries found in '{install_root}'.", "muted")
        return

    tasks: list[asyncio.Task] = []
    ignored: int = 0
    for entry in entries:
        parsed: tuple[str, str] | None = _parse_installed_publication_dir(entry)
        if parsed is None:
            ignored += 1
            _print_status("skip", f"Could not parse installed library directory '{entry}'.", "warning")
            continue
        pub, rel = parsed
        tasks.append(_queue_install_to_root(pub, rel, install_root, True))

    if not tasks:
        _print_status("miss", "No reinstallable libraries were found.", "warning")
        if ignored:
            _print_status("info", f"Ignored {ignored} unrecognized directory(ies).", "muted")
        return

    results: list[InstallResult] = await asyncio.gather(*tasks)
    failures: int = 0
    for result in results:
        _print_install_result(result)
        failures += int(bool(result.exit_code))
    if failures:
        _print_status("fail", f"Library reinstall finished with {failures} failure{'s' if failures != 1 else ''}.", "error")
        raise SystemExit(1)

    _print_status("done", f"Reinstalled {len(results)} librar{'y' if len(results) == 1 else 'ies'} from {install_root}.", "success")

def _install_publication(pub: str, rel: str, reinstall: bool = True) -> InstallResult:
    return _install_publication_to_root(pub, rel, "ww", reinstall)

def _install_publication_to_root(pub: str, rel: str, install_root: str, reinstall: bool = True, work_dir: str = ".", emit: bool = True) -> InstallResult:
    pub = parsepub(pub)
    pub_lower: str = pub.lower()
    dirname: str = os.path.join(install_root, _publication_leaf(pub, rel))
    release_token: str = _release_token(rel)
    archive_path: str = os.path.join(work_dir, f"{pub_lower}-{release_token}.zip")
    extract_dir: str = os.path.join(work_dir, f"{pub_lower}-repo-{release_token}")
    url: str = f"https://github.com/Wednesware/{pub.capitalize()}/archive/refs/heads/main.zip" if rel == "beta" else f"https://github.com/Wednesware/{pub.capitalize()}/releases/{rel + '/download' if rel == 'latest' else 'download/' + rel}/{pub_lower}.zip"
    try:
        if os.path.exists(dirname) and not reinstall:
            if emit:
                _print_status("info", f"{pub_lower} {rel}: Publication is already installed.", "muted")
            return InstallResult("info", [f"{pub_lower} {rel}: Publication is already installed."])
        os.makedirs(work_dir, exist_ok=True)
        try:
            urlretrieve(
                url,
                archive_path,
            )
        except urllib.error.HTTPError:
            return InstallResult(
                "error",
                [f"{pub_lower} {rel}: Could not find this release. Are you sure you spelled it right?"],
                1,
            )

        with zipfile.ZipFile(archive_path, "r") as zip_ref:
            zip_ref.extractall(extract_dir)
        os.makedirs(install_root, exist_ok=True)
        if os.path.exists(dirname):
            shutil.rmtree(dirname)

        source_root: str = next(os.scandir(extract_dir)).name
        shutil.move(os.path.join(extract_dir, source_root, pub_lower), dirname)
        if emit:
            _print_status("done", f"{pub_lower} {rel}: Installation complete!", "success")
        return InstallResult("success", [f"{pub_lower} {rel}: Installation complete!"])
    except Exception:
        return InstallResult(
            "error",
            [line for line in traceback.format_exc().split("\n") if line.strip()],
            1,
        )
    finally:
        if os.path.exists(extract_dir):
            shutil.rmtree(extract_dir)
        if os.path.exists(archive_path):
            os.remove(archive_path)


def _queue_install(pub: str, rel: str, reinstall: bool = True, install_root: str = "ww", work_dir: str = ".", emit: bool = True) -> asyncio.Task:
    return _queue_install_to_root(pub, rel, install_root, reinstall, work_dir, emit)


async def install_async(pub: str, rel: str, reinstall: bool = True, color: bool = True, emit: bool = True, fatal: bool = True, install_root: str = "ww", work_dir: str = ".") -> InstallResult:
    result: InstallResult = await _queue_install(pub, rel, reinstall, install_root, work_dir, emit)
    if emit:
        _print_install_result(result, color)
    if fatal and result.exit_code:
        raise SystemExit(result.exit_code)
    return result


async def _getdep_recursive(path: str, color: bool = True, log: bool = True, visited: set[str] | None = None, installed: set[tuple[str, str]] | None = None, force: bool = False, install_root: str = "ww", work_dir: str = ".") -> None:
    dep_path: str = _dependency_file_path(path)
    if visited is None:
        visited = set()
    if installed is None:
        installed = set()
    resolved_path: str = os.path.realpath(dep_path)
    if resolved_path in visited:
        return
    visited.add(resolved_path)

    if not os.path.isfile(dep_path):
        _print_status("miss", f"No dependency file found at '{dep_path}'", "warning")
        return
    with open(dep_path) as file:
        content: str = file.read()
    deps: list[tuple[str, str]] = [(line.split()[0].strip(), line.split(maxsplit=1)[1].strip() if len(line.split(maxsplit=1)) > 1 else "latest") for line in content.split("\n") if line.strip() and not line.strip().startswith("//")]
    if not deps:
        if log:
            _print_status("done", "No dependencies needed.", "success")
        return
    if log:
        _print_status("deps", f"Loaded {len(deps)} dependenc{'y' if len(deps) == 1 else 'ies'} from {dep_path}", "info")
    pending_deps: list[tuple[str, str]] = []
    scripts_allowed: bool = "allow" if "--allow" in sys.argv else ("skip" if "--skip" in sys.argv else "deny")
    print_tip: bool = False
    for pub, rel in deps:
        dep_key: tuple[str, str] = (parsepub(pub).lower(), rel)
        if dep_key in installed:
            continue
        if pub.lower().startswith("script:"):
            if scripts_allowed == "allow":
                _print_status("script", f"Executing script dependency: {pub} {rel}", "info")
                script_path: str = pub[len("script:"):]
                if not os.path.isfile(script_path):
                    _print_status("fail", f"Script file '{script_path}' not found.", "error")
                    raise SystemExit(1)
                try:
                    with open(script_path) as script_file:
                        script_content: str = script_file.read()
                    exec(script_content, {"__name__": "__main__"})
                except Exception:
                    _print_status("fail", f"Error executing script '{script_path}':\n{traceback.format_exc()}", "error")
                    raise SystemExit(1)
            elif scripts_allowed == "skip":
                _print_status("skip", f"Skipping script dependency: {pub} {rel}", "muted")
            else:
                _print_status("deny", f"Script dependency '{pub}' is not allowed. Use '--allow' to allow or '--skip' to skip.", "error")
                raise SystemExit(1)
            continue
        installed.add(dep_key)
        pending_deps.append((pub, rel))
    if print_tip:
        _print_status("deny", "To allow scripts, re-run with '--allow'. To skip scripts, re-run with '--skip'.", "info")
    tasks: list[asyncio.Task] = [_queue_install(pub, rel, (rel == "latest") or force, install_root, work_dir) for pub, rel in pending_deps]
    results: list[InstallResult] = await asyncio.gather(*tasks)
    for result in results:
        _print_install_result(result, color)

    failures: int = sum(1 for result in results if result.exit_code)
    if failures:
        if log:
            _print_status("fail", f"Dependency install finished with {failures} failure{'s' if failures != 1 else ''}.", "error")
        raise SystemExit(1)

    for pub, rel in deps:
        installed_dep_path: str = _dependency_file_path(_publication_dirname(parsepub(pub), rel, install_root))
        await _getdep_recursive(installed_dep_path, color=color, log=False, visited=visited, installed=installed, install_root=install_root, work_dir=work_dir)
    if log:
        _print_status("done", "All dependencies are ready.", "success")
                
async def getdep(path: str, color: bool = True, log: bool = True, force: bool = False, install_root: str = "ww", work_dir: str = ".") -> None:
    await _getdep_recursive(path, color=color, log=log, force=force, install_root=install_root, work_dir=work_dir)


async def getdep_everywhere(path: str, color: bool = True, force: bool = False, install_root: str = "ww", work_dir: str = ".") -> None:
    dep_files: list[str] = _find_nitrodep_files(path)
    if not dep_files:
        _print_status("miss", f"No .nitrodep files found under '{path}'.", "warning")
        return

    _print_status("deps", f"Found {len(dep_files)} .nitrodep file{'s' if len(dep_files) != 1 else ''} under '{path}'.", "info")
    visited: set[str] = set()
    installed: set[tuple[str, str]] = set()
    for dep_file in dep_files:
        await _getdep_recursive(dep_file, color=color, log=True, visited=visited, installed=installed, force=force, install_root=install_root, work_dir=work_dir)


async def _install_subdependencies(pub: str, rel: str, color: bool = True, install_root: str = "ww", work_dir: str = ".", emit: bool = True) -> None:
    resolved_pub: str = parsepub(pub)
    dep_path: str = _dependency_file_path(_publication_dirname(resolved_pub, rel, install_root))
    if emit:
        _print_status("deps", f"Checking sub-dependencies for {resolved_pub.lower()} {rel}", "info")
    if not os.path.isfile(dep_path):
        if emit:
            _print_status("info", "No sub-dependencies declared.", "muted")
        return
    await getdep(dep_path, color=color, log=emit, install_root=install_root, work_dir=work_dir)
    if emit:
        _print_status("done", f"Sub-dependencies for {resolved_pub.lower()} {rel} are ready.", "success")
        
def trust(ext_filename: str, ext_dir_path: str) -> None:
    ext_path: str = os.path.join(EXTENSIONS_DIR, ext_filename)
    if not os.path.exists(ext_path):
        print(f"\033[91mExtension '{ext_filename}' not found and cannot be trusted.")
        return
    with open(TRUSTED_EXTENSIONS_FILE) as file:
        content: str = file.read()
    if ext_filename not in content:
        try:
            if input(f"\033[38;5;208m/!\\ WARNING: You are running this extension for the first time.\n    Make sure to review the contents of\n      \033[0;1;3m{ext_dir_path}\033[0;38;5;208m\n    before running.\n    Trust extension and run command? (y/N) \033[0m").strip().lower() in ["y", "yes", "yeah", "true", "t"]:
                with open(TRUSTED_EXTENSIONS_FILE, "a") as file:
                    file.write(f"{ext_filename}\n")
            else:
                raise KeyboardInterrupt
        except (KeyboardInterrupt, EOFError):
            print("\n\033[91m    Extension not trusted. Aborting.\033[0m")
            sys.exit(0)
            
def load_len() -> None:
    try:
        if os.path.exists(LEN_PATH):
            unload_len()
        _print_status("sync", "Loading LEN from GitHub...", "info")
        proc = subprocess.Popen(
            [
                "git",
                "clone",
                "--progress",
                "https://github.com/Wednesware/LEN.git",
                LEN_PATH,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )

        for line in proc.stdout:
            print(_cli(f"  {line.rstrip()}", CLI_DIM))
        if proc.returncode != 0 and proc.returncode is not None:
            raise subprocess.CalledProcessError(proc.returncode, proc.args)
        proc.wait()
        _print_status("done", "LEN loaded successfully.", "success")
    except subprocess.CalledProcessError:
        _print_status("fail", "Could not load LEN from GitHub. Are you sure you have an internet connection?", "error")
        sys.exit(1)
        
def unload_len() -> None:
    if os.path.exists(LEN_PATH):
        shutil.rmtree(LEN_PATH)
        _print_status("done", "LEN unloaded.", "success")
    else:
        _print_status("info", "LEN is not loaded.", "muted")

async def build(format: str, source_path: str = ".", output_path: str = "build.%") -> None:
    _print_status("build", "Preparing build...", "info")
    try:
        output_path = output_path.replace("%", {
            "zip": "zip",
            "targz": "tar.gz",
            "n2x": "n2x",
            "modm": "modm"
        }[format])
    except KeyError:
        _print_status("fail", f"Unknown build format '{format}'.", "error")
        return
    if not os.path.isdir(source_path):
        _print_status("fail", f"Source path '{source_path}' does not exist or is not a directory.", "error")
        return
    source_abs: str = os.path.abspath(source_path)
    output_abs: str = os.path.abspath(output_path)
    output_dir: str = os.path.dirname(output_abs)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    def should_skip(path: str) -> bool:
        return os.path.abspath(path) == output_abs

    match format:
        case "zip":
            _print_status("build", f"Building project into {output_path}...", "info")
            with zipfile.ZipFile(output_abs, "w", zipfile.ZIP_DEFLATED) as zipf:
                for root, dirs, files in os.walk(source_abs):
                    for file in files:
                        file_path = os.path.join(root, file)
                        if should_skip(file_path):
                            continue
                        arcname = os.path.relpath(file_path, source_abs)
                        _print_status("pack", f"Packing {arcname}", "info")
                        zipf.write(file_path, arcname)
            _print_status("done", f"Build complete in {output_path}", "success")
        case "targz":
            _print_status("build", f"Building project into {output_path}...", "info")
            with tarfile.open(output_abs, "w:gz") as tar:
                for root, dirs, files in os.walk(source_abs):
                    for file in files:
                        file_path = os.path.join(root, file)
                        if should_skip(file_path):
                            continue
                        arcname = os.path.relpath(file_path, source_abs)
                        _print_status("pack", f"Packing {arcname}", "info")
                        tar.add(file_path, arcname=arcname)
            _print_status("done", f"Build complete in {output_path}", "success")
        case "n2x":
            _print_status("build", f"Building project into {output_path}...", "info")
            required_files = ["ext.py", "README.md", "LICENSE.md", ".nitrodep"]
            with tarfile.open(output_abs, "w:gz") as tar:
                for file in required_files:
                    file_path = os.path.join(source_abs, file)
                    _print_status("pack", f"Packing {file}", "info")
                    if not os.path.isfile(file_path):
                        _print_status("fail", f"Required file for build not found: '{file}'", "error")
                        return
                    tar.add(file_path, arcname=file)
            _print_status("done", f"Build complete in {output_path}", "success")
        case "modm":
            _print_status("build", f"Building project into {output_path}...", "info")
            with tarfile.open(output_abs, "w:gz") as tar:
                for root, dirs, files in os.walk(source_abs):
                    for file in files:
                        file_path = os.path.join(root, file)
                        if should_skip(file_path):
                            continue
                        arcname = os.path.relpath(file_path, source_abs)
                        _print_status("pack", f"Packing {arcname}", "info")
                        tar.add(file_path, arcname=arcname)
            _print_status("done", f"Build complete in {output_path}", "success")
        case _:
            _print_status("fail", f"Unknown build format '{format}'.", "error")

async def main() -> None:
    if len(sys.argv) == 1:
        print(_cli(f"Nitrogen v{VERSION}", CLI_INFO, bold=True))
        print(_cli("Fast installer for Wednesware publications.", CLI_DIM))
        print()
        print("Usage: n2 <command> [args]")
        print(f"Run {_cli('n2 help', CLI_INFO)} for a full command list.")
        sys.exit(0)

    if not os.path.exists(EXTENSIONS_DIR):
        os.makedirs(EXTENSIONS_DIR)
    if not os.path.exists(TRUSTED_EXTENSIONS_FILE):
        with open(TRUSTED_EXTENSIONS_FILE, "w") as file:
            file.write("")

    if len(sys.argv) == 1:
        print(_cli(f"Nitrogen v{VERSION}", CLI_INFO, bold=True))
        print(_cli("Fast installer for Wednesware publications.", CLI_DIM))
        print()
        print("Usage: n2 <command> [args]")
        print(f"Run {_cli('n2 help', CLI_INFO)} for a full command list.")
        sys.exit(0)

    match sys.argv[1]:
        case "get":
            if len(sys.argv) == 2:
                _print_status("help", "Usage: n2 get <publication> [release]", "warning")
                sys.exit(1)
            pub: str = sys.argv[2]
            rel: str = sys.argv[3] if len(sys.argv) > 3 else "latest"
            result: InstallResult = await install_async(pub, rel)
            if not result.exit_code:
                await _install_subdependencies(pub, rel)
        case "getlib":
            if len(sys.argv) < 4:
                _print_status("help", "Usage: n2 getlib <project> <publication> [release]", "warning")
                sys.exit(1)
            project: str = sys.argv[2]
            pub = sys.argv[3]
            rel = sys.argv[4] if len(sys.argv) > 4 else "latest"
            install_root: str = os.path.join(project, "libraries", "ww")
            result = await _queue_install_to_root(pub, rel, install_root, True)
            _print_install_result(result)
            if result.exit_code:
                raise SystemExit(result.exit_code)
        case "rm":
            if len(sys.argv) == 2:
                _print_status("help", "Usage: n2 rm <publication> [release]", "warning")
                sys.exit(1)
            pub: str = parsepub(sys.argv[2])
            _print_status("rm", f"Deleting {pub}", "info")
            if pub.strip() == "all":
                if os.path.exists("ww"):
                    shutil.rmtree("ww")
                else:
                    _print_status("info", "No publications installed.", "muted")
            elif pub in PUBLICATION_CACHE or pub in REVERSE_PUBLICATION_CACHE:
                if len(sys.argv) > 3:
                    rel: str = sys.argv[3]
                    deleted: int = _remove_publication_versions("ww", pub, rel)
                    if deleted:
                        _print_status("done", "Operation complete.", "success")
                    else:
                        _print_status("miss", f"Release '{rel}' of publication '{pub.capitalize()}' is not installed here. Are you sure you spelled it right?", "warning")
                else:
                    deleted: int = _remove_publication_versions("ww", pub)
                    if deleted:
                        _print_status("done", "Operation complete.", "success")
                    else:
                        _print_status("miss", f"Publication '{pub.capitalize()}' is not installed here. Are you sure you spelled it right?", "warning")
            else:
                _print_status("miss", f"Could not find publication '{pub.capitalize()}'. Are you sure you spelled it right?", "warning")
        case "install":
            if len(sys.argv) == 2:
                _print_status("help", "Usage: n2 install <path> [--name <command>] [--bin <dir>] [--no-deps]", "warning")
                sys.exit(1)
            args = sys.argv[2:]
            path = args[0]
            command_name = None
            bin_dir = None
            no_deps = False
            for index in range(1, len(args)):
                if args[index] == "--name" and index + 1 < len(args):
                    command_name = args[index + 1]
                elif args[index] == "--bin" and index + 1 < len(args):
                    bin_dir = args[index + 1]
                elif args[index] == "--no-deps":
                    no_deps = True
            try:
                result = install_target(path, bin_dir=bin_dir, command_name=command_name, no_deps=no_deps)
                _print_status("done", f"Installed command '{result['command_name']}'", "success")
                _print_status("info", f"Target: {result['target']}", "info")
                _print_status("info", f"Bin: {result['bin_path']}", "info")
                _print_status("info", "You can run it directly from the shell now.", "info")
                sys.exit(0)
            except (FileNotFoundError, ValueError, RuntimeError) as exc:
                _print_status("fail", str(exc), "error")
                sys.exit(1)
        case "uninstall":
            if len(sys.argv) == 2:
                _print_status("help", "Usage: n2 uninstall <command> [--bin <dir>]", "warning")
                sys.exit(1)
            args = sys.argv[2:]
            command_name = args[0]
            bin_dir = None
            for index in range(1, len(args)):
                if args[index] == "--bin" and index + 1 < len(args):
                    bin_dir = args[index + 1]
            result = uninstall_target(command_name, bin_dir=bin_dir)
            if result["removed"]:
                _print_status("done", f"Removed command '{command_name}' from {result['bin_dir']}", "success")
                sys.exit(0)
            _print_status("fail", result.get("reason", f"No Nitrogen-managed command '{command_name}' found."), "error")
            sys.exit(1)
        case "getdep":
            path: str = sys.argv[2] if len(sys.argv) > 2 else "."
            await getdep_everywhere(path)
        case "forcegetdep":
            path: str = sys.argv[2] if len(sys.argv) > 2 else "."
            await getdep_everywhere(path, force=True)
        case "updlibs":
            if len(sys.argv) < 3:
                _print_status("help", "Usage: n2 updlibs <project>", "warning")
                sys.exit(1)
            await _reinstall_project_libraries(sys.argv[2])
        case "getinternal":
            if len(sys.argv) == 2:
                _print_status("help", "Usage: n2 getinternal <publication> [release]", "warning")
                sys.exit(1)
            pub = sys.argv[2]
            rel = sys.argv[3] if len(sys.argv) > 3 else "latest"
            result = await install_async(pub, rel, install_root=INTERNAL_WW_DIR, work_dir=INTERNAL_TEMP_DIR)
            if not result.exit_code:
                await _install_subdependencies(pub, rel, install_root=INTERNAL_WW_DIR, work_dir=INTERNAL_TEMP_DIR)
        case "rminternal":
            if len(sys.argv) == 2:
                _print_status("help", "Usage: n2 rminternal <publication> [release]", "warning")
                sys.exit(1)
            pub = parsepub(sys.argv[2])
            _print_status("rm", f"Deleting {pub}", "info")
            if pub.strip() == "all":
                if os.path.isdir(INTERNAL_WW_DIR):
                    for entry in os.listdir(INTERNAL_WW_DIR):
                        if entry in ("len", "temp"):
                            continue
                        entry_path: str = os.path.join(INTERNAL_WW_DIR, entry)
                        if os.path.isdir(entry_path):
                            shutil.rmtree(entry_path)
                        else:
                            os.remove(entry_path)
                else:
                    _print_status("info", "No publications installed.", "muted")
            elif pub in PUBLICATION_CACHE or pub in REVERSE_PUBLICATION_CACHE:
                if len(sys.argv) > 3:
                    rel = sys.argv[3]
                    deleted = _remove_publication_versions(INTERNAL_WW_DIR, pub, rel)
                    if deleted:
                        _print_status("done", "Operation complete.", "success")
                    else:
                        _print_status("miss", f"Release '{rel}' of publication '{pub.capitalize()}' is not installed here. Are you sure you spelled it right?", "warning")
                else:
                    deleted = _remove_publication_versions(INTERNAL_WW_DIR, pub)
                    if deleted:
                        _print_status("done", "Operation complete.", "success")
                    else:
                        _print_status("miss", f"Publication '{pub.capitalize()}' is not installed here. Are you sure you spelled it right?", "warning")
            else:
                _print_status("miss", f"Could not find publication '{pub.capitalize()}'. Are you sure you spelled it right?", "warning")
        case "getdepinternal":
            path = sys.argv[2] if len(sys.argv) > 2 else "."
            await getdep_everywhere(path, install_root=INTERNAL_WW_DIR, work_dir=INTERNAL_TEMP_DIR)
        case "compat":
            if len(sys.argv) < 4:
                _print_status("help", "Usage: n2 compat <mode(abs|rel|rel-up1|rel-up2|rel-up3|abs-ww|rel-ww|rel-libs-ww|custom)> <publication|directory> [custom-phrase]", "warning")
                sys.exit(1)
            compat_target: str = sys.argv[3]
            compat_mode: str = sys.argv[2]
            if compat_mode not in COMPAT_MODES and compat_mode != "custom":
                _print_status("help", "Usage: n2 compat <mode(abs|rel|rel-up1|rel-up2|rel-up3|abs-ww|rel-ww|rel-libs-ww|custom)> <publication|directory> [custom-phrase]", "warning")
                sys.exit(1)
            compat_custom_phrase: str = ""
            if compat_mode == "custom":
                if len(sys.argv) < 5:
                    _print_status("help", "Usage: n2 compat custom <publication|directory> <custom-phrase>", "warning")
                    sys.exit(1)
                compat_custom_phrase = sys.argv[4]

            compat_dirs: list[str]
            if "/" in compat_target:
                compat_dirs = [compat_target]
            else:
                compat_pub: str = parsepub(compat_target).lower()
                compat_symbol: str = REVERSE_PUBLICATION_CACHE.get(compat_pub, compat_pub)
                compat_prefixes: set[str] = {compat_pub, compat_symbol}
                compat_dirs = []
                if os.path.isdir("ww"):
                    compat_dirs = [
                        os.path.join("ww", name) for name in os.listdir("ww")
                        if os.path.isdir(os.path.join("ww", name)) and any(name.lower().startswith(prefix) for prefix in compat_prefixes)
                    ]

            compat_dirs = [directory for directory in compat_dirs if os.path.exists(directory)]
            if not compat_dirs:
                _print_status("miss", f"Could not find any installed directories for '{compat_target}'.", "warning")
                sys.exit(1)

            compat_total_files: int = 0
            compat_total_lines: int = 0
            for compat_dir in compat_dirs:
                files_changed, lines_changed = _apply_compat(compat_dir, compat_mode, compat_custom_phrase)
                compat_total_files += files_changed
                compat_total_lines += lines_changed
            _print_status("done", f"Updated {compat_total_lines} line{'s' if compat_total_lines != 1 else ''} across {compat_total_files} file{'s' if compat_total_files != 1 else ''}.", "success")
        case "build":
            if len(sys.argv) == 2:
                _print_status("help", "Usage: n2 build <format(zip|targz|n2x|modm)> [source path] [output path]", "warning")
                sys.exit(1)
            await build(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else ".", sys.argv[4] if len(sys.argv) > 4 else "build.%")
        case "readme":
            if len(sys.argv) == 2:
                with open(os.path.join(os.path.dirname(__file__), "README.md")) as file:
                    print(file.read())
                sys.exit(0)
            ext_path: str = sys.argv[2] + ".n2x"
            with zipfile.ZipFile(os.path.join(EXTENSIONS_DIR, ext_path), "r") as zip_ref:
                zip_ref.extractall(ext_path.replace('.', '-'))
            with open(os.path.join(ext_path.replace('.', '-'), "README.md")) as file:
                print(file.read())
        case "license":
            if len(sys.argv) == 2:
                with open(os.path.join(os.path.dirname(__file__), "LICENSE.md")) as file:
                    print(file.read())
                sys.exit(0)
            ext_path: str = sys.argv[2] + ".n2x"
            with zipfile.ZipFile(os.path.join(EXTENSIONS_DIR, ext_path), "r") as zip_ref:
                zip_ref.extractall(ext_path.replace('.', '-'))
            with open(os.path.join(ext_path.replace('.', '-'), "LICENSE.md")) as file:
                print(file.read())
        case "trust-ext":
            if len(sys.argv) == 2:
                _print_status("help", "Usage: n2 trust-ext <extension>", "warning")
                sys.exit(1)
            ext_filename: str = sys.argv[2] + ".n2x"
            ext_path: str = os.path.join(EXTENSIONS_DIR, ext_filename)
            ext_dir_path: str = ext_path.replace('.', '-')
            trust(ext_filename, ext_dir_path)
        case "untrust-ext":
            if len(sys.argv) == 2:
                _print_status("help", "Usage: n2 untrust-ext <extension>", "warning")
                sys.exit(1)
            ext_filename: str = sys.argv[2] + ".n2x"
            with open(TRUSTED_EXTENSIONS_FILE) as file:
                content: str = file.read()
            with open(TRUSTED_EXTENSIONS_FILE, "w") as file:
                file.write("\n".join([line for line in content.split("\n") if line.strip() != ext_filename]))
        case "list-ext":
            _print_installed_extensions()
        case "load-len":
            load_len()
        case "unload-len":
            unload_len()
        case "install-ext":
            if len(sys.argv) == 2:
                _print_status("help", "Usage: n2 install-ext <extension>", "warning")
                sys.exit(1)
            load_len()
            install_ext_filename: str = sys.argv[2] if sys.argv[2].endswith(".n2x") else sys.argv[2] + ".n2x"
            if os.path.exists(os.path.join(LEN_PATH, install_ext_filename)):
                shutil.copy(os.path.join(LEN_PATH, install_ext_filename), EXTENSIONS_DIR)
                _print_status("done", f"Extension '{sys.argv[2]}' installed successfully.", "success")
            else:
                _print_status("miss", f"Extension '{sys.argv[2]}' not found in the LEN repository.", "warning")
        case "uninstall-ext":
            if len(sys.argv) == 2:
                _print_status("help", "Usage: n2 uninstall-ext <extension>", "warning")
                sys.exit(1)
            ext_filename: str = sys.argv[2] + ".n2x" if not sys.argv[2].endswith(".n2x") else sys.argv[2]
            ext_path: str = os.path.join(EXTENSIONS_DIR, ext_filename)
            if os.path.exists(ext_path):
                os.remove(ext_path)
                _print_status("done", f"Extension '{sys.argv[2]}' uninstalled successfully.", "success")
            else:
                _print_status("miss", f"Extension '{sys.argv[2]}' not installed.", "warning")
        case "list-len":
            load_len()
            _print_len_extensions()
        case "help":
            _print_help()
            print()
            _print_extension_commands()
        case _:
            for ext_filename2 in [item for item in os.listdir(EXTENSIONS_DIR) if item.endswith(".n2x") or item.endswith(".n2xp")]:
                ext_path2: str = os.path.join(EXTENSIONS_DIR, ext_filename2)
                for ext_filename in [item for item in os.listdir(ext_path2) if item.endswith(".n2x")] if ext_filename2.endswith(".n2xp") else [ext_filename2]:
                    try:
                        if sys.argv[1] == ext_filename.removesuffix(".n2x"):
                            ext_path: str = os.path.join(EXTENSIONS_DIR, ext_filename)
                            ext_dir_path: str = ext_path.replace('.', '-')
                            with tarfile.open(ext_path, "r:gz") as tar:
                                tar.extractall(ext_dir_path)
                            trust(ext_filename, ext_dir_path)
                            script_path: str = os.path.join(ext_dir_path, "ext.py")
                            nitrodep_path: str = os.path.join(ext_dir_path, ".nitrodep")
                            if os.path.exists(nitrodep_path):
                                print("\033[94m", end="", flush=True)
                                await getdep(nitrodep_path, log=False)
                                print("\033[0m", end="", flush=True)
                            subprocess.run(["python", script_path, *sys.argv[2:]])
                            if os.path.exists(ext_dir_path):
                                shutil.rmtree(ext_dir_path)
                            if os.path.exists("ww"):
                                shutil.rmtree("ww")
                            return
                    except Exception:
                        for line in traceback.format_exc().split("\n"):
                            if line.strip():
                                print(_cli(f"  {line}", CLI_ERROR))
            _print_status("miss", f"Unknown command: {sys.argv[1]}", "warning")
            print(f"Run {_cli('n2 help', CLI_INFO)} for a list of commands.")
            
async def require_async(pub: str, rel: str | None = None) -> None:
    pub, submodule = [pub, None] if len(pub.split(".", 1)) == 1 else pub.split(".", 1)
    pub = PUBLICATION_CACHE.get(pub, pub)
    rel = rel or "latest"
    result: InstallResult = await install_async(pub, rel, reinstall=False, emit=False)
    if not result.exit_code:
        await _install_subdependencies(pub, rel, emit=False)
    return importlib.import_module(f"ww.{REVERSE_PUBLICATION_CACHE[pub]}{rel if rel != 'latest' else ''}{'.' + submodule if submodule else ''}")

def require(pub: str, rel: str | None = None) -> None:
    return asyncio.run(require_async(pub, rel))
            
def entrypoint() -> None:
    asyncio.run(main())
    
if __name__ == "__main__":
    entrypoint()