# Scriptorium

A command-line tool that captures the pages of a Scribd document and assembles them into a single PDF.

Repository: [michaelolufade/scriptorium](https://github.com/michaelolufade/scriptorium)

## How it works

1. Resolves the document URL from an ID or a full Scribd link.
2. Reads the document's static HTML to detect the file name and page count (skipped if you pass both `--fname` and `--end-page`).
3. Opens the document in Chromium (via Playwright) with [uBlock Origin Lite](https://github.com/uBlockOrigin/uBOL-home) loaded, hides fixed and sticky overlays, and screenshots each rendered page.
4. Combines the screenshots into a PDF with `img2pdf`.

Pages are captured in chunks of 300, each in a fresh browser session, so long documents don't exhaust a single session.

## Requirements

- Linux or macOS (on Windows, use WSL). The launcher is a Bash script.
- Python 3.12 or newer
- `curl`, `jq`, and `unzip`
- Internet access to GitHub, for downloading the extension

## Quick start

```bash
git clone https://github.com/michaelolufade/scriptorium.git
cd scriptorium

./run.sh --doc 123456789
```

The first run bootstraps everything automatically:

1. Checks that `python3`, `curl`, `jq`, and `unzip` are installed.
2. Creates a `.venv` virtual environment and installs `requirements.txt`.
3. Installs Playwright's Chromium.
4. Downloads the latest uBlock Origin Lite (Chromium build) from GitHub into `extensions/uBOLite/`.

Later runs skip setup and go straight to the scraper. A marker file, `.venv/.installed`, is written only after every step succeeds, so a failed setup is retried on the next run.

## Usage

```bash
./run.sh [--rebuild-venv] [scraper options...]
```

### Launcher options

| Option | Description |
| --- | --- |
| `--rebuild-venv` | Delete and recreate the virtual environment, reinstall Chromium, re-download the extension, then run. |
| `-h`, `--help` | Show launcher help. Also shows the scraper's options once setup has completed. |

All other arguments are passed to `scraper.py`.

### Scraper options

| Option | Description | Default |
| --- | --- | --- |
| `--doc`, `--doc-id` | Scribd document ID or full document URL (required). | none |
| `--fname` | Output file name. `.pdf` is added if missing. | Derived from the page title |
| `--start-page` | First page to capture (1-based). | `1` |
| `--end-page` | Last page to capture (inclusive). | Last page of the document |

### Examples

```bash
# Whole document, name and page count detected automatically
./run.sh --doc 123456789

# From a URL
./run.sh --doc "https://www.scribd.com/document/123456789/Some-Title"

# Pages 10 to 25 with a custom name
./run.sh --doc 123456789 --start-page 10 --end-page 25 --fname chapter2

# Skip the page-count lookup entirely
./run.sh --doc 123456789 --fname report --end-page 80

# Refresh the environment and extension, then run
./run.sh --rebuild-venv --doc 123456789
```

## Manual setup

If you'd rather not use `run.sh`:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium

# Download and unzip the uBOLite *.chromium.zip release from
# https://github.com/uBlockOrigin/uBOL-home/releases, then:
export EXT_PATH=/path/to/unpacked/uBOLite

python scraper.py --doc 123456789
```

Scriptorium checks `EXT_PATH` before doing any network or browser work and exits with an error if it is unset or not a directory.

## Output

| Path | Contents |
| --- | --- |
| `outputs/<name>.pdf` | The finished PDF. An existing file with the same name is overwritten. |
| `outputs/screenshots/` | Temporary working folders, removed after each run. |
| `playwright_profile/` | Persistent Chromium profile, reused between runs. |
| `extensions/uBOLite/` | The downloaded extension. |

`run.sh` changes into the repository directory first, so these paths are always relative to the repo root.

## File names

- Names you pass with `--fname` are never silently rewritten. Names containing path separators, control characters, or any of `\ / : * ? " < > |` are rejected.
- Names derived from the page title are sanitized: illegal characters become `_`, trailing dots and spaces are removed, Windows reserved names (`CON`, `NUL`, `COM1`, ...) are prefixed with `_`, and the result is truncated to the 255-byte filesystem limit.

## Troubleshooting

**`Missing required tools: ...`**
Install the listed tools (`python3`, `curl`, `jq`, `unzip`) and run again.

**`Could not find the uBOLite chromium asset in the latest release`**
The release layout on GitHub changed, or the GitHub API rate limit was hit. Wait and retry, or set the extension up manually (see above).

**`Redirected to ...; the document may be private or behind a login/captcha`**
The static-HTML lookup was redirected away from the document. Pass `--fname` and `--end-page` to skip the lookup.

**`Could not detect page count`**
The page structure wasn't found in the static HTML. Pass `--end-page` explicitly.

**`--start-page (N) is beyond the document's M pages`**
The start page is past the detected page count.

**Setup failed halfway**
Just run `./run.sh` again, or use `--rebuild-venv` for a clean slate.

## Known limitations

- If you pass an `--end-page` larger than the document's real page count, the run fails on the first nonexistent page and the temporary screenshots are deleted, so progress is lost.
- A page shortfall is only reported as a log line (`Retrieved N of M pages`), not treated as an error.
- Page-count detection relies on the HTML Scribd serves to the default `requests` client, which may change without notice.
- Every run opens a visible (non-headless) browser window.
- Only `/document/` URLs are supported. Presentations and books are treated as documents.

## Responsible use

Use Scriptorium only on documents you have the right to access and copy, such as your own uploads or content whose license permits it. Respect copyright and Scribd's Terms of Service. You are responsible for how you use this tool.

## License

Add a license for the repository (for example MIT) and reference it here.