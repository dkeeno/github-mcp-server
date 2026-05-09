"""Remote file operations: update_file, batch_commit, get_file, clone."""
import base64
import os
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path

from github import Github, GithubException, InputGitTreeElement, Auth
import config as cfg


def _gh() -> Github:
    return Github(auth=Auth.Token(cfg.GITHUB_TOKEN))


def _resolve(repo: str, gh: Github) -> str:
    return repo if "/" in repo else f"{gh.get_user().login}/{repo}"


def register(mcp):

    @mcp.tool()
    def github_update_file(
        repo: str,
        path: str,
        content: str,
        commit_message: str,
        branch: str = "",
    ) -> dict:
        """Create or update a single file in a remote repo. No local clone needed.

        Args:
            repo: 'owner/repo' or just 'repo'.
            path: File path within the repo (e.g. 'README.md', 'src/app.py').
            content: New file content (full replacement).
            commit_message: Commit message.
            branch: Target branch. Defaults to the repo's default branch.
        """
        gh = _gh()
        full = _resolve(repo, gh)
        try:
            r = gh.get_repo(full)
            br = branch or r.default_branch

            try:
                existing = r.get_contents(path, ref=br)
                resp = r.update_file(path, commit_message, content, existing.sha, branch=br)
                action = "updated"
            except GithubException as e:
                if e.status != 404:
                    raise
                resp = r.create_file(path, commit_message, content, branch=br)
                action = "created"

            commit = resp["commit"]
            return {
                "status": "ok",
                "action": action,
                "repo": full,
                "path": path,
                "branch": br,
                "commit_sha": commit.sha,
                "commit_url": commit.html_url,
            }
        except GithubException as e:
            return {"status": "error", "error": str(e), "data": getattr(e, "data", None)}

    @mcp.tool()
    def github_batch_commit(
        repo: str,
        commit_message: str,
        files: list[dict],
        branch: str = "",
    ) -> dict:
        """Commit multiple file changes atomically in a single commit.

        Args:
            repo: 'owner/repo' or just 'repo'.
            commit_message: Commit message.
            files: List of {'path': str, 'content': str (None to delete)}.
            branch: Target branch. Defaults to the repo's default branch.
        """
        gh = _gh()
        full = _resolve(repo, gh)
        try:
            r = gh.get_repo(full)
            br = branch or r.default_branch
            ref = r.get_git_ref(f"heads/{br}")
            base_commit = r.get_git_commit(ref.object.sha)
            base_tree = base_commit.tree

            tree_elements = []
            for f in files:
                path = f["path"]
                content = f.get("content")
                if content is None:
                    tree_elements.append(InputGitTreeElement(path=path, mode="100644", type="blob", sha=None))
                else:
                    blob = r.create_git_blob(content, "utf-8")
                    tree_elements.append(InputGitTreeElement(path=path, mode="100644", type="blob", sha=blob.sha))

            new_tree = r.create_git_tree(tree_elements, base_tree)
            new_commit = r.create_git_commit(commit_message, new_tree, [base_commit])
            ref.edit(new_commit.sha)

            return {
                "status": "ok",
                "repo": full,
                "branch": br,
                "commit_sha": new_commit.sha,
                "commit_url": f"https://github.com/{full}/commit/{new_commit.sha}",
                "files_changed": len(files),
            }
        except GithubException as e:
            return {"status": "error", "error": str(e), "data": getattr(e, "data", None)}

    @mcp.tool()
    def github_get_file(repo: str, path: str, ref: str = "") -> dict:
        """Read a file from a remote repo without cloning.

        Args:
            repo: 'owner/repo' or just 'repo'.
            path: File path within the repo.
            ref: Branch / tag / commit SHA. Defaults to the repo's default branch.
        """
        gh = _gh()
        full = _resolve(repo, gh)
        try:
            r = gh.get_repo(full)
            ref = ref or r.default_branch
            content_obj = r.get_contents(path, ref=ref)
            text = base64.b64decode(content_obj.content).decode("utf-8", errors="replace")
            return {
                "status": "ok",
                "path": path,
                "ref": ref,
                "size": content_obj.size,
                "sha": content_obj.sha,
                "content": text,
            }
        except GithubException as e:
            return {"status": "error", "error": str(e), "status_code": getattr(e, "status", None)}

    @mcp.tool()
    def github_clone_repo(
        repo: str,
        destination: str = "",
        branch: str = "",
        depth: int = 0,
    ) -> dict:
        """Clone a GitHub repo locally. Token is sanitized from the resulting .git/config.

        Args:
            repo: 'owner/repo' or just 'repo'.
            destination: Absolute path. Defaults to ./<repo-basename> in cwd.
            branch: Optional branch/tag to checkout.
            depth: Optional shallow-clone depth (0 = full history).
        """
        gh = _gh()
        full = _resolve(repo, gh)
        try:
            r = gh.get_repo(full)
            dest = destination or os.path.join(os.getcwd(), full.split("/")[-1])
            dest = os.path.abspath(os.path.expanduser(dest))
            if Path(dest).exists() and any(Path(dest).iterdir()):
                return {"status": "error", "error": f"destination exists and is non-empty: {dest}"}

            # Token-injected URL for the clone, then sanitize after
            clone_url_with_token = r.clone_url.replace(
                "https://", f"https://x-access-token:{cfg.GITHUB_TOKEN}@", 1
            )
            cmd = ["git", "clone"]
            if depth and depth > 0:
                cmd += ["--depth", str(depth)]
            if branch:
                cmd += ["-b", branch]
            cmd += [clone_url_with_token, dest]

            proc = subprocess.run(cmd, capture_output=True, text=True)
            if proc.returncode != 0:
                err = proc.stderr.replace(cfg.GITHUB_TOKEN, "***REDACTED***")
                return {"status": "error", "error": f"git clone failed: {err}"}

            # Rewrite origin URL to remove the token
            subprocess.run(
                ["git", "remote", "set-url", "origin", r.clone_url],
                cwd=dest, capture_output=True,
            )

            return {
                "status": "ok",
                "destination": dest,
                "branch": branch or r.default_branch,
                "remote_url": r.clone_url,
            }
        except GithubException as e:
            return {"status": "error", "error": str(e)}
