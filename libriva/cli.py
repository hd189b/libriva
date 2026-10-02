"""Command line: expand the inputs, then build one print-ready PDF per book."""
import argparse, os, re, shutil, sys, tempfile, traceback

from . import fonts, pages as paper
from .document import build_html
from .epub import read_epub
from .errors import BookBuildError, RenderError
from .render import Renderer
from .sources import expand_inputs, prepare
from .stamp import stamp, write_pdf
from .utils import FONTS, ask

# A preface stands in for an introduction when there is no introduction. The title has
# to *start* with the word: "An Introduction to The DevOps Handbook" and "THE
# INTRODUCTION OF SOVIET DEMOCRACY" are ordinary chapters, not the book's introduction.
INTRO_WORDS = ("introduc", "preface")
LEADING_JUNK = " \"'\u201c\u2018([*-"


def level_arg(v):
    """--level takes a depth, or 'auto' (None) for as deep as the book goes."""
    v = str(v).strip().lower()
    if v in ("auto", "max", "full"):
        return None
    try:
        n = int(v)
    except ValueError:
        raise argparse.ArgumentTypeError("--level takes a number or 'auto'")
    if n < 1:
        raise argparse.ArgumentTypeError("--level must be 1 or more, or 'auto'")
    return n


def parse_args(argv=None):
    ap = argparse.ArgumentParser(
        prog="libriva.py", description="EPUB/AZW3/MOBI to a printable, double-sided PDF",
        epilog="Examples:\n"
               "  libriva.py -i book.epub\n"
               "  libriva.py -i '*.epub' -o out/          (quoted pattern, expanded by the script)\n"
               "  libriva.py -i books/ -o out/ --level 2 --font Lora --stamp-font Spectral\n"
               "  libriva.py -i book.epub --size b5          (a5 default; also a4, letter, legal)\n"
               "  libriva.py -i 'lib/**/*.azw3' -o out/   (** searches sub-folders)",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-i", nargs="+", required=True, metavar="INPUT",
                    help="input ebooks: files, folders or glob patterns "
                         "(.epub .azw3 .azw .mobi .prc .kf8)")
    ap.add_argument("-o", help="output .pdf, or a folder (required as a folder for several inputs)")
    ap.add_argument("-ac", help="extra image added as the very first page, kept at its own size")
    ap.add_argument("--size", default=paper.DEFAULT, metavar="NAME",
                    help="paper size: " + ", ".join(paper.names()) + f" (default {paper.DEFAULT}); "
                         "margins scale to suit each one")
    ap.add_argument("--level", type=level_arg, default=None, metavar="N|auto",
                    help="TOC depth treated as chapters; default 'auto' = as deep as "
                         "this book's own table of contents goes")
    ap.add_argument("--intro", type=int, metavar="N",
                    help="chapter number of the introduction (0 = none). "
                         "Found automatically when not given")
    ap.add_argument("--ask-intro", action="store_true",
                    help="show the chapter menu even when an introduction was found")
    ap.add_argument("--number-from", type=int, metavar="N",
                    help="with no introduction, the chapter where page 1 starts "
                         "(0 = the first page of the book; the default)")
    ap.add_argument("--font", metavar="NAME",
                    help="body font: any Google Fonts or installed family; skips the menu")
    ap.add_argument("--font-file", metavar="PATH", help="local .ttf/.otf/.woff2 for the body text")
    ap.add_argument("--font-size", type=float, default=11)
    ap.add_argument("--stamp-font", metavar="NAME|PATH",
                    help="font for the page numbers and the top-right chapter name: "
                         "a Google Fonts or installed family name, or a .ttf path (default Times)")
    ap.add_argument("-y", "--yes", action="store_true", help="never ask anything; use the defaults")
    ap.add_argument("--skip-existing", action="store_true", help="leave books whose PDF already exists")
    ap.add_argument("--stop-on-error", action="store_true", help="stop at the first failure (default: skip it)")
    ap.add_argument("--debug", action="store_true", help="print the full traceback on failure")
    return ap.parse_args(argv)


# ------------------------------------------------------------------ fonts
def _try(name):
    """(family, src) for a font name, or (None, None) if it is nowhere to be found."""
    kind, detail = fonts.resolve_body(name)
    return (detail, (kind, detail)) if kind else (None, None)


