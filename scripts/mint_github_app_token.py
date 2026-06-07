#!/usr/bin/env python3
"""Mint a short-lived GitHub App installation access token.

The local GitHub MCP server (``ghcr.io/github/github-mcp-server``) is launched
by ``scripts/mcp_github_launch.sh`` on every (re)start. Instead of handing the
server a long-lived personal access token, the wrapper calls this module to
mint a fresh GitHub App *installation* token at launch time. Installation
tokens expire after about an hour, so binding the mint to the launch keeps the
credential current without any operator handoff (Refs #1063).

Inputs come from the environment only -- nothing is read from a tracked file:

* ``GITHUB_APP_ID`` -- the numeric App id (the JWT ``iss`` claim).
* ``GITHUB_APP_INSTALLATION_ID`` -- the installation to mint a token for.
* ``GITHUB_APP_PRIVATE_KEY`` -- the App private key, PEM text. This is the only
  root secret; it is held in memory, written to a ``0600`` temp file only for
  the duration of the openssl signing call, and removed immediately after.
* ``GITHUB_APP_PRIVATE_KEY_FILE`` -- optional path to a file holding the PEM
  (e.g. a Vault Agent template sink). Used only when ``GITHUB_APP_PRIVATE_KEY``
  is unset; the literal env var takes precedence.
* ``GITHUB_API_URL`` -- optional API base (default ``https://api.github.com``)
  for GitHub Enterprise Server installs.

The minted token is written to stdout and nowhere else. The JWT, the private
key, and the token are never logged, echoed to stderr, or placed on a command
line (CLAUDE.md section 4). RS256 signing shells out to ``openssl`` so the
script adds no third-party dependency to this repo.

Least privilege is enforced at App-installation time (see
``docs/standards/github-mcp-app-auth.md``); this module requests the
installation's full granted permission set and does not widen it.
"""

from __future__ import annotations

import base64
import contextlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_API_URL = "https://api.github.com"
# GitHub rejects App JWTs whose lifetime exceeds 10 minutes. Stay under that
# with a small backdated ``iat`` to tolerate minor clock skew between the
# minting host and GitHub.
_JWT_BACKDATE_SECONDS = 60
# 8 minutes forward + 1 minute backdate = a 9-minute span, comfortably inside
# GitHub's 10-minute App-JWT ceiling even with clock skew at both ends.
_JWT_LIFETIME_SECONDS = 8 * 60


class MintError(RuntimeError):
    """A credential is missing or the token could not be minted.

    Carries an operator-facing message that names *what* failed without ever
    embedding the private key, the JWT, or the token value.
    """


def _b64url(raw: bytes) -> str:
    """Return base64url text without padding, per the JWS spec."""
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _sign_rs256(signing_input: bytes, private_key_pem: str) -> bytes:
    """Return the RS256 signature of *signing_input* using *private_key_pem*.

    The PEM is written to a ``0600`` temp file because ``openssl dgst -sign``
    reads the key from a path while the data to sign arrives on stdin. The file
    is removed in ``finally`` so the key never outlives the call on disk.
    """
    openssl = shutil.which("openssl")
    if openssl is None:
        raise MintError("openssl is not installed; it is required to sign the App JWT")
    fd, key_path = tempfile.mkstemp(prefix="gh_app_key_", suffix=".pem")
    try:
        os.write(fd, private_key_pem.encode("utf-8"))
        os.close(fd)
        completed = subprocess.run(  # noqa: S603 -- fixed argv (no shell); key path and data are not shell-interpolated
            [openssl, "dgst", "-sha256", "-sign", key_path],
            input=signing_input,
            capture_output=True,
            check=False,
        )
    finally:
        # Best-effort removal of the on-disk key material.
        with contextlib.suppress(OSError):
            Path(key_path).unlink()
    if completed.returncode != 0:
        # openssl writes parse errors (not key material) to stderr; surface a
        # generic message rather than echoing it, in case a key fragment leaks.
        raise MintError("openssl failed to sign the App JWT; check that GITHUB_APP_PRIVATE_KEY is a valid PEM key")
    return completed.stdout


