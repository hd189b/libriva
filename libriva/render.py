"""Chromium rendering. One browser is shared by the whole batch."""
import os

from .errors import BookBuildError, RenderError

# How much of the cover may be zoomed off the page before filling stops being sensible
# and the whole image is fitted (with bands) instead.
MAX_COVER_CROP = 0.20

COVER_CSS = ("@page{{size:{w}mm {h}mm;margin:0}}body{{margin:0}}"
             "img{{width:{w}mm;height:{h}mm;object-fit:{fit};"
             "object-position:center;display:block}}")


def cover_fit(path, page):
    """'cover' zooms the image until it touches both page edges, trimming the
    overflow on the long axis; a wildly different aspect falls back to 'contain'."""
    try:
        from PIL import Image
        with Image.open(path) as im:
            aspect = im.width / im.height
    except Exception:
        return "cover", 0.0
    pa = page["w"] / page["h"]
    crop = (1 - pa / aspect) if aspect > pa else (1 - aspect / pa)
    return ("contain" if crop > MAX_COVER_CROP else "cover"), crop


class Renderer:
    def __enter__(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise RenderError("playwright is not installed - pip install playwright")
        self._pw = sync_playwright().start()
        try:
            self._br = self._pw.chromium.launch()
        except Exception as e:
            self._pw.stop()
            raise RenderError(f"cannot start Chromium ({e}).\n"
                              "  Install it with: python -m playwright install chromium")
        return self

    def __exit__(self, *exc):
        try:
            self._br.close()
        finally:
            self._pw.stop()
        return False

    def _page(self):
        return self._br.new_page()

    def cover_pdf(self, cover_img, tmp, page):
        """Render the EPUB cover full-bleed on A5. Returns a pdf path or None."""
        if not cover_img or not os.path.exists(cover_img):
            return None
        html = os.path.join(tmp, "cover.html")
        out = os.path.join(tmp, "cover.pdf")
        fit, crop = cover_fit(cover_img, page)
        if fit == "contain":
            print(f"  cover is {crop * 100:.0f}% off {page['name'].upper()}'s shape; "
                  "fitted whole rather than cropping that much")
        with open(html, "w", encoding="utf-8") as f:
            f.write(f'<html><style>{COVER_CSS.format(fit=fit, w=page["w"], h=page["h"])}</style>'
                    f'<img src="file://{cover_img}"></html>')
        pg = self._page()
        try:
            pg.goto("file://" + html)
            pg.pdf(path=out, width=f"{page['w']}mm", height=f"{page['h']}mm",
                   prefer_css_page_size=True, print_background=True)
        except Exception:
            return None            # a broken cover is not worth failing the book for
        finally:
            pg.close()
        return out

    def book_pdf(self, book_html, tmp, page, timeout=120000):
        out = os.path.join(tmp, "book.pdf")
        pg = self._page()
        try:
            try:
                pg.goto("file://" + book_html, wait_until="networkidle", timeout=timeout)
            except Exception:
                pg.goto("file://" + book_html, wait_until="load", timeout=timeout)
            pg.evaluate("document.fonts.ready.then(()=>true)")
            side = (page["inside"] + page["outside"]) / 2
            pg.pdf(path=out, width=f"{page['w']}mm", height=f"{page['h']}mm",
                   prefer_css_page_size=True, print_background=True,
                   margin=dict(top=f"{page['top']}mm", bottom=f"{page['bottom']}mm",
                               left=f"{side}mm", right=f"{side}mm"))
        except Exception as e:
            raise BookBuildError(f"rendering failed: {e}")
        finally:
            pg.close()
        return out
