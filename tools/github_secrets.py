"""Repo / org secrets and variables for GitHub Actions."""
import base64
import requests

try:
    from nacl import encoding, public
    _HAS_NACL = True
except ImportError:
    _HAS_NACL = False

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


def _encrypt_secret(public_key_b64: str, secret_value: str) -> str:
    """Encrypt a secret using libsodium sealed box (GitHub's required encryption)."""
    if not _HAS_NACL:
        raise RuntimeError("Install pynacl: pip install pynacl")
    public_key = public.PublicKey(public_key_b64.encode("utf-8"), encoding.Base64Encoder())
    sealed_box = public.SealedBox(public_key)
    encrypted = sealed_box.encrypt(secret_value.encode("utf-8"))
    return base64.b64encode(encrypted).decode("utf-8")


def register(mcp):

    @mcp.tool()
    def github_set_secret(repo: str, name: str, value: str) -> dict:
        """Create / update a repo secret for GitHub Actions.

        Note: requires `pynacl` for libsodium-encrypted secret payload.

        Args:
            repo: 'owner/repo' or just 'repo'.
            name: Secret name (uppercase, no spaces, max 1024 chars).
            value: Secret value.
        """
        if not _HAS_NACL:
            return {"status": "error", "error": "pip install pynacl required for github_set_secret"}
        gh = _gh()
        full = _resolve(repo, gh)
        try:
            key_resp = _api(f"/repos/{full}/actions/secrets/public-key")
            key_resp.raise_for_status()
            key_data = key_resp.json()
            encrypted = _encrypt_secret(key_data["key"], value)
            put_resp = _api(
                f"/repos/{full}/actions/secrets/{name}",
                method="PUT",
                json={"encrypted_value": encrypted, "key_id": key_data["key_id"]},
            )
            if put_resp.status_code in (201, 204):
                return {"status": "ok", "repo": full, "name": name,
                        "action": "created" if put_resp.status_code == 201 else "updated"}
            return {"status": "error", "error": f"HTTP {put_resp.status_code}: {put_resp.text[:200]}"}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    @mcp.tool()
    def github_list_secrets(repo: str) -> dict:
        """List repo secret NAMES (values are not retrievable from the API).

        Args:
            repo: 'owner/repo' or just 'repo'.
        """
        gh = _gh()
        full = _resolve(repo, gh)
        try:
            resp = _api(f"/repos/{full}/actions/secrets")
            resp.raise_for_status()
            data = resp.json()
            return {
                "status": "ok",
                "count": data.get("total_count", 0),
                "secrets": [{"name": s["name"], "updated_at": s["updated_at"]} for s in data.get("secrets", [])],
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    @mcp.tool()
    def github_delete_secret(repo: str, name: str) -> dict:
        """Delete a repo secret.

        Args:
            repo: 'owner/repo' or just 'repo'.
            name: Secret name.
        """
        gh = _gh()
        full = _resolve(repo, gh)
        try:
            resp = _api(f"/repos/{full}/actions/secrets/{name}", method="DELETE")
            return {"status": "ok" if resp.status_code == 204 else "error",
                    "http_status": resp.status_code}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    @mcp.tool()
    def github_set_variable(repo: str, name: str, value: str) -> dict:
        """Create / update a repo Actions variable (non-secret).

        Args:
            repo: 'owner/repo' or just 'repo'.
            name: Variable name (uppercase recommended).
            value: Variable value.
        """
        gh = _gh()
        full = _resolve(repo, gh)
        try:
            existing = _api(f"/repos/{full}/actions/variables/{name}")
            if existing.status_code == 200:
                resp = _api(f"/repos/{full}/actions/variables/{name}", method="PATCH",
                            json={"name": name, "value": value})
                action = "updated"
            else:
                resp = _api(f"/repos/{full}/actions/variables", method="POST",
                            json={"name": name, "value": value})
                action = "created"
            if resp.status_code in (201, 204):
                return {"status": "ok", "repo": full, "name": name, "action": action}
            return {"status": "error", "error": f"HTTP {resp.status_code}: {resp.text[:200]}"}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    @mcp.tool()
    def github_list_variables(repo: str) -> dict:
        """List repo Actions variables.

        Args:
            repo: 'owner/repo' or just 'repo'.
        """
        gh = _gh()
        full = _resolve(repo, gh)
        try:
            resp = _api(f"/repos/{full}/actions/variables")
            resp.raise_for_status()
            data = resp.json()
            return {
                "status": "ok",
                "count": data.get("total_count", 0),
                "variables": [{"name": v["name"], "value": v["value"]} for v in data.get("variables", [])],
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}
