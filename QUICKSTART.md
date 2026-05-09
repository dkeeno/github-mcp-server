# Quick Start — github-mcp-server

You're 3 steps from `github_push_portfolio` working end-to-end.

## 1. Create a GitHub PAT

Go to https://github.com/settings/personal-access-tokens → **Generate new token (fine-grained)**.

For Tier 1 (just push the portfolio), grant:

| Permission | Access |
|---|---|
| Contents | Read and write |
| Administration | Read and write |
| Metadata | Read-only |

For full feature set, also add:

| Permission | Access |
|---|---|
| Workflows | Read and write |
| Pull requests | Read and write |
| Issues | Read and write |
| Secrets | Read and write |
| Pages | Read and write |

Set expiry: 90 days. Repository access: **All repositories** (or limit to specific ones).

Copy the token (`github_pat_...`) — you only see it once.

## 2. Set the token

```bash
cd ~/.mcp-servers/github-mcp-server
cp .env.example .env
# Edit .env — set GITHUB_TOKEN=github_pat_...
```

## 3. Restart Claude Code

Quit and relaunch (so the MCP server picks up the new env). Then verify:

```
"Use github_validate_auth"
```

Should return your username, scopes, and rate-limit remaining.

## 4. Push your portfolio in one command

```
"Use github_push_portfolio with parent_dir=/Users/youruser/Documents/Base/DevOps-ClaudeAi/test-cases/SM1/freelance/GITHUB-PROJECTS/projects, visibility=public"
```

Then for the MCP servers folder:

```
"Use github_push_portfolio with parent_dir=/Users/youruser/Documents/Base/DevOps-ClaudeAi/test-cases/SM1/freelance/GITHUB-PROJECTS/mcp-servers, visibility=public"
```

That's it. 11 repos created + pushed in ~1 minute.

## Common follow-ups

```
"Pin my top 3 repos to my profile: aws-eks-production-terraform, gcp-gke-terraform-argocd-wif, gitlab-mcp-server"
"Update my GitHub profile bio to: 'AWS & GCP DevOps Engineer | Terraform, EKS, GKE, GitLab CI/CD, MCP & AI-DevOps'"
"Set the homepage of every repo I just pushed to https://my-portfolio-site.com"
"Run github_audit_repo on each of my new repos and tell me what's missing"
"Generate a Terraform CI workflow for every repo with .tf files"
"Create v0.1.0 releases on all 11 repos with auto-generated notes"
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| `github` shows "Failed to connect" in `claude mcp list` | GITHUB_TOKEN not set or invalid. Edit `.env` and restart Claude Code. |
| `pip install` errors on PyNaCl | macOS may need: `brew install libsodium` first |
| `github_set_secret` errors with "pynacl required" | `pip3 install pynacl` (already in requirements.txt) |
| 403 errors on push | Token lacks `Contents: write` on the target repo. Re-issue with broader scope. |
| 422 errors on create_repo | Repo name already exists. Set `skip_if_exists=True` or pick a different name. |
| Rate limit hit | Authenticated requests get 5,000/hr. Wait an hour or use a different token. |