def font_menu():
    n = len(FONTS)
    while True:
        print("\nFonts:")
        for i, f in enumerate(FONTS, 1):
            print(f"  {i:2}. {f}")
        net = "" if fonts.online() else "   (no internet - installed fonts only)"
        print(f"  {n + 1:2}. Search Google Fonts{net}")
        print(f"  {n + 2:2}. Type a font name (Google Fonts or installed)")
        print(f"  {n + 3:2}. Load a .ttf/.otf file")
        k = ask("Choose font", n + 3, 1)
        if 1 <= k <= n:
            fam, src = _try(FONTS[k - 1])
            if fam:
                return fam, src
            print(f"  ! {FONTS[k - 1]} is neither installed nor reachable on Google Fonts")
        elif k == n + 1:
            hits = fonts.search_google(input("  Search Google Fonts: ").strip())
            if not hits:
                print("  nothing found" if fonts.online() else "  no internet")
                continue
            for i, f in enumerate(hits, 1):
                print(f"  {i:2}. {f}")
            j = ask("  Choose (0 = back)", len(hits), 0)
            if j:
                return hits[j - 1], ("google", hits[j - 1])
        elif k == n + 2:
            name = input("  Font name: ").strip()
            fam, src = _try(name)
            if fam:
                return fam, src
            print(f"  ! '{name}' is neither installed nor on Google Fonts")
        else:
            path = os.path.expanduser(input("  Path to .ttf/.otf: ").strip())
            if os.path.exists(path):
                return os.path.splitext(os.path.basename(path))[0], ("file", os.path.abspath(path))
            print(f"  ! no such file: {path}")


def choose_font(a, interactive):
    if a.font_file:
        if not os.path.exists(a.font_file):
            print(f"error: --font-file not found: {a.font_file}", file=sys.stderr)
            sys.exit(2)
        return (a.font or os.path.splitext(os.path.basename(a.font_file))[0],
                ("file", os.path.abspath(a.font_file)))
    if a.font:
        fam, src = _try(a.font)
        if fam:                                  # named and available: never ask
            return fam, src
        print(f"  ! font '{a.font}' is neither installed nor on Google Fonts")
        if not interactive:
            return a.font, (None, None)          # generic serif stack takes over
    if not interactive:
        fam, src = _try(FONTS[0])
        return (fam, src) if fam else (FONTS[0], (None, None))
    return font_menu()


