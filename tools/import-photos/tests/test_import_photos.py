import subprocess
import sys
from pathlib import Path


def test_dry_run_does_not_create_destination_or_move_source(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    photo = source / "IMG_0001.JPG"
    photo.write_bytes(b"sample")
    destination = tmp_path / "destination"
    script = Path(__file__).resolve().parents[1] / "import_photos.py"
    result = subprocess.run(
        [sys.executable, str(script), str(source), "--dest", str(destination), "--dry-run", "--move"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert photo.read_bytes() == b"sample"
    assert not destination.exists()
