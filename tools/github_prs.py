"""Pull requests + reviews."""
from github import Github, GithubException, Auth
import config as cfg


def _gh() -> Github:
    return Github(auth=Auth.Token(cfg.GITHUB_TOKEN))


def _resolve(repo: str, gh: Github) -> str:
    return repo if "/" in repo else f"{gh.get_user().login}/{repo}"


def _summary(pr) -> dict:
    return {
        "number": pr.number,
        "title": pr.title,
        "state": pr.state,
        "draft": pr.draft,
        "merged": pr.merged,
        "mergeable": pr.mergeable,
        "head": pr.head.ref,
        "base": pr.base.ref,
        "author": pr.user.login if pr.user else None,
        "additions": pr.additions,
        "deletions": pr.deletions,
        "changed_files": pr.changed_files,
        "html_url": pr.html_url,
        "created_at": str(pr.created_at) if pr.created_at else None,
    }


def register(mcp):

    @mcp.tool()
    def github_list_prs(
        repo: str,
        state: str = "open",
        base: str = "",
        head: str = "",
        sort: str = "created",
        limit: int = 30,
    ) -> dict:
        """List pull requests.

        Args:
            repo: 'owner/repo' or just 'repo'.
            state: 'open' | 'closed' | 'all'.
            base: Filter by base branch.
            head: Filter by head branch (format 'owner:branch').
            sort: 'created' | 'updated' | 'popularity' | 'long-running'.
            limit: Max PRs to return.
        """
        gh = _gh()
        full = _resolve(repo, gh)
        try:
            r = gh.get_repo(full)
            kwargs = {"state": state, "sort": sort}
            if base: kwargs["base"] = base
            if head: kwargs["head"] = head
            prs = []
            for i, pr in enumerate(r.get_pulls(**kwargs)):
                if i >= limit: break
                prs.append(_summary(pr))
            return {"status": "ok", "repo": full, "count": len(prs), "prs": prs}
        except GithubException as e:
            return {"status": "error", "error": str(e)}

    @mcp.tool()
    def github_create_pr(
        repo: str,
        source_branch: str,
        target_branch: str = "",
        title: str = "",
        body: str = "",
        draft: bool = False,
    ) -> dict:
        """Create a pull request.

        Args:
            repo: 'owner/repo' or just 'repo'.
            source_branch: Branch with the changes.
            target_branch: Branch to merge into. Defaults to default branch.
            title: PR title. Defaults to last commit subject.
            body: PR body (markdown).
            draft: True for a draft PR.
        """
        gh = _gh()
        full = _resolve(repo, gh)
        try:
            r = gh.get_repo(full)
            target = target_branch or r.default_branch
            if not title:
                # Get last commit on source branch
                commit = r.get_branch(source_branch).commit
                title = commit.commit.message.splitlines()[0]
            pr = r.create_pull(title=title, body=body, head=source_branch, base=target, draft=draft)
            return {"status": "ok", **_summary(pr)}
        except GithubException as e:
            return {"status": "error", "error": str(e), "data": getattr(e, "data", None)}

    @mcp.tool()
    def github_get_pr(repo: str, pr_number: int) -> dict:
        """Get full details for a single PR, including review status.

        Args:
            repo: 'owner/repo' or just 'repo'.
            pr_number: PR number.
        """
        gh = _gh()
        full = _resolve(repo, gh)
        try:
            r = gh.get_repo(full)
            pr = r.get_pull(pr_number)
            reviews = [
                {"reviewer": rv.user.login if rv.user else None, "state": rv.state,
                 "body": rv.body, "submitted_at": str(rv.submitted_at) if rv.submitted_at else None}
                for rv in pr.get_reviews()
            ]
            return {"status": "ok", **_summary(pr), "body": pr.body, "reviews": reviews}
        except GithubException as e:
            return {"status": "error", "error": str(e)}

    @mcp.tool()
    def github_review_pr(
        repo: str,
        pr_number: int,
        event: str = "COMMENT",
        body: str = "",
    ) -> dict:
        """Submit a review on a PR.

        Args:
            repo: 'owner/repo' or just 'repo'.
            pr_number: PR number.
            event: 'APPROVE' | 'REQUEST_CHANGES' | 'COMMENT'.
            body: Review body (required for REQUEST_CHANGES + COMMENT).
        """
        gh = _gh()
        full = _resolve(repo, gh)
        try:
            r = gh.get_repo(full)
            pr = r.get_pull(pr_number)
            review = pr.create_review(event=event, body=body)
            return {"status": "ok", "id": review.id, "state": review.state}
        except GithubException as e:
            return {"status": "error", "error": str(e)}

    @mcp.tool()
    def github_merge_pr(
        repo: str,
        pr_number: int,
        method: str = "merge",
        commit_title: str = "",
        commit_message: str = "",
    ) -> dict:
        """Merge a PR.

        Args:
            repo: 'owner/repo' or just 'repo'.
            pr_number: PR number.
            method: 'merge' | 'squash' | 'rebase'.
            commit_title: Override merge commit title (squash/merge only).
            commit_message: Override merge commit message body.
        """
        gh = _gh()
        full = _resolve(repo, gh)
        try:
            r = gh.get_repo(full)
            pr = r.get_pull(pr_number)
            if not pr.mergeable:
                return {"status": "error", "error": "PR is not mergeable (conflicts? failing checks?)"}
            kwargs = {"merge_method": method}
            if commit_title:   kwargs["commit_title"] = commit_title
            if commit_message: kwargs["commit_message"] = commit_message
            result = pr.merge(**kwargs)
            return {"status": "ok", "merged": result.merged, "sha": result.sha, "message": result.message}
        except GithubException as e:
            return {"status": "error", "error": str(e)}

    @mcp.tool()
    def github_close_pr(repo: str, pr_number: int, comment: str = "") -> dict:
        """Close a PR without merging.

        Args:
            repo: 'owner/repo' or just 'repo'.
            pr_number: PR number.
            comment: Optional comment before closing.
        """
        gh = _gh()
        full = _resolve(repo, gh)
        try:
            r = gh.get_repo(full)
            pr = r.get_pull(pr_number)
            if comment:
                pr.create_issue_comment(comment)
            pr.edit(state="closed")
            return {"status": "ok", **_summary(pr)}
        except GithubException as e:
            return {"status": "error", "error": str(e)}
