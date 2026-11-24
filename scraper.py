import os
import re
from shutil import rmtree
from tempfile import mkdtemp

import click
import img2pdf
import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from tqdm import tqdm


SCRIBD_URL = "https://www.scribd.com/document/"
USER_DATA_DIR = os.path.expanduser("./playwright_profile/")
OUTPUT_PATH = os.path.abspath("./outputs/")
SCREENSHOTS = f"{OUTPUT_PATH}/screenshots/"
IMG_EXTENSION = ".png"
CHUNK_SIZE = 300
EXT_PATH = os.getenv("EXT_DIR")
MAX_NAME_BYTES = 255
INVALID_NAME_CHARS = re.compile(r'[\x00-\x1f\x7f\\/:*?"<>|]')
WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def create_pdf(fname, image_data_list):
    """
    Combine page images into a single PDF in OUTPUT_PATH.

    Args:
        fname: Output file name, including '.pdf'. Written inside
            OUTPUT_PATH; an existing file with the same name is overwritten.
        image_data_list: Image file paths, in page order. Passed straight
            to img2pdf.convert().

    Raises:
        Exception: Whatever img2pdf raises, e.g. if the list is empty or an
            image can't be read. Nothing is caught here.
    """
    file_path = os.path.join(OUTPUT_PATH, fname)
    with open(file_path, "wb") as f:
        f.write(img2pdf.convert(image_data_list))
    print(f"Successfully created {file_path} from {
          len(image_data_list)} images!")


def get_images(playwright, url, img_folder, start_page, end_page, pbar):
    """
    Screenshot a range of rendered pages from a Scribd document.

    Launches a persistent, headed Chromium context with the extension at
    EXT_PATH loaded, opens the document, hides all fixed/sticky elements
    (banners, headers, paywall overlays), then scrolls to each page element
    and saves a screenshot of it as '<img_folder>/page<N>.png'. The context
    is always closed on exit.

    Args:
        playwright: An active sync Playwright instance.
        url: Full Scribd document URL.
        start_page: First page to capture (1-based).
        end_page: Page to stop at, EXCLUSIVE (unlike run() and the CLI,
            where end_page is inclusive).
        img_folder: Existing directory to write screenshots into.
        pbar: tqdm bar; advanced by one per page captured.

    Returns:
        Absolute path of img_folder.

    Raises:
        playwright.sync_api.TimeoutError: If a page element can't be found
            or scrolled into view, e.g. the range exceeds the document's
            real page count. Pages captured before the failure remain on
            disk in img_folder.
    """
    context = playwright.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR,
            headless=True,
            args=[
                f"--disable-extensions-except={EXT_PATH}",
                f"--load-extension={EXT_PATH}",
            ],
        )

    try:
        page = context.new_page()
        page.goto(url, wait_until="domcontentloaded")
        page.evaluate("""
            () => document.querySelectorAll('*').forEach(e => {
                const pos = getComputedStyle(e).position;
                if (pos === 'fixed' || pos === 'sticky') e.style.setProperty('display', 'none', 'important');
            })
            """)

        for page_idx in range(start_page, end_page):
            page.locator('.outer_page').nth(page_idx - 1)\
                .scroll_into_view_if_needed()
            page.locator(f'#outer_page_{page_idx}')\
                .scroll_into_view_if_needed()
            page.locator(f"#page{page_idx}").screenshot(
                path=f"{img_folder}/page{page_idx}{IMG_EXTENSION}")

            pbar.update(1)
        return os.path.abspath(img_folder)

    finally:
        context.close()


def run(fname, url, start_page, end_page):
    """
    Screenshot a page range in chunks and assemble the PDF.

    Pages are captured in batches of CHUNK_SIZE, each in a fresh Playwright
    session and browser context, so a long document doesn't exhaust one
    session. Screenshots go to a temporary folder under SCREENSHOTS, are
    sorted by the page number in their file name, and are combined by
    create_pdf(). The temporary folder is always deleted afterwards,
    including on failure.

    The page range is 1-based and inclusive on both ends. A progress line
    reports how many pages were retrieved versus expected, but a shortfall
    is not treated as an error.

    Args:
        fname: Output file name, including '.pdf'.
        url: Full Scribd document URL.
        start_page: First page to capture (1-based).
        end_page: Last page to capture (inclusive).

    Raises:
        playwright.sync_api.TimeoutError: If a page can't be captured.
            Progress is lost because the temporary folder is deleted.
        Exception: Whatever create_pdf() raises, e.g. if no screenshots
            were produced.
    """
    expected = end_page - start_page + 1
    img_folder = os.path.abspath(mkdtemp(dir=SCREENSHOTS))

    try:
        with tqdm(total=end_page, desc="Scraping pages", unit="page") as pbar:
            for chunk_start in range(start_page, end_page + 1, CHUNK_SIZE):
                chunk_end = min(chunk_start + CHUNK_SIZE, end_page + 1)
                with sync_playwright() as p:
                    get_images(p, url, img_folder,
                               chunk_start, chunk_end, pbar)

        pages = sorted(
            (
                os.path.join(img_folder, name)
                for name in os.listdir(img_folder)
                if name.lower().endswith(IMG_EXTENSION)
            ),
            key=page_number,
        )

        tqdm.write(f"Retrieved {len(pages)} of {expected} pages...")
        create_pdf(fname, pages)
    finally:
        rmtree(img_folder)


def page_number(path):
    """
    Extract the page number from a screenshot path, for sorting.

    Takes the first run of digits in the file name (not the full path), so
    'page12.png' gives 12.

    Args:
        path: Path to a screenshot file.

    Returns:
        The page number as an int, or -1 if the file name has no digits.
    """
    match = re.search(r"(\d+)", os.path.basename(path))
    return int(match.group(1)) if match else -1


