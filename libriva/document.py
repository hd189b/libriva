"""Turn an unpacked EPUB into one HTML file split into chapter sections."""
import os, re, urllib.parse
from bs4 import BeautifulSoup

from .errors import ParseError
from .utils import MARK, resolve, soup


def find_footnotes(spine, toc, cover_html):
    """Small spine documents outside the TOC with no headings hold footnotes."""
    toc_files = {t[1] for t in toc}
    fn_files, notes = set(), {}
    for p, lin in spine:
        if p == cover_html or p in toc_files or not os.path.exists(p):
            continue
        try:
            s = soup(p)
        except OSError:
            continue
        b = s.body or s
        if (not lin or len(b.get_text(strip=True)) < 1500) and not b.find(["h1", "h2", "h3"]):
            fn_files.add(p)
    for p in fn_files:
        s = soup(p)
        for el in s.find_all(id=True):
            blk = el if el.name in ("p", "div", "li", "aside") else el.find_parent(["p", "div", "li", "aside"])
            if blk:
                for x in blk.find_all("a", href=True):
                    x.unwrap()
                notes[(p, el["id"])] = blk.decode_contents()
    return fn_files, notes


# "1. Something", "2) Something", "3 - Something": the number is an artefact of the
# TOC, not part of the title. A bare "1." (nothing after it) is left alone, and so is
# anything roman, so Seneca's letters II, III, V keep their names.
NUMBER_PREFIX = re.compile(r"^\s*\d{1,3}\s*[.)\]:\u2013\u2014-]\s+")


def clean_title(t):
    """Drop a leading enumeration from a TOC title, keeping the words."""
    t = (t or "").strip()
    return NUMBER_PREFIX.sub("", t, count=1).strip() or t


def toc_depth(toc):
    """Deepest level the book's own table of contents reaches."""
    return max((lv for _, _, _, lv in toc), default=1)


def chapter_starts(toc, flow, level=None):
    """Chapters = TOC entries at or above `level`; fall back to one per file.

    level None/0 means auto: go as deep as this book's TOC actually goes.
    """
    if not level:
        level = toc_depth(toc)
    order = {p: i for i, p in enumerate(flow)}
    starts, seen = [], set()
    for t, f, fr, lv in toc:
        if lv <= level and f in order and (f, fr) not in seen:
            seen.add((f, fr))
            starts.append(dict(title=clean_title(t), file=f, frag=fr, level=lv))
    if not starts:
        for p in flow:
            h = soup(p).find(["h1", "h2", "h3", "title"])
            starts.append(dict(title=clean_title(h.get_text(" ", strip=True)) if h
                               else os.path.basename(p), file=p, frag="", level=1))
    return starts


