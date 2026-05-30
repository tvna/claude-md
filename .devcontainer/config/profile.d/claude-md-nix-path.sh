# Make binaries linked from Nix-built packages available in plain terminals.
case ":${PATH}:" in
  *:/usr/local/bin:*) ;;
  *) export PATH="/usr/local/bin:${PATH}" ;;
esac
