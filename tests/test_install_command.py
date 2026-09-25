import asyncio
import json
import os
import pathlib
import subprocess
import tempfile
import urllib.error

import pytest

import nitrogen


def _make_package(project_dir: str, *, entry: str = "main.py"):
    metadata = {"name": "demo-app", "entry": entry}
    with open(os.path.join(project_dir, ".nitropkg"), "w", encoding="utf-8") as handle:
        json.dump(metadata, handle)
    with open(os.path.join(project_dir, entry), "w", encoding="utf-8") as handle:
        handle.write("print('hello')\n")


def test_install_target_rejects_non_cached_project_directory(tmp_path):
    project_dir = tmp_path / "demo-app"
    project_dir.mkdir()
    (project_dir / ".nitropkg").write_text(json.dumps({"name": "demo-app", "entry": "main.py"}), encoding="utf-8")
    (project_dir / "main.py").write_text("print('hello')\n", encoding="utf-8")

    with pytest.raises(ValueError, match="cached Wednesware publication|direct local package installs are disabled|pipx"):
        asyncio.run(nitrogen.install_target(str(project_dir), no_deps=True))


def test_help_restricts_install_to_publications_only(capsys):
    nitrogen._print_help()
    captured = capsys.readouterr().out.lower()
    assert "install <publication> [release]" in captured
    assert "path|publication" not in captured


def test_uninstall_target_uses_pipx_only(monkeypatch):
    calls = []

    def fake_which(name):
        return "/usr/bin/pipx" if name == "pipx" else None

    def fake_run(cmd, capture_output, text, check=False):
        calls.append(cmd)
        class Result:
            returncode = 0
        return Result()

    monkeypatch.setattr(nitrogen.shutil, "which", fake_which)
    monkeypatch.setattr(nitrogen.subprocess, "run", fake_run)

    result = nitrogen.uninstall_target("demo-app")

    assert result["removed"] is True
    assert "bin_dir" not in result
    assert calls == [["pipx", "uninstall", "demo-app"]]


def test_uninstall_target_resolves_publication_aliases(monkeypatch):
    calls = []

    def fake_which(name):
        return "/usr/bin/pipx" if name == "pipx" else None

    def fake_run(cmd, capture_output, text, check=False):
        calls.append(cmd)
        class Result:
            returncode = 0
        return Result()

    monkeypatch.setattr(nitrogen.shutil, "which", fake_which)
    monkeypatch.setattr(nitrogen.subprocess, "run", fake_run)

    result = nitrogen.uninstall_target("mg")

    assert result["removed"] is True
    assert calls == [["pipx", "uninstall", "magnesium"]]


def test_load_nitropkg_removes_name_field(tmp_path):
    pkg_dir = tmp_path / "demo-pkg"
    pkg_dir.mkdir()
    (pkg_dir / ".nitropkg").write_text(json.dumps({"name": "legacy-name", "entry": "main.py", "dependencies": ["requests>=2"]}), encoding="utf-8")

    metadata = nitrogen._load_nitropkg(str(pkg_dir))

    assert metadata == {"entry": "main.py", "dependencies": ["requests>=2"]}


def test_write_pyproject_toml_includes_dependencies(tmp_path):
    pkg_dir = tmp_path / "demo-pkg"
    pkg_dir.mkdir()
    (pkg_dir / "main.py").write_text("print('hello')\n", encoding="utf-8")

    pyproject_path = nitrogen._write_pyproject_toml(
        str(pkg_dir),
        "demo-app",
        {"entry": "main.py", "dependencies": ["requests>=2", "httpx>=0.28"]},
    )

    pyproject = pyproject_path and pathlib.Path(pyproject_path).read_text(encoding="utf-8")
    assert 'dependencies = ["requests>=2", "httpx>=0.28"]' in pyproject


