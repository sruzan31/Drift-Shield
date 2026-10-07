"""driftshield.api
=================
FastAPI application, routes, and schemas for DriftShield.
"""

from .app import app, create_app
from .routes import router

__all__ = ["app", "create_app", "router"]
