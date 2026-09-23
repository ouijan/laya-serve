"""AGENTS.md carries the onboarding procedure, including the index.ts an agent
is told to paste. It is pasted rather than executed by CI, so this keeps it
identical to the example folder, which is typechecked against the published
client.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGENTS = ROOT / "AGENTS.md"
EXAMPLE = ROOT / "examples/typescript-quickstart/index.ts"

HEREDOC_OPEN = "cat > index.ts <<'EOF'\n"
HEREDOC_CLOSE = "\nEOF\n"


def agents_heredoc() -> str:
    """The index.ts the onboarding procedure tells an agent to paste."""
    text = AGENTS.read_text()
    assert HEREDOC_OPEN in text, f"AGENTS.md lost the {HEREDOC_OPEN.strip()} block"
    body = text.split(HEREDOC_OPEN, 1)[1]
    assert HEREDOC_CLOSE in body, "AGENTS.md onboarding heredoc is not terminated"
    return body.split(HEREDOC_CLOSE, 1)[0] + "\n"


def test_quickstart_matches_the_example():
    assert agents_heredoc() == EXAMPLE.read_text(), (
        "AGENTS.md and examples/typescript-quickstart/index.ts have drifted; "
        "make them identical"
    )


def test_quickstart_uses_the_published_client():
    """Importing from a relative path would mean the reader needs this repo."""
    assert '"@ouijan/laya-client"' in EXAMPLE.read_text()
