import asyncio
import json
import os
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


def test_install_requires_nitropkg_directory():
    async def run():
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = os.path.join(tmpdir, "demo-app")
            os.makedirs(project_dir)
            with open(os.path.join(project_dir, "main.py"), "w", encoding="utf-8") as handle:
                handle.write("print('no package here')\n")

            try:
                await nitrogen.install_target(project_dir, bin_dir=os.path.join(tmpdir, "bin"), no_deps=True)
                assert False, "Expected ValueError for a directory without .nitropkg"
            except ValueError as exc:
                assert ".nitropkg" in str(exc)

    asyncio.run(run())


def test_install_creates_executable_wrapper_in_bin_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = os.path.join(tmpdir, "demo-app")
        os.makedirs(project_dir)
        _make_package(project_dir)

        bin_dir = os.path.join(tmpdir, "bin")
        os.makedirs(bin_dir)

        async def run():
            result = await nitrogen.install_target(project_dir, bin_dir=bin_dir, no_deps=True)

            assert result["command_name"] == "demo-app"
            wrapper = os.path.join(bin_dir, "demo-app")
            assert os.path.exists(wrapper)
            assert os.access(wrapper, os.X_OK)

            with open(wrapper, "r", encoding="utf-8") as handle:
                content = handle.read()
            assert "nitropkg-managed" in content or "demo-app" in content

        asyncio.run(run())


def test_install_uses_module_execution_for_package_entrypoints(tmp_path):
    project_dir = tmp_path / "myproject"
    project_dir.mkdir()
    (project_dir / ".nitropkg").write_text(json.dumps({"name": "myproject", "entry": "__main__.py"}), encoding="utf-8")
    (project_dir / "__init__.py").write_text("x = 20\n", encoding="utf-8")
    (project_dir / "__main__.py").write_text("from . import x\nprint(x)\n", encoding="utf-8")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()

    async def run():
        result = await nitrogen.install_target(str(project_dir), bin_dir=str(bin_dir), no_deps=True)
        assert result["command_name"] == "myproject"

        wrapper = bin_dir / "myproject"
        assert wrapper.exists()
        content = wrapper.read_text(encoding="utf-8")
        assert "-m myproject" in content

        completed = subprocess.run([str(wrapper)], capture_output=True, text=True, check=True)
        assert "20" in completed.stdout

    asyncio.run(run())


def test_uninstall_removes_only_nitropkg_wrappers():
    async def run():
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = os.path.join(tmpdir, "demo-app")
            os.makedirs(project_dir)
            _make_package(project_dir)

            bin_dir = os.path.join(tmpdir, "bin")
            os.makedirs(bin_dir)

            installed = await nitrogen.install_target(project_dir, bin_dir=bin_dir, no_deps=True)
            uninstall_result = nitrogen.uninstall_target(installed["command_name"], bin_dir=bin_dir)

            assert uninstall_result["removed"] is True
            assert not os.path.exists(os.path.join(bin_dir, installed["command_name"]))

            rogue_wrapper = os.path.join(bin_dir, "rogue")
            with open(rogue_wrapper, "w", encoding="utf-8") as handle:
                handle.write("#!/usr/bin/env python\nprint('not managed')\n")

            refusal = nitrogen.uninstall_target("rogue", bin_dir=bin_dir)
            assert refusal["removed"] is False
            assert refusal["reason"] == "refusing to remove a non-nitropkg command"

    asyncio.run(run())


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


def test_install_cached_publication_creates_wrapper_from_internal_cache(tmp_path):
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()

    pub_dir = cache_dir / "mg26_5"
    pub_dir.mkdir()
    (pub_dir / "__main__.py").write_text("print('cached publication run')\n", encoding="utf-8")

    nitrogen.INTERNAL_WW_DIR = str(cache_dir)

    result = nitrogen.install_cached_publication("mg", "26.5", bin_dir=str(bin_dir), command_name="mg-run")

    assert result["command_name"] == "mg-run"
    wrapper = bin_dir / "mg-run"
    assert wrapper.exists()
    assert os.access(wrapper, os.X_OK)
    content = wrapper.read_text(encoding="utf-8")
    assert "-m mg" in content or "__main__" in content


def test_install_cached_publication_uses_module_execution_for_package_entrypoints(tmp_path):
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()

    pub_dir = cache_dir / "b"
    pub_dir.mkdir()
    (pub_dir / "__init__.py").write_text("VALUE = 7\n", encoding="utf-8")
    (pub_dir / "__main__.py").write_text("from . import VALUE\nprint(VALUE)\n", encoding="utf-8")

    nitrogen.INTERNAL_WW_DIR = str(cache_dir)

    result = nitrogen.install_cached_publication("b", "latest", bin_dir=str(bin_dir), command_name="boron")
    assert result["command_name"] == "boron"

    wrapper = bin_dir / "boron"
    content = wrapper.read_text(encoding="utf-8")
    assert "-m b" in content

    completed = subprocess.run([str(wrapper)], capture_output=True, text=True, check=True)
    assert "7" in completed.stdout


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


def test_help_and_docs_use_documented_cache_install_command(capsys):
    nitrogen._print_help()
    captured = capsys.readouterr().out.lower()
    assert "install-cache" in captured
    assert "--from-cache" not in captured

    readme = open("README.md", "r", encoding="utf-8").read().lower()
    assert "install-cache" in readme
    assert "--from-cache" not in readme


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
