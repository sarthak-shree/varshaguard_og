"""Standalone Bihar v1 Flask application.

This app is intentionally separate from backend/app.py (the v0.2.0 prototype).
"""
from flask import Flask
from flask_cors import CORS

from .api import bp


def create_app() -> Flask:
    app = Flask(__name__)
    CORS(app)
    app.register_blueprint(bp)
    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=False)