def build_jwt(app_id: str, private_key_pem: str, *, now: int | None = None) -> str:
    """Build a signed RS256 JWT asserting the App identity.

    *now* is injectable so tests can pin the time window deterministically.
    """
    issued_at = int(time.time()) if now is None else now
    header = {"alg": "RS256", "typ": "JWT"}
    payload = {
        "iat": issued_at - _JWT_BACKDATE_SECONDS,
        "exp": issued_at + _JWT_LIFETIME_SECONDS,
        "iss": app_id,
    }
    segments = [
        _b64url(json.dumps(header, separators=(",", ":")).encode("utf-8")),
        _b64url(json.dumps(payload, separators=(",", ":")).encode("utf-8")),
    ]
    signing_input = ".".join(segments).encode("ascii")
    signature = _sign_rs256(signing_input, private_key_pem)
    segments.append(_b64url(signature))
    return ".".join(segments)


def request_installation_token(
    jwt_token: str,
    installation_id: str,
    *,
    api_url: str = DEFAULT_API_URL,
) -> str:
    """Exchange an App JWT for an installation access token.

    Returns the token string. Raises :class:`MintError` on any HTTP, network,
    or response-shape failure -- never returning an empty or partial token.
    """
    if not api_url.startswith("https://"):
        # Refuse to send the App JWT (a bearer credential) over cleartext. A
        # typo'd or downgraded GITHUB_API_URL would otherwise leak it.
        raise MintError("GITHUB_API_URL must be an https:// URL; refusing to send the App JWT over cleartext")
    url = f"{api_url.rstrip('/')}/app/installations/{installation_id}/access_tokens"
    request = urllib.request.Request(  # noqa: S310 - fixed https GitHub API host
        url,
        data=b"",
        method="POST",
        headers={
            "Authorization": f"Bearer {jwt_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "claude-md-github-mcp-launcher",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
            body = response.read()
    except urllib.error.HTTPError as exc:
        # exc.code is safe to surface; the response body may echo request
        # context, so it is deliberately not included.
        raise MintError(
            f"GitHub rejected the App token request (HTTP {exc.code}); "
            "verify GITHUB_APP_ID, GITHUB_APP_INSTALLATION_ID, and that the "
            "App is installed on the target with the private key still valid"
        ) from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise MintError(f"could not reach the GitHub API to mint a token: {exc.__class__.__name__}") from None

    try:
        token = json.loads(body)["token"]
    except (ValueError, KeyError, TypeError):
        raise MintError("GitHub token response did not contain a token field") from None
    if not isinstance(token, str) or not token:
        raise MintError("GitHub returned an empty installation token")
    return token


def _require_env(name: str) -> str:
    value = os.environ.get(name, "")
    if not value.strip():
        raise MintError(f"{name} is not set; cannot mint a GitHub App token")
    return value


def _require_private_key() -> str:
    """Return the App private key PEM from the env literal or a file.

    Precedence: ``GITHUB_APP_PRIVATE_KEY`` (literal) wins; otherwise
    ``GITHUB_APP_PRIVATE_KEY_FILE`` (a path, e.g. a Vault Agent template sink)
    is read. Fails loudly naming the missing input. Only the path -- never the
    file contents -- is named on error, so the key cannot leak into a log.
    """
    literal = os.environ.get("GITHUB_APP_PRIVATE_KEY", "")
    if literal.strip():
        return literal
    path = os.environ.get("GITHUB_APP_PRIVATE_KEY_FILE", "")
    if path.strip():
        try:
            pem = Path(path).read_text(encoding="utf-8")
        except OSError as exc:
            raise MintError(
                f"GITHUB_APP_PRIVATE_KEY_FILE ({path}) could not be read: {exc.__class__.__name__}"
            ) from None
        if not pem.strip():
            raise MintError(f"GITHUB_APP_PRIVATE_KEY_FILE ({path}) is empty")
        return pem
    raise MintError(
        "neither GITHUB_APP_PRIVATE_KEY nor GITHUB_APP_PRIVATE_KEY_FILE is set; "
        "cannot mint a GitHub App token"
    )


def mint_from_env() -> str:
    """Read credentials from the environment and return an installation token."""
    app_id = _require_env("GITHUB_APP_ID")
    installation_id = _require_env("GITHUB_APP_INSTALLATION_ID")
    private_key_pem = _require_private_key()
    api_url = os.environ.get("GITHUB_API_URL", DEFAULT_API_URL)

    jwt_token = build_jwt(app_id, private_key_pem)
    return request_installation_token(jwt_token, installation_id, api_url=api_url)


def main() -> int:
    try:
        token = mint_from_env()
    except MintError as exc:
        # Operator-facing reason only; never the secret values.
        print(f"mint_github_app_token: {exc}", file=sys.stderr)
        return 1
    # The token is the sole stdout output so the wrapper can capture it cleanly.
    sys.stdout.write(token)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