def preflight():
    """
    Fail fast on environment problems before any network or browser work.

    Checks that EXT_PATH is set and points to an existing directory, and
    creates the screenshots directory (and OUTPUT_PATH) if missing.

    Raises:
        click.ClickException: If EXT_PATH is unset or not a directory.
    """
    if not EXT_PATH or not os.path.isdir(EXT_PATH):
        raise click.ClickException(
            "EXT_PATH must be set to the directory of the unpacked browser "
            "extension.")
    os.makedirs(SCREENSHOTS, exist_ok=True)


def validate_user_fname(fname):
    """
    Reject a user-supplied file name that contains invalid characters.

    Control characters, path separators, and any of \\ / : * ? " < > | are
    refused rather than silently rewritten, so the user never gets a file
    named differently from what they typed.

    Args:
        fname: Stripped, non-empty --fname value.

    Raises:
        click.BadParameter: If fname contains an invalid character.
    """
    if INVALID_NAME_CHARS.search(fname):
        raise click.BadParameter(
            'Must not contain path separators, control characters, or '
            'any of \\ / : * ? " < > |. Files are written to the '
            "output directory.",
            param_hint="--fname")


def fetch_soup(url, doc_id):
    """
    Fetch the document's static HTML and parse it.

    Uses the default requests User-Agent on purpose: it receives the
    bot-specific HTML that contains the accurate page count.

    Args:
        url: Full Scribd document URL.
        doc_id: Document ID, used to detect redirects away from the
            document (usually a login page or captcha).

    Returns:
        A BeautifulSoup tree of the response body.

    Raises:
        click.ClickException: If the request fails, returns an HTTP error,
            or is redirected to a URL that no longer contains doc_id.
    """
    try:
        # Deliberately no custom User-Agent: the default client gets the
        # bot-specific HTML that contains the accurate page count.
        response = requests.get(url, timeout=15)
        response.raise_for_status()
    except requests.RequestException as e:
        raise click.ClickException(f"Could not fetch {url}: {e}") from e

    # A redirect away from the document usually means login or a captcha.
    if doc_id not in response.url:
        raise click.ClickException(
            f"Redirected to {response.url}; the document may be private or "
            "behind a login/captcha. Pass --fname and --end-page to skip "
            "this lookup.")
    # .content lets bs4 detect the encoding itself.
    return BeautifulSoup(response.content, "html.parser")


def detect_page_count(soup):
    """
    Count the pages in the document's static HTML.

    Counts <div class="outer_page"> elements.

    Args:
        soup: Parsed document page.

    Returns:
        The number of pages, always at least 1.

    Raises:
        click.ClickException: If no page elements are found.
    """
    count = len(soup.find_all("div", class_="outer_page"))
    if count == 0:
        raise click.ClickException(
            "Could not detect page count. Pass --end-page explicitly.")
    return count


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.option("--doc", "--doc-id", "doc", required=True,
              help="Scribd document ID or full document URL.")
@click.option("--fname",
              help="Output file name. '.pdf' is added if missing.")
@click.option("--start-page", default=1, type=click.IntRange(min=1),
              help="First page to fetch. Default: 1.")
@click.option("--end-page", type=click.IntRange(min=1),
              help="Last page to fetch. Default: last page of the document.")
def cli(doc, fname, start_page, end_page):
    """
    Download a Scribd document's pages and save them as a PDF.

    \f
    Resolves the document URL, fills in a missing output name and end page
    from the document's static HTML, validates the page range, then hands
    off to run().

    Args:
        doc: Numeric Scribd document ID, or a document URL containing it.
        fname: Output file name; derived from the page title if omitted.
        start_page: First page to fetch (1-based).
        end_page: Last page to fetch (inclusive); detected if omitted.

    Raises:
        click.BadParameter: If no document ID can be found in doc, or fname
            contains invalid characters.
        click.ClickException: If the environment is misconfigured, the page
            can't be fetched, or the page count can't be detected.
        click.UsageError: If the page range is invalid.
    """
    match = re.search(r"\d+", doc)
    if not match:
        raise click.BadParameter("No numeric document ID found.",
                                 param_hint="--doc-id")
    doc_id = match.group()
    url = f"{SCRIBD_URL}{doc_id}"


    # Validate the explicit range before any network access.
    if end_page is not None and end_page < start_page:
        raise click.UsageError(
            f"--end-page ({end_page}) must be >= --start-page "
            f"({start_page}).")

    preflight()

    soup = None
    if fname is None or end_page is None:
        soup = fetch_soup(url, doc_id)

    fname = (fname or "").strip() or None
    if fname:
        validate_user_fname(fname)
    else:
        contents = [m.get("content", "")
                    for m in soup.find_all("meta", property="og:title")]
        pdf_title = next((c for c in contents if c.lower().endswith(".pdf")),
                         None)
        if pdf_title:
            fname = pdf_title
        elif contents:
            fname = contents[0].partition("|")[0].strip()
        fname = fname or f"scribd_{doc_id}"

    fname = re.sub(r'[\\/:*?"<>|]', "_", fname.strip())
    if not fname.lower().endswith(".pdf"):
        fname += ".pdf"

    if end_page is None:
        end_page = detect_page_count(soup)
        if start_page > end_page:
            raise click.UsageError(
                f"--start-page ({start_page}) is beyond the document's "
                f"{end_page} pages.")

    run(fname, url, start_page, end_page)


if __name__ == "__main__":
    cli()