def test_install_cached_publication_ignores_nitropkg_name_and_uses_publication_name(tmp_path, monkeypatch):
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    pub_dir = cache_dir / "mg26_5"
    pub_dir.mkdir()
    (pub_dir / ".nitropkg").write_text(json.dumps({"name": "legacy-name", "entry": "__main__.py"}), encoding="utf-8")
    (pub_dir / "__main__.py").write_text("print('cached publication run')\n", encoding="utf-8")

    monkeypatch.setattr(nitrogen, "INTERNAL_WW_DIR", str(cache_dir))

    calls = []

    def fake_which(name):
        return "/usr/bin/pipx" if name == "pipx" else None

    def fake_run(cmd, capture_output, text, check=False, env=None):
        calls.append(cmd)
        return type("Result", (), {"returncode": 0})()

    monkeypatch.setattr(nitrogen.shutil, "which", fake_which)
    monkeypatch.setattr(nitrogen.subprocess, "run", fake_run)

    result = nitrogen.install_cached_publication("mg", "26.5")

    assert result["command_name"] == "magnesium"
    assert calls[0] == ["pipx", "uninstall", "magnesium"]
    assert calls[1] == ["pipx", "install", str(pub_dir), "--force"]


def test_require_uses_cached_internal_install_without_redownloading(monkeypatch, tmp_path):
    cache_dir = tmp_path / "cache"
    temp_dir = tmp_path / "temp"
    cache_dir.mkdir()
    temp_dir.mkdir()
    package_dir = cache_dir / "mg26_5"
    package_dir.mkdir()
    module_file = package_dir / "__init__.py"
    module_file.write_text("VALUE = 42\n", encoding="utf-8")

    monkeypatch.setattr(nitrogen, "INTERNAL_WW_DIR", str(cache_dir))
    monkeypatch.setattr(nitrogen, "INTERNAL_TEMP_DIR", str(temp_dir))

    async def fail_install(*args, **kwargs):
        raise AssertionError("require should not redownload while a cached install already exists")

    monkeypatch.setattr(nitrogen, "install_async", fail_install)

    module = nitrogen.require("mg", "26.5")
    assert module.VALUE == 42


def test_require_works_when_called_from_a_running_event_loop(monkeypatch, tmp_path):
    cache_dir = tmp_path / "cache"
    temp_dir = tmp_path / "temp"
    cache_dir.mkdir()
    temp_dir.mkdir()
    package_dir = cache_dir / "mg26_5"
    package_dir.mkdir()
    (package_dir / "__init__.py").write_text("VALUE = 99\n", encoding="utf-8")

    monkeypatch.setattr(nitrogen, "INTERNAL_WW_DIR", str(cache_dir))
    monkeypatch.setattr(nitrogen, "INTERNAL_TEMP_DIR", str(temp_dir))

    async def fail_install(*args, **kwargs):
        raise AssertionError("require should not redownload while a cached install already exists")

    monkeypatch.setattr(nitrogen, "install_async", fail_install)

    async def run():
        module = nitrogen.require("mg", "26.5")
        assert module.VALUE == 99

    asyncio.run(run())


def test_require_raises_custom_error_when_site_is_unreachable(monkeypatch):
    async def fail_install(*args, **kwargs):
        raise urllib.error.URLError("offline")

    monkeypatch.setattr(nitrogen, "install_async", fail_install)

    with pytest.raises(nitrogen.NitrogenDependencyError, match="offline|site|unreachable"):
        asyncio.run(nitrogen.require_async("mg", "26.5"))


