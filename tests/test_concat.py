import subprocess
import sys

import pytest

from scripts import concat


def test_project_explicit_defaults_override_global(tmp_path, monkeypatch):
    global_dir = tmp_path / "config" / "concat"
    global_dir.mkdir(parents=True)
    (global_dir / "config.toml").write_text('[output]\npretty = true\nmode = "tree"\n[patterns]\nexclude = ["*.log"]\n')
    project = tmp_path / "project"
    project.mkdir()
    (project / ".concat.toml").write_text('[output]\npretty = false\nmode = "concat"\n[patterns]\nexclude = ["*.tmp"]\n')
    monkeypatch.setenv("XDG_CONFIG_HOME", str(global_dir.parent))
    monkeypatch.chdir(project)
    config = concat.load_config()
    assert config.pretty is False
    assert config.output_mode == "concat"
    assert config.exclude_patterns == ["*.log", "*.tmp"]


@pytest.mark.parametrize("text", ['[output]\npretty = "false"', '[output]\nmode = "unknown"', '[files]\nmax_scan_bytes = 0'])
def test_invalid_config_fails_explicitly(tmp_path, text):
    path = tmp_path / ".concat.toml"
    path.write_text(text)
    with pytest.raises(ValueError, match="Failed to load config"):
        concat.load_toml_config(path)


def test_matching_uses_one_base_and_preserves_negation(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    matcher = concat.PatternMatcher(["/secret.txt", "*.log", "!keep.log"])
    assert matcher.matches("secret.txt")
    assert matcher.matches(str(tmp_path / "secret.txt"))
    assert not matcher.matches("nested/secret.txt")
    assert not matcher.matches("keep.log")


def test_terminal_output_is_only_payload(tmp_path, monkeypatch, capsys):
    path = tmp_path / "sample.txt"
    path.write_text("payload")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(concat, "load_config", concat.Config)
    monkeypatch.setattr(concat, "find_fd", lambda: None)
    monkeypatch.setattr(sys, "argv", ["concat", "--terminal", "--no-header", str(path)])
    concat.main()
    assert capsys.readouterr().out == "payload\n"


def test_ignore_rules_are_never_silently_skipped(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(concat, "load_config", concat.Config)
    monkeypatch.setattr(concat, "find_fd", lambda: None)
    monkeypatch.setattr(sys, "argv", ["concat", "--gitignore", str(tmp_path)])
    with pytest.raises(SystemExit) as exc:
        concat.main()
    assert exc.value.code == 2
    assert "refusing to scan without ignore rules" in capsys.readouterr().err


def test_fd_failure_is_not_an_empty_success(monkeypatch):
    monkeypatch.setattr(concat.subprocess, "run", lambda *args, **kwargs: subprocess.CompletedProcess(args, 1, b"", b"bad pattern"))
    with pytest.raises(RuntimeError, match="bad pattern"):
        concat.run_fd(["fd"], ["."])


def test_tree_includes_single_and_underscore_files(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "__init__.py"
    path.write_text("hello\n")
    concat.format_tree_output([str(path)], concat.Config())
    output = capsys.readouterr().out
    assert "__init__.py" in output.split("Top ")[0]
    assert "1L" in output


def test_default_excludes_apply_in_python_scanner(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("secret")
    (tmp_path / "visible.txt").write_text("visible")
    assert concat.gather_fallback(["."], concat.PatternMatcher(concat.DEFAULT_EXCLUDES)) == [str(tmp_path / "visible.txt")]
