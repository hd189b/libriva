"""EPUB container parsing: manifest, spine, cover, table of contents."""
import os, urllib.parse

from .errors import ParseError
from .utils import resolve, soup


def find_opf(root):
    """Path of the OPF package file, via container.xml or by searching the tree."""
    cpath = os.path.join(root, "META-INF", "container.xml")
    if os.path.exists(cpath):
        try:
            rf = soup(cpath).find("rootfile")
            if rf and rf.get("full-path"):
                opf = os.path.join(root, urllib.parse.unquote(rf["full-path"]))
                if os.path.exists(opf):
                    return opf
        except Exception:
            pass
    for dirpath, _, names in os.walk(root):
        for n in sorted(names):
            if n.lower().endswith(".opf"):
                return os.path.join(dirpath, n)
    raise ParseError("no OPF package file found (not a readable EPUB)")


def read_epub(root):
    """Return (spine, cover_image, cover_html, toc) for an unpacked EPUB tree."""
    opf = find_opf(root)
    o = soup(opf)
    od = os.path.dirname(opf)
    man = {}
    for it in o.find_all("item"):
        if not it.get("id") or not it.get("href"):
            continue
        man[it["id"]] = dict(path=os.path.normpath(os.path.join(od, urllib.parse.unquote(it["href"]))),
                             type=it.get("media-type", ""), props=it.get("properties", ""))
    spine = [(man[r["idref"]]["path"], r.get("linear", "yes") != "no")
             for r in o.find_all("itemref") if r.get("idref") in man]
    if not spine:
        raise ParseError("the spine is empty (no readable text content)")

    # cover image
    cover = None
    for it in man.values():
        if "cover-image" in it["props"]:
            cover = it["path"]
    m = o.find("meta", attrs={"name": "cover"})
    if not cover and m and m.get("content") in man:
        cover = man[m["content"]]["path"]
    cover_html = None
    ref = o.find("reference", attrs={"type": "cover"})
    if ref and ref.get("href"):
        cover_html = resolve(opf, ref["href"])[0]
    elif spine and "cover" in os.path.basename(spine[0][0]).lower():
        cover_html = spine[0][0]
    if cover_html and os.path.exists(cover_html):
        s = soup(cover_html)
        img = s.find("img") or s.find("image")
        src = img and (img.get("src") or img.get("xlink:href") or img.get("href"))
        if not cover and src:
            cover = resolve(cover_html, src)[0]

    # table of contents (EPUB3 nav, else NCX)
    toc = []
    nav = next((i["path"] for i in man.values() if "nav" in i["props"]), None)
    if nav and os.path.exists(nav):
        s = soup(nav)
        n = s.find("nav", attrs={"epub:type": "toc"}) or s.find("nav")

        def walk(ol, lv):
            for li in ol.find_all("li", recursive=False):
                a = li.find("a")
                if a and a.get("href"):
                    f, fr = resolve(nav, a["href"])
                    toc.append((a.get_text(" ", strip=True), f, fr, lv))
                sub = li.find("ol")
                if sub:
                    walk(sub, lv + 1)

        if n and n.find("ol"):
            walk(n.find("ol"), 1)
    if not toc:
        ncx = next((i["path"] for i in man.values() if i["type"] == "application/x-dtbncx+xml"), None)
        if ncx and os.path.exists(ncx):
            s = soup(ncx)

            def walkn(node, lv):
                for np in node.find_all("navpoint", recursive=False):
                    t = np.find("text")
                    ct = np.find("content")
                    if ct and ct.get("src"):
                        f, fr = resolve(ncx, ct["src"])
                        toc.append((t.get_text(" ", strip=True) if t else "", f, fr, lv))
                    walkn(np, lv + 1)

            nm = s.find("navmap")
            if nm:
                walkn(nm, 1)
    return spine, cover, cover_html, toc
