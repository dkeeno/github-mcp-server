"""Discoverability + metadata: topics, homepage, description, badges, Pages."""
from github import Github, GithubException, Auth
import config as cfg


def _gh() -> Github:
    return Github(auth=Auth.Token(cfg.GITHUB_TOKEN))


def _resolve(repo: str, gh: Github) -> str:
    return repo if "/" in repo else f"{gh.get_user().login}/{repo}"


def register(mcp):

    @mcp.tool()
    def github_set_topics(repo: str, topics: list[str]) -> dict:
        """Replace the topic tags on a repo (used for GitHub search ranking).

        Args:
            repo: 'owner/repo' or just 'repo'.
            topics: List of topics (lowercased, hyphens allowed). Replaces all existing topics.
        """
        gh = _gh()
        full = _resolve(repo, gh)
        try:
            r = gh.get_repo(full)
            r.replace_topics([t.lower() for t in topics])
            return {"status": "ok", "repo": full, "topics": list(r.get_topics())}
        except GithubException as e:
            return {"status": "error", "error": str(e)}

    @mcp.tool()
    def github_set_homepage(repo: str, url: str) -> dict:
        """Set the homepage URL displayed on the repo card.

        Args:
            repo: 'owner/repo' or just 'repo'.
            url: Project URL (your portfolio, docs site, demo).
        """
        gh = _gh()
        full = _resolve(repo, gh)
        try:
            r = gh.get_repo(full)
            r.edit(homepage=url)
            return {"status": "ok", "repo": full, "homepage": url}
        except GithubException as e:
            return {"status": "error", "error": str(e)}

    @mcp.tool()
    def github_set_description(repo: str, description: str) -> dict:
        """Set the short description shown under the repo title.

        Args:
            repo: 'owner/repo' or just 'repo'.
            description: One-sentence description.
        """
        gh = _gh()
        full = _resolve(repo, gh)
        try:
            r = gh.get_repo(full)
            r.edit(description=description)
            return {"status": "ok", "repo": full, "description": description}
        except GithubException as e:
            return {"status": "error", "error": str(e)}

    @mcp.tool()
    def github_add_readme_badges(
        repo: str,
        badges: list[dict] = None,
        position: str = "top",
        commit_message: str = "Add README badges",
    ) -> dict:
        """Inject markdown badge images at the top (or bottom) of the README.

        Args:
            repo: 'owner/repo' or just 'repo'.
            badges: List of {'label': str, 'image_url': str, 'link': str}.
                If None, sensible defaults are added: license, last commit, language.
            position: 'top' (just below the H1) or 'bottom'.
            commit_message: Commit message for the README change.
        """
        gh = _gh()
        full = _resolve(repo, gh)
        try:
            r = gh.get_repo(full)
            try:
                readme = r.get_readme()
                content = readme.decoded_content.decode("utf-8")
            except GithubException:
                return {"status": "error", "error": "no README found in repo"}

            owner, name = full.split("/", 1)
            if badges is None:
                badges = [
                    {
                        "label": "License",
                        "image_url": f"https://img.shields.io/github/license/{full}",
                        "link": f"https://github.com/{full}/blob/{r.default_branch}/LICENSE",
                    },
                    {
                        "label": "Last commit",
                        "image_url": f"https://img.shields.io/github/last-commit/{full}",
                        "link": f"https://github.com/{full}/commits/{r.default_branch}",
                    },
                    {
                        "label": "Top language",
                        "image_url": f"https://img.shields.io/github/languages/top/{full}",
                        "link": f"https://github.com/{full}",
                    },
                ]

            badge_md = " ".join(
                f"[![{b['label']}]({b['image_url']})]({b.get('link', b['image_url'])})"
                for b in badges
            )

            lines = content.splitlines()
            if position == "top":
                # insert just after the first H1 line
                inserted = False
                new_lines = []
                for ln in lines:
                    new_lines.append(ln)
                    if not inserted and ln.startswith("# "):
                        new_lines.append("")
                        new_lines.append(badge_md)
                        inserted = True
                if not inserted:
                    new_lines = [badge_md, ""] + new_lines
                new_content = "\n".join(new_lines) + "\n"
            else:
                new_content = content.rstrip() + "\n\n---\n\n" + badge_md + "\n"

            r.update_file(readme.path, commit_message, new_content, readme.sha)
            return {"status": "ok", "repo": full, "path": readme.path, "badges_added": len(badges)}
        except GithubException as e:
            return {"status": "error", "error": str(e)}

    @mcp.tool()
    def github_enable_pages(
        repo: str,
        branch: str = "",
        path: str = "/",
    ) -> dict:
        """Enable GitHub Pages on the repo, served from the given branch + path.

        Args:
            repo: 'owner/repo' or just 'repo'.
            branch: Source branch (default: repo default branch).
            path: '/' or '/docs'.
        """
        gh = _gh()
        full = _resolve(repo, gh)
        try:
            r = gh.get_repo(full)
            br = branch or r.default_branch
            r._requester.requestJsonAndCheck(
                "POST",
                f"{r.url}/pages",
                input={"source": {"branch": br, "path": path}, "build_type": "legacy"},
            )
            return {
                "status": "ok",
                "repo": full,
                "branch": br,
                "path": path,
                "pages_url": f"https://{full.split('/')[0]}.github.io/{full.split('/')[1]}/",
            }
        except GithubException as e:
            return {"status": "error", "error": str(e), "hint": "Pages may already be enabled."}
