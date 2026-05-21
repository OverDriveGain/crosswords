import datetime
import logging
import os
import re
import shutil
import tempfile
from io import BytesIO
from typing import Optional

import cloudscraper
import fitz
import PIL
from PIL import Image

log = logging.getLogger(__name__)
DATE_FORMAT = "%Y/%m/%d"

scraper = cloudscraper.create_scraper()


def _fetch_pdf_url(day_str: str) -> Optional[str]:
    url = f"https://addiyar.com/pdf/{day_str}"
    log.debug("Fetching %s", url)
    try:
        r = scraper.get(url, timeout=30)
        r.raise_for_status()
    except Exception as e:
        log.error("Fetch failed for %s: %s", url, e)
        return None
    m = re.search(r"(?P<url>https?://[^\s]+\.pdf)", r.text)
    if not m:
        log.info("No PDF on %s (weekend?)", url)
        return None
    return m.group("url")


def _download(url: str, path: str) -> bool:
    try:
        with scraper.get(url, stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(path, "wb") as f:
                shutil.copyfileobj(r.raw, f)
        return True
    except Exception as e:
        log.error("Download failed for %s: %s", url, e)
        return False


def build_crosswords_pdf(*, from_date: str, max_count: int, target_page: int):
    """Returns (pdf_bytes | None, processed_dates: list[str])."""
    today = datetime.datetime.today()
    start = datetime.datetime.strptime(from_date, DATE_FORMAT)

    pdf_links: list[tuple[str, str]] = []
    for i in range(max_count):
        day = start + datetime.timedelta(days=i)
        if day >= today:
            break
        day_str = day.strftime(DATE_FORMAT)
        link = _fetch_pdf_url(day_str)
        if link:
            pdf_links.append((link, day_str))

    if not pdf_links:
        return None, []

    images: list[Image.Image] = []
    processed: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        for link, day_str in pdf_links:
            fname = os.path.join(tmp, os.path.basename(link))
            if not _download(link, fname):
                continue
            try:
                pages = fitz.open(fname)
                if target_page >= len(pages):
                    log.warning("Day %s: target_page %d out of range (%d pages)",
                                day_str, target_page, len(pages))
                    pages.close()
                    continue
                pix = pages[target_page].get_pixmap()
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                img = img.resize((2038, 3426))
                img = img.crop((1026, 302, 1950, 1888))
                img = img.resize((1445, 2480), PIL.Image.LANCZOS)
                images.append(img)
                processed.append(day_str)
                pages.close()
            except Exception as e:
                log.error("Process failed for %s: %s", fname, e)

    if not images:
        return None, []

    buf = BytesIO()
    images[0].save(
        buf, "PDF", resolution=100.0,
        save_all=True, append_images=images[1:],
    )
    return buf.getvalue(), processed
