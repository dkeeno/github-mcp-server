"""Push & portfolio bulk-deploy. The hero tools live here."""
import os
import re
import shlex
import subprocess
from pathlib import Path

from github import Github, GithubException, Auth
import config as cfg


def _gh() -> Github:
    return Github(auth=Auth.Token(cfg.GITHUB_TOKEN))


def _run(cmd: list[str], cwd: str = None, env: dict = None) -> tuple[int, str, str]:
    """Run a shell command, return (rc, stdout, stderr). Stdout/stderr decoded as utf-8."""
    proc = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True)
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def _is_git_repo(path: str) -> bool:
    return Path(path, ".git").exists()


def _git_init_commit_push(local_path: str, remote_url: str, branch: str, commit_message: str) -> dict:
    """Initialize git in local_path (if needed), commit everything, set remote, push.

    Token is injected into the remote URL only for the push, then the URL is rewritten
    to remove the token from .git/config.
    """
    if not Path(local_path).is_dir():
        return {"status": "error", "error": f"local_path does not exist: {local_path}"}

    if not _is_git_repo(local_path):
        rc, _, err = _run(["git", "init", "-b", branch], cwd=local_path)
        if rc != 0:
            return {"status": "error", "error": f"git init failed: {err}"}
    else:
        # Ensure we're on the requested branch (rename if necessary, soft).
        _run(["git", "checkout", "-B", branch], cwd=local_path)

    # Stage everything
    rc, _, err = _run(["git", "add", "-A"], cwd=local_path)
    if rc != 0:
        return {"status": "error", "error": f"git add failed: {err}"}

    # Check if there's anything to commit
    rc_status, status_out, _ = _run(["git", "status", "--porcelain"], cwd=local_path)
    if rc_status == 0 and not status_out:
        # Nothing to commit — but we still need to ensure a HEAD exists for push to work.
        rc_log, _, _ = _run(["git", "log", "-1", "--oneline"], cwd=local_path)
        if rc_log != 0:
            return {"status": "error", "error": "no files to commit and no prior commits"}
    else:
        rc, _, err = _run(
            ["git", "-c", "user.name=github-mcp-server",
             "-c", "user.email=mcp@local",
             "commit", "-m", commit_message],
            cwd=local_path,
        )
        if rc != 0:
            return {"status": "error", "error": f"git commit failed: {err}"}

    # Inject token into push URL (only for the push), don't persist it.
    if remote_url.startswith("https://"):
        push_url = remote_url.replace(
            "https://", f"https://x-access-token:{cfg.GITHUB_TOKEN}@", 1
        )
    else:
        push_url = remote_url

    # Add or update origin
    rc, _, _ = _run(["git", "remote", "remove", "origin"], cwd=local_path)
    rc, _, err = _run(["git", "remote", "add", "origin", remote_url], cwd=local_path)
    if rc != 0:
        return {"status": "error", "error": f"git remote add failed: {err}"}

    # Push using the token-injected URL (one-shot, never persisted)
    rc, out, err = _run(["git", "push", push_url, branch], cwd=local_path)
    if rc != 0:
        # Sanitize token from error before returning
        err = err.replace(cfg.GITHUB_TOKEN, "***REDACTED***") if cfg.GITHUB_TOKEN else err
        return {"status": "error", "error": f"git push failed: {err}"}

    return {"status": "ok", "branch": branch, "remote_url": remote_url}


def _topics_from_readme(local_path: str) -> list[str]:
    """Heuristic: derive topic tags from README content + folder name."""
    keywords = {
        "terraform": ["terraform", "tofu", "iac"],
        "aws": ["aws ", "amazon web", "eks", "ecr", "vpc", "lambda", "s3", "iam"],
        "gcp": ["gcp", "google cloud", "gke", "wif", "workload identity"],
        "kubernetes": ["kubernetes", "k8s", "kubectl", "helm"],
        "argocd": ["argocd", "argo cd", "gitops"],
        "mcp-server": ["mcp server", "model context protocol", "mcp tool"],
        "devops": ["ci/cd", "pipeline", "devops"],
        "docker": ["dockerfile", "docker build"],
        "python": ["import os\nimport", "pyproject", "requirements.txt"],
        "go": ["package main", "go.mod"],
        "nodejs": ["package.json", "express"],
    }
    text = ""
    readme = Path(local_path, "README.md")
    if readme.exists():
        try:
            text = readme.read_text(errors="ignore").lower()
        except Exception:
            pass
    text += " " + Path(local_path).name.lower()
    found = []
    for topic, kws in keywords.items():
        if any(kw in text for kw in kws):
            found.append(topic)
    return found[:15]


