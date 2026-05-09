"""Security & hygiene: Dependabot, secret scanning, code scanning, branch protection, audit."""
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


_DEPENDABOT_TEMPLATE = """version: 2
updates:
  - package-ecosystem: "{ecosystem}"
    directory: "/"
    schedule:
      interval: "weekly"
"""


def register(mcp):

    @mcp.tool()
    def github_set_branch_protection(
        repo: str,
        branch: str = "",
        require_pr_reviews: bool = True,
        required_approving_review_count: int = 1,
        require_status_checks: bool = False,
        required_status_check_contexts: list[str] = None,
        enforce_admins: bool = False,
        allow_force_pushes: bool = False,
        allow_deletions: bool = False,
    ) -> dict:
        """Set branch protection rules for a branch.

        Args:
            repo: 'owner/repo' or just 'repo'.
            branch: Branch name. Defaults to default branch.
            require_pr_reviews: Require pull request reviews before merging.
            required_approving_review_count: Number of required approving reviews.
            require_status_checks: Require status checks (e.g. CI) to pass.
            required_status_check_contexts: List of required check names.
            enforce_admins: Apply rules even to admins.
            allow_force_pushes: Allow force pushes (default False).
            allow_deletions: Allow deleting the branch (default False).
        """
        gh = _gh()
        full = _resolve(repo, gh)
        try:
            r = gh.get_repo(full)
            br = branch or r.default_branch

            payload = {
                "required_status_checks": ({
                    "strict": True,
                    "contexts": required_status_check_contexts or [],
                } if require_status_checks else None),
                "enforce_admins": enforce_admins,
                "required_pull_request_reviews": ({
                    "required_approving_review_count": required_approving_review_count,
                    "dismiss_stale_reviews": True,
                } if require_pr_reviews else None),
                "restrictions": None,
                "allow_force_pushes": allow_force_pushes,
                "allow_deletions": allow_deletions,
            }
            resp = _api(f"/repos/{full}/branches/{br}/protection", method="PUT", json=payload)
            if resp.status_code in (200, 201):
                return {"status": "ok", "repo": full, "branch": br, "protection": resp.json()}
            return {"status": "error", "error": f"HTTP {resp.status_code}: {resp.text[:300]}"}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    @mcp.tool()
    def github_get_branch_protection(repo: str, branch: str = "") -> dict:
        """Get the current protection rules on a branch.

        Args:
            repo: 'owner/repo' or just 'repo'.
            branch: Branch name. Defaults to default branch.
        """
        gh = _gh()
        full = _resolve(repo, gh)
        try:
            r = gh.get_repo(full)
            br = branch or r.default_branch
            resp = _api(f"/repos/{full}/branches/{br}/protection")
            if resp.status_code == 404:
                return {"status": "ok", "repo": full, "branch": br, "protected": False}
            if resp.status_code != 200:
                return {"status": "error", "error": f"HTTP {resp.status_code}"}
            return {"status": "ok", "repo": full, "branch": br, "protected": True, "rules": resp.json()}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    @mcp.tool()
    def github_remove_branch_protection(repo: str, branch: str = "") -> dict:
        """Remove protection on a branch.

        Args:
            repo: 'owner/repo' or just 'repo'.
            branch: Branch name. Defaults to default branch.
        """
        gh = _gh()
        full = _resolve(repo, gh)
        try:
            r = gh.get_repo(full)
            br = branch or r.default_branch
            resp = _api(f"/repos/{full}/branches/{br}/protection", method="DELETE")
            return {"status": "ok" if resp.status_code in (204, 200) else "error",
                    "http_status": resp.status_code}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    @mcp.tool()
    def github_enable_dependabot(
        repo: str,
        ecosystem: str = "github-actions",
        commit_message: str = "Enable Dependabot",
    ) -> dict:
        """Enable Dependabot version updates by committing .github/dependabot.yml.

        Args:
            repo: 'owner/repo' or just 'repo'.
            ecosystem: One of: github-actions, npm, pip, gomod, terraform, docker, bundler, cargo, etc.
            commit_message: Commit message.
        """
        gh = _gh()
        full = _resolve(repo, gh)
        try:
            r = gh.get_repo(full)
            content = _DEPENDABOT_TEMPLATE.format(ecosystem=ecosystem)
            try:
                existing = r.get_contents(".github/dependabot.yml", ref=r.default_branch)
                r.update_file(".github/dependabot.yml", commit_message, content, existing.sha)
                action = "updated"
            except GithubException:
                r.create_file(".github/dependabot.yml", commit_message, content)
                action = "created"
            return {"status": "ok", "action": action, "repo": full, "ecosystem": ecosystem}
        except GithubException as e:
            return {"status": "error", "error": str(e)}

    @mcp.tool()
    def github_enable_secret_scanning(repo: str) -> dict:
        """Enable GitHub secret scanning + push protection on a repo (public repos free; private may require GHAS).

        Args:
            repo: 'owner/repo' or just 'repo'.
        """
        gh = _gh()
        full = _resolve(repo, gh)
        try:
            payload = {
                "security_and_analysis": {
                    "secret_scanning": {"status": "enabled"},
                    "secret_scanning_push_protection": {"status": "enabled"},
                }
            }
            resp = _api(f"/repos/{full}", method="PATCH", json=payload)
            if resp.status_code in (200, 204):
                return {"status": "ok", "repo": full}
            return {"status": "error", "error": f"HTTP {resp.status_code}: {resp.text[:200]}"}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    @mcp.tool()
    def github_list_security_alerts(
        repo: str,
        type: str = "dependabot",
        state: str = "open",
        severity: str = "",
    ) -> dict:
        """List security alerts.

        Args:
            repo: 'owner/repo' or just 'repo'.
            type: 'dependabot' | 'secret-scanning' | 'code-scanning'.
            state: 'open' | 'fixed' | 'dismissed' | 'resolved'.
            severity: Optional severity filter for code-scanning ('critical', 'high', 'medium', 'low').
        """
        gh = _gh()
        full = _resolve(repo, gh)
        path_map = {
            "dependabot": f"/repos/{full}/dependabot/alerts",
            "secret-scanning": f"/repos/{full}/secret-scanning/alerts",
            "code-scanning": f"/repos/{full}/code-scanning/alerts",
        }
        if type not in path_map:
            return {"status": "error", "error": f"unknown type '{type}'"}
        try:
            params = {"state": state, "per_page": 50}
            if severity and type == "code-scanning":
                params["severity"] = severity
            resp = _api(path_map[type], params=params)
            if resp.status_code == 404:
                return {"status": "ok", "repo": full, "alerts": [], "note": "feature not enabled or no alerts"}
            resp.raise_for_status()
            return {"status": "ok", "repo": full, "type": type, "count": len(resp.json()), "alerts": resp.json()[:50]}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    @mcp.tool()
    def github_audit_repo(repo: str) -> dict:
        """Single-call repo health check: README, license, branch protection, Dependabot, secret scanning, etc.

        Args:
            repo: 'owner/repo' or just 'repo'.
        """
        gh = _gh()
        full = _resolve(repo, gh)
        report = {"repo": full, "checks": {}, "score": 0, "max_score": 0}

        try:
            r = gh.get_repo(full)
        except GithubException as e:
            return {"status": "error", "error": str(e)}

        def chk(name, ok, note=""):
            report["checks"][name] = {"ok": ok, "note": note}
            report["max_score"] += 1
            if ok:
                report["score"] += 1

        # README
        try:
            r.get_readme()
            chk("readme", True)
        except GithubException:
            chk("readme", False, "no README at the repo root")

        # LICENSE
        try:
            r.get_license()
            chk("license", True)
        except GithubException:
            chk("license", False, "no LICENSE file")

        # Description
        chk("description", bool(r.description), "" if r.description else "no description set")

        # Topics
        topics = list(r.get_topics())
        chk("topics", bool(topics), "" if topics else "no topics — search ranking suffers")

        # Homepage
        chk("homepage", bool(r.homepage), "" if r.homepage else "no homepage URL")

        # Branch protection
        prot = github_get_branch_protection.fn(repo=full)  # type: ignore[attr-defined]
        chk("branch_protection", prot.get("protected", False), "" if prot.get("protected") else "default branch unprotected")

        # Dependabot
        try:
            r.get_contents(".github/dependabot.yml", ref=r.default_branch)
            chk("dependabot", True)
        except GithubException:
            chk("dependabot", False, "no .github/dependabot.yml")

        # CI workflows
        try:
            workflows = r.get_contents(".github/workflows", ref=r.default_branch)
            has_wf = any(getattr(w, 'name', '').endswith(('.yml', '.yaml')) for w in (workflows if isinstance(workflows, list) else [workflows]))
            chk("ci_workflow", has_wf, "" if has_wf else "no .github/workflows/*.yml")
        except GithubException:
            chk("ci_workflow", False, "no .github/workflows/ directory")

        report["status"] = "ok"
        report["health_pct"] = round(100 * report["score"] / report["max_score"]) if report["max_score"] else 0
        return report
