#!/usr/bin/env python3
"""GitHub MCP Server — global Claude Code integration for GitHub.

Mirrors the design of gitlab-mcp-server. Capabilities are split into focused
tool modules under `tools/`, each with a `register(mcp)` function.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from mcp.server.fastmcp import FastMCP
import config as cfg

mcp = FastMCP(
    "github",
    instructions=(
        "GitHub MCP server. Capabilities:\n"
        "- Repository lifecycle: create, update, delete, list, archive, transfer\n"
        "- Push & file ops: init+push from a local folder, batch portfolio push, "
        "single-file remote edit, atomic batch commit, token-sanitized clone\n"
        "- Discoverability: topics, homepage URL, description, README badges, GitHub Pages\n"
        "- Releases & versioning: create_release, generate_release_notes, tags\n"
        "- Issues & PRs: create / list / comment / close / merge / review\n"
        "- GitHub Actions: list / trigger / cancel / rerun / get logs / "
        "analyze workflow failure (root-cause classification + suggested fix), "
        "scaffold .github/workflows/ci.yml from a template\n"
        "- Secrets & variables: repo + org-level\n"
        "- Security & hygiene: enable Dependabot / secret scanning / code scanning, "
        "branch protection, vulnerability listing, repo health audit\n"
        "- Profile: bio, profile README, pinned repos, follower stats\n"
        "- Community: stars, traffic, stargazers list\n"
        "- Search: repos / code / users\n"
        "- Token / auth lifecycle: validate auth, check token scopes, list PATs\n"
        "\n"
        "Hero tool for portfolio launch:\n"
        "  github_push_portfolio(parent_dir, visibility) — loops over every subfolder, "
        "creates the repo on GitHub, initializes git locally, commits, and pushes. "
        "One call deploys an entire portfolio.\n"
        "\n"
        "Auth: GITHUB_TOKEN env var (fine-grained PAT recommended). "
        "Validate with github_validate_auth before bulk operations."
    ),
)


def _load_tools():
    from tools import (
        github_repo,
        github_push,
        github_files,
        github_meta,
        github_releases,
        github_actions,
        github_issues,
        github_prs,
        github_secrets,
        github_security,
        github_profile,
        github_community,
        github_search,
        github_tokens,
    )
    github_repo.register(mcp)
    github_push.register(mcp)
    github_files.register(mcp)
    github_meta.register(mcp)
    github_releases.register(mcp)
    github_actions.register(mcp)
    github_issues.register(mcp)
    github_prs.register(mcp)
    github_secrets.register(mcp)
    github_security.register(mcp)
    github_profile.register(mcp)
    github_community.register(mcp)
    github_search.register(mcp)
    github_tokens.register(mcp)


if __name__ == "__main__":
    try:
        cfg.validate()
        _load_tools()
        mcp.run()
    except Exception as e:
        print(f"github-mcp-server failed to start: {e}", file=sys.stderr)
        sys.exit(1)
