"""Tests for layered_memory.py — static memory file reading + formatting."""
from .layered_memory import format_static_memory_for_injection, invalidate_static_memory_cache, read_static_memory_files


class TestStaticMemoryReader:
    def test_no_dir_returns_empty(self):
        invalidate_static_memory_cache()
        result = read_static_memory_files("/tmp/nonexistent_static_memory_test_dir_xyz")
        assert result == []

    def test_reads_markdown_files(self, tmp_path):
        invalidate_static_memory_cache()
        d = tmp_path / "static-memory"
        d.mkdir()
        (d / "rules.md").write_text("Always use Chinese.\nNever share secrets.")
        (d / "prefs.md").write_text("User prefers short answers.")
        result = read_static_memory_files(str(d))
        assert len(result) == 2
        assert "Always use Chinese" in result[0] or "Always use Chinese" in result[1]

    def test_skips_empty_files(self, tmp_path):
        invalidate_static_memory_cache()
        d = tmp_path / "static-memory-empty"
        d.mkdir()
        (d / "empty.md").write_text("")
        (d / "nonempty.md").write_text("content")
        result = read_static_memory_files(str(d))
        assert len(result) == 1
        assert result[0] == "content"

    def test_caching(self, tmp_path):
        invalidate_static_memory_cache()
        d = tmp_path / "static-memory-cache"
        d.mkdir()
        (d / "test.md").write_text("initial")
        result1 = read_static_memory_files(str(d))
        assert len(result1) == 1
        (d / "test2.md").write_text("new file")
        result2 = read_static_memory_files(str(d))
        assert len(result2) == 1  # cached


class TestFormatStaticMemory:
    def test_empty_list(self):
        assert format_static_memory_for_injection([]) == ""

    def test_single_rule(self):
        result = format_static_memory_for_injection(["Always use Chinese."])
        assert "<static_memory>" in result
        assert "Always use Chinese" in result

    def test_multiple_rules(self):
        result = format_static_memory_for_injection(["Rule 1", "Rule 2"])
        assert result.count("<rule>") == 2
