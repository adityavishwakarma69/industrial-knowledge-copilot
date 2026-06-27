"""FastAPI application exposing the Copilot over REST + a mobile web UI."""
from .app import create_app, app

__all__ = ["create_app", "app"]
