"""Vercel entrypoint for the Bihar Live v0.3.0 Flask service."""

from backend.bihar_live.app import app


# Vercel's Python runtime uses this Flask app as the serverless handler.
