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
        in
        {
          inherit claude-cli codex-cli pinned-uv apm-cli waza-cli rtk-cli;
          bubblewrap = pkgs.bubblewrap;
          gh-cli = pkgs.gh;
          python-runtime = pkgs.python311;
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
            nodejs_22
            python311
            ripgrep
            agentPackages.pinned-uv
            agentPackages.waza-cli
            agentPackages.rtk-cli
          ];
          pythonQualityPackages = with pkgs; [
            mypy
            python311Packages.pytest-xdist
            ruff
          ];
          networkPackages = with pkgs; [
            dnsutils
            iproute2
            iptables
          ];
          mkAgentShell = name: extraPackages:
            pkgs.mkShell {
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
            pkgs.nodePackages.npm
          ];
          codex = mkAgentShell "codex" [
            agentPackages.bubblewrap
            agentPackages.codex-cli
            pkgs.nodePackages.pnpm
          ];
          network = pkgs.mkShell {
            packages = networkPackages;
          };
        };
    in
    {
      packages = forAllSystems mkPackages;
      devShells = forAllSystems mkShells;
    };
}
