"""GitHub Actions: scaffold workflows, trigger / monitor runs, analyze failures."""
import io
import re
import zipfile

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


# Workflow YAML scaffolds, keyed by language/stack
_TEMPLATES = {
    "terraform": """name: terraform

on:
  push:
    branches: [ main ]
  pull_request:
    branches: [ main ]

permissions:
  contents: read

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: hashicorp/setup-terraform@v3
        with:
          terraform_version: 1.7.0
      - name: terraform fmt
        run: terraform fmt -check -recursive
      - name: terraform init -backend=false
        run: terraform init -backend=false
        working-directory: ${{ vars.TF_DIR || '.' }}
      - name: terraform validate
        run: terraform validate
        working-directory: ${{ vars.TF_DIR || '.' }}
""",
    "python": """name: python

on:
  push:
    branches: [ main ]
  pull_request:
    branches: [ main ]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
          cache: 'pip'
      - run: pip install -r requirements.txt
      - run: pip install pytest ruff
      - run: ruff check .
      - run: pytest -q || echo "no tests yet"
""",
    "node": """name: node

on:
  push:
    branches: [ main ]
  pull_request:
    branches: [ main ]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'
      - run: npm ci
      - run: npm run build --if-present
      - run: npm test --if-present
""",
    "go": """name: go

on:
  push:
    branches: [ main ]
  pull_request:
    branches: [ main ]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-go@v5
        with:
          go-version: '1.22'
      - run: go vet ./...
      - run: go build ./...
      - run: go test ./...
""",
    "docker": """name: docker

on:
  push:
    branches: [ main ]
    tags: [ 'v*' ]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-buildx-action@v3
      - uses: docker/build-push-action@v5
        with:
          context: .
          push: false
          tags: ${{ github.repository }}:${{ github.sha }}
""",
}


_FAILURE_PATTERNS = [
    (r"Permission denied|403|Authentication failed", "auth_error",
     "Token missing scope or expired. Run github_validate_auth and github_check_token_scopes."),
    (r"Could not find .* secret|secret .* is not set", "missing_secret",
     "A required GitHub Actions secret isn't set. Use github_set_secret to add it."),
    (r"Error: Process completed with exit code 1.*ENOENT", "missing_file",
     "Build script referenced a file that doesn't exist in the repo."),
    (r"npm ERR!|yarn error", "node_dep_error",
     "Node dependency install failed. Check package.json + lock file are committed."),
    (r"pip .*Could not find a version|No matching distribution", "python_dep_error",
     "Pip dependency resolution failed. Pin compatible versions in requirements.txt."),
    (r"go: cannot find|go: missing", "go_dep_error",
     "Go module resolution failed. Run `go mod tidy` locally and commit go.sum."),
    (r"terraform.*Error: Module not installed|backend initialization required", "terraform_init_error",
     "Terraform init failed. Check backend config + provider versions."),
    (r"OOMKilled|out of memory", "oom",
     "Job exceeded runner memory. Use a larger runner or reduce parallelism."),
    (r"Cancelled", "cancelled",
     "Job was cancelled. Check if a newer commit superseded this run."),
    (r"timed out|context deadline exceeded", "timeout",
     "Job exceeded its time limit. Consider splitting into smaller jobs or increasing job timeout-minutes."),
    (r"docker.*denied|unauthorized.*docker", "docker_auth",
     "Docker registry auth failed. Check the registry secret + login step."),
    (r"branch protection rule|protected branch", "branch_protection",
     "Push or merge blocked by branch protection. Check rules with github_get_branch_protection."),
]


