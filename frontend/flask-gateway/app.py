"""Flask gateway entry point for the UMockMe frontend shell."""

from flask import Flask

app = Flask(__name__)


@app.get("/")
def index() -> str:
    """Render the root page for the gateway application."""
    return "UMockMe Flask Gateway"
