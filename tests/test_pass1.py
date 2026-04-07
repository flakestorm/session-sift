from session_sift.config import SessionSiftConfig
from session_sift.passes.pass1 import StructuralPruner


def test_pass1_collapses_large_code_fence() -> None:
    pruner = StructuralPruner(SessionSiftConfig())
    body = "\n".join(f"line {index}" for index in range(60))
    messages = [
        {
            "role": "user",
            "content": f"```python\n{body}\n```",
            "_session_sift": {"index": 0, "protected": False},
        }
    ]

    refined, savings = pruner.run(messages)

    assert "code block collapsed" in refined[0]["content"]
    assert savings > 0


def test_pass1_preserves_existing_session_sift_marker() -> None:
    pruner = StructuralPruner(SessionSiftConfig())
    messages = [
        {
            "role": "assistant",
            "content": "[SESSION SIFT: file tree collapsed, 12 nodes]",
            "_session_sift": {"index": 0, "protected": False},
        }
    ]

    refined, _ = pruner.run(messages)

    assert refined[0]["content"] == messages[0]["content"]


def test_pass1_collapses_git_diff_headers_but_keeps_hunks() -> None:
    pruner = StructuralPruner(SessionSiftConfig())
    content = "\n".join(
        [
            "diff --git a/app.py b/app.py",
            "index 123..456 100644",
            "--- a/app.py",
            "+++ b/app.py",
            "@@ -1,2 +1,2 @@",
            "-old",
            "+new",
        ]
    )
    messages = [{"role": "user", "content": content, "_session_sift": {"index": 0, "protected": False}}]

    refined, _ = pruner.run(messages)

    assert "git diff headers collapsed" in refined[0]["content"]
    assert "+new" in refined[0]["content"]


def test_pass1_extracts_tool_result_scaffolding() -> None:
    pruner = StructuralPruner(SessionSiftConfig())
    content = '{"type":"tool_result","tool_use_id":"abc","content":[{"path":"./src/app.py","status":"ok"}]}'
    messages = [{"role": "tool", "content": content, "_session_sift": {"index": 0, "protected": False}}]

    refined, _ = pruner.run(messages)

    assert 'tool_result' not in refined[0]["content"]
    assert './src/app.py' in refined[0]["content"]


def test_pass1_large_json_fallback_on_invalid_payload() -> None:
    pruner = StructuralPruner(SessionSiftConfig())
    bad_json = "{" + ("x" * 600) + "}"
    messages = [{"role": "user", "content": bad_json, "_session_sift": {"index": 0, "protected": False}}]

    refined, _ = pruner.run(messages)

    assert "large JSON collapsed" in refined[0]["content"]


def test_pass1_collapses_file_trees_stack_traces_and_dedup() -> None:
    pruner = StructuralPruner(SessionSiftConfig())
    first = {
        "role": "assistant",
        "content": "src/\n├── app.py\n├── lib/\n└── tests/\nTraceback (most recent call last):\n  File \"./src/app.py\", line 1, in <module>\nValueError: boom\n",
        "_session_sift": {"index": 0, "protected": False},
    }
    second = {
        "role": "assistant",
        "content": first["content"],
        "_session_sift": {"index": 1, "protected": False},
    }

    refined, _ = pruner.run([first, second])

    assert "file tree collapsed" in refined[0]["content"]
    assert "traceback" in refined[0]["content"]
    assert "duplicate content" in refined[1]["content"]


def test_pass1_collapses_code_fences_and_install_output_and_git_headers() -> None:
    pruner = StructuralPruner(SessionSiftConfig())
    long_block = "```python\n" + "\n".join("print(1)" for _ in range(45)) + "\n```\n"
    text = "Collecting x\nInstalling collected packages\nSuccessfully installed x\ndiff --git a/a b/a\nindex 1..2 100644\n" + long_block
    message = {"role": "assistant", "content": text, "_session_sift": {"index": 0, "protected": False}}

    refined, _ = pruner.run([message])

    assert "install output collapsed" in refined[0]["content"]
    assert "git diff headers collapsed" in refined[0]["content"]
    assert "code block collapsed" in refined[0]["content"]


def test_pass1_tool_scaffolding_invalid_json_is_unchanged() -> None:
    pruner = StructuralPruner(SessionSiftConfig())
    text = '<tool_result>{bad-json}</tool_result>'
    message = {"role": "assistant", "content": text, "_session_sift": {"index": 0, "protected": False}}

    refined, _ = pruner.run([message])

    assert refined[0]["content"] == text
