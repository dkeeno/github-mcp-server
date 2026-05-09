"""Releases & versioning."""
from github import Github, GithubException, Auth
import config as cfg


def _gh() -> Github:
    return Github(auth=Auth.Token(cfg.GITHUB_TOKEN))


def _resolve(repo: str, gh: Github) -> str:
    return repo if "/" in repo else f"{gh.get_user().login}/{repo}"


def register(mcp):

    @mcp.tool()
    def github_create_release(
        repo: str,
        tag: str,
        name: str = "",
        body: str = "",
        draft: bool = False,
        prerelease: bool = False,
        target: str = "",
        generate_notes: bool = False,
    ) -> dict:
        """Create a release on the repo.

        Args:
            repo: 'owner/repo' or just 'repo'.
            tag: Tag name (e.g. 'v0.1.0'). Created if doesn't exist.
            name: Release title (defaults to tag).
            body: Release notes (markdown).
            draft: True to save as draft.
            prerelease: True for pre-release.
            target: Commit-ish (branch / SHA) to tag. Defaults to default branch.
            generate_notes: If True, GitHub auto-generates notes from PRs/commits.
        """
        gh = _gh()
        full = _resolve(repo, gh)
        try:
            r = gh.get_repo(full)
            target = target or r.default_branch
            release = r.create_git_release(
                tag=tag,
                name=name or tag,
                message=body,
                draft=draft,
                prerelease=prerelease,
                target_commitish=target,
                generate_release_notes=generate_notes,
            )
            return {
                "status": "ok",
                "repo": full,
                "tag": tag,
                "html_url": release.html_url,
                "id": release.id,
            }
        except GithubException as e:
            return {"status": "error", "error": str(e), "data": getattr(e, "data", None)}

    @mcp.tool()
    def github_list_releases(repo: str, limit: int = 20) -> dict:
        """List releases for a repo (newest first).

        Args:
            repo: 'owner/repo' or just 'repo'.
            limit: Max releases to return.
        """
        gh = _gh()
        full = _resolve(repo, gh)
        try:
            r = gh.get_repo(full)
            out = []
            for i, rel in enumerate(r.get_releases()):
                if i >= limit:
                    break
                out.append({
                    "tag": rel.tag_name,
                    "name": rel.title,
                    "draft": rel.draft,
                    "prerelease": rel.prerelease,
                    "created_at": str(rel.created_at) if rel.created_at else None,
                    "html_url": rel.html_url,
                })
            return {"status": "ok", "repo": full, "count": len(out), "releases": out}
        except GithubException as e:
            return {"status": "error", "error": str(e)}

    @mcp.tool()
    def github_generate_release_notes(
        repo: str,
        tag: str,
        previous_tag: str = "",
        target: str = "",
    ) -> dict:
        """Generate release notes (preview) for a tag — does NOT publish a release.

        Args:
            repo: 'owner/repo' or just 'repo'.
            tag: New tag the release would be cut at.
            previous_tag: Compare from this tag (defaults to last release).
            target: Branch / SHA the tag would point to.
        """
        gh = _gh()
        full = _resolve(repo, gh)
        try:
            r = gh.get_repo(full)
            payload = {"tag_name": tag}
            if previous_tag: payload["previous_tag_name"] = previous_tag
            if target:        payload["target_commitish"] = target
            _, data = r._requester.requestJsonAndCheck(
                "POST", f"{r.url}/releases/generate-notes", input=payload,
            )
            return {"status": "ok", "name": data.get("name"), "body": data.get("body")}
        except GithubException as e:
            return {"status": "error", "error": str(e)}

    @mcp.tool()
    def github_create_tag(
        repo: str,
        tag: str,
        ref: str = "",
        message: str = "",
    ) -> dict:
        """Create a git tag (no release wrapper).

        Args:
            repo: 'owner/repo' or just 'repo'.
            tag: Tag name.
            ref: Commit SHA or branch name to tag from. Defaults to default branch HEAD.
            message: Annotated tag message. If empty, creates a lightweight tag.
        """
        gh = _gh()
        full = _resolve(repo, gh)
        try:
            r = gh.get_repo(full)
            if not ref:
                ref = r.get_branch(r.default_branch).commit.sha
            elif not all(c in "0123456789abcdef" for c in ref) or len(ref) != 40:
                # Branch name → resolve to SHA
                try:
                    ref = r.get_branch(ref).commit.sha
                except GithubException:
                    pass

            if message:
                # Annotated tag
                tag_obj = r.create_git_tag(tag, message, ref, "commit")
                r.create_git_ref(f"refs/tags/{tag}", tag_obj.sha)
            else:
                # Lightweight tag — direct ref to the commit
                r.create_git_ref(f"refs/tags/{tag}", ref)

            return {"status": "ok", "repo": full, "tag": tag, "ref": ref}
        except GithubException as e:
            return {"status": "error", "error": str(e)}
