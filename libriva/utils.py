"""Small shared helpers."""
import os, sys, urllib.parse
from bs4 import BeautifulSoup

MM = 2.8346
MARK = "ZQXCH{}ZQX"
FONTS = ["EB Garamond", "Libre Baskerville", "Crimson Pro", "Cormorant Garamond",
         "Lora", "Merriweather", "Spectral", "Source Serif 4", "Alegreya"]


def soup(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return BeautifulSoup(f.read(), "html.parser")


def roman(n):
    r = ""
    for v, s in [(1000, "m"), (900, "cm"), (500, "d"), (400, "cd"), (100, "c"), (90, "xc"),
                 (50, "l"), (40, "xl"), (10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i")]:
        while n >= v:
            r += s
            n -= v
    return r


def resolve(base_file, href):
    """Return (absolute_file, fragment) for an href relative to base_file."""
    href = urllib.parse.unquote(href)
    path, _, frag = href.partition("#")
    f = os.path.normpath(os.path.join(os.path.dirname(base_file), path)) if path else base_file
    return f, frag


def ask(prompt, n, default):
    if not sys.stdin.isatty():
        return default
    while True:
        try:
            a = input(f"{prompt} [{default}]: ").strip()
        except EOFError:
            return default
        if not a:
            return default
        if a.isdigit() and 0 <= int(a) <= n:
            return int(a)
        print("  invalid choice")
