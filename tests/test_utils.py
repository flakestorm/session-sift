from session_sift.utils import count_tokens, ensure_parent_dir, safe_str, sha256_text


def test_utils_cover_safe_str_and_helpers(tmp_path) -> None:
    target = tmp_path / "nested" / "file.txt"
    ensure_parent_dir(str(target))

    assert target.parent.exists()
    assert safe_str(b"hello") == "hello"
    assert safe_str([{"a": 1}]).startswith("[")
    assert count_tokens([{"content": "1234"}, {"content": b"5678"}]) == 2
    assert len(sha256_text("abc")) == 64