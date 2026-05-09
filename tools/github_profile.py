"""Profile-level operations: bio, profile README, pinned repos, stats."""
import requests
from github import Github, GithubException, Auth
import config as cfg


def _gh() -> Github:
    return Github(auth=Auth.Token(cfg.GITHUB_TOKEN))


def _api(path: str, method: str = "GET", **kwargs):
    headers = kwargs.pop("headers", {})
    headers.update({
        "Authorization": f"Bearer {cfg.GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    return requests.request(method, f"{cfg.GITHUB_API_URL}{path}", headers=headers, **kwargs)


def register(mcp):

    @mcp.tool()
    def github_update_profile(
        name: str = None,
        bio: str = None,
        company: str = None,
        location: str = None,
        blog: str = None,
        twitter_username: str = None,
        email: str = None,
        hireable: bool = None,
    ) -> dict:
        """Update the authenticated user's profile fields. Pass only what you want to change.

        Args:
            name: Display name shown on your profile.
            bio: Bio text (max 160 chars).
            company: Optional org affiliation.
            location: City / country / "Remote".
            blog: URL displayed in the profile.
            twitter_username: Twitter handle (no @).
            email: Public email.
            hireable: Show "Available for hire" badge.
        """
        payload = {}
        if name is not None:             payload["name"] = name
        if bio is not None:              payload["bio"] = bio
        if company is not None:          payload["company"] = company
        if location is not None:         payload["location"] = location
        if blog is not None:             payload["blog"] = blog
        if twitter_username is not None: payload["twitter_username"] = twitter_username
        if email is not None:            payload["email"] = email
        if hireable is not None:         payload["hireable"] = hireable

        if not payload:
            return {"status": "error", "error": "no fields to update"}

        try:
            resp = _api("/user", method="PATCH", json=payload)
            if resp.status_code == 200:
                u = resp.json()
                return {"status": "ok", "login": u.get("login"), "updated": list(payload.keys())}
            return {"status": "error", "error": f"HTTP {resp.status_code}: {resp.text[:200]}"}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    @mcp.tool()
    def github_update_profile_readme(
        content: str,
        commit_message: str = "Update profile README",
    ) -> dict:
        """Create / update your profile README — the special <username>/<username> repo.

        Args:
            content: Full markdown content for the profile README.
            commit_message: Commit message.
        """
        gh = _gh()
        try:
            user = gh.get_user()
            login = user.login

            # The special profile-README repo is named identically to your username.
            try:
                repo = gh.get_repo(f"{login}/{login}")
            except GithubException:
                repo = user.create_repo(
                    name=login,
                    description=f"Profile README for {login}",
                    private=False,
                    auto_init=True,
                )

            try:
                existing = repo.get_contents("README.md", ref=repo.default_branch)
                resp = repo.update_file("README.md", commit_message, content, existing.sha)
                action = "updated"
            except GithubException:
                resp = repo.create_file("README.md", commit_message, content)
                action = "created"

            return {
                "status": "ok",
                "action": action,
                "repo": f"{login}/{login}",
                "profile_url": f"https://github.com/{login}",
                "commit_sha": resp["commit"].sha,
            }
        except GithubException as e:
            return {"status": "error", "error": str(e)}

    @mcp.tool()
    def github_pin_repos(repos: list[str]) -> dict:
        """Pin up to 6 repos to your GitHub profile. Uses the GraphQL API.

        Args:
            repos: List of repo names you own (e.g. ['my-repo-1', 'my-repo-2']) or 'owner/repo'.
                Max 6.
        """
        if not repos:
            return {"status": "error", "error": "repos list is empty"}
        if len(repos) > 6:
            return {"status": "error", "error": "GitHub allows max 6 pinned repos"}

        gh = _gh()
        login = gh.get_user().login

        # Resolve repo node IDs
        repo_node_ids = []
        for rname in repos:
            full = rname if "/" in rname else f"{login}/{rname}"
            try:
                r = gh.get_repo(full)
                repo_node_ids.append(r.node_id)
            except GithubException as e:
                return {"status": "error", "error": f"could not resolve {full}: {e}"}

        # GraphQL mutation
        mutation = """
        mutation($items: [ID!]!) {
          updateUserPinnedItems(input: {assignedItemIds: $items}) {
            user { login }
          }
        }
        """
        try:
            resp = requests.post(
                "https://api.github.com/graphql",
                headers={"Authorization": f"Bearer {cfg.GITHUB_TOKEN}"},
                json={"query": mutation, "variables": {"items": repo_node_ids}},
                timeout=15,
            )
            data = resp.json()
            if "errors" in data:
                return {"status": "error", "error": data["errors"]}
            return {"status": "ok", "pinned": repos, "user": data["data"]["updateUserPinnedItems"]["user"]["login"]}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    @mcp.tool()
    def github_get_profile_stats(username: str = "") -> dict:
        """Aggregate profile stats: followers, public repos, total stars across owned repos.

        Args:
            username: Optional. If empty, uses the authenticated user.
        """
        gh = _gh()
        try:
            user = gh.get_user(username) if username else gh.get_user()
            total_stars = 0
            languages = {}
            repo_count = 0
            for r in user.get_repos(visibility="public" if username else "all"):
                if not r.fork:
                    repo_count += 1
                    total_stars += r.stargazers_count
                    if r.language:
                        languages[r.language] = languages.get(r.language, 0) + 1
            return {
                "status": "ok",
                "login": user.login,
                "name": user.name,
                "bio": user.bio,
                "followers": user.followers,
                "following": user.following,
                "public_repos": user.public_repos,
                "owned_non_fork_repos": repo_count,
                "total_stars_on_owned_repos": total_stars,
                "top_languages": dict(sorted(languages.items(), key=lambda kv: -kv[1])[:5]),
                "profile_url": user.html_url,
            }
        except GithubException as e:
            return {"status": "error", "error": str(e)}
