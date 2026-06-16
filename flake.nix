{
  description = "Pinned devcontainer toolchains for claude-md agent workspaces";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-25.05";
  };

  outputs = { nixpkgs, ... }:
    let
      systems = [
        "aarch64-linux"
        "x86_64-linux"
      ];
      uvVersionSpec = (builtins.fromTOML (builtins.readFile ./pyproject.toml)).tool.uv.required-version;
      uvVersion =
        assert nixpkgs.lib.hasPrefix "==" uvVersionSpec;
        nixpkgs.lib.removePrefix "==" uvVersionSpec;
      forAllSystems = nixpkgs.lib.genAttrs systems;
      mkPackages = system:
        let
          pkgs = import nixpkgs {
            inherit system;
          };
          claudeCodeVersion = "2.1.154";
          codexCliVersion = "0.135.0";
          apmVersion = "0.12.1";
          wazaVersion = "0.33.0";
          rtkVersion = "0.42.1";
          actionlintVersion = "1.7.7";
          ccusageVersion = "20.0.6";
          # zizmor / lychee / betterleaks are provisioned ONLY by the
          # SessionStart installers (scripts/install-{zizmor,lychee,betterleaks}.sh)
          # in Claude Code on the Web sessions; they are deliberately NOT wired
          # into the nix devShell / sharedPackages. flake.nix stays the single
          # pin source of truth (scripts/flake_pin.py reads these via the same
          # contract as rtk/waza), but the let-bindings below are intentionally
          # unused by any derivation -- they exist so the pin lives in exactly
          # one place and scan_flake_pin_drift.py can guard the checksum. They
          # run alongside the existing scan_workflow_*/scan_markdown_links/
          # scan_secrets gates during the effectiveness-measurement phase; no
          # existing gate is removed. Refs #1610.
          zizmorVersion = "1.25.2";
          lycheeVersion = "0.24.2";
          betterleaksVersion = "1.4.1";
          claudeCodeNative = {
            aarch64-linux = {
              package = "claude-code-linux-arm64";
              hash = "sha512-kUx+agGdSbKdSUPPWxq8O/4XsbGrMDQ89APe/vb4jvsCnt5hQAPWYd+gMaspL/QlvHd77wd8BJf5+fuqt5ck4g==";
            };
            x86_64-linux = {
              package = "claude-code-linux-x64";
              hash = "sha512-AQxDm3rhPLnS5DLKYYUUSC4G40Fgc/zD7yOSTFyGvLLtI7S9Enuj8ltxVNWAQqF5U6mdWvnjuu8hZS1Ftk1IaQ==";
            };
          }.${system};
          codexCliNative = {
            aarch64-linux = {
              target = "aarch64-unknown-linux-musl";
              packageVersion = "${codexCliVersion}-linux-arm64";
              hash = "sha512-dM+cv5ZL+BgIQzEIvMg9AxZ98n5lkKLgtp5zJLXWSrbCllbnUSqxYMUiWI5c1a1uBDUtkbY9fcGKXFLf+d+gyg==";
            };
            x86_64-linux = {
              target = "x86_64-unknown-linux-musl";
              packageVersion = "${codexCliVersion}-linux-x64";
              hash = "sha512-5EosY67yU28UJSnl/obdN2F1CDaimYbzm9SLR8dwwzkeBBnY6dHgAKJ2GTu9Nc8CmgmtVFBGzgPqehsIcueVvA==";
            };
          }.${system};
          apmNative = {
            aarch64-linux = {
              archive = "apm-linux-arm64";
              hash = "sha256-NkplG444MzHPCumW09V7fxZLON40VjSuCP5xFMT546c=";
            };
            x86_64-linux = {
              archive = "apm-linux-x86_64";
              hash = "sha256-oLiW6MvdEEQRJemJqhnRgMYgUu2nyKqFD+s2eAXRJW8=";
            };
          }.${system};
          uvNative = {
            aarch64-linux = {
              target = "aarch64-unknown-linux-gnu";
              hash = "sha256-FV/k07PLS/zhGKtLE4D3FRWuh00T2YWBcbT5wm4WaE0=";
            };
            x86_64-linux = {
              target = "x86_64-unknown-linux-gnu";
              hash = "sha256-p2eEglQ5GFXJbfJx6cqLf3LdFy0xBGBEeFPSXZB7muA=";
            };
          }.${system};
          wazaNative = {
            aarch64-linux = {
              asset = "waza-linux-arm64";
              hash = "sha256-VSuk9F5fc+PpwMk0KeLFniHxpN6LmJX5j1Te6n8D36g=";
            };
            x86_64-linux = {
              asset = "waza-linux-amd64";
              hash = "sha256-waMaFdlZ0s1Tb+tBz3sg+UsENKjoaUnT3j0hweP7b/M=";
            };
          }.${system};
          # rtk publishes per-target release tarballs; the asset field carries
          # the full archive filename because the x86_64 build is musl-static
          # while the aarch64 build is gnu-dynamic (no shared target suffix to
          # template). Each tarball unpacks to a single ``rtk`` binary.
          rtkNative = {
            aarch64-linux = {
              asset = "rtk-aarch64-unknown-linux-gnu.tar.gz";
              hash = "sha256-MvTXh2bi9bQ3Vu/OPGmdxNqL7vUpbesC+ndW8yV+slw=";
            };
            x86_64-linux = {
              asset = "rtk-x86_64-unknown-linux-musl.tar.gz";
              hash = "sha256-o3yjAKQlEKlkRT8rwuIXdp7whyeAr4AtuKfWmPHaJGU=";
            };
          }.${system};
          # actionlint (rhysd/actionlint) ships per-target release tarballs, each
          # holding a single ``actionlint`` binary. The asset filenames embed the
          # version, but they MUST stay STATIC strings (not ``${actionlintVersion}``
          # interpolations): scripts/flake_pin.py parses this block with a
          # brace-naive regex, and a ``}`` inside an interpolation would truncate
          # the match. A version bump must therefore update the filenames here
          # alongside the version and hashes (see scripts/flake_pin.py).
          actionlintNative = {
            aarch64-linux = {
              asset = "actionlint_1.7.7_linux_arm64.tar.gz";
              hash = "sha256-QBlC+cJO1x5P5xt2x9Y49m2GM1dcQBbv0pd858KDF9A=";
            };
            x86_64-linux = {
              asset = "actionlint_1.7.7_linux_amd64.tar.gz";
              hash = "sha256-AjBwoofNjMzXFRX+3IQ/GYW/lsQ2t+/67M5nKQ5+B1c=";
            };
          }.${system};
          # ccusage (ryoppippi/ccusage) ships platform-specific native binaries
          # via npm scoped packages (@ccusage/ccusage-linux-<arch>), each a
          # self-contained static-pie ELF holding ``package/bin/ccusage`` (no
          # Node runtime needed). The main ``ccusage`` npm package declares them
          # as optionalDependencies; we fetch the per-system binary package
          # directly, mirroring claude-cli / codex-cli. The ``pkg`` field is the
          # scoped package basename and drives both the registry URL and the
          # tarball filename. Pinned by SHA256 for supply-chain hardening (the
          # npm sha512 integrity was verified against these tarballs first);
          # SHA256 keeps the pin in scan_flake_pin_drift.py's coverage. Refs #1404.
          ccusageNative = {
            aarch64-linux = {
              pkg = "ccusage-linux-arm64";
              hash = "sha256-vcXhHYK2+CkKcq/u5WQZhAUs5FNXq36HSgJ8fKWZ2zE=";
            };
            x86_64-linux = {
              pkg = "ccusage-linux-x64";
              hash = "sha256-Wl94vPpOZ4A74sG3AFDz64grUmUxPTF/PIWze7yO/xw=";
            };
          }.${system};
          # zizmor (zizmorcore/zizmor) ships per-target release tarballs, each
          # unpacking to a single bare ``zizmor`` binary. Only a gnu linux build
          # is published per arch, so the asset carries no shared target suffix
          # to template -- the full filename is stored verbatim (rtk shape). The
          # filename embeds no version, so a bump only rewrites version + hashes.
          zizmorNative = {
            aarch64-linux = {
              asset = "zizmor-aarch64-unknown-linux-gnu.tar.gz";
              hash = "sha256-S0uUkREsKgmzGBAcDTNJtzrxxPUy4JfdbQFk8qvadg0=";
            };
            x86_64-linux = {
              asset = "zizmor-x86_64-unknown-linux-gnu.tar.gz";
              hash = "sha256-qh+s0QXw2D/lxVsa3NnXQX3l2DqidHH5HcC2bPOANXc=";
            };
          }.${system};
          # lychee (lycheeverse/lychee) publishes musl-static per-target tarballs
          # that unpack to ``lychee-<target>/lychee`` (a nested dir, unlike rtk's
          # bare layout -- the installer locates the binary with ``find``). The
          # release tag is ``lychee-v<version>`` (not ``v<version>``); the
          # flake_pin.py url_template encodes that prefix. Asset embeds no
          # version.
          lycheeNative = {
            aarch64-linux = {
              asset = "lychee-aarch64-unknown-linux-musl.tar.gz";
              hash = "sha256-XQsOOuqyQPQZIMYzpur5dZm+bu3aA0s26Fjt59ul5TU=";
            };
            x86_64-linux = {
              asset = "lychee-x86_64-unknown-linux-musl.tar.gz";
              hash = "sha256-c2V6ERgZowxHwINSiWeW8j1k5OsrPtObbTIUkkFWb8U=";
            };
          }.${system};
          # betterleaks (betterleaks/betterleaks) ships per-arch Go-static
          # tarballs holding a bare ``betterleaks`` binary (plus LICENSE/README).
          # The asset filenames EMBED the version, so -- like actionlintNative --
          # they MUST stay STATIC strings (no ``${betterleaksVersion}``): the
          # flake_pin.py _native_block regex is brace-naive and a ``}`` inside an
          # interpolation would truncate the match. A version bump must rewrite
          # the embedded filenames here alongside the version and hashes.
          betterleaksNative = {
            aarch64-linux = {
              asset = "betterleaks_1.4.1_linux_arm64.tar.gz";
              hash = "sha256-I+0FziF8IdOecjxtlwqf0Lnptobq4a6/nXePt6d6zJI=";
            };
            x86_64-linux = {
              asset = "betterleaks_1.4.1_linux_x64.tar.gz";
              hash = "sha256-JjX/mI2RlM0wcBVROFiQgaVKNDjXnKm4Mmit3S/YRMw=";
            };
          }.${system};
          pinned-uv = pkgs.stdenvNoCC.mkDerivation {
            pname = "uv";
            version = uvVersion;
            src = pkgs.fetchurl {
              url = "https://releases.astral.sh/github/uv/releases/download/${uvVersion}/uv-${uvNative.target}.tar.gz";
              hash = uvNative.hash;
            };
            dontBuild = true;
            installPhase = ''
              runHook preInstall

              install -Dm755 uv $out/bin/uv
              install -Dm755 uvx $out/bin/uvx

              runHook postInstall
            '';
          };
          claude-cli = pkgs.stdenvNoCC.mkDerivation {
            pname = "claude-code-cli";
            version = claudeCodeVersion;
            src = pkgs.fetchurl {
              url = "https://registry.npmjs.org/@anthropic-ai/${claudeCodeNative.package}/-/${claudeCodeNative.package}-${claudeCodeVersion}.tgz";
              hash = claudeCodeNative.hash;
            };
            dontBuild = true;
            installPhase = ''
              runHook preInstall

              install -Dm755 claude $out/bin/claude

              runHook postInstall
            '';
          };
          codex-cli = pkgs.stdenvNoCC.mkDerivation {
            pname = "codex-cli";
            version = codexCliVersion;
            src = pkgs.fetchurl {
              url = "https://registry.npmjs.org/@openai/codex/-/codex-${codexCliNative.packageVersion}.tgz";
              hash = codexCliNative.hash;
            };
            dontBuild = true;
            installPhase = ''
              runHook preInstall

              mkdir -p $out/bin
              cp -R vendor $out/vendor
              chmod +x $out/vendor/${codexCliNative.target}/bin/codex
              cat > $out/bin/codex <<EOF
#!${pkgs.runtimeShell}
export PATH="$out/vendor/${codexCliNative.target}/codex-path:''${PATH:-}"
export CODEX_MANAGED_BY_NIX=1
export CODEX_MANAGED_PACKAGE_ROOT="$out"
exec "$out/vendor/${codexCliNative.target}/bin/codex" "\$@"
EOF
              chmod +x $out/bin/codex

              runHook postInstall
            '';
          };
          apm-cli = pkgs.stdenvNoCC.mkDerivation {
            pname = "apm-cli";
            version = apmVersion;
            src = pkgs.fetchurl {
              url = "https://github.com/microsoft/apm/releases/download/v${apmVersion}/${apmNative.archive}.tar.gz";
              hash = apmNative.hash;
            };
            dontBuild = true;
            dontStrip = true;
            dontPatchELF = true;
            installPhase = ''
              runHook preInstall

              mkdir -p $out/libexec/apm $out/bin
              install -Dm755 apm $out/libexec/apm/apm
              cp -R _internal $out/libexec/apm/_internal
              cat > $out/bin/apm <<EOF
#!${pkgs.runtimeShell}
exec "$out/libexec/apm/apm" "\$@"
EOF
              chmod +x $out/bin/apm

              runHook postInstall
            '';
          };
          # waza ships a single prebuilt release binary (no archive), so the
          # source is fetched verbatim and installed without unpacking. Mirrors
          # the apm-cli ELF handling (no strip / no patchelf): the devcontainer
          # image is a standard FHS distro, so the dynamic loader resolves
          # normally. Pinned by SHA256 for supply-chain hardening. Refs #1103.
          waza-cli = pkgs.stdenvNoCC.mkDerivation {
            pname = "waza";
            version = wazaVersion;
            src = pkgs.fetchurl {
              url = "https://github.com/microsoft/waza/releases/download/v${wazaVersion}/${wazaNative.asset}";
              hash = wazaNative.hash;
            };
            dontUnpack = true;
            dontBuild = true;
            dontStrip = true;
            dontPatchELF = true;
            installPhase = ''
              runHook preInstall

              install -Dm755 $src $out/bin/waza

              runHook postInstall
            '';
          };
          # rtk (rtk-ai/rtk) ships prebuilt release tarballs, each holding a
          # single ``rtk`` binary. Mirrors the apm-cli ELF handling (no strip /
          # no patchelf): the aarch64 build is gnu-dynamic and the devcontainer
          # is a standard FHS distro, so the dynamic loader resolves normally;
          # the x86_64 build is musl-static. Pinned by SHA256 for supply-chain
          # hardening. Refs #1193.
          rtk-cli = pkgs.stdenvNoCC.mkDerivation {
            pname = "rtk";
            version = rtkVersion;
            src = pkgs.fetchurl {
              url = "https://github.com/rtk-ai/rtk/releases/download/v${rtkVersion}/${rtkNative.asset}";
              hash = rtkNative.hash;
            };
            # The tarball holds a bare ``rtk`` binary with no enclosing
            # directory, so the default unpackPhase fails to pick a source root
            # ("unpacker appears to have produced no directories"). Point it at
            # the unpack dir itself so installPhase finds ./rtk.
            sourceRoot = ".";
            dontBuild = true;
            dontStrip = true;
            dontPatchELF = true;
            installPhase = ''
              runHook preInstall

              install -Dm755 rtk $out/bin/rtk

              runHook postInstall
            '';
          };
          # actionlint (rhysd/actionlint) ships prebuilt release tarballs, each
          # holding a single bare ``actionlint`` binary (no enclosing dir), so
          # point sourceRoot at the unpack dir itself -- mirrors rtk-cli. Pinned
          # by SHA256 for supply-chain hardening. Refs #1263.
          actionlint-cli = pkgs.stdenvNoCC.mkDerivation {
            pname = "actionlint";
            version = actionlintVersion;
            src = pkgs.fetchurl {
              url = "https://github.com/rhysd/actionlint/releases/download/v${actionlintVersion}/${actionlintNative.asset}";
              hash = actionlintNative.hash;
            };
            sourceRoot = ".";
            dontBuild = true;
            dontStrip = true;
            dontPatchELF = true;
            installPhase = ''
              runHook preInstall

              install -Dm755 actionlint $out/bin/actionlint

              runHook postInstall
            '';
          };
          # ccusage's per-system npm tarball unpacks to the standard npm
          # ``package/`` source root holding ``bin/ccusage`` (a self-contained
          # ELF). Mirrors claude-cli minus the bin path: install that binary.
          ccusage-cli = pkgs.stdenvNoCC.mkDerivation {
            pname = "ccusage";
            version = ccusageVersion;
            src = pkgs.fetchurl {
              url = "https://registry.npmjs.org/@ccusage/${ccusageNative.pkg}/-/${ccusageNative.pkg}-${ccusageVersion}.tgz";
              hash = ccusageNative.hash;
            };
            dontBuild = true;
            dontStrip = true;
            dontPatchELF = true;
            installPhase = ''
              runHook preInstall

              install -Dm755 bin/ccusage $out/bin/ccusage

              runHook postInstall
            '';
          };
        in
        {
          inherit claude-cli codex-cli pinned-uv apm-cli waza-cli rtk-cli actionlint-cli ccusage-cli;
          bubblewrap = pkgs.bubblewrap;
          gh-cli = pkgs.gh;
          python-runtime = pkgs.python312;
          # GitHub MCP server binary for the local-stdio launch path used by
          # scripts/mcp_github_launch.sh (#1063). In the devcontainer there is no
          # Docker daemon, so the wrapper execs this Nix-pinned binary instead of
          # `docker run`. Pinned transitively through the nixos-25.05 nixpkgs input.
          github-mcp-server = pkgs.github-mcp-server;
        };
      mkShells = system:
        let
          pkgs = import nixpkgs {
            inherit system;
          };
          agentPackages = mkPackages system;
          sharedPackages = with pkgs; [
            bashInteractive
            cacert
            coreutils
            fd
            gh
            git
            jq
            # bun, not nodejs_22 + npm/pnpm: this repo has no package.json and
            # never invokes node/npm/npx -- the agent CLIs (claude/codex/ccusage)
            # are self-contained native binaries and the only MCP server is the
            # native github-mcp-server, so a full Node toolchain (nodejs ~91 MB +
            # its ~69 MB -dev output + npm/pnpm) was unused weight in the baked
            # image (#1491). bun is a single ~90 MB binary that still gives the
            # agents a JS runtime + `bunx` (npx-equivalent) for ad-hoc work, with
            # no separate -dev output. If a workflow needs strict node/npm
            # behavior, reintroduce nodejs_22 + the package manager and document
            # the consumer.
            bun
            python312
            ripgrep
            shellcheck
            agentPackages.pinned-uv
            agentPackages.waza-cli
            agentPackages.rtk-cli
            agentPackages.actionlint-cli
          ];
          pythonQualityPackages = with pkgs; [
            # Bare `mypy` (= pkgs.mypy) is built against the nixpkgs-default
            # interpreter, which in nixpkgs 25.05 is python312 -- the same
            # interpreter the project now targets (pyproject requires-python
            # >=3.12) and that sharedPackages provides. So mypy shares the one
            # python in the closure; there is no duplicate interpreter to avoid,
            # and no python312Packages override is needed for mypy. Keeps the
            # baked claude image (#1491) to a single Python.
            mypy
            python312Packages.pytest-xdist
            ruff
          ];
          networkPackages = with pkgs; [
            bpftrace
            dnsmasq
            dnsutils
            ipset
            iproute2
            iptables
          ];
          # mkShellNoCC, not mkShell: mkShell pulls the full stdenv C toolchain
          # (gcc ~256 MB + binutils ~62 MB) into every agent devShell closure.
          # This repo's `uv sync` installs only wheels (pyyaml/pytest/ruff/mypy/
          # hypothesis/pytest-xdist all ship manylinux wheels), and the agents run
          # no from-source C/native builds, so the compiler is dead weight in the
          # closure -- and in the baked claude image (#1491). Drop it with the
          # NoCC stdenv. If a future dependency needs to compile from sdist,
          # restore mkShell (or add a cc to packages) and document the need.
          mkAgentShell = name: extraPackages:
            pkgs.mkShellNoCC {
              packages = sharedPackages ++ pythonQualityPackages ++ extraPackages;
              shellHook = ''
                export AGENT_CONTAINER="${name}"
              '';
            };
        in
        {
          default = mkAgentShell "shared" [ ];
          claude = mkAgentShell "claude" [
            agentPackages.claude-cli
            agentPackages.ccusage-cli
          ];
          codex = mkAgentShell "codex" [
            agentPackages.bubblewrap
            agentPackages.codex-cli
            agentPackages.ccusage-cli
          ];
          network = pkgs.mkShell {
            packages = networkPackages;
          };
        };
      darwinSystems = [
        "aarch64-darwin"
        "x86_64-darwin"
      ];
      # Minimal devShell for macOS developers using `nix develop`.
      # Only git is needed; the shellHook configures SSH commit signing
      # for the local repo when a public key is found in ~/.ssh.
      # The linux agent tools (claude-cli, codex-cli, etc.) have no darwin
      # prebuilt binaries and are intentionally omitted from this shell.
      mkDarwinShell = system:
        let
          pkgs = import nixpkgs {
            inherit system;
          };
        in
        {
          default = pkgs.mkShellNoCC {
            packages = [ pkgs.git ];
            shellHook = ''
              if git rev-parse --git-dir >/dev/null 2>&1; then
                _signing_key=""
                for _k in "$HOME/.ssh/id_ed25519.pub" "$HOME/.ssh/id_rsa.pub" "$HOME/.ssh/id_ecdsa.pub"; do
                  if [ -f "$_k" ]; then _signing_key="$_k"; break; fi
                done
                if [ -n "$_signing_key" ]; then
                  git config --local gpg.format ssh
                  git config --local user.signingKey "$_signing_key"
                  git config --local commit.gpgsign true
                  echo "git SSH signing configured: $_signing_key"
                fi
                unset _signing_key _k
              fi
            '';
          };
        };
      forAllDarwinSystems = nixpkgs.lib.genAttrs darwinSystems;
    in
    {
      packages = forAllSystems mkPackages;
      devShells = forAllSystems mkShells // forAllDarwinSystems mkDarwinShell;
    };
}
