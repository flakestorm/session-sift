from __future__ import annotations

import re


FILE_TREE = re.compile(
    r"(?:^[A-Za-z0-9_./\\-]+/?\n)(?:[│├└].*\n){3,}",
    re.MULTILINE,
)

STACK_TRACE_PY = re.compile(
    r"Traceback \(most recent call last\):\n(?:  File .*\n)+[A-Za-z_]+(?:Error|Exception):.+",
    re.MULTILINE,
)

STACK_TRACE_NODE = re.compile(
    r"(?:Error|TypeError|ReferenceError): .+\n(?:\s+at .+\n){2,}",
    re.MULTILINE,
)

STACK_TRACE_JAVA = re.compile(
    r"(?:Exception in thread|Caused by): .+\n(?:\s+at .+\n){2,}",
    re.MULTILINE,
)

LARGE_JSON = re.compile(r"^(?:\{|\[)[\s\S]{500,}(?:\}|\])$", re.MULTILINE)

CODE_FENCE = re.compile(
    r"```(?P<lang>[a-zA-Z0-9_+-]*)\n(?P<body>[\s\S]+?)```",
    re.MULTILINE,
)

INSTALL_OUTPUT = re.compile(
    r"^(?:npm warn|npm notice|Downloading|Collecting|Resolving|Building wheel|Successfully installed|Requirement already).*$",
    re.MULTILINE,
)

GIT_DIFF_HEADER = re.compile(
    r"^(?:diff --git.*|index [0-9a-f.]+.*|--- .*|\+\+\+ .*|@@ .* @@.*)$",
    re.MULTILINE,
)

TOOL_RESULT_WRAP = re.compile(
    r'^\s*\{\s*"type"\s*:\s*"tool_result".*"content"\s*:\s*(?P<content>\[.*\]|".*")\s*\}\s*$',
    re.DOTALL,
)

SESSION_SIFT_MARKER = re.compile(r"^\[SESSION SIFT:", re.MULTILINE)