# ------------------------------------------------------------------ numbering
def detect_intro(starts):
    # An introduction lives at the front; one found in the back half belongs to some
    # appended extra (The Phoenix Project carries a whole second book's front matter).
    limit = max(3, len(starts) // 2)
    for word in INTRO_WORDS:
        for i, st in enumerate(starts, 1):
            if i <= limit and st["title"].lower().lstrip(LEADING_JUNK).startswith(word):
                return i
    return 0


def print_chapters(starts, zero_label):
    print("\nChapters:")
    for i, st in enumerate(starts, 1):
        print(f"  {i:3}. {'   ' * (st['level'] - 1)}{st['title']}")
    print(f"    0. {zero_label}")


def choose_numbering(starts, a, interactive):
    """Return (intro, number_from).

    An introduction is used automatically when one is found; --ask-intro brings
    back the menu. With no introduction there are no roman numerals - the user
    picks the chapter where page 1 falls, defaulting to the first page.
    """
    intro = a.intro if a.intro is not None else detect_intro(starts)
    if interactive and a.ask_intro:
        print_chapters(starts, "No introduction")
        intro = ask("Which chapter is the introduction?", len(starts), intro)
    if intro and 1 <= intro <= len(starts):
        print(f"  introduction: {intro}. {starts[intro - 1]['title']}  (roman, then arabic after it)")
        return intro, 0

    nf = a.number_from
    if nf is None:
        if interactive:
            print_chapters(starts, "Start numbering on the first page of the book")
            nf = ask("No introduction found - number pages from which chapter?", len(starts), 0)
        else:
            nf = 0
    if nf and 1 <= nf <= len(starts):
        print(f"  no introduction; page 1 starts at {nf}. {starts[nf - 1]['title']}")
    else:
        nf = 0
        print("  no introduction; arabic numbering from the first page")
    return 0, nf


# ------------------------------------------------------------------ build
def output_path(src, a, many, used, suffix="A5"):
    name = os.path.splitext(os.path.basename(src))[0] + f"_{suffix}.pdf"
    if not a.o:
        out = os.path.join(os.path.dirname(src), name)
    elif many or os.path.isdir(a.o) or a.o.endswith(os.sep) or not a.o.lower().endswith(".pdf"):
        out = os.path.join(a.o, name)
    else:
        out = a.o
    out = os.path.abspath(out)
    if out in used:                      # same basename from two folders
        base, ext = os.path.splitext(out)
        n = 2
        while f"{base}_{n}{ext}" in used:
            n += 1
        out = f"{base}_{n}{ext}"
    used.add(out)
    return out


def build_one(src, out, a, renderer, font, font_src, stamp_fonts, page, interactive):
    tmp = tempfile.mkdtemp(prefix="epub2a5_")
    try:
        root = prepare(src, tmp)
        spine, cover, cover_html, toc = read_epub(root)
        book_html, starts = build_html(root, tmp, spine, cover_html, toc,
                                       a.level, font, font_src, a.font_size, page)
        intro, number_from = choose_numbering(starts, a, interactive)
        cover_pdf = renderer.cover_pdf(cover, tmp, page)
        body_pdf = renderer.book_pdf(book_html, tmp, page)
        pdf_pages = stamp(body_pdf, starts, page, intro, number_from, stamp_fonts)
        n = write_pdf(out, pdf_pages, cover_pdf, a.ac)
        depth = max((st["level"] for st in starts), default=1)
        return n, len(starts), depth
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv=None):
    a = parse_args(argv)
    books, skipped = expand_inputs(a.i)
    for p, why in skipped:
        print(f"skip  {os.path.basename(p) or p}: {why}")
    if not books:
        print("Nothing to build.", file=sys.stderr)
        return 2
    many = len(books) > 1
    if many and a.o and a.o.lower().endswith(".pdf"):
        print(f"error: -o must be a folder when there are several inputs ({len(books)} books)",
              file=sys.stderr)
        return 2
    if a.ac and not os.path.exists(a.ac):
        print(f"error: -ac image not found: {a.ac}", file=sys.stderr)
        return 2

    try:
        page = paper.get(a.size)
    except KeyError:
        print(f"error: unknown paper size '{a.size}'; choose from {', '.join(paper.names())}",
              file=sys.stderr)
        return 2

    interactive = sys.stdin.isatty() and not a.yes
    font, font_src = choose_font(a, interactive)
    stamp_fonts = fonts.resolve_stamp(a.stamp_font)
    if a.stamp_font and not stamp_fonts[0]:
        print(f"  ! stamp font '{a.stamp_font}' not found; using Times")
    # menus per book: always for a single book, in a batch only when asked for
    per_book_menu = interactive and (not many or a.ask_intro)

    where = {"file": "local file", "google": "Google Fonts", "system": "installed"}.get(font_src[0], "fallback serif")
    stamp_name = os.path.basename(stamp_fonts[0]) if stamp_fonts[0] else "Times"
    print(f"\n{len(books)} book{'s' if many else ''} to build on {page['label']}")
    print(f"  body font: {font} ({where})   page numbers/headers: {stamp_name}")

    used, ok, failed = set(), [], []
    try:
        with Renderer() as renderer:
            for n, src in enumerate(books, 1):
                out = output_path(src, a, many, used, page["name"].upper())
                head = f"[{n}/{len(books)}] {os.path.basename(src)}"
                if a.skip_existing and os.path.exists(out):
                    print(f"{head}\n  exists, skipped -> {out}")
                    continue
                print(head)
                try:
                    npages, chapters, depth = build_one(src, out, a, renderer, font, font_src,
                                                        stamp_fonts, page, per_book_menu)
                    how = "auto" if a.level is None else "--level"
                    print(f"  -> {out}\n     {npages} pages, {chapters} chapters "
                          f"(TOC depth {depth}, {how})")
                    ok.append(out)
                except BookBuildError as e:
                    print(f"  ! skipped: {e}")
                    failed.append((src, str(e)))
                    if a.stop_on_error:
                        break
                except KeyboardInterrupt:
                    raise
                except Exception as e:
                    if a.debug:
                        traceback.print_exc()
                    print(f"  ! skipped: unexpected error: {type(e).__name__}: {e}")
                    failed.append((src, f"{type(e).__name__}: {e}"))
                    if a.stop_on_error:
                        break
    except RenderError as e:
        print(f"\nerror: {e}", file=sys.stderr)
        return 3
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130

    print(f"\nDone: {len(ok)} built, {len(failed)} failed, {len(skipped)} skipped")
    for src, why in failed:
        print(f"  failed  {os.path.basename(src)}: {why}")
    return 1 if failed else 0
