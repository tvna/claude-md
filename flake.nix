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
        in
        {
          inherit claude-cli codex-cli pinned-uv;
          bubblewrap = pkgs.bubblewrap;
          gh-cli = pkgs.gh;
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
