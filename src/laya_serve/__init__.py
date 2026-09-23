"""A slim HTTP wrapper around Laya."""

from importlib.metadata import version

# pyproject.toml is the single source of truth; the TypeScript client's
# package.json is checked against it in tests.
__version__ = version("laya-serve")

__all__ = ["__version__"]
