"""Repository lifecycle: create / update / list / delete / archive / transfer."""
from github import Github, GithubException, Auth
import config as cfg


def _gh() -> Github:
    return Github(auth=Auth.Token(cfg.GITHUB_TOKEN))


def _safe_user(gh: Github):
    return gh.get_user()


def _repo_summary(repo) -> dict:
    return {
        "full_name": repo.full_name,
        "name": repo.name,
        "owner": repo.owner.login,
        "description": repo.description or "",
        "html_url": repo.html_url,
        "ssh_url": repo.ssh_url,
        "clone_url": repo.clone_url,
        "default_branch": repo.default_branch,
        "visibility": repo.visibility,
        "topics": list(repo.get_topics()),
        "stars": repo.stargazers_count,
        "forks": repo.forks_count,
        "open_issues": repo.open_issues_count,
        "archived": repo.archived,
        "created_at": str(repo.created_at) if repo.created_at else None,
        "pushed_at": str(repo.pushed_at) if repo.pushed_at else None,
    }


def register(mcp):

    @mcp.tool()
    def github_create_repo(
        name: str,
        description: str = "",
        visibility: str = "",
        topics: list[str] = None,
        homepage: str = "",
        has_issues: bool = True,
        has_wiki: bool = False,
        has_projects: bool = False,
        auto_init: bool = False,
        gitignore_template: str = "",
        license_template: str = "",
        org: str = "",
    ) -> dict:
        """Create a new GitHub repository.

        Args:
            name: Repository name (no slashes; just the bare name).
            description: Short description shown under the repo title.
            visibility: 'public', 'private', or 'internal' (orgs only). Defaults to DEFAULT_REPO_VISIBILITY.
            topics: List of topic tags for search ranking (e.g. ['terraform', 'aws-eks']).
            homepage: Project URL shown on the repo card (your portfolio site, docs, demo).
            has_issues: Enable Issues tab.
            has_wiki: Enable Wiki tab.
            has_projects: Enable Projects tab.
            auto_init: Create with an empty README + .gitignore + LICENSE. Set False if you'll push existing local code.
            gitignore_template: e.g. 'Terraform', 'Python', 'Node'. Only honored if auto_init=True.
            license_template: e.g. 'mit', 'apache-2.0'. Only honored if auto_init=True.
            org: Create under an organization instead of the authenticated user.

        Returns:
            Repo summary dict including html_url, ssh_url, clone_url.
        """
        gh = _gh()
        vis = (visibility or cfg.DEFAULT_REPO_VISIBILITY).lower()
        private = vis in ("private", "internal")

        try:
            owner = gh.get_organization(org) if org else _safe_user(gh)
            kwargs = {
                "name": name,
                "description": description,
                "homepage": homepage,
                "private": private,
                "has_issues": has_issues,
                "has_wiki": has_wiki,
                "has_projects": has_projects,
                "auto_init": auto_init,
            }
            if auto_init and gitignore_template:
                kwargs["gitignore_template"] = gitignore_template
            if auto_init and license_template:
                kwargs["license_template"] = license_template

            repo = owner.create_repo(**kwargs)

            if topics:
                repo.replace_topics([t.lower() for t in topics])
        except GithubException as e:
            return {"error": str(e), "status": getattr(e, "status", None), "data": getattr(e, "data", None)}

        return _repo_summary(repo)

    @mcp.tool()
    def github_list_repos(
        visibility: str = "all",
        sort: str = "updated",
        limit: int = 30,
        affiliation: str = "owner",
    ) -> dict:
        """List repositories for the authenticated user.

        Args:
            visibility: 'all', 'public', 'private'.
            sort: 'created', 'updated', 'pushed', 'full_name'.
            limit: Max repos to return (default 30).
            affiliation: 'owner', 'collaborator', 'organization_member', or comma-separated combo.
        """
        gh = _gh()
        try:
            user = _safe_user(gh)
            repos = []
            for i, r in enumerate(user.get_repos(visibility=visibility, sort=sort, affiliation=affiliation)):
                if i >= limit:
                    break
                repos.append(_repo_summary(r))
            return {"count": len(repos), "repos": repos}
        except GithubException as e:
            return {"error": str(e), "status": getattr(e, "status", None)}

    @mcp.tool()
    def github_get_repo(repo: str) -> dict:
        """Get full details for a single repo.

        Args:
            repo: 'owner/repo' or just 'repo' (assumes authenticated user).
        """
        gh = _gh()
        try:
            full = repo if "/" in repo else f"{_safe_user(gh).login}/{repo}"
            return _repo_summary(gh.get_repo(full))
        except GithubException as e:
            return {"error": str(e), "status": getattr(e, "status", None)}

    @mcp.tool()
    def github_update_repo_settings(
        repo: str,
        description: str = None,
        homepage: str = None,
        visibility: str = None,
        has_issues: bool = None,
        has_wiki: bool = None,
        has_projects: bool = None,
        default_branch: str = None,
        archived: bool = None,
    ) -> dict:
        """Patch repo settings. Pass only the fields you want to change.

        Args:
            repo: 'owner/repo' or just 'repo'.
        """
        gh = _gh()
        try:
            full = repo if "/" in repo else f"{_safe_user(gh).login}/{repo}"
            r = gh.get_repo(full)
            kwargs = {}
            if description is not None: kwargs["description"] = description
            if homepage is not None:    kwargs["homepage"] = homepage
            if has_issues is not None:  kwargs["has_issues"] = has_issues
            if has_wiki is not None:    kwargs["has_wiki"] = has_wiki
            if has_projects is not None: kwargs["has_projects"] = has_projects
            if default_branch is not None: kwargs["default_branch"] = default_branch
            if archived is not None:    kwargs["archived"] = archived
            if visibility is not None:
                kwargs["private"] = visibility.lower() in ("private", "internal")
            r.edit(**kwargs)
            return _repo_summary(gh.get_repo(full))
        except GithubException as e:
            return {"error": str(e), "status": getattr(e, "status", None)}

    @mcp.tool()
    def github_delete_repo(repo: str) -> dict:
        """Delete a repository. Irreversible.

        Args:
            repo: 'owner/repo' or just 'repo'.
        """
        gh = _gh()
        try:
            full = repo if "/" in repo else f"{_safe_user(gh).login}/{repo}"
            gh.get_repo(full).delete()
            return {"status": "deleted", "repo": full}
        except GithubException as e:
            return {"error": str(e), "status": getattr(e, "status", None)}

    @mcp.tool()
    def github_archive_repo(repo: str, archive: bool = True) -> dict:
        """Archive (or unarchive) a repository — read-only marker without deleting.

        Args:
            repo: 'owner/repo' or just 'repo'.
            archive: True to archive, False to unarchive.
        """
        gh = _gh()
        try:
            full = repo if "/" in repo else f"{_safe_user(gh).login}/{repo}"
            gh.get_repo(full).edit(archived=archive)
            return {"status": "archived" if archive else "unarchived", "repo": full}
        except GithubException as e:
            return {"error": str(e), "status": getattr(e, "status", None)}

    @mcp.tool()
    def github_transfer_repo(repo: str, new_owner: str) -> dict:
        """Transfer a repository to a different user or organization.

        Args:
            repo: 'owner/repo' or just 'repo'.
            new_owner: Username or org name to transfer to.
        """
        gh = _gh()
        try:
            full = repo if "/" in repo else f"{_safe_user(gh).login}/{repo}"
            r = gh.get_repo(full)
            r._requester.requestJsonAndCheck("POST", f"{r.url}/transfer", input={"new_owner": new_owner})
            return {"status": "transferred", "repo": full, "new_owner": new_owner}
        except GithubException as e:
            return {"error": str(e), "status": getattr(e, "status", None)}
