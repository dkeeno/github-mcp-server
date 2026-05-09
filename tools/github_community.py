"""Community signals: stars, stargazers, traffic, forks."""
import requests
from github import Github, GithubException, Auth
import config as cfg


def _gh() -> Github:
    return Github(auth=Auth.Token(cfg.GITHUB_TOKEN))


def _resolve(repo: str, gh: Github) -> str:
    return repo if "/" in repo else f"{gh.get_user().login}/{repo}"


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
    def github_get_repo_stats(repo: str) -> dict:
        """Stars, forks, watchers, traffic counts. Useful for tracking portfolio reception.

        Args:
            repo: 'owner/repo' or just 'repo'.
        """
        gh = _gh()
        full = _resolve(repo, gh)
        try:
            r = gh.get_repo(full)
            views_resp = _api(f"/repos/{full}/traffic/views")
            clones_resp = _api(f"/repos/{full}/traffic/clones")
            views = views_resp.json() if views_resp.status_code == 200 else {}
            clones = clones_resp.json() if clones_resp.status_code == 200 else {}
            return {
                "status": "ok",
                "repo": full,
                "stars": r.stargazers_count,
                "forks": r.forks_count,
                "watchers": r.subscribers_count,
                "open_issues": r.open_issues_count,
                "size_kb": r.size,
                "default_branch": r.default_branch,
                "language": r.language,
                "views_14d": views.get("count", 0),
                "unique_visitors_14d": views.get("uniques", 0),
                "clones_14d": clones.get("count", 0),
                "unique_cloners_14d": clones.get("uniques", 0),
            }
        except GithubException as e:
            return {"status": "error", "error": str(e)}

    @mcp.tool()
    def github_list_stargazers(repo: str, limit: int = 50) -> dict:
        """List users who starred the repo.

        Args:
            repo: 'owner/repo' or just 'repo'.
            limit: Max stargazers to return.
        """
        gh = _gh()
        full = _resolve(repo, gh)
        try:
            r = gh.get_repo(full)
            users = []
            for i, u in enumerate(r.get_stargazers()):
                if i >= limit: break
                users.append({"login": u.login, "html_url": u.html_url, "avatar_url": u.avatar_url})
            return {"status": "ok", "repo": full, "count": len(users), "stargazers": users}
        except GithubException as e:
            return {"status": "error", "error": str(e)}

    @mcp.tool()
    def github_star_repo(repo: str) -> dict:
        """Star a repo (curate your starred list — visible on your profile).

        Args:
            repo: 'owner/repo'.
        """
        gh = _gh()
        try:
            r = gh.get_repo(repo)
            gh.get_user().add_to_starred(r)
            return {"status": "ok", "repo": repo, "action": "starred"}
        except GithubException as e:
            return {"status": "error", "error": str(e)}

    @mcp.tool()
    def github_unstar_repo(repo: str) -> dict:
        """Unstar a repo.

        Args:
            repo: 'owner/repo'.
        """
        gh = _gh()
        try:
            r = gh.get_repo(repo)
            gh.get_user().remove_from_starred(r)
            return {"status": "ok", "repo": repo, "action": "unstarred"}
        except GithubException as e:
            return {"status": "error", "error": str(e)}

    @mcp.tool()
    def github_get_traffic(repo: str) -> dict:
        """Detailed 14-day traffic breakdown: views per day, top referrers, top paths.

        Args:
            repo: 'owner/repo' or just 'repo'.
        """
        gh = _gh()
        full = _resolve(repo, gh)
        try:
            views = _api(f"/repos/{full}/traffic/views").json()
            referrers = _api(f"/repos/{full}/traffic/popular/referrers").json()
            paths = _api(f"/repos/{full}/traffic/popular/paths").json()
            return {
                "status": "ok",
                "repo": full,
                "views_14d": views,
                "top_referrers": referrers,
                "top_paths": paths,
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}
