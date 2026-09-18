import sys, zipfile, shutil, os, urllib.error, subprocess, traceback, asyncio, re, importlib.util, json, sysconfig, platform, threading
from dataclasses import dataclass
from urllib.request import urlretrieve


VERSION: str = "26.59"


class NitrogenDependencyError(RuntimeError):
    """Raised when a publication cannot be loaded from the local cache and cannot be downloaded."""


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
    "pd": "palladium",
    "ra": "radium",
    "rn": "radon"
}
REVERSE_PUBLICATION_CACHE: dict[str, str] = {v: k for k, v in PUBLICATION_CACHE.items()}
# "internal" installs live inside the nitrogen package itself (not the cwd), so commands like
INTERNAL_WW_DIR: str = os.path.join(os.path.dirname(__file__), "ww")
INTERNAL_TEMP_DIR: str = os.path.join(os.path.dirname(__file__), "temp")

running_installs: dict[tuple[str, str, str], asyncio.Task] = {}

def _default_bin_dir() -> str:
    user_home = os.path.expanduser("~")
    candidates: list[str] = []
    if os.name == "nt":
        candidates.extend([
            os.path.join(user_home, "bin"),
            os.path.join(user_home, "AppData", "Local", "Programs", "Python", "Scripts"),
            os.path.join(user_home, "AppData", "Roaming", "Python", "Scripts"),
        ])
    else:
        candidates.extend([
            os.path.join(user_home, ".local", "bin"),
            os.path.join(sys.prefix, "bin"),
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
    root_abs = os.path.abspath(root)
    parent_abs = os.path.dirname(root_abs)
    entries: list[str] = []
    for candidate in (parent_abs, root_abs):
        if candidate and candidate not in entries:
            entries.append(candidate)
    for relative in ("ww", "libraries", os.path.join("libraries", "ww")):
        candidate = os.path.join(root_abs, relative)
        if os.path.isdir(candidate) and candidate not in entries:
            entries.append(candidate)
    for relative in ("ww", "libraries", os.path.join("libraries", "ww")):
        candidate = os.path.join(parent_abs, relative)
        if os.path.isdir(candidate) and candidate not in entries:
            entries.append(candidate)
    return entries


def _module_name_from_root(root: str) -> str | None:
    package_init = os.path.join(root, "__init__.py")
    if os.path.isfile(package_init):
        package_name = os.path.basename(root)
        normalized = package_name.replace("-", "_").replace(".", "_")
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", normalized):
            return normalized
    return None


def _write_bin_script(bin_dir: str, command_name: str, target: str, root: str, module_name: str | None = None) -> str:
    os.makedirs(bin_dir, exist_ok=True)
    script_path = os.path.join(bin_dir, command_name)
    run_target = target
    if module_name:
        run_target = f"-m {module_name}"

    if os.name == "nt":
        script_path += ".cmd"
        pythonpath = os.pathsep.join(_as_path_list(root))
        script_content = (
            "@echo off\r\n"
            "setlocal\r\n"
            "rem nitropkg-managed\r\n"
            f"rem nitropkg-root={root}\r\n"
            f"set \"PYTHONPATH={pythonpath};%PYTHONPATH%\"\r\n"
            f'"{sys.executable}" {run_target} %*\r\n'
        )
        with open(script_path, "w", encoding="utf-8", newline="") as handle:
            handle.write(script_content)
        return script_path

    script_content = "#!/usr/bin/env sh\n"
    script_content += "set -eu\n"
    script_content += "# nitropkg-managed\n"
    script_content += f"# nitropkg-root={root}\n"
    script_content += f"export PYTHONPATH='{os.pathsep.join(_as_path_list(root))}:$PYTHONPATH'\n"
    script_content += f'exec "{sys.executable}" {run_target} "$@"\n'
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
    module_name = _module_name_from_root(pkg_dir)
    script_path = _write_bin_script(target_bin_dir, resolved_name, target, pkg_dir, module_name=module_name)

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


def install_cached_publication(pub: str, rel: str = "latest", *, bin_dir: str | None = None, command_name: str | None = None, cache_root: str | None = None) -> dict:
    resolved_pub = parsepub(pub)
    target_root = cache_root or INTERNAL_WW_DIR
    publication_dir = os.path.join(target_root, _publication_leaf(resolved_pub, rel))
    if not os.path.isdir(publication_dir):
        raise FileNotFoundError(f"Publication '{resolved_pub}' release '{rel}' is not installed in the internal cache at '{publication_dir}'.")

    candidates = [
        os.path.join(publication_dir, "__main__.py"),
        os.path.join(publication_dir, "main.py"),
        os.path.join(publication_dir, "app.py"),
        os.path.join(publication_dir, "run.py"),
    ]
    target = next((candidate for candidate in candidates if os.path.isfile(candidate)), None)
    if target is None:
        raise ValueError(f"No executable entry point was found for cached publication '{resolved_pub}' release '{rel}' in '{publication_dir}'.")

    resolved_name = command_name or resolved_pub.lower()
    target_bin_dir = bin_dir or _default_bin_dir()
    script_path = _write_bin_script(target_bin_dir, resolved_name, target, publication_dir)
    return {
        "command_name": resolved_name,
        "publication": resolved_pub,
        "release": rel,
        "source_path": publication_dir,
        "root": publication_dir,
        "target": target,
        "bin_dir": os.path.abspath(target_bin_dir),
        "bin_path": os.path.abspath(script_path),
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
    print(_cli(" Fast installer for Wednesware publications.", CLI_DIM))
    print()
    _print_section("Usage")
    print("  n2 <command> [args]")
    print()
    _print_section("General")
    _print_command("get <publication> [release]", "Download a Wednesware publication from GitHub.")
    _print_command("rm <publication> [release]", "Delete one release or all installed releases for a publication.")
    _print_command("install <path> [--name <command>] [--bin <dir>] [--no-deps]", "Install a Nitrogen package from a local directory.")
    _print_command("install-cache <publication> [release] [--name <command>] [--bin <dir>]", "Install a cached publication from the Nitrogen internal cache as a command.")
    _print_command("uninstall <command> [--bin <dir>]", "Uninstall a Nitrogen package by its command name.")
    print()
    _print_section("Documentation")
    _print_command("readme", "Show the Nitrogen README.")
    _print_command("license", "Show the Nitrogen license.")
    _print_command("help", "Show this help message.")

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


def _queue_install_to_root(pub: str, rel: str, install_root: str, reinstall: bool = True, work_dir: str = ".", emit: bool = True, error: bool = False) -> asyncio.Task:
    resolved_pub: str = parsepub(pub)
    key: tuple[str, str, str] = (resolved_pub.lower(), rel, os.path.realpath(install_root))
    if key in running_installs:
        if emit:
            _print_status("wait", f"Already queued {resolved_pub.lower()} {rel} -> {install_root}", "muted")
        return running_installs[key]

    if emit:
        _print_status("queue", f"{resolved_pub.lower()} {rel} -> {install_root}", "info")
    task: asyncio.Task = asyncio.create_task(asyncio.to_thread(_install_publication_to_root, resolved_pub, rel, install_root, reinstall, work_dir, emit, error))
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

def _install_publication_to_root(pub: str, rel: str, install_root: str, reinstall: bool = True, work_dir: str = ".", emit: bool = True, error: bool = False) -> InstallResult:
    pub = parsepub(pub)
    pub_lower: str = pub.lower()
    dirname: str = os.path.join(install_root, _publication_leaf(pub, rel))
    release_token: str = _release_token(rel)
    archive_path: str = os.path.join(work_dir, f"{pub_lower}-{release_token}.zip")
    extract_dir: str = os.path.join(work_dir, f"{pub_lower}-repo-{release_token}")
    url: str = f"https://github.com/Wednesware/{pub.capitalize()}/archive/refs/heads/main.zip" if rel == "beta" else f"https://github.com/Wednesware/{pub.capitalize()}/releases/{rel + '/download' if rel == 'latest' else 'download/' + rel}/{pub_lower}.zip"
    not_found: bool = False
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
            not_found = True
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
        if error and not_found:
            raise FileNotFoundError(f"Could not find release '{rel}' for publication '{pub_lower}'.")


def _queue_install(pub: str, rel: str, reinstall: bool = True, install_root: str = "ww", work_dir: str = ".", emit: bool = True, error: bool = False) -> asyncio.Task:
    return _queue_install_to_root(pub, rel, install_root, reinstall, work_dir, emit, error=error)


async def install_async(pub: str, rel: str, reinstall: bool = True, color: bool = True, emit: bool = True, fatal: bool = True, install_root: str = "ww", work_dir: str = ".", error: bool = False) -> InstallResult:
    result: InstallResult = await _queue_install(pub, rel, reinstall, install_root, work_dir, emit, error)
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
        
async def main() -> None:
    if len(sys.argv) == 1:
        print(_cli(f"Nitrogen v{VERSION}", CLI_INFO, bold=True))
        print(_cli("Fast installer for Wednesware publications.", CLI_DIM))
        print()
        print("Usage: n2 <command> [args]")
        print(f"Run {_cli('n2 help', CLI_INFO)} for a full command list.")
        sys.exit(0)

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
            pub = sys.argv[2]
            rel = sys.argv[3] if len(sys.argv) > 3 else "latest"
            result = await install_async(pub, rel, install_root=INTERNAL_WW_DIR, work_dir=INTERNAL_TEMP_DIR)
            if not result.exit_code:
                await _install_subdependencies(pub, rel, install_root=INTERNAL_WW_DIR, work_dir=INTERNAL_TEMP_DIR)
        case "rm":
            if len(sys.argv) == 2:
                _print_status("help", "Usage: n2 rm <publication> [release]", "warning")
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
                result = await install_target(path, bin_dir=bin_dir, command_name=command_name, no_deps=no_deps)
                _print_status("done", f"Installed command '{result['command_name']}'", "success")
                _print_status("info", f"Target: {result['target']}", "info")
                _print_status("info", f"Bin: {result['bin_path']}", "info")
                _print_status("info", "You can run it directly from the shell now.", "info")
                sys.exit(0)
            except (FileNotFoundError, ValueError, RuntimeError) as exc:
                _print_status("fail", str(exc), "error")
                sys.exit(1)
        case "install-cache":
            if len(sys.argv) == 2:
                _print_status("help", "Usage: n2 install-cache <publication> [release] [--name <command>] [--bin <dir>]", "warning")
                sys.exit(1)
            args = sys.argv[2:]
            pub = args[0]
            rel = args[1] if len(args) > 1 and not args[1].startswith("--") else "latest"
            command_name = None
            bin_dir = None
            for index in range(1 if len(args) > 1 and args[1].startswith("--") else 2, len(args)):
                if args[index] == "--name" and index + 1 < len(args):
                    command_name = args[index + 1]
                elif args[index] == "--bin" and index + 1 < len(args):
                    bin_dir = args[index + 1]
            try:
                result = install_cached_publication(pub, rel, bin_dir=bin_dir, command_name=command_name)
                _print_status("done", f"Installed cached command '{result['command_name']}'", "success")
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
        case "readme":
            with open(os.path.join(os.path.dirname(__file__), "README.md")) as file:
                print(file.read())
            sys.exit(0)
        case "license":
            with open(os.path.join(os.path.dirname(__file__), "LICENSE.md")) as file:
                print(file.read())
            sys.exit(0)
        case "help":
            _print_help()
        case _:
            _print_status("miss", f"Unknown command: {sys.argv[1]}", "warning")
            print(f"Run {_cli('n2 help', CLI_INFO)} for a list of commands.")
            
async def require_async(pub: str, rel: str | None = None) -> object:
    pub_name, submodule = [pub, None] if len(pub.split(".", 1)) == 1 else pub.split(".", 1)
    pub = parsepub(pub_name)
    rel = rel or "latest"
    cache_dir = os.path.join(INTERNAL_WW_DIR, _publication_leaf(pub, rel))

    if not os.path.isdir(cache_dir):
        try:
            result: InstallResult = await install_async(pub, rel, reinstall=False, install_root=INTERNAL_WW_DIR, work_dir=INTERNAL_TEMP_DIR, emit=False, error=True)
        except (urllib.error.URLError, urllib.error.HTTPError, OSError, TimeoutError, ConnectionError) as exc:
            raise NitrogenDependencyError(
                f"Could not install '{pub}' release '{rel}' because the site is unreachable or offline. "
                "Install it once online or make sure the package is already cached locally."
            ) from exc
        if result.exit_code:
            lines = " ".join(result.lines)
            raise NitrogenDependencyError(
                f"Could not install '{pub}' release '{rel}' because the dependency is unavailable or the site is unreachable: {lines}"
            )
        await _install_subdependencies(pub, rel, emit=False)

    name: str = _publication_leaf(pub, rel)
    module_path = os.path.join(cache_dir, f"{submodule.replace('.', os.sep)}.py" if submodule else "__init__.py")
    if not os.path.exists(module_path):
        if submodule is None:
            raise ModuleNotFoundError(f"No package entry point found in publication '{pub}' release '{rel}'")
        raise ModuleNotFoundError(f"No such submodule: '{submodule}' in publication '{pub}' release '{rel}'")

    module_name = f"{name}.{submodule}" if submodule else name

    package_spec = importlib.util.spec_from_file_location(
        name,
        os.path.join(cache_dir, "__init__.py"),
        submodule_search_locations=[cache_dir],
    )

    if package_spec is None or package_spec.loader is None:
        raise ModuleNotFoundError(
            f"Could not load publication '{pub}' release '{rel}'"
        )

    package = importlib.util.module_from_spec(package_spec)
    sys.modules[name] = package

    try:
        package_spec.loader.exec_module(package)
    except FileNotFoundError as exc:
        raise ModuleNotFoundError(
            f"No package entry point found in publication '{pub}' release '{rel}'"
        ) from exc

    if submodule is None:
        return package

    return importlib.import_module(module_name)

def _run_coroutine_from_sync(coro):
    result: dict[str, object] = {}
    error: dict[str, BaseException] = {}

    def runner() -> None:
        try:
            result["value"] = asyncio.run(coro)
        except BaseException as exc:  # pragma: no cover - exercised via tests
            error["value"] = exc

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    thread.join()

    if "value" in error:
        raise error["value"]
    return result["value"]


def require(pub: str, rel: str | None = None) -> object:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(require_async(pub, rel))
    return _run_coroutine_from_sync(require_async(pub, rel))

def cleanup() -> None:
    if os.path.exists(INTERNAL_TEMP_DIR):
        shutil.rmtree(INTERNAL_TEMP_DIR)
        os.mkdir(INTERNAL_TEMP_DIR)
    if os.path.exists(INTERNAL_WW_DIR):
        shutil.rmtree(INTERNAL_WW_DIR)
        os.mkdir(INTERNAL_WW_DIR)
            
def entrypoint() -> None:
    asyncio.run(main())
    
if __name__ == "__main__":
    entrypoint()