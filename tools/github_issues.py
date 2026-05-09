"""Issues + comments."""
from github import Github, GithubException, Auth
import config as cfg


def _gh() -> Github:
    return Github(auth=Auth.Token(cfg.GITHUB_TOKEN))


def _resolve(repo: str, gh: Github) -> str:
    return repo if "/" in repo else f"{gh.get_user().login}/{repo}"


def _summary(issue) -> dict:
    return {
        "number": issue.number,
        "title": issue.title,
        "state": issue.state,
        "labels": [l.name for l in issue.labels],
        "assignees": [a.login for a in issue.assignees],
        "author": issue.user.login if issue.user else None,
        "comments": issue.comments,
        "created_at": str(issue.created_at) if issue.created_at else None,
        "updated_at": str(issue.updated_at) if issue.updated_at else None,
        "html_url": issue.html_url,
    }


def register(mcp):

    @mcp.tool()
    def github_list_issues(
        repo: str,
        state: str = "open",
        labels: list[str] = None,
        assignee: str = "",
        limit: int = 30,
    ) -> dict:
        """List issues in a repo.

        Args:
            repo: 'owner/repo' or just 'repo'.
            state: 'open' | 'closed' | 'all'.
            labels: Filter by label names.
            assignee: Filter by assignee username, or '*' for any assignee, or 'none'.
            limit: Max issues to return.
        """
        gh = _gh()
        full = _resolve(repo, gh)
        try:
            r = gh.get_repo(full)
            kwargs = {"state": state}
            if labels:    kwargs["labels"] = labels
            if assignee:  kwargs["assignee"] = assignee
            issues = []
            for i, issue in enumerate(r.get_issues(**kwargs)):
                if i >= limit: break
                # Filter out PRs (GitHub returns them as issues too)
                if issue.pull_request: continue
                issues.append(_summary(issue))
            return {"status": "ok", "repo": full, "count": len(issues), "issues": issues}
        except GithubException as e:
            return {"status": "error", "error": str(e)}

    @mcp.tool()
    def github_create_issue(
        repo: str,
        title: str,
        body: str = "",
        labels: list[str] = None,
        assignees: list[str] = None,
    ) -> dict:
        """Create a new issue.

        Args:
            repo: 'owner/repo' or just 'repo'.
            title: Issue title.
            body: Issue body (markdown).
            labels: Label names (must already exist on the repo).
            assignees: Usernames to assign.
        """
        gh = _gh()
        full = _resolve(repo, gh)
        try:
            r = gh.get_repo(full)
            issue = r.create_issue(
                title=title,
                body=body,
                labels=labels or [],
                assignees=assignees or [],
            )
            return {"status": "ok", **_summary(issue)}
        except GithubException as e:
            return {"status": "error", "error": str(e)}

    @mcp.tool()
    def github_get_issue(repo: str, issue_number: int) -> dict:
        """Get full details for one issue, including comments.

        Args:
            repo: 'owner/repo' or just 'repo'.
            issue_number: Issue number.
        """
        gh = _gh()
        full = _resolve(repo, gh)
        try:
            r = gh.get_repo(full)
            issue = r.get_issue(issue_number)
            comments = [
                {
                    "author": c.user.login if c.user else None,
                    "body": c.body,
                    "created_at": str(c.created_at) if c.created_at else None,
                    "html_url": c.html_url,
                }
                for c in issue.get_comments()
            ]
            return {"status": "ok", **_summary(issue), "body": issue.body, "comments_data": comments}
        except GithubException as e:
            return {"status": "error", "error": str(e)}

    @mcp.tool()
    def github_comment_on_issue(repo: str, issue_number: int, body: str) -> dict:
        """Add a comment to an issue (or PR).

        Args:
            repo: 'owner/repo' or just 'repo'.
            issue_number: Issue or PR number.
            body: Comment body (markdown).
        """
        gh = _gh()
        full = _resolve(repo, gh)
        try:
            r = gh.get_repo(full)
            issue = r.get_issue(issue_number)
            comment = issue.create_comment(body)
            return {"status": "ok", "id": comment.id, "html_url": comment.html_url}
        except GithubException as e:
            return {"status": "error", "error": str(e)}

    @mcp.tool()
    def github_close_issue(
        repo: str,
        issue_number: int,
        reason: str = "completed",
        comment: str = "",
    ) -> dict:
        """Close an issue.

        Args:
            repo: 'owner/repo' or just 'repo'.
            issue_number: Issue number.
            reason: 'completed' or 'not_planned'.
            comment: Optional comment to post before closing.
        """
        gh = _gh()
        full = _resolve(repo, gh)
        try:
            r = gh.get_repo(full)
            issue = r.get_issue(issue_number)
            if comment:
                issue.create_comment(comment)
            issue.edit(state="closed", state_reason=reason)
            return {"status": "ok", **_summary(issue)}
        except GithubException as e:
            return {"status": "error", "error": str(e)}
