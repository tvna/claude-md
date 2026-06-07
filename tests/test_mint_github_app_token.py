"""Tests for ``scripts/mint_github_app_token.py``.

Covers the security-critical contract for the GitHub App token minter (#1063):

* the JWT is genuinely RS256-signed by the App private key (verified with a
  real ``openssl`` round-trip against the matching public key),
* the installation-token exchange returns the token and fails loudly on every
  HTTP / network / shape error,
* missing credentials raise a named ``MintError`` rather than a silent default,
* the minted token is the *only* thing written to stdout and never leaks to
  stderr on the success path.
"""

from __future__ import annotations

import base64
import json
import subprocess
import sys
import urllib.error
from pathlib import Path
from typing import Any

import mint_github_app_token as mint
import pytest

pytestmark = pytest.mark.shard_default

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "mint_github_app_token.py"


@pytest.fixture(scope="module")
def rsa_keypair(tmp_path_factory: pytest.TempPathFactory) -> tuple[str, Path]:
    """Return (private_key_pem_text, public_key_path) from a real openssl key."""
    key_dir = tmp_path_factory.mktemp("rsa")
    key_path = key_dir / "key.pem"
    pub_path = key_dir / "pub.pem"
    subprocess.run(
        ["openssl", "genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:2048", "-out", str(key_path)],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["openssl", "rsa", "-in", str(key_path), "-pubout", "-out", str(pub_path)],
        check=True,
        capture_output=True,
    )
    return key_path.read_text(), pub_path


def _b64url_decode(segment: str) -> bytes:
    padding = "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode(segment + padding)


class _FakeResponse:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def read(self) -> bytes:
        return self._body