def test_install_cached_publication_uses_pipx_without_custom_bin_dir(tmp_path, monkeypatch):
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    pub_dir = cache_dir / "mg26_5"
    pub_dir.mkdir()
    (pub_dir / "__main__.py").write_text("print('cached publication run')\n", encoding="utf-8")

    nitrogen.INTERNAL_WW_DIR = str(cache_dir)

    calls = []

    def fake_which(name):
        return "/usr/bin/pipx" if name == "pipx" else None

    def fake_run(cmd, capture_output, text, check=False, env=None):
        calls.append(cmd)
        return type("Result", (), {"returncode": 0})()

    monkeypatch.setattr(nitrogen.shutil, "which", fake_which)
    monkeypatch.setattr(nitrogen.subprocess, "run", fake_run)

    result = nitrogen.install_cached_publication("mg", "26.5", command_name="mg-run")

    assert result["command_name"] == "mg-run"
    assert "bin_dir" not in result
    assert "bin_path" not in result
    assert calls[0] == ["pipx", "uninstall", "mg-run"]
    assert calls[1] == ["pipx", "install", str(pub_dir), "--force"]


def test_install_cached_publication_uses_module_execution_for_package_entrypoints(tmp_path, monkeypatch):
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    pub_dir = cache_dir / "b"
    pub_dir.mkdir()
    (pub_dir / "__init__.py").write_text("VALUE = 7\n", encoding="utf-8")
    (pub_dir / "__main__.py").write_text("from . import VALUE\nprint(VALUE)\n", encoding="utf-8")

    nitrogen.INTERNAL_WW_DIR = str(cache_dir)

    monkeypatch.setattr(nitrogen.shutil, "which", lambda name: "/usr/bin/pipx" if name == "pipx" else None)

    def fake_run(cmd, capture_output, text, check=False, env=None):
        return type("Result", (), {"returncode": 0})()

    monkeypatch.setattr(nitrogen.subprocess, "run", fake_run)

    result = nitrogen.install_cached_publication("b", "latest", command_name="boron")
    assert result["command_name"] == "boron"
    assert "bin_dir" not in result
    assert "bin_path" not in result


def test_build_and_compat_commands_are_removed_from_cli_and_docs(capsys):
    assert not hasattr(nitrogen, "build")
    assert not hasattr(nitrogen, "_apply_compat")

    nitrogen._print_help()
    help_output = capsys.readouterr().out.lower()
    assert "build" not in help_output
    assert "compat" not in help_output

    readme = open("README.md", "r", encoding="utf-8").read().lower()
    assert "build zip" not in readme
    assert "build targz" not in readme
    assert "build modm" not in readme
    assert "compat" not in readme


def test_library_and_internal_commands_are_removed_from_cli_and_docs(capsys):
    nitrogen._print_help()
    help_output = capsys.readouterr().out.lower()
    assert "getlib" not in help_output
    assert "updlibs" not in help_output
    assert "getinternal" not in help_output
    assert "rminternal" not in help_output

    readme = open("README.md", "r", encoding="utf-8").read().lower()
    assert "getlib" not in readme
    assert "updlibs" not in readme
    assert "getinternal" not in readme
    assert "rminternal" not in readme


def test_help_and_docs_do_not_reference_install_cache(capsys):
    nitrogen._print_help()
    captured = capsys.readouterr().out.lower()
    assert "install-cache" not in captured
    assert "--from-cache" not in captured
    assert "pipx" in captured

    readme = open("README.md", "r", encoding="utf-8").read().lower()
    assert "install-cache" not in readme
    assert "--from-cache" not in readme
    assert "pipx" in readme


def test_help_and_docs_include_list_and_cache_commands(capsys):
    nitrogen._print_help()
    captured = capsys.readouterr().out.lower()
    assert "list" in captured
    assert "cache" in captured

    readme = open("README.md", "r", encoding="utf-8").read().lower()
    assert "### `list`" in readme
    assert "### `cache`" in readme


def test_help_and_docs_do_not_reference_extensions_or_n2x(capsys):
    nitrogen._print_help()
    captured = capsys.readouterr().out
    assert "n2x" not in captured.lower()
    assert "list-ext" not in captured.lower()
    assert "install-ext" not in captured.lower()
    assert "extensions" not in captured.lower()

    readme = open("README.md", "r", encoding="utf-8").read().lower()
    assert "n2x" not in readme
    assert "extensions" not in readme