def build_html(root, tmp, spine, cover_html, toc, level, font, font_src, font_size, page):
    """Write book.html into tmp; return (path, starts).

    font_src is (kind, detail) from fonts.resolve_body: 'file' with a path,
    'google' with a family name, 'system' with a family name, or (None, None)
    to fall through to the generic serif stack.
    """
    fn_files, notes = find_footnotes(spine, toc, cover_html)
    flow = [p for p, lin in spine if p != cover_html and p not in fn_files and os.path.exists(p)]
    if not flow:
        raise ParseError("no readable text documents in this book")
    starts = chapter_starts(toc, flow, level)

    css_files, pieces = [], []   # pieces: (chapter index | "START" | None, html)

    def pid(f, i):
        return re.sub(r"\W", "_", os.path.relpath(f, root)) + "__" + i

    for p in flow:
        s = soup(p)
        for l in s.find_all("link", rel="stylesheet"):
            if not l.get("href"):
                continue
            c = resolve(p, l["href"])[0]
            if c not in css_files and os.path.exists(c):
                css_files.append(c)
        body = s.body or s
        drop = []
        for el in body.find_all(id=True):
            el["id"] = pid(p, el["id"])
        for el in body.find_all("a", attrs={"name": True}):
            if not el.get("id"):
                el["id"] = pid(p, el["name"])
        for ln in body.find_all("a", href=True):
            h = ln["href"]
            if re.match(r"^[a-z]+:", h):
                continue
            f, fr = resolve(p, h)
            if (f, fr) in notes:                      # footnote in a separate file -> inline
                blk = ln.find_parent(["p", "div", "li", "td", "blockquote"]) or ln
                n = s.new_tag("div", attrs={"class": "fnote"})
                n.append(BeautifulSoup(notes[(f, fr)], "html.parser"))
                blk.insert_after(n)
                ln.unwrap()
                continue
            if f == p and fr:
                tgt = body.find(id=pid(p, fr))
                if tgt is not None and tgt.name == "aside":   # EPUB3 aside footnote -> inline
                    blk = ln.find_parent(["p", "div", "li"]) or ln
                    n = s.new_tag("div", attrs={"class": "fnote"})
                    n.append(BeautifulSoup(tgt.decode_contents(), "html.parser"))
                    blk.insert_after(n)
                    drop.append(tgt)
                    ln.unwrap()
                    continue
            ln["href"] = "#" + (pid(f, fr) if fr else pid(f, "top"))
        for d in drop:
            if d.parent:
                d.decompose()
        for img in body.find_all(["img", "image"]):
            for attr in ("src", "xlink:href", "href"):
                if img.get(attr) and not img[attr].startswith("data:"):
                    img[attr] = "file://" + resolve(p, img[attr])[0]
        # flatten wrapper divs, then split top-level children at chapter anchors
        cont = body
        while (len(cont.find_all(True, recursive=False)) == 1
               and cont.find(True, recursive=False).name in ("div", "section", "article")):
            cont = cont.find(True, recursive=False)
        kids = list(cont.children)
        cuts = []
        for ci, st in enumerate(starts):
            if st["file"] != p:
                continue
            if not st["frag"]:
                cuts.append((0, ci))
                continue
            el = cont.find(id=pid(p, st["frag"]))
            if el is None:
                cuts.append((0, ci))
                continue
            while el.parent is not cont and el.parent is not None:
                el = el.parent
            cuts.append((kids.index(el) if el in kids else 0, ci))
        cuts.sort()
        pos, cur = 0, None
        topid = f'<a id="{pid(p, "top")}"></a>'
        for k, ci in cuts + [(len(kids), None)]:
            html = "".join(str(x) for x in kids[pos:k])
            if pos == 0:
                html = topid + html
            if html.strip():
                pieces.append((cur, html))
            pos, cur = k, ci
            if ci is not None:
                pieces.append(("START", ci))

    body_html, open_ = "", False
    for key, html in pieces:
        if key == "START":
            if open_:
                body_html += "</section>"
            body_html += f'<section class="chap"><span class="mk">{MARK.format(html)}</span>'
            open_ = True
        else:
            if not open_:
                body_html += '<section class="chap">'
                open_ = True
            body_html += html
    if open_:
        body_html += "</section>"

    css = ""
    for c in css_files:
        try:
            t = open(c, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        css += re.sub(r"url\(['\"]?([^)'\"]+)['\"]?\)",
                      lambda m: "url(file://" + resolve(c, m.group(1))[0] + ")", t)
    fontcss, gf = "", ""
    kind, detail = font_src if font_src else (None, None)
    if kind == "file":
        fontcss = f"@font-face{{font-family:'{font}';src:url(file://{os.path.abspath(detail)})}}"
    elif kind == "google":
        fam = urllib.parse.quote_plus(detail)
        gf = (f'<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family={fam}:'
              f'ital,wght@0,400;0,600;0,700;1,400;1,600&display=block">')
    # 'system' needs nothing: Chromium picks the installed family up by name
    extra = fontcss + f"""
@page{{size:{page['w']}mm {page['h']}mm;margin:{page['top']}mm {page['outside']}mm {page['bottom']}mm {page['outside']}mm}}
@page :left{{margin-left:{page['outside']}mm;margin-right:{page['inside']}mm}}
@page :right{{margin-left:{page['inside']}mm;margin-right:{page['outside']}mm}}
*{{page-break-before:auto!important;break-before:auto!important}}
html,body{{margin:0;padding:0}}
body{{font-size:{font_size}pt;line-height:1.38;text-align:justify;hyphens:auto;color:#000}}
body,body *:not(code):not(pre):not(.mk){{font-family:'{font}','EB Garamond',Georgia,serif!important}}
section.chap{{break-before:page!important;page-break-before:always!important;position:relative}}
.mk{{position:absolute;top:0;left:0;font:1px Courier,monospace!important;color:#fff}}
p{{margin:0;orphans:2;widows:2}}
h1,h2,h3,h4{{font-weight:500;text-align:center;hyphens:none;break-after:avoid}}
.fnote{{font-size:.8em;line-height:1.3;margin:.4em 0 .5em;padding-left:1em;border-left:.5pt solid #999;text-indent:0}}
a{{color:inherit;text-decoration:none}}
img,svg{{max-width:100%;height:auto}}
"""
    book = os.path.join(tmp, "book.html")
    with open(book, "w", encoding="utf-8") as f:
        f.write(f'<!doctype html><html lang="en"><head><meta charset="utf-8">{gf}'
                f"<style>{css}</style><style>{extra}</style></head>"
                f"<body>{body_html}</body></html>")
    return book, starts