class TestBuildJwt:
    def test_jwt_has_three_segments_and_rs256_header(self, rsa_keypair: tuple[str, Path]) -> None:
        pem, _ = rsa_keypair
        token = mint.build_jwt("123456", pem, now=1_000_000)
        segments = token.split(".")
        assert len(segments) == 3
        header = json.loads(_b64url_decode(segments[0]))
        assert header == {"alg": "RS256", "typ": "JWT"}

    def test_jwt_payload_window_and_issuer(self, rsa_keypair: tuple[str, Path]) -> None:
        pem, _ = rsa_keypair
        token = mint.build_jwt("987", pem, now=1_000_000)
        payload = json.loads(_b64url_decode(token.split(".")[1]))
        assert payload["iss"] == "987"
        assert payload["iat"] == 1_000_000 - 60
        assert payload["exp"] == 1_000_000 + 8 * 60
        # GitHub rejects lifetimes over 10 minutes; stay strictly under.
        assert payload["exp"] - payload["iat"] < 10 * 60

    def test_signature_verifies_against_public_key(self, rsa_keypair: tuple[str, Path], tmp_path: Path) -> None:
        pem, pub_path = rsa_keypair
        token = mint.build_jwt("123", pem, now=1_000_000)
        header_b64, payload_b64, sig_b64 = token.split(".")
        data = tmp_path / "data"
        sig = tmp_path / "sig"
        data.write_text(f"{header_b64}.{payload_b64}")
        sig.write_bytes(_b64url_decode(sig_b64))
        result = subprocess.run(
            ["openssl", "dgst", "-sha256", "-verify", str(pub_path), "-signature", str(sig), str(data)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        assert "Verified OK" in result.stdout

    def test_invalid_pem_fails_loudly(self) -> None:
        with pytest.raises(mint.MintError) as excinfo:
            mint.build_jwt("123", "not a real pem key", now=1_000_000)
        assert "PEM" in str(excinfo.value)


class TestRequestInstallationToken:
    def test_returns_token_on_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: dict[str, Any] = {}

        def fake_urlopen(request: Any, timeout: int = 0) -> _FakeResponse:
            captured["url"] = request.full_url
            captured["auth"] = request.headers.get("Authorization")
            return _FakeResponse(json.dumps({"token": "ghs_minted"}).encode())

        monkeypatch.setattr(mint.urllib.request, "urlopen", fake_urlopen)
        token = mint.request_installation_token("jwt.value", "42", api_url="https://api.github.com")
        assert token == "ghs_minted"
        assert captured["url"] == "https://api.github.com/app/installations/42/access_tokens"
        assert captured["auth"] == "Bearer jwt.value"

    def test_http_error_raises_minterror_without_body(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def fake_urlopen(request: Any, timeout: int = 0) -> _FakeResponse:
            raise urllib.error.HTTPError("https://x", 404, "Not Found", hdrs=None, fp=None)  # type: ignore[arg-type]

        monkeypatch.setattr(mint.urllib.request, "urlopen", fake_urlopen)
        with pytest.raises(mint.MintError) as excinfo:
            mint.request_installation_token("jwt", "42")
        assert "404" in str(excinfo.value)

    def test_network_error_raises_minterror(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def fake_urlopen(request: Any, timeout: int = 0) -> _FakeResponse:
            raise urllib.error.URLError("dns down")

        monkeypatch.setattr(mint.urllib.request, "urlopen", fake_urlopen)
        with pytest.raises(mint.MintError):
            mint.request_installation_token("jwt", "42")

    def test_missing_token_field_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            mint.urllib.request,
            "urlopen",
            lambda request, timeout=0: _FakeResponse(b'{"message": "no token here"}'),
        )
        with pytest.raises(mint.MintError):
            mint.request_installation_token("jwt", "42")

    def test_cleartext_api_url_refused(self, monkeypatch: pytest.MonkeyPatch) -> None:
        called = False

        def fake_urlopen(request: Any, timeout: int = 0) -> _FakeResponse:
            nonlocal called
            called = True
            return _FakeResponse(b'{"token": "x"}')

        monkeypatch.setattr(mint.urllib.request, "urlopen", fake_urlopen)
        with pytest.raises(mint.MintError) as excinfo:
            mint.request_installation_token("jwt", "42", api_url="http://ghe.internal")
        assert "https" in str(excinfo.value)
        assert called is False, "must refuse before sending the JWT"

    def test_empty_token_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            mint.urllib.request,
            "urlopen",
            lambda request, timeout=0: _FakeResponse(b'{"token": ""}'),
        )
        with pytest.raises(mint.MintError):
            mint.request_installation_token("jwt", "42")


class TestRequireEnvAndMint:
    @pytest.mark.parametrize("missing", ["GITHUB_APP_ID", "GITHUB_APP_INSTALLATION_ID", "GITHUB_APP_PRIVATE_KEY"])
    def test_missing_env_named_in_error(self, monkeypatch: pytest.MonkeyPatch, missing: str) -> None:
        monkeypatch.setenv("GITHUB_APP_ID", "1")
        monkeypatch.setenv("GITHUB_APP_INSTALLATION_ID", "2")
        monkeypatch.setenv("GITHUB_APP_PRIVATE_KEY", "pem")
        monkeypatch.delenv(missing, raising=False)
        with pytest.raises(mint.MintError) as excinfo:
            mint.mint_from_env()
        assert missing in str(excinfo.value)

    def test_mint_reads_key_from_file_when_literal_unset(
        self, monkeypatch: pytest.MonkeyPatch, rsa_keypair: tuple[str, Path], tmp_path: Path
    ) -> None:
        pem, _ = rsa_keypair
        key_file = tmp_path / "sink.pem"
        key_file.write_text(pem)
        monkeypatch.setenv("GITHUB_APP_ID", "555")
        monkeypatch.setenv("GITHUB_APP_INSTALLATION_ID", "777")
        monkeypatch.delenv("GITHUB_APP_PRIVATE_KEY", raising=False)
        monkeypatch.setenv("GITHUB_APP_PRIVATE_KEY_FILE", str(key_file))
        monkeypatch.setattr(mint, "request_installation_token", lambda *a, **k: "ghs_from_file")
        assert mint.mint_from_env() == "ghs_from_file"

    def test_literal_key_takes_precedence_over_file(
        self, monkeypatch: pytest.MonkeyPatch, rsa_keypair: tuple[str, Path], tmp_path: Path
    ) -> None:
        pem, _ = rsa_keypair
        bad = tmp_path / "bad.pem"
        bad.write_text("not a pem")  # would fail signing if it were used
        monkeypatch.setenv("GITHUB_APP_ID", "1")
        monkeypatch.setenv("GITHUB_APP_INSTALLATION_ID", "2")
        monkeypatch.setenv("GITHUB_APP_PRIVATE_KEY", pem)
        monkeypatch.setenv("GITHUB_APP_PRIVATE_KEY_FILE", str(bad))
        monkeypatch.setattr(mint, "request_installation_token", lambda *a, **k: "ghs_literal")
        assert mint.mint_from_env() == "ghs_literal"

    def test_missing_key_file_fails_loudly_without_leaking(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        missing = tmp_path / "nope.pem"
        monkeypatch.setenv("GITHUB_APP_ID", "1")
        monkeypatch.setenv("GITHUB_APP_INSTALLATION_ID", "2")
        monkeypatch.delenv("GITHUB_APP_PRIVATE_KEY", raising=False)
        monkeypatch.setenv("GITHUB_APP_PRIVATE_KEY_FILE", str(missing))
        with pytest.raises(mint.MintError) as excinfo:
            mint.mint_from_env()
        assert str(missing) in str(excinfo.value)
        assert "PRIVATE KEY" not in str(excinfo.value)

    def test_empty_key_file_fails_loudly(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        empty = tmp_path / "empty.pem"
        empty.write_text("")
        monkeypatch.setenv("GITHUB_APP_ID", "1")
        monkeypatch.setenv("GITHUB_APP_INSTALLATION_ID", "2")
        monkeypatch.delenv("GITHUB_APP_PRIVATE_KEY", raising=False)
        monkeypatch.setenv("GITHUB_APP_PRIVATE_KEY_FILE", str(empty))
        with pytest.raises(mint.MintError):
            mint.mint_from_env()

    def test_mint_from_env_uses_real_jwt_and_returns_token(
        self, monkeypatch: pytest.MonkeyPatch, rsa_keypair: tuple[str, Path]
    ) -> None:
        pem, _ = rsa_keypair
        monkeypatch.setenv("GITHUB_APP_ID", "555")
        monkeypatch.setenv("GITHUB_APP_INSTALLATION_ID", "777")
        monkeypatch.setenv("GITHUB_APP_PRIVATE_KEY", pem)
        monkeypatch.delenv("GITHUB_API_URL", raising=False)

        seen: dict[str, Any] = {}

        def fake_request(jwt_token: str, installation_id: str, *, api_url: str) -> str:
            seen["installation_id"] = installation_id
            seen["api_url"] = api_url
            seen["segments"] = jwt_token.count(".")
            return "ghs_from_env"

        monkeypatch.setattr(mint, "request_installation_token", fake_request)
        token = mint.mint_from_env()
        assert token == "ghs_from_env"
        assert seen["installation_id"] == "777"
        assert seen["api_url"] == mint.DEFAULT_API_URL
        assert seen["segments"] == 2  # a well-formed JWT was built and passed through


class TestMain:
    def test_main_writes_only_token_to_stdout(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(mint, "mint_from_env", lambda: "ghs_main")
        rc = mint.main()
        captured = capsys.readouterr()
        assert rc == 0
        assert captured.out == "ghs_main"
        assert captured.err == ""

    def test_main_reports_error_without_token(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        def boom() -> str:
            raise mint.MintError("GITHUB_APP_ID is not set; cannot mint a GitHub App token")

        monkeypatch.setattr(mint, "mint_from_env", boom)
        rc = mint.main()
        captured = capsys.readouterr()
        assert rc == 1
        assert captured.out == ""
        assert "GITHUB_APP_ID" in captured.err

    def test_module_entrypoint_exits_nonzero_without_creds(self) -> None:
        """Driving the file as __main__ with no creds exits 1 and prints no token."""
        result = subprocess.run(
            [sys.executable, str(SCRIPT)],
            env={"PATH": "/usr/bin:/bin"},
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1
        assert result.stdout == ""
        assert "GITHUB_APP_ID" in result.stderr
