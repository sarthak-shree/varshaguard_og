"""Flask registration point for the isolated JalDrishti shell."""
from flask import Flask
from .api import bp

def create_app() -> Flask:
    app = Flask(__name__)
    app.register_blueprint(bp)
    return app

app = create_app()
