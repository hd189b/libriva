"""Finding fonts: the curated list, Google Fonts, installed fonts, or a local file.

Everything degrades: no internet falls back to installed fonts, no fontconfig
falls back to Google, and nothing at all falls back to the built-in Times.
"""
import json, os, re, shutil, subprocess, urllib.parse, urllib.request

CACHE = os.path.join(os.path.expanduser("~/.cache"), "bookbuild", "fonts")
# Google serves woff2 to browsers and plain TTF to anything else; reportlab needs TTF.
TTF_UA = "bookbuild/1.0"
METADATA = "https://fonts.google.com/metadata/fonts"
SFNT_MAGIC = (b"\x00\x01\x00\x00", b"true", b"ttcf")

_families = None        # None = not looked up yet, [] = looked up and offline


def _get(url, ua="Mozilla/5.0", timeout=10):
    req = urllib.request.Request(url, headers={"User-Agent": ua})
    return urllib.request.urlopen(req, timeout=timeout).read()


# ------------------------------------------------------------------ Google
def google_families(timeout=8):
    """Every Google Fonts family, [] when offline. Cached on disk for offline search."""
    global _families
    if _families is not None:
        return _families
    cache = os.path.join(CACHE, "families.json")
    try:
        raw = _get(METADATA, timeout=timeout).decode("utf-8", "replace")
        data = json.loads(raw.lstrip(")]}'\n"))
        _families = sorted(f["family"] for f in data.get("familyMetadataList", []))
        os.makedirs(CACHE, exist_ok=True)
        with open(cache, "w") as f:
            json.dump(_families, f)
    except Exception:
        try:
            with open(cache) as f:
                _families = json.load(f)          # stale list, but search still works
        except Exception:
            _families = []
    return _families


def online():
    return bool(google_families())


def find_google(name):
    """Canonical Google family name, or None."""
    n = (name or "").strip().lower()
    return next((f for f in google_families() if f.lower() == n), None)


def search_google(query, limit=30):
    q = (query or "").strip().lower()
    if not q:
        return []
    fams = google_families()
    starts = [f for f in fams if f.lower().startswith(q)]
    rest = [f for f in fams if q in f.lower() and f not in starts]
    return (starts + rest)[:limit]


def google_ttf(name, italic=False):
    """Download one Google family as TTF and cache it. Returns a path or None."""
    slug = re.sub(r"\W+", "-", name.lower()).strip("-") + ("-italic" if italic else "")
    path = os.path.join(CACHE, slug + ".ttf")
    if os.path.exists(path) and os.path.getsize(path) > 1024:
        return path
    fam = urllib.parse.quote_plus(name)
    url = f"https://fonts.googleapis.com/css2?family={fam}" + (":ital@1" if italic else "")
    try:
        css = _get(url, TTF_UA).decode("utf-8", "replace")
        urls = re.findall(r"url\((https[^)]+)\)", css)
        if not urls:
            return None
        data = _get(urls[0], TTF_UA, timeout=30)
    except Exception:
        return None
    if not data.startswith(SFNT_MAGIC):     # OTTO/CFF or woff2: reportlab cannot read it
        return None
    os.makedirs(CACHE, exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)
    return path


# ------------------------------------------------------------------ installed
def _fc(args):
    try:
        r = subprocess.run(args, capture_output=True, timeout=15)
        return r.stdout.decode("utf-8", "replace")
    except Exception:
        return ""


def system_families():
    if not shutil.which("fc-list"):
        return []
    names = set()
    for line in _fc(["fc-list", ":", "family"]).splitlines():
        for part in line.split(","):
            if part.strip():
                names.add(part.strip())
    return sorted(names)


def find_system(name):
    """Installed family whose name matches, or None (fc-match always answers,
    so the reply has to be checked against what was asked for)."""
    if not name or not shutil.which("fc-match"):
        return None
    n = name.strip().lower()
    out = _fc(["fc-match", "-f", "%{family}", name])
    if any(p.strip().lower() == n for p in out.split(",")):
        return name.strip()
    return next((f for f in system_families() if f.lower() == n), None)


def _reportlab_readable(path):
    """reportlab reads glyf-based sfnt only: no CFF (OTTO) and no collections."""
    try:
        with open(path, "rb") as f:
            return f.read(4) in (b"\x00\x01\x00\x00", b"true")
    except OSError:
        return False


def system_file(name, italic=False):
    """Path of an installed font file reportlab can use for a family, or None."""
    if not name or not shutil.which("fc-match"):
        return None
    pattern = name + (":style=Italic" if italic else "")
    out = _fc(["fc-match", "-f", "%{family}\t%{file}\t%{style}", pattern])
    parts = out.split("\t")
    if len(parts) < 2:
        return None
    fams, path, style = parts[0], parts[1], (parts[2] if len(parts) > 2 else "")
    if not any(p.strip().lower() == name.strip().lower() for p in fams.split(",")):
        return None
    if italic and "italic" not in style.lower() and "oblique" not in style.lower():
        return None
    if not os.path.exists(path) or not _reportlab_readable(path):
        return None
    return path


# ------------------------------------------------------------------ resolution
def resolve_body(name):
    """Where should Chromium get this family from?

    Returns (kind, detail): 'google' (web font), 'system' (installed) or None.
    """
    if not name:
        return None, None
    g = find_google(name)
    if g:
        return "google", g
    s = find_system(name)
    if s:
        return "system", s
    return None, None


def resolve_stamp(spec):
    """Font for the folio and running head. Returns (regular, italic) file paths,
    either of which may be None (the caller then falls back to Times)."""
    if not spec:
        return None, None
    if os.path.exists(spec):
        return os.path.abspath(spec), None
    reg, ital = system_file(spec), system_file(spec, italic=True)
    if not reg and find_google(spec):
        reg, ital = google_ttf(spec), google_ttf(spec, italic=True)
    return reg, ital