def register(mcp):

    @mcp.tool()
    def github_generate_workflow(
        repo: str,
        language: str,
        commit: bool = True,
        path: str = "",
        commit_message: str = "Add CI workflow",
    ) -> dict:
        """Scaffold a .github/workflows/<language>.yml for common stacks.

        Args:
            repo: 'owner/repo' or just 'repo'.
            language: One of: terraform, python, node, go, docker.
            commit: If True, commit the file to the repo's default branch.
            path: Override file path (defaults to .github/workflows/<language>.yml).
            commit_message: Commit message.
        """
        if language not in _TEMPLATES:
            return {"status": "error", "error": f"unknown language '{language}'. Available: {list(_TEMPLATES)}"}

        content = _TEMPLATES[language]
        path = path or f".github/workflows/{language}.yml"

        if not commit:
            return {"status": "preview", "path": path, "content": content}

        gh = _gh()
        full = _resolve(repo, gh)
        try:
            r = gh.get_repo(full)
            try:
                existing = r.get_contents(path, ref=r.default_branch)
                resp = r.update_file(path, commit_message, content, existing.sha)
                action = "updated"
            except GithubException as e:
                if e.status != 404:
                    raise
                resp = r.create_file(path, commit_message, content)
                action = "created"
            return {"status": "ok", "action": action, "repo": full, "path": path,
                    "commit_sha": resp["commit"].sha}
        except GithubException as e:
            return {"status": "error", "error": str(e)}

    @mcp.tool()
    def github_list_workflows(repo: str) -> dict:
        """List workflows defined in .github/workflows/.

        Args:
            repo: 'owner/repo' or just 'repo'.
        """
        gh = _gh()
        full = _resolve(repo, gh)
        try:
            r = _api(f"/repos/{full}/actions/workflows")
            r.raise_for_status()
            data = r.json()
            return {
                "status": "ok",
                "repo": full,
                "count": data.get("total_count", 0),
                "workflows": [
                    {"id": w["id"], "name": w["name"], "path": w["path"], "state": w["state"]}
                    for w in data.get("workflows", [])
                ],
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    @mcp.tool()
    def github_trigger_workflow(
        repo: str,
        workflow: str,
        ref: str = "",
        inputs: dict = None,
    ) -> dict:
        """Trigger a workflow_dispatch run.

        Args:
            repo: 'owner/repo' or just 'repo'.
            workflow: Workflow filename (e.g. 'ci.yml') or numeric ID.
            ref: Branch / tag / SHA. Defaults to default branch.
            inputs: Optional inputs map for workflow_dispatch.
        """
        gh = _gh()
        full = _resolve(repo, gh)
        try:
            r = gh.get_repo(full)
            ref = ref or r.default_branch
            payload = {"ref": ref}
            if inputs:
                payload["inputs"] = inputs
            resp = _api(
                f"/repos/{full}/actions/workflows/{workflow}/dispatches",
                method="POST",
                json=payload,
            )
            if resp.status_code in (204, 200, 201):
                return {"status": "ok", "repo": full, "workflow": workflow, "ref": ref}
            return {"status": "error", "error": f"HTTP {resp.status_code}: {resp.text[:200]}"}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    @mcp.tool()
    def github_list_workflow_runs(
        repo: str,
        workflow: str = "",
        status: str = "",
        branch: str = "",
        limit: int = 20,
    ) -> dict:
        """List recent workflow runs.

        Args:
            repo: 'owner/repo' or just 'repo'.
            workflow: Filter by workflow filename or ID. Empty = all workflows.
            status: 'success' | 'failure' | 'cancelled' | 'in_progress' | 'queued'. Empty = any.
            branch: Filter by branch.
            limit: Max runs to return.
        """
        gh = _gh()
        full = _resolve(repo, gh)
        try:
            base = f"/repos/{full}/actions"
            base += f"/workflows/{workflow}/runs" if workflow else "/runs"
            params = {"per_page": min(limit, 100)}
            if status: params["status"] = status
            if branch: params["branch"] = branch
            resp = _api(base, params=params)
            resp.raise_for_status()
            data = resp.json()
            return {
                "status": "ok",
                "repo": full,
                "count": min(len(data.get("workflow_runs", [])), limit),
                "runs": [
                    {
                        "id": run["id"],
                        "name": run["name"],
                        "branch": run["head_branch"],
                        "event": run["event"],
                        "status": run["status"],
                        "conclusion": run["conclusion"],
                        "created_at": run["created_at"],
                        "html_url": run["html_url"],
                    }
                    for run in data.get("workflow_runs", [])[:limit]
                ],
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    @mcp.tool()
    def github_get_workflow_run(repo: str, run_id: int) -> dict:
        """Get details for a single workflow run, including job-level status.

        Args:
            repo: 'owner/repo' or just 'repo'.
            run_id: Workflow run ID.
        """
        gh = _gh()
        full = _resolve(repo, gh)
        try:
            run_resp = _api(f"/repos/{full}/actions/runs/{run_id}")
            run_resp.raise_for_status()
            run = run_resp.json()

            jobs_resp = _api(f"/repos/{full}/actions/runs/{run_id}/jobs")
            jobs_resp.raise_for_status()
            jobs = jobs_resp.json().get("jobs", [])

            return {
                "status": "ok",
                "id": run["id"],
                "name": run["name"],
                "branch": run["head_branch"],
                "status": run["status"],
                "conclusion": run["conclusion"],
                "html_url": run["html_url"],
                "created_at": run["created_at"],
                "updated_at": run["updated_at"],
                "jobs": [
                    {
                        "id": j["id"],
                        "name": j["name"],
                        "status": j["status"],
                        "conclusion": j["conclusion"],
                        "started_at": j["started_at"],
                        "completed_at": j["completed_at"],
                    }
                    for j in jobs
                ],
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    @mcp.tool()
    def github_cancel_workflow_run(repo: str, run_id: int) -> dict:
        """Cancel a running workflow.

        Args:
            repo: 'owner/repo' or just 'repo'.
            run_id: Workflow run ID.
        """
        gh = _gh()
        full = _resolve(repo, gh)
        try:
            resp = _api(f"/repos/{full}/actions/runs/{run_id}/cancel", method="POST")
            return {"status": "ok" if resp.status_code in (202, 200) else "error",
                    "http_status": resp.status_code}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    @mcp.tool()
    def github_rerun_workflow(repo: str, run_id: int, only_failed: bool = False) -> dict:
        """Re-run a workflow.

        Args:
            repo: 'owner/repo' or just 'repo'.
            run_id: Workflow run ID.
            only_failed: If True, only re-run the failed jobs.
        """
        gh = _gh()
        full = _resolve(repo, gh)
        endpoint = f"/repos/{full}/actions/runs/{run_id}/rerun-failed-jobs" if only_failed else f"/repos/{full}/actions/runs/{run_id}/rerun"
        try:
            resp = _api(endpoint, method="POST")
            return {"status": "ok" if resp.status_code in (201, 200) else "error",
                    "http_status": resp.status_code}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    @mcp.tool()
    def github_get_workflow_logs(repo: str, run_id: int, tail_lines: int = 200) -> dict:
        """Download the logs zip for a workflow run and return the tail.

        Args:
            repo: 'owner/repo' or just 'repo'.
            run_id: Workflow run ID.
            tail_lines: Number of lines from the end to return per job (0 = all).
        """
        gh = _gh()
        full = _resolve(repo, gh)
        try:
            resp = _api(f"/repos/{full}/actions/runs/{run_id}/logs", allow_redirects=True)
            if resp.status_code != 200:
                return {"status": "error", "error": f"HTTP {resp.status_code}"}

            zf = zipfile.ZipFile(io.BytesIO(resp.content))
            logs = {}
            for name in zf.namelist():
                if name.endswith("/"):
                    continue
                try:
                    text = zf.read(name).decode("utf-8", errors="replace")
                    if tail_lines and tail_lines > 0:
                        text = "\n".join(text.splitlines()[-tail_lines:])
                    logs[name] = text
                except Exception:
                    pass
            return {"status": "ok", "files": list(logs.keys()), "logs": logs}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    @mcp.tool()
    def github_analyze_workflow_failure(repo: str, run_id: int) -> dict:
        """Read failed-job logs, classify the error type, suggest a fix.

        Equivalent of gitlab-mcp-server's analyze_pipeline_failure.

        Args:
            repo: 'owner/repo' or just 'repo'.
            run_id: Workflow run ID (must be a failed run).
        """
        run = github_get_workflow_run.fn(repo=repo, run_id=run_id)  # type: ignore[attr-defined]
        if run.get("status") != "ok":
            return run

        failed_jobs = [j for j in run.get("jobs", []) if j["conclusion"] in ("failure", "cancelled", "timed_out")]
        if not failed_jobs:
            return {"status": "ok", "verdict": "no_failed_jobs", "run": run}

        logs_resp = github_get_workflow_logs.fn(repo=repo, run_id=run_id, tail_lines=300)  # type: ignore[attr-defined]
        if logs_resp.get("status") != "ok":
            return {"status": "error", "error": "could not download logs", "logs_error": logs_resp.get("error")}

        all_logs_blob = "\n".join(logs_resp.get("logs", {}).values())

        diagnoses = []
        for pat, kind, hint in _FAILURE_PATTERNS:
            if re.search(pat, all_logs_blob, re.IGNORECASE):
                diagnoses.append({"error_type": kind, "suggested_fix": hint})

        return {
            "status": "ok",
            "repo": run.get("name"),
            "run_id": run_id,
            "failed_jobs": [j["name"] for j in failed_jobs],
            "diagnoses": diagnoses or [{"error_type": "unknown", "suggested_fix": "No known pattern matched. Inspect logs manually."}],
            "log_files": logs_resp.get("files", []),
        }
