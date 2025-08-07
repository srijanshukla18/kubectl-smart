"""CLI front-end module for kubectl-smart

This module implements the Typer-based CLI interface with the three core commands:
diag, graph, and top as specified in the technical requirements.
"""

from .main import app

__all__ = ['app']