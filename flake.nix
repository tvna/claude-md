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
      forAllSystems = nixpkgs.lib.genAttrs systems;
      mkShells = system:
        let
          pkgs = import nixpkgs {
            inherit system;
          };
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
            uv
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
            pkgs.nodePackages.npm
          ];
          codex = mkAgentShell "codex" [
            pkgs.nodePackages.pnpm
          ];
          network = pkgs.mkShell {
            packages = networkPackages;
          };
        };
    in
    {
      devShells = forAllSystems mkShells;
    };
}
