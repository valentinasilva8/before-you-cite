from pathlib import Path


def test_pyproject_does_not_list_mcp():
    text = (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    assert "mcp" not in text.casefold()
