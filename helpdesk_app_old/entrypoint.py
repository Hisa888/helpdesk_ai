from __future__ import annotations

"""Public app entrypoints.

This module is the stable import target for launching the Streamlit app.
Keep callers importing from here even if the internal runner changes.
"""


def run_app() -> None:
    """Launch the helpdesk Streamlit application."""
    from .runtime_main import run_app as _run_app

    _run_app()


def main() -> None:
    """CLI-friendly alias for run_app()."""
    run_app()


__all__ = ["run_app", "main"]
