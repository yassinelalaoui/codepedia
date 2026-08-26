#!/bin/sh
# Installs the standalone `codepedia` binary (specs/020-cli-packaging).
# Usage: curl -fsSL <release-url>/install.sh | sh
#
# Downloads the release asset matching this machine's OS/arch from the
# latest GitHub Release of yassinelalaoui/codepedia, installs it to
# ~/.local/bin/codepedia, and adds that directory to PATH if it isn't
# already there. Re-running this script upgrades an existing install in
# place (research.md §5-§6; contracts/packaging-interface.md).
set -eu

REPO="yassinelalaoui/codepedia"
INSTALL_DIR="$HOME/.local/bin"
BINARY_NAME="codepedia"

fail() {
    echo "Error: $1" >&2
    exit 1
}

command -v curl >/dev/null 2>&1 || fail "curl is required but was not found on PATH."

os="$(uname -s)"
case "$os" in
    Linux) target_os="linux" ;;
    Darwin) target_os="macos" ;;
    *) fail "Unsupported operating system: $os. codepedia currently ships binaries for Linux and macOS (x86_64) - see specs/020-cli-packaging/research.md §9." ;;
esac

arch="$(uname -m)"
case "$arch" in
    x86_64|amd64) target_arch="x86_64" ;;
    *) fail "Unsupported architecture: $arch. codepedia currently only ships x86_64 binaries - see specs/020-cli-packaging/research.md §9." ;;
esac

api_url="https://api.github.com/repos/${REPO}/releases/latest"
tmp_release_json="$(mktemp)"
trap 'rm -f "$tmp_release_json"' EXIT
http_status="$(curl -sL -w '%{http_code}' -o "$tmp_release_json" "$api_url")" || fail "Could not reach GitHub to resolve the latest release. Check your network connection and try again."

case "$http_status" in
    200) ;;
    404) fail "No release of ${REPO} has been published yet. See packaging/README.md for the release process, or check https://github.com/${REPO}/releases." ;;
    *) fail "GitHub returned an unexpected response (HTTP $http_status) while resolving the latest release. Check your network connection and try again." ;;
esac

release_json="$(cat "$tmp_release_json")"
rm -f "$tmp_release_json"
trap - EXIT

asset_pattern="codepedia-.*-${target_os}-${target_arch}\$"
download_url="$(printf '%s' "$release_json" | grep -o '"browser_download_url": *"[^"]*"' | sed -E 's/.*"(https:[^"]+)"/\1/' | grep -E "$asset_pattern" | head -n1)"

[ -n "$download_url" ] || fail "No release asset found for ${target_os}-${target_arch}. This build of codepedia does not (yet) support this platform - see specs/020-cli-packaging/research.md §9."

mkdir -p "$INSTALL_DIR"
tmp_file="$(mktemp)"
trap 'rm -f "$tmp_file"' EXIT

curl -fsSL "$download_url" -o "$tmp_file" || fail "Failed to download $download_url. Check your network connection and try again."

chmod +x "$tmp_file"
mv "$tmp_file" "$INSTALL_DIR/$BINARY_NAME"
trap - EXIT

case ":$PATH:" in
    *":$INSTALL_DIR:"*) ;;
    *)
        profile="$HOME/.profile"
        case "${SHELL:-}" in
            */zsh) profile="$HOME/.zshrc" ;;
            */bash) [ -f "$HOME/.bash_profile" ] && profile="$HOME/.bash_profile" || profile="$HOME/.bashrc" ;;
        esac
        printf '\nexport PATH="%s:$PATH"\n' "$INSTALL_DIR" >> "$profile"
        echo "Added $INSTALL_DIR to PATH in $profile. Open a new terminal (or run: source $profile) for it to take effect."
        ;;
esac

installed_version="$("$INSTALL_DIR/$BINARY_NAME" --version)"
echo "codepedia $installed_version installed to $INSTALL_DIR/$BINARY_NAME"
echo "Verify with: codepedia --version"
