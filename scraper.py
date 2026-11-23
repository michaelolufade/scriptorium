import os
import random
import time

import click
import img2pdf
import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from tqdm import tqdm


SCRIBD_URL = "https://www.scribd.com/document/"
USER_DATA_DIR = os.path.expanduser("./playwright_profile/")
OUTPUT_PATH = os.path.abspath("./outputs/")
CHUNK_SIZE = 300


def download_images(img_src_list):
    image_data_list = []
    print("Downloading images...")
    for i, url in enumerate(tqdm(img_src_list.values())):
        time.sleep(random.random() * 2)
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            image_data_list.append(response.content)
        except Exception as e:
            print(f"Failed to download {url}: {e}")

        if i % 50 == 0:
            time.sleep(2 + (random.random() * 3))
    print("Download complete!")
    return image_data_list


def create_pdf(fname, image_data_list):
    with open(fname, "wb") as f:
        f.write(img2pdf.convert(image_data_list))
    print(f"Successfully created {fname} from {
          len(image_data_list)} images!")


def get_image_src(playwright, url, start_page, end_page, pbar):
    context = playwright.chromium.launch_persistent_context(
        user_data_dir=USER_DATA_DIR,
        headless=True,
    )

    page = context.new_page()
    page.goto(url, wait_until="domcontentloaded")

    time.sleep(1)

    for page_idx in range(start_page - 1, end_page):
        page.locator('.outer_page').nth(page_idx).scroll_into_view_if_needed()
        pbar.update(1)

    time.sleep(1)
    get_img_js = """
        () => {
            // Select all outer_page container elements currently in the DOM
            const outerPages = document.querySelectorAll('.outer_page');
            const mapping = {};

            outerPages.forEach((el, index) => {
                // Find a unique identifier for the page (data-page-number, id, or fallback index)
                const pageId = el.getAttribute('data-page-number') || el.id || `page_${index + 1}`;

                // Find the image nested inside this specific outer_page div
                const img = el.querySelector('img');

                if (img && img.src && img.src.startsWith('http')) {
                    const src = img.src;
                    // Apply your filter criteria
                    if (src.includes('scribdassets') || src.includes('doc')) {
                                    mapping[pageId] = src;
                    }
                }
            });

            return mapping;
        }
    """
    page_image_dict = page.evaluate(get_img_js)
    return page_image_dict


def run(fname, url, start_page, end_page):
    image_sources = {}
    with tqdm(total=end_page, desc="Scraping pages", unit="page") as pbar:
        for page in range(start_page, end_page, CHUNK_SIZE):
            if page + CHUNK_SIZE >= end_page:
                stop = end_page
            else:
                stop = page + CHUNK_SIZE
            with sync_playwright() as p:
                image_sources.update(get_image_src(p, url, page, stop, pbar))

    print(f"Retrieved {len(image_sources)} pages...")
    image_data_list = download_images(image_sources)
    create_pdf(fname, image_data_list)


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.option("--doc-id", required=True,
              help="SCRIBD documnet ID, typically available in the url")
@click.option("--fname",
              help="Name of produced file. DO NOT add '.pdf'")
@click.option("--start-page", default=1, type=click.INT,
              help="Page number to start with. Default is 1")
@click.option("--end-page", type=click.INT,
              help="Page number to end with. Default is 1")
def cli(doc_id, fname, start_page, end_page):
    url = os.path.join(SCRIBD_URL, doc_id)

    if not fname or not end_page:
        response = requests.get(url)
        soup = BeautifulSoup(response.text, 'html.parser')

    if not fname:
        title_metas = soup.find_all("meta", property="og:title")
        title = title_metas[0].get("content", "")
        fname = f"{title.split('|')[0].strip()}.pdf"

        for meta in title_metas:
            if meta.get("content").endswith(".pdf"):
                fname = meta.get("content")
    else:
        fname += ".pdf"

    if not end_page:
        page_tags = soup.find_all("div", class_="outer_page")
        end_page = len(page_tags)

    run(fname, url, start_page, end_page)


if __name__ == "__main__":
    cli()
