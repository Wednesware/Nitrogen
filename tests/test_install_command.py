import json
import os
import tempfile

import nitrogen


def _make_package(project_dir: str, *, entry: str = "main.py"):
    metadata = {"name": "demo-app", "entry": entry}
    with open(os.path.join(project_dir, ".nitropkg"), "w", encoding="utf-8") as handle:
        json.dump(metadata, handle)
    with open(os.path.join(project_dir, entry), "w", encoding="utf-8") as handle:
        handle.write("print('hello')\n")


def test_install_requires_nitropkg_directory():
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = os.path.join(tmpdir, "demo-app")
        os.makedirs(project_dir)
        with open(os.path.join(project_dir, "main.py"), "w", encoding="utf-8") as handle:
            handle.write("print('no package here')\n")

        try:
            nitrogen.install_target(project_dir, bin_dir=os.path.join(tmpdir, "bin"), no_deps=True)
            assert False, "Expected ValueError for a directory without .nitropkg"
        except ValueError as exc:
            assert ".nitropkg" in str(exc)


def test_install_creates_executable_wrapper_in_bin_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = os.path.join(tmpdir, "demo-app")
        os.makedirs(project_dir)
        _make_package(project_dir)

        bin_dir = os.path.join(tmpdir, "bin")
        os.makedirs(bin_dir)

        result = nitrogen.install_target(project_dir, bin_dir=bin_dir, no_deps=True)

        assert result["command_name"] == "demo-app"
        wrapper = os.path.join(bin_dir, "demo-app")
        assert os.path.exists(wrapper)
        assert os.access(wrapper, os.X_OK)

        with open(wrapper, "r", encoding="utf-8") as handle:
            content = handle.read()
        assert "nitropkg-managed" in content or "demo-app" in content


def test_uninstall_removes_only_nitropkg_wrappers():
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = os.path.join(tmpdir, "demo-app")
        os.makedirs(project_dir)
        _make_package(project_dir)

        bin_dir = os.path.join(tmpdir, "bin")
        os.makedirs(bin_dir)

        installed = nitrogen.install_target(project_dir, bin_dir=bin_dir, no_deps=True)
        uninstall_result = nitrogen.uninstall_target(installed["command_name"], bin_dir=bin_dir)

        assert uninstall_result["removed"] is True
        assert not os.path.exists(os.path.join(bin_dir, installed["command_name"]))

        rogue_wrapper = os.path.join(bin_dir, "rogue")
        with open(rogue_wrapper, "w", encoding="utf-8") as handle:
            handle.write("#!/usr/bin/env python\nprint('not managed')\n")

        refusal = nitrogen.uninstall_target("rogue", bin_dir=bin_dir)
        assert refusal["removed"] is False
        assert refusal["reason"] == "refusing to remove a non-nitropkg command"
