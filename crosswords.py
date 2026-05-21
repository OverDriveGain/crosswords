import datetime
import logging
import os
import re
import shutil
import tempfile
from io import BytesIO
from typing import Callable, Optional

import cloudscraper
import fitz
import PIL
from PIL import Image

log = logging.getLogger(__name__)
DATE_FORMAT = "%Y/%m/%d"

scraper = cloudscraper.create_scraper()

# progress_cb receives a dict: {phase, done, total, current}
ProgressCb = Callable[[dict], None]


def _noop(_):
    pass


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


def build_crosswords_pdf(
    *,
    from_date: str,
    max_count: int,
    target_page: int,
    progress_cb: ProgressCb = _noop,
):
    """Returns (pdf_bytes | None, processed_dates: list[str])."""
    today = datetime.datetime.today()
    start = datetime.datetime.strptime(from_date, DATE_FORMAT)

    pdf_links: list[tuple[str, str]] = []
    progress_cb({"phase": "scanning", "done": 0, "total": max_count, "current": ""})
    for i in range(max_count):
        day = start + datetime.timedelta(days=i)
        if day >= today:
            break
        day_str = day.strftime(DATE_FORMAT)
        progress_cb({"phase": "scanning", "done": i, "total": max_count, "current": day_str})
        link = _fetch_pdf_url(day_str)
        if link:
            pdf_links.append((link, day_str))
    progress_cb({"phase": "scanning", "done": max_count, "total": max_count, "current": ""})

    if not pdf_links:
        return None, []

    images: list[Image.Image] = []
    processed: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        n = len(pdf_links)
        downloaded: list[tuple[str, str]] = []
        progress_cb({"phase": "downloading", "done": 0, "total": n, "current": ""})
        for i, (link, day_str) in enumerate(pdf_links):
            progress_cb({"phase": "downloading", "done": i, "total": n, "current": day_str})
            fname = os.path.join(tmp, os.path.basename(link))
            if _download(link, fname):
                downloaded.append((fname, day_str))
        progress_cb({"phase": "downloading", "done": n, "total": n, "current": ""})

        m = len(downloaded)
        progress_cb({"phase": "processing", "done": 0, "total": m, "current": ""})
        for i, (fname, day_str) in enumerate(downloaded):
            progress_cb({"phase": "processing", "done": i, "total": m, "current": day_str})
            try:
                pages = fitz.open(fname)
                if target_page >= len(pages):
                    log.warning("Day %s: target_page %d out of range (%d pages)",
                                day_str, target_page, len(pages))
                    pages.close()
                    continue
                page = pages[target_page]
                # Render directly at the target raster from vector source — no upscaling of a 72dpi raster.
                matrix = fitz.Matrix(2038 / page.rect.width, 3426 / page.rect.height)
                pix = page.get_pixmap(matrix=matrix, alpha=False)
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                img = img.crop((1026, 302, 1950, 1888))
                img = img.resize((1445, 2480), PIL.Image.LANCZOS)
                padded = Image.new("RGB", (img.width + 16, img.height), "white")
                padded.paste(img, (0, 0))
                img = padded
                images.append(img)
                processed.append(day_str)
                pages.close()
            except Exception as e:
                log.error("Process failed for %s: %s", fname, e)
        progress_cb({"phase": "processing", "done": m, "total": m, "current": ""})

    if not images:
        return None, []

    buf = BytesIO()
    images[0].save(
        buf, "PDF", resolution=100.0,
        save_all=True, append_images=images[1:],
    )
    return buf.getvalue(), processed
