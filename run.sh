#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

UBOL_REPO="uBlockOrigin/uBOL-home"
export EXT_DIR="$PWD/extensions/uBOLite"

usage() {
    cat <<'EOF'
Usage: ./run.sh [--rebuild-venv] [scraper options...]

Launcher options:
  --rebuild-venv    Delete and recreate the virtual environment, then run

All other arguments are passed to scraper.py. Its own options follow below.

EOF
}

TMP_DIRS=()
cleanup() { rm -rf "${TMP_DIRS[@]+"${TMP_DIRS[@]}"}"; }
trap cleanup EXIT

check_tools() {
    local missing=()
    for tool in python3 curl jq unzip; do
        command -v "$tool" >/dev/null || missing+=("$tool")
    done
    if [ "${#missing[@]}" -gt 0 ]; then
        echo "Missing required tools: ${missing[*]}" >&2
        exit 1
    fi
}

setup_venv() {
    echo "Setting up virtual environment '.venv'"
    rm -rf .venv
    python3 -m venv .venv
    .venv/bin/pip install -r requirements.txt
}

setup_playwright() {
    .venv/bin/playwright install chromium
}

setup_extension() {
    echo "Downloading uBlock Origin Lite"
    tmp="$(mktemp -d)"
    TMP_DIRS+=("$tmp")

    url="$(curl -fsSL "https://api.github.com/repos/$UBOL_REPO/releases/latest" \
        | jq -r '[.assets[] | select(.name | test("^uBOLite_.*\\.chromium\\.zip$"))][0].browser_download_url // empty')"
    if [ -z "$url" ]; then
        echo "Could not find the uBOLite chromium asset in the latest release." >&2
        return 1
    fi

    curl -fsSL -o "$tmp/ubol.zip" "$url"
    unzip -q "$tmp/ubol.zip" -d "$tmp/ext"

    # Some releases wrap everything in a subfolder; find the manifest.
    local manifest
    manifest="$(find "$tmp/ext" -name manifest.json -print -quit)"
    if [ -z "$manifest" ]; then
        echo "manifest.json not found in the downloaded extension." >&2
        return 1
    fi

    # Swap in only after everything above succeeded.
    rm -rf "$EXT_DIR"
    mkdir -p "$(dirname "$EXT_DIR")"
    mv "$(dirname "$manifest")" "$EXT_DIR"
}

bootstrap() {
    check_tools
    setup_venv
    setup_playwright
    setup_extension
    touch .venv/.installed   # last, so a failed step is retried next run
}

rebuild=0
show_help=0
args=()
for arg in "$@"; do
    case "$arg" in
        --rebuild-venv) rebuild=1 ;;
        -h|--help) show_help=1; args+=("$arg") ;;
        *) args+=("$arg") ;;
    esac
done

if [ "$show_help" -eq 1 ]; then
    usage
    # Only show scraper's help if the venv is already set up
    if [ -f .venv/.installed ] && [ "$rebuild" -eq 0 ]; then
        exec .venv/bin/python scraper.py ${args[@]+"${args[@]}"}
    fi
    echo "(Run ./run.sh once to set up the environment and see scraper options.)"
    exit 0
fi

if [ "$rebuild" -eq 1 ] || [ ! -f .venv/.installed ]; then
    bootstrap
fi

exec .venv/bin/python scraper.py ${args[@]+"${args[@]}"}