def register(mcp):

    @mcp.tool()
    def github_init_and_push(
        local_path: str,
        repo_name: str = "",
        description: str = "",
        visibility: str = "",
        branch: str = "main",
        commit_message: str = "Initial commit",
        topics: list[str] = None,
        homepage: str = "",
        org: str = "",
        skip_if_exists: bool = True,
    ) -> dict:
        """Create a GitHub repo + git init + commit + push, in one call.

        Args:
            local_path: Absolute path to the local folder to push.
            repo_name: Repo name on GitHub. Defaults to basename(local_path).
            description: Repo description.
            visibility: 'public' | 'private' | 'internal'. Defaults to DEFAULT_REPO_VISIBILITY.
            branch: Branch name (default 'main').
            commit_message: Initial commit message.
            topics: Topic tags. If None, derived heuristically from README + folder name.
            homepage: Repo card URL.
            org: Push under an organization instead of the user.
            skip_if_exists: If a repo with the same name exists, return its details
                instead of failing. Useful when re-running portfolio pushes.
        """
        local_path = os.path.abspath(os.path.expanduser(local_path))
        if not Path(local_path).is_dir():
            return {"status": "error", "error": f"local_path does not exist: {local_path}"}

        repo_name = repo_name or Path(local_path).name
        gh = _gh()
        owner_login = (gh.get_organization(org).login if org else gh.get_user().login)
        full = f"{owner_login}/{repo_name}"

        # Try to find existing repo
        existing = None
        try:
            existing = gh.get_repo(full)
        except GithubException:
            pass

        if existing and skip_if_exists:
            repo = existing
        elif existing and not skip_if_exists:
            return {"status": "error", "error": f"repo {full} already exists; skip_if_exists=False"}
        else:
            vis = (visibility or cfg.DEFAULT_REPO_VISIBILITY).lower()
            try:
                owner = gh.get_organization(org) if org else gh.get_user()
                repo = owner.create_repo(
                    name=repo_name,
                    description=description,
                    homepage=homepage,
                    private=vis in ("private", "internal"),
                    has_issues=True,
                    has_wiki=False,
                    has_projects=False,
                    auto_init=False,
                )
            except GithubException as e:
                return {"status": "error", "error": f"create_repo failed: {e}"}

        # Apply topics
        chosen_topics = topics if topics is not None else _topics_from_readme(local_path)
        if chosen_topics:
            try:
                repo.replace_topics([t.lower() for t in chosen_topics])
            except GithubException:
                pass

        # Initialize git + push
        push_result = _git_init_commit_push(local_path, repo.clone_url, branch, commit_message)

        return {
            "status": push_result["status"],
            "repo": full,
            "html_url": repo.html_url,
            "branch": branch,
            "topics": chosen_topics,
            "push": push_result,
        }

    @mcp.tool()
    def github_push_portfolio(
        parent_dir: str,
        visibility: str = "public",
        branch: str = "main",
        commit_message: str = "Initial portfolio publish",
        org: str = "",
        topics_per_repo: dict = None,
        homepage_per_repo: dict = None,
        skip_dirs: list[str] = None,
    ) -> dict:
        """Push every immediate subdirectory of `parent_dir` as its own GitHub repo.

        Hero tool. One call deploys an entire portfolio (e.g. 11 repos in 1 minute).

        Args:
            parent_dir: Absolute path to a folder containing repo-shaped subfolders.
                E.g. '/Users/me/portfolio/projects' (with subfolders that each become a repo).
            visibility: Default visibility for all repos created.
            branch: Branch name to push to.
            commit_message: Initial commit message.
            org: Push under an organization instead of the authenticated user.
            topics_per_repo: Optional override map: {'repo-name': ['topic1','topic2']}.
                If a repo isn't in the map, topics are derived heuristically.
            homepage_per_repo: Optional map: {'repo-name': 'https://...'}.
            skip_dirs: List of directory names to skip (e.g. ['scratch', 'tmp']).
        """
        parent_dir = os.path.abspath(os.path.expanduser(parent_dir))
        if not Path(parent_dir).is_dir():
            return {"status": "error", "error": f"parent_dir does not exist: {parent_dir}"}

        skip = set(skip_dirs or [])
        topics_map = topics_per_repo or {}
        homepage_map = homepage_per_repo or {}

        results = []
        succeeded = []
        failed = []
        skipped = []

        for entry in sorted(Path(parent_dir).iterdir()):
            if not entry.is_dir():
                continue
            if entry.name in skip or entry.name.startswith("."):
                skipped.append(entry.name)
                continue

            res = github_init_and_push.fn(  # type: ignore[attr-defined]
                local_path=str(entry),
                repo_name=entry.name,
                visibility=visibility,
                branch=branch,
                commit_message=commit_message,
                topics=topics_map.get(entry.name),
                homepage=homepage_map.get(entry.name, ""),
                org=org,
                skip_if_exists=True,
            )
            results.append({"folder": entry.name, **{k: v for k, v in res.items() if k != "push"}})
            if res.get("status") == "ok":
                succeeded.append(entry.name)
            else:
                failed.append({"folder": entry.name, "error": res.get("error", res.get("push", {}))})

        return {
            "status": "complete" if not failed else "partial",
            "parent_dir": parent_dir,
            "succeeded": succeeded,
            "failed": failed,
            "skipped": skipped,
            "results": results,
        }
