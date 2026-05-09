"""Token / auth lifecycle. Validate, check scopes, list PATs."""
import requests
from github import Github, GithubException, Auth
import config as cfg


def _gh() -> Github:
    return Github(auth=Auth.Token(cfg.GITHUB_TOKEN))


def register(mcp):

    @mcp.tool()
    def github_validate_auth() -> dict:
        """Health check: confirm the configured GITHUB_TOKEN works and report user, scopes, rate limit.

        This is the first tool to call after install. Run it before any bulk operation.
        """
        try:
            r = requests.get(
                f"{cfg.GITHUB_API_URL}/user",
                headers={
                    "Authorization": f"Bearer {cfg.GITHUB_TOKEN}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
                timeout=15,
            )
        except Exception as e:
            return {"status": "error", "error": f"network: {e}"}

        if r.status_code == 401:
            return {"status": "error", "error": "GITHUB_TOKEN is invalid or expired"}
        if r.status_code != 200:
            return {"status": "error", "error": f"HTTP {r.status_code}: {r.text[:200]}"}

        user = r.json()
        scopes_header = r.headers.get("x-oauth-scopes", "")
        scopes = [s.strip() for s in scopes_header.split(",") if s.strip()]

        # Rate limit
        rl = requests.get(
            f"{cfg.GITHUB_API_URL}/rate_limit",
            headers={"Authorization": f"Bearer {cfg.GITHUB_TOKEN}"},
            timeout=15,
        ).json().get("resources", {}).get("core", {})

        return {
            "status": "ok",
            "user": user.get("login"),
            "name": user.get("name"),
            "user_url": user.get("html_url"),
            "scopes": scopes if scopes else "fine-grained PAT (per-repo permissions, not classic scopes)",
            "rate_limit": {
                "remaining": rl.get("remaining"),
                "limit": rl.get("limit"),
                "reset": rl.get("reset"),
            },
            "api_url": cfg.GITHUB_API_URL,
        }

    @mcp.tool()
    def github_check_token_scopes(required: list[str] = None) -> dict:
        """Check whether the current token has the required (classic) scopes.

        Args:
            required: List of required scope names (e.g. ['repo', 'workflow', 'admin:org']).
                If empty, just lists current scopes.
        """
        try:
            r = requests.get(
                f"{cfg.GITHUB_API_URL}/user",
                headers={"Authorization": f"Bearer {cfg.GITHUB_TOKEN}"},
                timeout=15,
            )
        except Exception as e:
            return {"status": "error", "error": str(e)}

        if r.status_code != 200:
            return {"status": "error", "error": f"HTTP {r.status_code}"}

        scopes_header = r.headers.get("x-oauth-scopes", "")
        present = set(s.strip() for s in scopes_header.split(",") if s.strip())
        required = required or []
        missing = [s for s in required if s not in present]

        return {
            "status": "ok" if not missing else "missing_scopes",
            "present": sorted(present) if present else [],
            "missing": missing,
            "is_fine_grained": not present,
            "note": (
                "Fine-grained PATs don't expose classic scopes — they enforce per-repo "
                "permission grants instead. If 'present' is empty, you have a fine-grained PAT."
            ),
        }

    @mcp.tool()
    def github_get_user(username: str = "") -> dict:
        """Get a GitHub user's profile.

        Args:
            username: Optional. If empty, returns the authenticated user.
        """
        gh = _gh()
        try:
            user = gh.get_user(username) if username else gh.get_user()
            return {
                "login": user.login,
                "name": user.name,
                "bio": user.bio,
                "company": user.company,
                "location": user.location,
                "blog": user.blog,
                "twitter_username": getattr(user, "twitter_username", None),
                "email": user.email,
                "html_url": user.html_url,
                "avatar_url": user.avatar_url,
                "followers": user.followers,
                "following": user.following,
                "public_repos": user.public_repos,
                "public_gists": user.public_gists,
                "created_at": str(user.created_at) if user.created_at else None,
            }
        except GithubException as e:
            return {"status": "error", "error": str(e)}
