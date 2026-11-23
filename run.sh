#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

usage() {
    cat <<'EOF'
Usage: ./run.sh [--rebuild-venv] [scraper options...]

Launcher options:
  --rebuild-venv    Delete and recreate the virtual environment, then run

All other arguments are passed to scraper.py. Its own options follow below.

EOF
}

setup_venv() {
    echo "Setting up virtual environment '.venv'"
    rm -rf .venv
    python3 -m venv .venv
    .venv/bin/pip install -r requirements.txt
    touch .venv/.installed

    # Setup playwright
    .venv/bin/playwright install
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
        exec .venv/bin/python scraper.py "${args[@]}"
    fi
    echo "(Run ./run.sh once to set up the environment and see scraper options.)"
    exit 0
fi

if [ "$rebuild" -eq 1 ] || [ ! -f .venv/.installed ]; then
    setup_venv
fi

exec .venv/bin/python scraper.py "${args[@]}"