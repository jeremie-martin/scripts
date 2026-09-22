"""Exercise native installation without changing the user's installed tools."""

import os
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PROJECTS = sorted((ROOT / "tools").glob("*/pyproject.toml"))


def run(args, cwd, env):
    result = subprocess.run([str(arg) for arg in args], cwd=cwd, env=env, capture_output=True, text=True, timeout=600)
    assert result.returncode == 0, f"{args}\n{result.stdout}\n{result.stderr}"
    return result.stdout


def environment(directory):
    # Do not pass unrelated credentials into build subprocesses or test reports.
    env = {key: os.environ[key] for key in ("PATH", "HOME", "XDG_CACHE_HOME", "UV_CACHE_DIR", "LANG") if key in os.environ}
    env.update(UV_TOOL_DIR=str(directory / "envs"), UV_TOOL_BIN_DIR=str(directory / "bin"), UV_LINK_MODE="copy")
    return env


@pytest.fixture(scope="module")
def wheels(tmp_path_factory):
    directory = tmp_path_factory.mktemp("wheels")
    env = environment(directory)
    for metadata in [ROOT / "packages/clipboard/pyproject.toml", *PROJECTS]:
        run(["uv", "build", metadata.parent, "--out-dir", directory], directory, env)
    assert len(list(directory.glob("*.whl"))) == len(PROJECTS) + 1
    assert len(list(directory.glob("*.tar.gz"))) == len(PROJECTS) + 1
    return directory


@pytest.mark.parametrize("mode", ["editable", "wheel"])
def test_independent_installations(tmp_path, wheels, mode):
    env = environment(tmp_path)
    for metadata in PROJECTS:
        project = tomllib.loads(metadata.read_text())["project"]
        name = project["name"]
        if mode == "editable":
            args = ["--editable", metadata.parent]
        else:
            wheel = next(wheels.glob(name.replace("-", "_") + "-*.whl"))
            args = ["--no-sources", "--find-links", wheels, wheel]
        run(["uv", "tool", "install", *args], tmp_path, env)
        for command in project["scripts"]:
            run([tmp_path / "bin" / command, "--help"], tmp_path, env)
        interpreter = tmp_path / "envs" / name / "bin/python"
        module = next(iter(project["scripts"].values())).split(":")[0]
        source = run([interpreter, "-c", f"import {module}; print({module}.__file__)"], tmp_path, env).strip()
        assert str(metadata.parent if mode == "editable" else tmp_path / "envs") in source
        installed = run(
            [
                interpreter,
                "-c",
                "from importlib.metadata import distributions; print(*[d.metadata['Name'] for d in distributions()], sep=chr(10))",
            ],
            tmp_path,
            env,
        )
        assert "scripts" not in installed.splitlines()
        assert "torch" not in installed.splitlines()
        if any(dep.startswith("scripts-clipboard") for dep in project.get("dependencies", [])):
            source = run([interpreter, "-c", "import scripts_clipboard; print(scripts_clipboard.__file__)"], tmp_path, env)
            assert str(ROOT / "packages/clipboard" if mode == "editable" else tmp_path / "envs") in source
    run([tmp_path / "bin/quick", "sample", "empty", "--base", tmp_path, "--no-git"], tmp_path, env)
    assert (tmp_path / "sample").is_dir()
    markdown = tmp_path / "sample.md"
    markdown.write_text("# Installation probe\n")
    html = run([tmp_path / "bin/mdclip", markdown, "--print-html"], tmp_path, env)
    assert "<h1 " in html and ">Installation probe</h1>" in html
    run([tmp_path / "envs/scripts-ffcut/bin/python", "-m", "yt_dlp", "--version"], tmp_path, env)
    run(["uv", "tool", "uninstall", "scripts-quick"], tmp_path, env)
    assert not (tmp_path / "bin/quick").exists()
    run([tmp_path / "bin/concat", "--help"], tmp_path, env)


def test_editable_changes_and_entrypoint_refresh(tmp_path):
    env = environment(tmp_path)
    project = tmp_path / "quick"
    shutil.copytree(ROOT / "tools/quick", project, ignore=shutil.ignore_patterns(".venv", "__pycache__", "*.egg-info"))
    run(["uv", "tool", "install", "--editable", project], tmp_path, env)
    source = project / "scripts_quick.py"
    source.write_text(source.read_text() + '\n\ndef probe():\n    print("editable-probe")\n')
    assert "editable-probe" in run(
        [tmp_path / "envs/scripts-quick/bin/python", "-c", "import scripts_quick; scripts_quick.probe()"], tmp_path, env
    )
    metadata = project / "pyproject.toml"
    metadata.write_text(metadata.read_text().replace("[project.scripts]", '[project.scripts]\nquick-probe = "scripts_quick:probe"'))
    run(["uv", "tool", "install", "--reinstall", "--editable", project], tmp_path, env)
    assert "editable-probe" in run([tmp_path / "bin/quick-probe"], tmp_path, env)


@pytest.mark.parametrize("name", ["import-photos", "ssh-clipboard", "nsxiv-open-dir"])
def test_standalone_links_and_collision_protection(tmp_path, name):
    env = environment(tmp_path)
    bindir = tmp_path / "bin with spaces"
    args = ["make", "-C", ROOT, f"install-{name}", f"BINDIR={bindir}"]
    run(args, tmp_path, env)
    link = bindir / name
    assert link.is_symlink()
    assert os.access(link, os.X_OK)
    run(args, tmp_path, env)
    link.unlink()
    for kind in ("file", "directory", "symlink"):
        if kind == "file":
            link.write_text("keep me")
        elif kind == "directory":
            link.mkdir()
        else:
            link.symlink_to(tmp_path / "missing")
        result = subprocess.run([str(arg) for arg in args], env=env, capture_output=True, text=True)
        assert result.returncode != 0
        if kind == "file":
            assert link.read_text() == "keep me"
        elif kind == "directory":
            assert list(link.iterdir()) == []
        else:
            assert link.readlink() == tmp_path / "missing"
        if kind == "directory":
            link.rmdir()
        else:
            link.unlink()
