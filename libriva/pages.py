"""Paper sizes and the book margins that suit each one.

Margins follow the usual printed-book proportions: the spine (inside) edge gets more
room than the outside, the foot more than the head once the running head is counted,
and everything scales with the sheet. `folio`/`head` are the baselines for the page
number and the running head, measured from the bottom and top edges.
"""

PAGES = {
    #        w      h     top  bottom inside outside folio head
    "a5":    dict(w=148.0, h=210.0, top=22, bottom=19, inside=19.0, outside=15.0, folio=10, head=12),
    "b5":    dict(w=176.0, h=250.0, top=25, bottom=22, inside=22.0, outside=17.0, folio=12, head=14),
    "a4":    dict(w=210.0, h=297.0, top=28, bottom=25, inside=25.0, outside=20.0, folio=14, head=16),
    "letter": dict(w=215.9, h=279.4, top=25.4, bottom=25.4, inside=25.4, outside=19.0, folio=13, head=14),
    "legal": dict(w=215.9, h=355.6, top=25.4, bottom=25.4, inside=25.4, outside=19.0, folio=13, head=14),
}
DEFAULT = "a5"


def names():
    return sorted(PAGES)


def get(name):
    """Look up a paper size by name; returns a dict with its name included."""
    key = (name or DEFAULT).strip().lower().replace(" ", "").replace("-", "")
    if key not in PAGES:
        raise KeyError(name)
    p = dict(PAGES[key])
    p["name"] = key
    p["label"] = f"{key.upper()} {p['w']:g}x{p['h']:g}mm"
    return p
