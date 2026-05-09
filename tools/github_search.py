"""Search: repos, code, users."""
from github import Github, GithubException, Auth
import config as cfg


def _gh() -> Github:
    return Github(auth=Auth.Token(cfg.GITHUB_TOKEN))


def register(mcp):

    @mcp.tool()
    def github_search_repos(
        query: str,
        language: str = "",
        sort: str = "best-match",
        order: str = "desc",
        limit: int = 20,
    ) -> dict:
        """Search public repositories.

        Args:
            query: Search query (e.g. 'terraform aws eks').
            language: Filter by primary language.
            sort: 'stars' | 'forks' | 'updated' | 'best-match'.
            order: 'asc' | 'desc'.
            limit: Max results.
        """
        gh = _gh()
        try:
            q = query
            if language: q += f" language:{language}"
            kwargs = {"order": order}
            if sort != "best-match":
                kwargs["sort"] = sort
            results = []
            for i, r in enumerate(gh.search_repositories(query=q, **kwargs)):
                if i >= limit: break
                results.append({
                    "full_name": r.full_name,
                    "description": r.description,
                    "language": r.language,
                    "stars": r.stargazers_count,
                    "forks": r.forks_count,
                    "html_url": r.html_url,
                    "topics": list(r.get_topics()),
                    "updated_at": str(r.updated_at) if r.updated_at else None,
                })
            return {"status": "ok", "query": q, "count": len(results), "results": results}
        except GithubException as e:
            return {"status": "error", "error": str(e)}

    @mcp.tool()
    def github_search_code(
        query: str,
        repo: str = "",
        user: str = "",
        language: str = "",
        limit: int = 20,
    ) -> dict:
        """Search code across GitHub (or scoped to a repo / user).

        Args:
            query: Search query.
            repo: Scope to a single repo ('owner/repo').
            user: Scope to a user's repos.
            language: Filter by language.
            limit: Max results.
        """
        gh = _gh()
        try:
            q = query
            if repo:     q += f" repo:{repo}"
            if user:     q += f" user:{user}"
            if language: q += f" language:{language}"
            results = []
            for i, c in enumerate(gh.search_code(query=q)):
                if i >= limit: break
                results.append({
                    "name": c.name,
                    "path": c.path,
                    "repo": c.repository.full_name,
                    "html_url": c.html_url,
                    "score": c.score,
                })
            return {"status": "ok", "query": q, "count": len(results), "results": results}
        except GithubException as e:
            return {"status": "error", "error": str(e)}

    @mcp.tool()
    def github_search_users(
        query: str,
        type: str = "",
        location: str = "",
        language: str = "",
        limit: int = 20,
    ) -> dict:
        """Search users (people / organizations).

        Args:
            query: Search query.
            type: 'user' or 'org'.
            location: Filter by location string.
            language: Filter by their main coding language.
            limit: Max results.
        """
        gh = _gh()
        try:
            q = query
            if type:     q += f" type:{type}"
            if location: q += f" location:\"{location}\""
            if language: q += f" language:{language}"
            results = []
            for i, u in enumerate(gh.search_users(query=q)):
                if i >= limit: break
                results.append({
                    "login": u.login,
                    "name": u.name,
                    "type": u.type,
                    "location": u.location,
                    "followers": u.followers,
                    "html_url": u.html_url,
                })
            return {"status": "ok", "query": q, "count": len(results), "results": results}
        except GithubException as e:
            return {"status": "error", "error": str(e)}
