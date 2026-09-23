"""The README quickstart is the first thing anyone runs, and it is pasted,
not executed by CI. This keeps it identical to the example folder, which is
typechecked against the published client, so a stale paste can't survive.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
EXAMPLE = ROOT / "examples/typescript-quickstart/index.ts"

HEREDOC_OPEN = "cat > index.ts <<'EOF'\n"
HEREDOC_CLOSE = "\nEOF\n"


def readme_heredoc() -> str:
    """The index.ts the quickstart tells you to paste."""
    text = README.read_text()
    assert HEREDOC_OPEN in text, f"README lost the {HEREDOC_OPEN.strip()} block"
    body = text.split(HEREDOC_OPEN, 1)[1]
    assert HEREDOC_CLOSE in body, "README quickstart heredoc is not terminated"
    return body.split(HEREDOC_CLOSE, 1)[0] + "\n"


def test_quickstart_matches_the_example():
    assert readme_heredoc() == EXAMPLE.read_text(), (
        "README.md quickstart and examples/typescript-quickstart/index.ts have "
        "drifted; make them identical"
    )


def test_quickstart_uses_the_published_client():
    """Importing from a relative path would mean the reader needs this repo."""
    assert '"@ouijan/laya-client"' in EXAMPLE.read_text()
