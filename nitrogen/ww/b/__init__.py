import sys, re, json, shutil, zipfile, subprocess, webbrowser, os, venv, tempfile
from dataclasses import dataclass, field
from html import escape
from pathlib import Path
import urllib.request
import urllib.error

require = None
nitrogen_missing: bool = False

Keymap = TextInput = SelectMenu = Color = App = info_window = error_window = Terminal = Page = div_tag = h1_tag = document = Script = event = title_tag = None

try:
    from nitrogen import require
    Keymap = require("iodine").Keymap
    TextInput = require("iodine.widgets.text_input").TextInput
    SelectMenu = require("iodine.widgets.select").SelectMenu
    Color = require("magnesium.color").Color
    Page = require("fluorine").Page
    Terminal = require("neon.terminal").Terminal
    div_tag = require("fluorine.structuring").div
    h1_tag = require("fluorine.structuring").h1
    document = require("fluorine.scripting").document
    Script = require("fluorine.scripting").Script
    event = require("fluorine.scripting").event
    title_tag = require("fluorine.structuring").title
    run = require("iodine").run
except ImportError:
    nitrogen_missing = True

VERSION: str = "26.11"

BORON_DIR: Path = Path(os.environ.get("BORON_DIR", str(Path.home() / ".boron")))
DEFAULT_CACHE_DIR: Path = BORON_DIR / "cache"
DEFAULT_BOOKMARKS_DIR: Path = BORON_DIR / "bookmarks"
DEFAULT_VENV_DIR: Path = Path(os.environ.get("BORON_VENV_DIR", str(BORON_DIR / "venv")))
LOOKUP_HISTORY_FILE: Path = DEFAULT_CACHE_DIR / "lookups.json"
EXIT_TEXT: str = "[exit]"
BACK_TEXT: str = "[back]"

if not nitrogen_missing:
    keymap: Keymap = Keymap() # type: ignore
    if not nitrogen_missing:
        @keymap.on("CTRL_C")
        def handle_ctrl_c(_) -> None:
            print("boron: Operation cancelled by user.")
            exit(0)

@dataclass
class Information:
    name: str
    kind: str = "directory"
    content: str | None = None
    path: str | None = None
    children: dict[str, "Information"] = field(default_factory=dict)

    @classmethod
    def from_directory(cls, root: Path, root_name: str | None = None) -> "Information":
        root_name = root_name or root.name
        node = cls(name=root_name, kind="directory", path=str(root))
        for child in sorted(root.iterdir(), key=lambda p: p.name.lower()):
            if child.name.startswith("_") or child.name.startswith("."):
                continue
            if child.is_dir():
                node.children[child.name] = cls.from_directory(child, child.name)
            elif child.is_file():
                try:
                    text = child.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    text = child.read_bytes().decode("utf-8", errors="replace")
                node.children[child.name] = cls(
                    name=child.name,
                    kind="file",
                    path=str(child),
                    content=text,
                )
        return node

    @classmethod
    def from_dict(cls, data: dict[str, any]) -> "Information":
        node = cls(
            name=data.get("name", "root"),
            kind=data.get("kind", "directory"),
            content=data.get("content"),
            path=data.get("path"),
        )
        for key, child in data.get("children", {}).items():
            node.children[key] = cls.from_dict(child)
        return node

    def to_dict(self) -> dict[str, any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "content": self.content,
            "path": self.path,
            "children": {key: child.to_dict() for key, child in self.children.items()},
        }

    def get(self, path: str, default: "Information | str | None" = None) -> "Information | str | None":
        if path is None:
            return default
        parts = [part for part in str(path).replace('\\', '/').strip('/').split('/') if part and part != '.']
        node: "Information | None" = self
        for part in parts:
            if node is None or node.kind != "directory":
                return default
            node = node.children.get(part)
        if node is None:
            return default
        return node

    def __getitem__(self, path: str) -> "Information":
        result = self.get(path, default=None)
        if result is None:
            raise KeyError(path)
        return result

    def get_file(self, path: str, default: str | None = None) -> str | None:
        info = self.get(path, default=None)
        if info is None or not isinstance(info, Information):
            return default
        if info.kind != "file":
            return default
        return info.content

