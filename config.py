"""Centralized config + token loading for the GitHub MCP server."""
import os
from pathlib import Path
from dotenv import load_dotenv

_env_path = Path(__file__).parent / ".env"
if _env_path.exists():
    load_dotenv(_env_path)

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_API_URL = os.environ.get("GITHUB_API_URL", "https://api.github.com")
DEFAULT_REPO_VISIBILITY = os.environ.get("DEFAULT_REPO_VISIBILITY", "public")


def validate() -> None:
    if not GITHUB_TOKEN:
        raise RuntimeError(
            "GITHUB_TOKEN is not set. "
            "Copy /Users/youruser/.mcp-servers/github-mcp-server/.env.example "
            "to .env and set GITHUB_TOKEN=ghp_... "
            "or export GITHUB_TOKEN in your shell."
        )
