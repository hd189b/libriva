"""Page numbers, running headers and the final merge."""
import hashlib, io, os, re

from pypdf import PdfReader, PdfWriter
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from .errors import BookBuildError
from .utils import MM, roman


def _register(paths):
    """Register the folio/running-head font; fall back to Times if it will not load."""
    reg, ital = paths if paths else (None, None)
    sf, sfi = "Times-Roman", "Times-Italic"
    if reg:
        try:
            name = "Stamp" + hashlib.md5(reg.encode()).hexdigest()[:8]
            pdfmetrics.registerFont(TTFont(name, reg))
            sf = sfi = name
        except Exception as e:
            print(f"  ! stamp font unusable ({e}); falling back to Times")
            return "Times-Roman", "Times-Italic"
    if ital:
        try:
            name = "StampIt" + hashlib.md5(ital.encode()).hexdigest()[:8]
            pdfmetrics.registerFont(TTFont(name, ital))
            sfi = name
        except Exception:
            pass                      # regular stands in for the italic head
    return sf, sfi


def stamp(book_pdf, starts, page, intro=0, number_from=0, stamp_fonts=None):
    """Draw page numbers + chapter headers onto the body pages. Returns the pages.

    With an introduction: unnumbered up to it, roman through it, arabic from 1 after.
    Without one: arabic from 1, starting at chapter `number_from` (0 = first page).
    """
    sf, sfi = _register(stamp_fonts)
    try:
        pages = list(PdfReader(book_pdf).pages)
    except Exception as e:
        raise BookBuildError(f"cannot read the rendered PDF: {e}")

    start_page = {}
    for i, p in enumerate(pages):
        try:
            text = p.extract_text() or ""
        except Exception:
            text = ""
        for m in re.finditer(r"ZQXCH(\d+)ZQX", text.replace(" ", "")):
            start_page.setdefault(int(m.group(1)), i)
    first_page_of = {v: k for k, v in sorted(start_page.items(), reverse=True)}

    if intro and (intro - 1) in start_page:
        ii = intro - 1
        lv = starts[ii]["level"]
        i0 = start_page[ii]
        nxt = [start_page[j] for j in range(ii + 1, len(starts))
               if j in start_page and starts[j]["level"] <= lv]
        a0 = nxt[0] if nxt else len(pages)
    else:
        ch = (number_from or 0) - 1
        i0 = a0 = start_page.get(ch, 0) if ch >= 0 else 0

    # type scales gently with the sheet: 9pt folio on A5, a touch more on bigger paper
    size = round(9 * (page["w"] / 148.0) ** 0.5, 1)
    head = round(size - 0.5, 1)
    cur = None
    for i, p in enumerate(pages):
        if i in first_page_of:
            cur = first_page_of[i]
        lab = str(i - a0 + 1) if i >= a0 else (roman(i - i0 + 1) if i >= i0 else None)
        if not lab:
            continue
        w, h = float(p.mediabox.width), float(p.mediabox.height)
        b = io.BytesIO()
        c = canvas.Canvas(b, pagesize=(w, h))
        c.setFont(sf, size)
        c.drawCentredString(w / 2, page["folio"] * MM, lab)
        if cur is not None and i not in first_page_of:
            t = starts[cur]["title"]
            c.setFont(sfi, head)
            room = w - (page["inside"] + page["outside"] + 6) * MM
            if c.stringWidth(t, sfi, head) > room:
                while c.stringWidth(t + "…", sfi, head) > room and len(t) > 4:
                    t = t[:-1]
                t = t.rstrip() + "…"
            # outer margin; page 1 of the body is a right page
            right = (page["outside"] if i % 2 == 0 else page["inside"]) * MM
            c.drawRightString(w - right, h - page["head"] * MM, t)
        c.save()
        b.seek(0)
        p.merge_page(PdfReader(b).pages[0])
    return pages


def image_page(path):
    """One PDF page holding the image at its native size (pixels / dpi)."""
    from PIL import Image
    try:
        im = Image.open(path)
    except Exception as e:
        raise BookBuildError(f"cannot read -ac image: {e}")
    dpi = (im.info.get("dpi") or (72, 72))[0] or 72
    w, h = im.width * 72 / dpi, im.height * 72 / dpi
    b = io.BytesIO()
    c = canvas.Canvas(b, pagesize=(w, h))
    c.drawImage(os.path.abspath(path), 0, 0, w, h)
    c.save()
    b.seek(0)
    return PdfReader(b).pages[0]


def write_pdf(out, pages, cover_pdf=None, ac_image=None):
    wr = PdfWriter()
    if ac_image:
        wr.add_page(image_page(ac_image))
    if cover_pdf and os.path.exists(cover_pdf):
        for p in PdfReader(cover_pdf).pages:
            wr.add_page(p)
    for p in pages:
        wr.add_page(p)
    d = os.path.dirname(os.path.abspath(out))
    if d:
        os.makedirs(d, exist_ok=True)
    try:
        with open(out, "wb") as f:
            wr.write(f)
    except OSError as e:
        raise BookBuildError(f"cannot write {out}: {e}")
    return len(wr.pages)
