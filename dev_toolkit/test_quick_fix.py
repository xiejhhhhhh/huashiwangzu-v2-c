from pathlib import Path

import pytest

from dev_toolkit.quick_fix import QuickFixError, quick_fix_patch, quick_fix_preview


def test_preview_returns_diff_without_writing(tmp_path: Path) -> None:
    target = tmp_path / "demo.py"
    target.write_text("alpha = 1\nbeta = 2\n", encoding="utf-8")

    result = quick_fix_preview(
        repo_root=tmp_path,
        path="demo.py",
        old_text="beta = 2\n",
        new_text="beta = 3\n",
    )

    assert result["success"] is True
    assert result["applied"] is False
    assert result["start_line"] == 2
    assert "+beta = 3" in result["diff"]
    assert target.read_text(encoding="utf-8") == "alpha = 1\nbeta = 2\n"


def test_patch_writes_atomically_after_exact_match(tmp_path: Path) -> None:
    target = tmp_path / "demo.py"
    target.write_text("alpha = 1\nbeta = 2\n", encoding="utf-8")

    result = quick_fix_patch(
        repo_root=tmp_path,
        path="demo.py",
        old_text="beta = 2\n",
        new_text="beta = 3\n",
        start_line=2,
        end_line=2,
    )

    assert result["applied"] is True
    assert target.read_text(encoding="utf-8") == "alpha = 1\nbeta = 3\n"


def test_rejects_ambiguous_old_text_without_line_window(tmp_path: Path) -> None:
    target = tmp_path / "demo.py"
    target.write_text("value = 1\nvalue = 1\n", encoding="utf-8")

    with pytest.raises(QuickFixError, match="ambiguous"):
        quick_fix_preview(
            repo_root=tmp_path,
            path="demo.py",
            old_text="value = 1\n",
            new_text="value = 2\n",
        )


def test_rejects_path_outside_repo(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.py"
    outside.write_text("x = 1\n", encoding="utf-8")

    with pytest.raises(QuickFixError, match="inside repo root"):
        quick_fix_preview(
            repo_root=tmp_path,
            path=str(outside),
            old_text="x = 1\n",
            new_text="x = 2\n",
        )