def parse_identifier(identifier: str, no_format: bool = False) -> tuple[str, str]:
    if identifier is None:
        raise ValueError("Boron identifier is required.")

    value = str(identifier).strip().replace("’", "'").replace("`", "'")
    if not value:
        raise ValueError("Boron identifier cannot be empty.")

    special_mode = "lookup"
    lowered = value.lower()
    if lowered.startswith("documentation of "):
        special_mode = "documentation"
        value = value[len("documentation of "):]
    elif lowered.startswith("license of "):
        special_mode = "license"
        value = value[len("license of "):]

    match = re.match(r"(?is)^(?P<author>.+?)(?:'s|')\s*(?P<repo>.+)$", value)
    if not match:
        raise ValueError(
            "Identifier must look like \"<author>'s <repo>\", \"documentation of <author>'s <repo>\", or \"license of <author>'s <repo>\"."
        )

    author_value = match.group("author").strip()
    repo_value = match.group("repo").strip()

    if not author_value or not repo_value:
        raise ValueError("Identifier must include both an author and a repository name.")

    if no_format:
        return author_value, repo_value

    author_name = re.sub(r"[^A-Za-z0-9\s]", "", author_value)
    author_parts = []
    for part in re.split(r"\s+", author_name.strip()):
        cleaned = re.sub(r"[^A-Za-z0-9]", "", part)
        if not cleaned:
            continue
        if cleaned.isupper():
            cleaned = cleaned[:1].upper() + cleaned[1:].lower()
        elif cleaned.islower() and cleaned:
            cleaned = cleaned[:1].upper() + cleaned[1:]
        author_parts.append(cleaned)
    author_name = "".join(author_parts)
    if not author_name:
        raise ValueError("Identifier author could not be resolved.")

    repo_name = re.sub(r"[^A-Za-z0-9]", "", repo_value)
    if not repo_name:
        raise ValueError("Identifier repository name could not be resolved.")
    if repo_name.isupper():
        repo_name = repo_name.lower()
    elif repo_name.islower():
        repo_name = repo_name
    elif repo_name:
        repo_name = repo_name[:1].upper() + repo_name[1:]

    if special_mode == "lookup":
        repo_name = f"b_{repo_name}"

    return author_name, repo_name

def _history_path(cache_dir: Path | str | None = None) -> Path:
    path = Path(cache_dir) if cache_dir is not None else DEFAULT_CACHE_DIR
    return path / "lookups.json"

def _resolve_boron_dir(boron_dir: Path | str | None = None) -> Path:
    if boron_dir is not None:
        return Path(boron_dir)
    env_value = os.environ.get("BORON_DIR")
    if env_value:
        return Path(env_value)
    return BORON_DIR


def _resolve_venv_dir(venv_dir: Path | str | None = None) -> Path:
    if venv_dir is not None:
        return Path(venv_dir)
    env_value = os.environ.get("BORON_VENV_DIR")
    if env_value:
        return Path(env_value)
    return DEFAULT_VENV_DIR


def _ensure_boron_dir(boron_dir: Path | str | None = None) -> Path:
    boron_dir = _resolve_boron_dir(boron_dir)
    boron_dir.mkdir(parents=True, exist_ok=True)
    _ensure_cache(boron_dir / "cache")
    _ensure_bookmarks(boron_dir / "bookmarks")
    _ensure_venv(boron_dir / "venv")
    return boron_dir


def _ensure_cache(cache_dir: Path | str | None = None) -> Path:
    cache_dir = Path(cache_dir) if cache_dir is not None else DEFAULT_CACHE_DIR
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir

def _ensure_bookmarks(bookmarks_dir: Path | str | None = None) -> Path:
    bookmarks_dir = Path(bookmarks_dir) if bookmarks_dir is not None else DEFAULT_BOOKMARKS_DIR
    bookmarks_dir.mkdir(parents=True, exist_ok=True)
    return bookmarks_dir

def _ensure_venv(venv_dir: Path | str | None = None) -> Path:
    venv_dir = _resolve_venv_dir(venv_dir)
    if not venv_dir.exists():
        venv.EnvBuilder(with_pip=True).create(str(venv_dir))
    return venv_dir


def _venv_python(venv_dir: Path | str | None = None) -> Path:
    resolved = _ensure_venv(venv_dir)
    if os.name == "nt":
        return resolved / "Scripts" / "python.exe"
    return resolved / "bin" / "python"


def _ensure_venv_dependencies(venv_dir: Path | str | None = None) -> Path:
    resolved_venv_dir = _ensure_venv(venv_dir)
    python_path = _venv_python(resolved_venv_dir)
    subprocess.run(
        [str(python_path), "-m", "pip", "install", "wwn", "pywebview", "pyperclip", "PySide6", "qtpy"],
        check=True,
        stdout=subprocess.DEVNULL,
    )
    return python_path


