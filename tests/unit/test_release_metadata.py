"""Release metadata must be internally consistent before publication."""

from pathlib import Path
import tomllib

from world_address_engine import __version__


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_package_versions_match():
    project = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text("utf-8"))
    assert project["project"]["version"] == __version__ == "0.1.0a1"


def test_alpha1_release_notes_are_explicitly_test_only():
    notes = (REPO_ROOT / "docs" / "releases" / "v0.1.0-alpha.1.md").read_text(
        "utf-8"
    )
    assert "TEST ONLY" in notes
    assert "NOT FOR PRODUCTION" in notes
    assert "synthetic" in notes.lower()
    assert "v0.1.0-alpha.0" in notes
    assert "main" in notes
