#!/usr/bin/env python3
"""
EPUB / AZW3 / MOBI -> printable double-sided PDF (A5 by default).

  python libriva.py -i book.epub [-o out.pdf] [-ac extra.jpg] [--size b5] [--level 2]
                  [--font "EB Garamond"] [--font-file my.ttf] [--font-size 11]
                  [--intro N] [--stamp-font my.ttf]

-i takes several inputs: files, folders, or shell-style patterns such as
'*.epub' or 'lib/**/*.azw3'. Every match is built; anything unsupported or
broken is reported and skipped, and the rest carry on.

Paper: --size a5 (default), b5, a4, letter or legal; the book margins scale with it.

Features: EPUB cover filling the front page, optional extra image (-ac) placed first
at its own size, each chapter starts on a new page, chapter title top-right,
roman page numbers on the chosen introduction, arabic numbers after it.

Needs: pip install playwright beautifulsoup4 pypdf reportlab pillow
       python -m playwright install chromium
       AZW3/MOBI also needs: pip install mobi   (or Calibre's ebook-convert)
"""
import warnings; warnings.filterwarnings("ignore")
import sys

from libriva.cli import main

if __name__ == "__main__":
    sys.exit(main())