def _sanitize_bookmark_part(value: str | None, fallback: str = "bookmark") -> str:
    text = str(value or fallback).strip()
    text = text.replace("/", "_").replace("\\", "_").replace(":", "_")
    text = re.sub(r"[^A-Za-z0-9_. -]", "_", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text or fallback

def _bookmark_path(author: str, source_title: str, item_name: str, bookmarks_dir: Path | str | None = None) -> Path:
    bookmarks_dir = _ensure_bookmarks(bookmarks_dir)
    author_name = _sanitize_bookmark_part(author, "unknown")
    source_name = _sanitize_bookmark_part(source_title, "lookup")
    file_name = _sanitize_bookmark_part(item_name, "bookmark")
    return bookmarks_dir / f"{author_name}--{source_name}--{file_name}.bbm"

def _read_bookmark_record(path: Path) -> dict[str, any]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return {}

    if not raw.strip():
        return {}

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        payload = None

    if isinstance(payload, dict):
        record = dict(payload)
        record.setdefault("kind", "file")
        record.setdefault("author", "unknown")
        record.setdefault("source", "unknown")
        record.setdefault("name", path.stem)
        if "content" not in record and "tree" not in record:
            record["content"] = raw
        return record

    author = "unknown"
    source = "unknown"
    name = path.stem
    if path.name.endswith(".bbm"):
        stem = path.name.removesuffix(".bbm")
        parts = stem.split("--", maxsplit=2)
        if len(parts) == 3:
            author, source, name = parts
    return {
        "kind": "file",
        "author": author,
        "source": source,
        "name": name,
        "content": raw,
    }


def _format_bookmark_name(name: str) -> str:
    text = str(name or "bookmark").strip()
    text = re.sub(r"^b_", "", text, flags=re.IGNORECASE)
    if re.fullmatch(r"[A-Za-z]+\d+", text):
        match = re.match(r"^(?P<label>[A-Za-z]+)(?P<number>\d+)$", text)
        if match:
            label = match.group("label")
            number = match.group("number")
            if len(number) > 1:
                text = f"{label}{number[:1]}.{number[1:]}"
    text = text.replace("_", " ")
    return text.strip() or "bookmark"


def _bookmark_label(record: dict[str, any]) -> str:
    name = _format_bookmark_name(str(record.get("name") or "bookmark").strip())
    source = str(record.get("source") or "unknown").strip()
    author = str(record.get("author") or "unknown").strip()
    kind = str(record.get("kind") or "file").lower()
    if kind == "lookup":
        if author not in {"unknown", ""}:
            return f"{name} from {author}"
        return name
    if source and author not in {"unknown", ""}:
        return f"{name} from {author}'s {source}"
    return name


def save_bookmark(content: str, author: str, source_title: str, item_name: str, bookmarks_dir: Path | str | None = None) -> Path:
    path = _bookmark_path(author, source_title, item_name, bookmarks_dir=bookmarks_dir)
    payload = {
        "kind": "file",
        "author": str(author).strip() or "unknown",
        "source": str(source_title).strip() or "lookup",
        "name": str(item_name).strip() or "bookmark",
        "content": str(content),
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def has_bookmark(author: str, source_title: str, item_name: str, bookmarks_dir: Path | str | None = None) -> bool:
    return _bookmark_path(author, source_title, item_name, bookmarks_dir=bookmarks_dir).exists()


def remove_bookmark(author: str, source_title: str, item_name: str, bookmarks_dir: Path | str | None = None) -> bool:
    path = _bookmark_path(author, source_title, item_name, bookmarks_dir=bookmarks_dir)
    if not path.exists():
        return False
    path.unlink()
    return True


def save_lookup_bookmark(info: Information, author: str, source_title: str, bookmarks_dir: Path | str | None = None, item_name: str | None = None) -> Path:
    path = _bookmark_path(author, source_title, item_name or info.name, bookmarks_dir=bookmarks_dir)
    payload = {
        "kind": "lookup",
        "author": str(author).strip() or "unknown",
        "source": str(source_title).strip() or "lookup",
        "name": str(item_name or info.name).strip() or "lookup",
        "tree": info.to_dict(),
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def load_bookmark(path: str | Path) -> Information | str:
    bookmark_path = Path(path)
    record = _read_bookmark_record(bookmark_path)
    if not record:
        return ""

    kind = str(record.get("kind", "file")).lower()
    name = str(record.get("name") or bookmark_path.stem).strip() or bookmark_path.stem

    if kind == "lookup":
        tree = record.get("tree")
        if isinstance(tree, dict):
            info = Information.from_dict(tree)
            info.name = name
            return info
        return Information(name=name, kind="directory", path=str(bookmark_path))

    content = record.get("content")
    if not isinstance(content, str):
        content = bookmark_path.read_text(encoding="utf-8") if bookmark_path.exists() else ""
    return Information(name=name, kind="file", content=content, path=str(bookmark_path))


def list_bookmarks(bookmarks_dir: Path | str | None = None) -> list[dict[str, any]]:
    root = _ensure_bookmarks(bookmarks_dir)
    entries: list[dict[str, any]] = []
    for bookmark_path in sorted(root.iterdir(), key=lambda item: item.name.lower()):
        if not bookmark_path.is_file() or bookmark_path.suffix.lower() != ".bbm":
            continue
        record = _read_bookmark_record(bookmark_path)
        if not record:
            continue
        record["path"] = str(bookmark_path)
        record["label"] = _bookmark_label(record)
        entries.append(record)
    return entries


def _is_offline_fallback_error(err: BaseException) -> bool:
    message = str(err).lower()
    return any(
        token in message
        for token in (
            "rate limit",
            "offline",
            "timed out",
            "network",
            "temporarily unavailable",
            "connection reset",
            "connection aborted",
            "failed to establish",
            "no cached copy was found",
        )
    )

def _load_history(cache_dir: Path | str | None = None) -> list[dict[str, any]]:
    history_path = _history_path(cache_dir)
    if not history_path.exists():
        return []
    try:
        raw = json.loads(history_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    if isinstance(raw, list):
        return raw
    return []

def _save_history(entries: list[dict[str, any]], cache_dir: Path | str | None = None) -> None:
    cache_dir = _ensure_cache(cache_dir)
    history_path = cache_dir / "lookups.json"
    history_path.write_text(json.dumps(list(entries), indent=2, sort_keys=True), encoding="utf-8")

def _history_lookup(owner: str, repo_name: str, cache_dir: Path | str | None = None) -> Information | None:
    cache_dir = _ensure_cache(cache_dir)
    for entry in _load_history(cache_dir):
        if entry.get("owner") == owner and entry.get("repo") == repo_name:
            tree = entry.get("tree")
            if isinstance(tree, dict):
                return Information.from_dict(tree)
    return None


def _restrict_lookup_to_allowed_files(info: Information, allowed_names: set[str], *, label: str) -> Information:
    filtered = Information(name=info.name, kind="directory", path=info.path)
    matches: list[Information] = []

    def walk(node: Information) -> None:
        if node.kind == "file" and node.name.lower() in allowed_names:
            matches.append(node)
            return
        for child in node.children.values():
            walk(child)

    walk(info)
    if not matches:
        raise RuntimeError(f"No matching {label} file was found in this lookup.")

    for match in matches:
        filtered.children[match.name] = Information(
            name=match.name,
            kind="file",
            content=match.content,
            path=match.path,
        )
    return filtered


def download_release(author: str, repo_name: str, cache_dir: Path | str | None = None) -> Path:
    cache_dir = _ensure_cache(cache_dir)
    api_url = f"https://api.github.com/repos/{author}/{repo_name}"
    token = ""
    try:
        token = subprocess.check_output(["gh", "auth", "token"], text=True, stderr=subprocess.DEVNULL).strip()
    except (FileNotFoundError, subprocess.CalledProcessError):
        token = ""
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": f"boron/{VERSION}",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        api_url,
        headers=headers,
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.load(response)
    except urllib.error.URLError as err:
        if "rate limit" in str(err).lower():
            raise RuntimeError(f"You're being rate limited! Try again later. {err}") from err
        raise RuntimeError(f"Nonexistent lookup.") from err

    default_branch = payload.get("default_branch") or "main"
    archive_url = f"https://github.com/{author}/{repo_name}/archive/refs/heads/{default_branch}.zip"
    archive_path = cache_dir / f"{author}-{repo_name}-{default_branch}.zip"
    if not archive_path.exists():
        urllib.request.urlretrieve(archive_url, archive_path)

    extraction_root = cache_dir / f"{repo_name}-{default_branch}"
    if extraction_root.exists():
        shutil.rmtree(extraction_root)

    with zipfile.ZipFile(archive_path) as archive:
        archive.extractall(cache_dir)

    candidate_dirs = sorted(
        [
            item
            for item in cache_dir.iterdir()
            if item.is_dir() and item.name.lower().startswith(repo_name.lower())
        ],
        key=lambda p: p.name.lower(),
    )

    if not candidate_dirs:
        raise RuntimeError(f"Could not locate the extracted default branch snapshot for {author}/{repo_name}.")

    return candidate_dirs[0]

def _effective_download_release():
    module = sys.modules.get("boron.lookup")
    if module is not None and hasattr(module, "download_release"):
        return module.download_release
    return download_release


def lookup(identifier: str, cache_dir: Path | str | None = None, offline: bool = False) -> Information:
    identifier_value = str(identifier).strip()
    lower_value = identifier_value.lower()
    if lower_value.startswith("documentation of "):
        mode = "documentation"
        allowed_names = {"readme.md"}
    elif lower_value.startswith("license of "):
        mode = "license"
        allowed_names = {"license", "license.md"}
    else:
        mode = "lookup"
        allowed_names = set()

    owner, repo_name = parse_identifier(identifier_value)
    cache_repo_name = repo_name
    cache_dir = _ensure_cache(cache_dir)

    cached = _history_lookup(owner, cache_repo_name, cache_dir=cache_dir)
    if offline and cached is not None:
        return cached

    try:
        download_repo = cache_repo_name
        extracted_root = _effective_download_release()(owner, download_repo, cache_dir=cache_dir)
        info = Information.from_directory(extracted_root)
        info.name = download_repo
        if mode == "documentation":
            info = _restrict_lookup_to_allowed_files(info, allowed_names, label="README")
        elif mode == "license":
            info = _restrict_lookup_to_allowed_files(info, allowed_names, label="LICENSE")
    except Exception as err:
        if _is_offline_fallback_error(err):
            if cached is not None:
                print(f"boron: {err}")
                return cached
            raise RuntimeError("Offline mode | Information may be outdated or incomplete. No cached copy was found for this lookup.") from err
        raise

    history = _load_history(cache_dir)
    history.append(
        {
            "owner": owner,
            "repo": cache_repo_name,
            "identifier": identifier_value,
            "tree": info.to_dict(),
        }
    )
    _save_history(history, cache_dir)

    shutil.rmtree(extracted_root, ignore_errors=True)
    return info

def _clear_terminal() -> None:
    if Terminal is not None and hasattr(Terminal, "clear"):
        Terminal.clear()


def _print_help() -> None:
    bold = getattr(Color, "bold", "") if Color is not None else ""
    gray = getattr(Color, "gray", "") if Color is not None else ""
    reset = getattr(Color, "reset", "") if Color is not None else ""
    print(f"\033[94m{bold}Boron v{VERSION}{reset}")
    print(f"{gray}Library-themed Python library and CLI for resolving information and documentation from Boron repositories on GitHub.{reset}")
    print("")
    print("Commands:")
    print("  help                         Show this help message")
    print("  license                      Show the license")
    print("  lookup \"<author>'s <repo>\"   Resolve and look up a Boron repository")
    print("  bm                           See your bookmarks")

def _print_license() -> None:
    with open(Path(__file__).parent / "LICENSE.md") as file:
        print(file.read())


def grab_file(info: Information, target_dir: Path | str | None = None) -> Path:
    if info.kind != "file":
        raise ValueError("Only file entries can be grabbed from a lookup.")

    dest_dir = Path(target_dir) if target_dir is not None else Path.cwd()
    dest_dir.mkdir(parents=True, exist_ok=True)

    source_path = Path(info.path) if info.path else None
    if source_path is not None and source_path.exists():
        target = dest_dir / source_path.name
        shutil.copy2(source_path, target)
        return target

    if info.content is None:
        raise ValueError(f"No content available to copy for {info.name}.")

    target = dest_dir / info.name
    target.write_text(info.content, encoding="utf-8")
    return target


def _write_information_tree(node: Information, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for child in node.children.values():
        child_path = destination / child.name
        if child.kind == "directory":
            _write_information_tree(child, child_path)
        else:
            child_path.parent.mkdir(parents=True, exist_ok=True)
            if child.content is None:
                child_path.mkdir(parents=True, exist_ok=True)
                continue
            child_path.write_text(child.content, encoding="utf-8")


def grab_folder(info: Information, target_dir: Path | str | None = None) -> Path:
    if info.kind != "directory":
        raise ValueError("Only directory entries can be grabbed from a lookup.")

    dest_dir = Path(target_dir) if target_dir is not None else Path.cwd()
    dest_dir.mkdir(parents=True, exist_ok=True)

    source_path = Path(info.path) if info.path else None
    if source_path is not None and source_path.exists() and source_path.is_dir():
        target = dest_dir / source_path.name
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(source_path, target)
        return target

    target = dest_dir / (info.name or "folder")
    if target.exists():
        shutil.rmtree(target)
    _write_information_tree(info, target)
    return target


def source_this(
    info: Information,
    *,
    source_info: Information | None = None,
    source_info_author: str | None = None,
    source_info_title: str | None = None,
    source_path: Path | str | None = None,
) -> None:
    file_name = Path(info.path).name if info.path else str(info.name)
    lookup_name = str(
        source_info_title
        or (source_info.name if source_info is not None else info.name)
        or "lookup"
    ).strip() or "lookup"
    author_name = str(source_info_author or "unknown").strip() or "unknown"
    line = f"- File: {file_name} | Lookup: {lookup_name} | Author: {author_name}"

    target = Path(source_path) if source_path is not None else Path.cwd() / "SOURCE.md"
    target.parent.mkdir(parents=True, exist_ok=True)

    existing = target.read_text(encoding="utf-8") if target.exists() else ""
    if any(existing_line.strip() == line for existing_line in existing.splitlines()):
        return

    if existing and not existing.endswith("\n"):
        existing += "\n"
    target.write_text(existing + line + "\n", encoding="utf-8")


def source(force: bool = False, *, cache_dir: Path | str | None = None, source_file: Path | str | None = None) -> str:
    target = Path(source_file) if source_file is not None else Path.cwd() / "SOURCE.md"
    target.parent.mkdir(parents=True, exist_ok=True)

    history = _load_history(cache_dir)
    repo_lines: list[str] = []
    seen: set[tuple[str, str]] = set()
    for entry in history:
        owner = str(entry.get("owner") or "").strip()
        repo = str(entry.get("repo") or "").strip()
        if not owner or not repo:
            continue
        key = (owner, repo)
        if key in seen:
            continue
        seen.add(key)
        repo_lines.append(f"- [{owner}/{repo}](https://github.com/{owner}/{repo})")

    content = "\n".join(repo_lines) + ("\n" if repo_lines else "")
    if force or not target.exists():
        target.write_text(content, encoding="utf-8")
    return content

def _information_select_loop(info: Information, title: str, *, source_author: str | None = None, source_title: str | None = None) -> Information:
    info_window = require("sulfur").info
    error_window = require("sulfur").error
    options: dict[str, Information | None] = {}
    for child_name, child in info.children.items():
        if child.kind == "file" and child.content is not None:
            content = child.content.strip()
            if content.startswith("#"):
                heading = content.split("\n", 1)[0].removeprefix("#").strip()
                if "(pinned)" in content.split("\n", 1)[0].lower():
                    options = {heading: child} | options
                else:
                    options |= {heading: child}
                continue
        options[child_name] = child

    author_name = str(source_author or "unknown").strip() or "unknown"
    source_name = str(source_title or info.name or "lookup").strip() or "lookup"
    lookup_bookmark_label = "[unbookmark lookup]" if has_bookmark(author_name, source_name, info.name, bookmarks_dir=DEFAULT_BOOKMARKS_DIR) else "[bookmark lookup]"
    options[lookup_bookmark_label] = None
    options |= {BACK_TEXT: None, EXIT_TEXT: None}
    while True:
        _clear_terminal()
        answer: str = run(SelectMenu(options, title), global_keymap=keymap)
        if not answer:
            error_window("Invalid selection.")
            continue
        elif answer == EXIT_TEXT:
            handle_ctrl_c(None)
            continue
        elif answer == BACK_TEXT:
            print("boron: Lookup complete.")
            return info
        elif answer == "---":
            continue
        elif answer in {"[bookmark lookup]", "[unbookmark lookup]"}:
            if answer == "[unbookmark lookup]":
                removed = remove_bookmark(author_name, source_name, info.name, bookmarks_dir=DEFAULT_BOOKMARKS_DIR)
                info_window("Lookup unbookmarked." if removed else "Lookup was not bookmarked.")
                updated_label = "[bookmark lookup]" if not has_bookmark(author_name, source_name, info.name, bookmarks_dir=DEFAULT_BOOKMARKS_DIR) else "[unbookmark lookup]"
            else:
                save_lookup_bookmark(
                    info,
                    author_name,
                    source_name,
                    bookmarks_dir=DEFAULT_BOOKMARKS_DIR,
                    item_name=info.name,
                )
                info_window("Lookup bookmarked.")
                updated_label = "[unbookmark lookup]" if has_bookmark(author_name, source_name, info.name, bookmarks_dir=DEFAULT_BOOKMARKS_DIR) else "[bookmark lookup]"
            options = {key: value for key, value in options.items() if key not in {"[bookmark lookup]", "[unbookmark lookup]"}}
            options[updated_label] = None
            continue
        if answer not in options:
            print("boron: Lookup complete.")
            return info
        selected_option = options.get(answer)
        if selected_option is None:
            print("boron: Lookup complete.")
            return info
        if selected_option.kind == "directory":
            try:
                info_shell(
                    info=selected_option,
                    source_info=info,
                    source_info_title=source_title or info.name,
                    source_info_author=source_author or "unknown",
                    info_title=answer,
                )
            except KeyboardInterrupt:
                pass
            continue
        if selected_option.content is not None:
            if TextInput is not None:
                try:
                    info_shell(
                        info=selected_option,
                        source_info=info,
                        source_info_title=source_title or info.name,
                        source_info_author=source_author or "unknown",
                        info_title=answer,
                    )
                except KeyboardInterrupt:
                    pass
            else:
                return info


def info_shell(info: Information, source_info: Information, source_info_title: str, source_info_author: str, info_title: str) -> None:
    info_window = require("sulfur").info
    error_window = require("sulfur").error
    if info.kind == "directory":
        folder_bookmark_label = "unbookmark this folder" if has_bookmark(source_info_author, source_info_title, info.name, bookmarks_dir=DEFAULT_BOOKMARKS_DIR) else "[bookmark folder]"
        options: dict[str, Information | None] = {}
        for child_name, child in info.children.items():
            if child.kind == "file" and child.content is not None:
                content = child.content.strip()
                if content.startswith("#"):
                    heading = content.split("\n", 1)[0].removeprefix("#").strip()
                    if "(pinned)" in content.split("\n", 1)[0].lower():
                        options = {heading: child} | options
                    else:
                        options |= {heading: child}
                    continue
            options[child_name] = child

        options["[grab folder]"] = None
        options[folder_bookmark_label] = None
        options[BACK_TEXT] = None
        options[EXIT_TEXT] = None

        while True:
            answer: str = run(SelectMenu(options, f"{info_title} ({info.name})"), global_keymap=keymap)
            if not answer:
                error_window("Invalid selection.")
            elif answer == "[grab folder]":
                try:
                    target = grab_folder(info, Path.cwd())
                except Exception as err:
                    error_window(str(err))
                else:
                    info_window(f"Folder copied to {target}.")
            elif answer in {"[bookmark folder]", "unbookmark this folder"}:
                if answer == "unbookmark this folder":
                    removed = remove_bookmark(source_info_author, source_info_title, info.name, bookmarks_dir=DEFAULT_BOOKMARKS_DIR)
                    info_window("Folder unbookmarked." if removed else "Folder was not bookmarked.")
                else:
                    save_lookup_bookmark(
                        info,
                        source_info_author,
                        source_info_title,
                        bookmarks_dir=DEFAULT_BOOKMARKS_DIR,
                        item_name=info.name,
                    )
                    info_window("Folder bookmarked.")
                updated_label = "unbookmark this folder" if has_bookmark(source_info_author, source_info_title, info.name, bookmarks_dir=DEFAULT_BOOKMARKS_DIR) else "[bookmark folder]"
                options = {key: value for key, value in options.items() if key not in {"[bookmark folder]", "unbookmark this folder"}}
                options[updated_label] = None
            elif answer == BACK_TEXT:
                _clear_terminal()
                return
            elif answer == EXIT_TEXT:
                exit(0)
            elif answer not in options:
                error_window("Invalid selection.")
            else:
                selected_option = options.get(answer)
                if selected_option is None:
                    continue
                if selected_option.kind == "directory":
                    try:
                        info_shell(
                            info=selected_option,
                            source_info=info,
                            source_info_title=source_info_title,
                            source_info_author=source_info_author,
                            info_title=answer,
                        )
                    except KeyboardInterrupt:
                        pass
                elif selected_option.content is not None:
                    try:
                        info_shell(
                            info=selected_option,
                            source_info=info,
                            source_info_title=source_info_title,
                            source_info_author=source_info_author,
                            info_title=answer,
                        )
                    except KeyboardInterrupt:
                        pass
            _clear_terminal()

    file_bookmark_label = "unbookmark this file" if has_bookmark(source_info_author, source_info_title, info.name, bookmarks_dir=DEFAULT_BOOKMARKS_DIR) else "[bookmark file]"
    lookup_bookmark_label = "[unbookmark lookup]" if has_bookmark(source_info_author, source_info_title, source_info.name, bookmarks_dir=DEFAULT_BOOKMARKS_DIR) else "[bookmark lookup]"
    options: list[str] = [
        "[open in web]",
        "[open in app]",
        "[copy content to clipboard]",
        "[grab file]",
        file_bookmark_label,
        lookup_bookmark_label,
        "[source this]",
        BACK_TEXT,
        EXIT_TEXT
    ]
    while True:
        _clear_terminal()
        if info.content is None:
            print("[No file content available.]")
        elif not info.content:
            print("[File content is empty.]")
        elif len(info.content) > 2500 or info.content.count("\n") > 50:
            print("[File content is too large to display in the terminal. Please open it in the browser or app instead.]")
        else:
            print(info.content)
        answer: str = run(SelectMenu(options, f"{info_title} ({info.name})"), global_keymap=keymap)
        if answer not in options:
            error_window(f"Invalid selection.")
        elif answer == "---":
            pass
        elif answer in ["[open in web]", "[open in app]"]:
            page: Page = Page("index") # type: ignore
            page.head(
                title_tag (info.name)
            )
            page.style(identifier="body",
                background_color="#050505"
            )
            page.style .content (
                color="#ffffff",
                font_family="arial"
            )
            page.body(
                div_tag .content (info.content)
            )
            if info.name.endswith(".md"):
                page.connect("https://cdn.jsdelivr.net/npm/marked/marked.min.js")
                page.script(Script(
                    """
                    const content = document.querySelector('.content');
                    if (window.marked) {
                        content.innerHTML = marked.parse(content.textContent);
                    } else {
                        content.innerHTML = content.textContent.replace(/\\n/g, '<br>');
                    }
                    """
                ))
            path: str = tempfile.NamedTemporaryFile(suffix=".html", delete=False).name
            page.build(path)
            if answer == "[open in app]":
                require("sulfur").App(path).open()
            else:
                webbrowser.open(str(path))
        elif answer == "[copy content to clipboard]":
            try:
                import pyperclip
            except ImportError:
                print(f"boron: Pyperclip is required for this action. Please install it using 'pip install pyperclip'.")
                exit(1)
            pyperclip.copy(info.content)
            info_window("Content copied to clipboard.")
        elif answer == "[grab file]":
            try:
                target = grab_file(info, Path.cwd())
            except Exception as err:
                error_window(str(err))
            else:
                info_window(f"File copied to {target}.")
        elif answer in {"[bookmark file]", "unbookmark this file"}:
            if answer == "unbookmark this file":
                removed = remove_bookmark(source_info_author, source_info_title, info.name, bookmarks_dir=DEFAULT_BOOKMARKS_DIR)
                info_window("File unbookmarked." if removed else "File was not bookmarked.")
            else:
                save_bookmark(
                    info.content or "",
                    source_info_author,
                    source_info_title,
                    info.name,
                    bookmarks_dir=DEFAULT_BOOKMARKS_DIR,
                )
                info_window("File bookmarked.")
            options[4] = "unbookmark this file" if has_bookmark(source_info_author, source_info_title, info.name, bookmarks_dir=DEFAULT_BOOKMARKS_DIR) else "[bookmark file]"
        elif answer in {"[bookmark lookup]", "[unbookmark lookup]"}:
            if answer == "[unbookmark lookup]":
                removed = remove_bookmark(source_info_author, source_info_title, source_info.name, bookmarks_dir=DEFAULT_BOOKMARKS_DIR)
                info_window("Lookup unbookmarked." if removed else "Lookup was not bookmarked.")
            else:
                save_lookup_bookmark(
                    source_info,
                    source_info_author,
                    source_info_title,
                    bookmarks_dir=DEFAULT_BOOKMARKS_DIR,
                )
                info_window("Lookup bookmarked.")
            options[5] = "[unbookmark lookup]" if has_bookmark(source_info_author, source_info_title, source_info.name, bookmarks_dir=DEFAULT_BOOKMARKS_DIR) else "[bookmark lookup]"
        elif answer == "[source this]":
            source_this(
                info,
                source_info=source_info,
                source_info_author=source_info_author,
                source_info_title=source_info_title,
            )
            info_window("File sourced to SOURCE.md.")
        elif answer == BACK_TEXT:
            _clear_terminal()
            return
        elif answer == EXIT_TEXT:
            exit(0)
        _clear_terminal()

def lookup_shell(identifier: str) -> Information:
    offline_used = False
    try:
        info: Information = lookup(identifier)
    except Exception as err:
        cached = None
        try:
            owner, repo_name = parse_identifier(identifier)
            cached = _history_lookup(owner, repo_name, cache_dir=DEFAULT_CACHE_DIR)
        except Exception:
            cached = None

        if cached is not None and _is_offline_fallback_error(err):
            print("You are offline, rate-limited or otherwise unable to fetch fresh data. You have the option of loading up a cached snapshot of this information from when you last looked it up.")
            choice = input("Use cached offline data? [Y/n]: ").strip().lower()
            if choice in {"", "y", "yes"}:
                info = cached
                offline_used = True
            else:
                print("Offline lookup cancelled.")
                exit(1)
        else:
            print(f"Error: {err}")
            exit(1)
    if offline_used:
        print("Offline mode | Information may be outdated or incomplete.\n")
    owner, repo_name = parse_identifier(identifier, no_format=True)
    title = identifier
    if offline_used:
        title = f"{title}{Color.gray} | Offline mode | Information may be outdated or incomplete{Color.reset}"
    if str(identifier).lower().startswith(("documentation of ", "license of ")):
        source_title = repo_name if not repo_name.lower().startswith("b_") else repo_name[2:]
    else:
        source_title = repo_name
    return _information_select_loop(info, title, source_author=owner, source_title=source_title)

def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    no_venv = "--no-venv" in argv
    if "--no-venv" in argv:
        argv.remove("--no-venv")
    if not no_venv:
        print("Loading env...")
        _ensure_boron_dir()
        venv_python = _ensure_venv_dependencies(DEFAULT_VENV_DIR)
        if Path(sys.prefix).resolve() != venv_python.parent.parent.resolve():
            os.execve(
                str(venv_python),
                [str(venv_python), __file__, *argv, "--no-venv"],
                os.environ
            )
    if not argv or argv[0] in {"help", "-h", "--help"}:
        _print_help()
        return 0
    command = argv[0]
    match command:
        case "license":
            _print_license()
            return 0
        case "lookup":
            if len(argv) < 2:
                print("Usage: boron lookup <identifier>")
                return 1
            lookup_shell(argv[1])
            return 0
        case "bm":
            bookmarks = list_bookmarks(DEFAULT_BOOKMARKS_DIR)
            if not bookmarks:
                print("...It's very empty in here...")
                return 0

            options = {entry["label"]: entry for entry in bookmarks}
            answer: str = run(SelectMenu(list(options.keys()), "Bookmarks"))
            if not answer:
                return 0
            if answer not in options:
                require("sulfur").error("Invalid selection.")
                return 1

            chosen = options[answer]
            loaded = load_bookmark(chosen["path"])
            if isinstance(loaded, Information):
                if loaded.kind == "directory":
                    _information_select_loop(
                        loaded,
                        title=str(chosen.get("label") or loaded.name),
                        source_author=str(chosen.get("author") or "unknown"),
                        source_title=str(chosen.get("source") or loaded.name),
                    )
                    return 0
                info_shell(
                    info=loaded,
                    source_info=loaded,
                    source_info_title=str(chosen.get("source") or "bookmark"),
                    source_info_author=str(chosen.get("author") or "unknown"),
                    info_title=str(chosen.get("name") or loaded.name),
                )
                return 0

            print(loaded)
            return 0
        case _:
            print(f"Unknown command: {command}")
            _print_help()
            return 1

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))