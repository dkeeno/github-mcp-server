# GitHub MCP Server

A Model Context Protocol server that lets Claude Code (or any MCP client) operate GitHub end-to-end: repos, pushes, releases, GitHub Actions, issues, PRs, secrets, security, profile, and search.

Mirrors the design of the sister `gitlab-mcp-server` — same modular `tools/` layout, same auth-via-`.env` pattern, same `register(mcp)` per module.

## What it does

| Category | Examples |
|---|---|
| **Portfolio launch** (the hero tool) | `github_push_portfolio` — loops over every subfolder of a directory, creates each as a GitHub repo, commits, pushes |
| **Repo lifecycle** | create / update / delete / list / archive / transfer |
| **Push & file ops** | init-and-push, single-file edit, atomic batch commit, token-sanitized clone |
| **Discoverability** | topics, homepage, description, README badges, GitHub Pages |
| **Releases** | create + auto-generate release notes |
| **Issues & PRs** | create / list / comment / close / merge / review |
| **GitHub Actions** | list / trigger / cancel / rerun / get logs / **analyze workflow failure** / scaffold ci.yml |
| **Secrets & variables** | repo + org level |
| **Security** | enable Dependabot / secret scanning / code scanning, branch protection, audit |
| **Profile** | bio, profile README, pinned repos, stats |
| **Community** | stars, stargazers, traffic |
| **Search** | repos / code / users |
| **Token lifecycle** | validate auth, check scopes, list PATs |

## Install

```bash
cd ~/.mcp-servers/github-mcp-server
pip install -r requirements.txt
cp .env.example .env
# Edit .env — set GITHUB_TOKEN to your fine-grained PAT
```

## Configure Claude Code

Add to `~/.claude/settings.json`:

```json
{
  "mcpServers": {
    "github": {
      "command": "python3",
      "args": ["/Users/youruser/.mcp-servers/github-mcp-server/server.py"]
    }
  }
}
```

Restart Claude Code. The tools become available with the `mcp__github__` prefix.

## Quick start — push your entire portfolio in one command

After install + config, in a Claude Code session:

```
"Use github_validate_auth to confirm my token works."
"Use github_push_portfolio with parent_dir=/path/to/GITHUB-PROJECTS/projects, visibility=public, and topics auto-derived from each repo's README."
```

That's it. Each subfolder becomes a public GitHub repo, ready to share.

## Token scopes (fine-grained PAT)

| Scope | Why |
|---|---|
| Contents: write | Push code, edit files, create releases |
| Administration: write | Create / delete / archive repos, set topics, branch protection |
| Metadata: read | Repo metadata, search |
| Workflows: write | Trigger / cancel GitHub Actions |
| Pull requests: write | PR create / merge / review |
| Issues: write | Issue create / comment / close |
| Secrets: write | Set repo / org secrets |
| Pages: write | Enable GitHub Pages |

For Tier 1 (just portfolio push), only **Contents: write** + **Administration: write** + **Metadata: read** are required.

## Folder structure

```
github-mcp-server/
├── server.py                 # FastMCP entry, registers all tool modules
├── config.py                 # Loads GITHUB_TOKEN from .env
├── requirements.txt
├── .env.example
├── .gitignore
├── README.md                 # this file
└── tools/
    ├── __init__.py
    ├── github_repo.py        # create / update / list / delete / archive / transfer
    ├── github_push.py        # init_and_push, push_portfolio (hero tool)
    ├── github_files.py       # update_file, batch_commit, get_file, clone
    ├── github_meta.py        # topics, homepage, badges, Pages
    ├── github_releases.py    # release lifecycle + tags
    ├── github_actions.py     # workflows: trigger, status, logs, failure analyzer
    ├── github_issues.py      # issues + comments
    ├── github_prs.py         # PRs + reviews
    ├── github_secrets.py     # secrets + variables
    ├── github_security.py    # Dependabot, secret/code scanning, branch protection, audit
    ├── github_profile.py     # bio, profile README, pinned repos, stats
    ├── github_community.py   # stars, stargazers, traffic
    ├── github_search.py      # repo / code / user search
    └── github_tokens.py      # validate_auth, check_scopes, list_pats
```

## Compared to GitHub's official MCP

GitHub publishes their own [`github/github-mcp-server`](https://github.com/github/github-mcp-server). That one is more complete for general API surface; this one is **portfolio-workflow tuned**:

- `github_push_portfolio` (loops a folder) doesn't exist in the official one
- `github_analyze_workflow_failure` (log → root cause → suggested fix) is custom
- `github_audit_repo` (single call: protection on? Dependabot? README? license?) is custom
- The token lifecycle tooling matches the pattern that lets you avoid orphan-token leaks

Use whichever fits your workflow. They can coexist if you give them different MCP server names.

## License

MIT
