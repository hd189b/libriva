# Libriva

Convert EPUB and AZW3/MOBI ebooks into PDFs laid out for printing, by default on **A5 paper (148 × 210 mm), double-sided**.

Libriva splits the book into chapters, inlines footnotes, adds page numbers and running headers, and gives you a full-bleed cover, ready for home duplex printing or print-on-demand.

## Features

- **Batch conversion**: files, folders and globs (`**` recurses); one bad book never stops the rest.
- **EPUB 2/3 and AZW3/MOBI/AZW/PRC** input (Kindle formats via Calibre or KindleUnpack).
- **Chapter detection** from the book's own table of contents (EPUB3 nav or NCX); each chapter starts on a new page.
- **Footnotes inlined** right after the paragraph that refers to them.
- **Folios and running headers** with roman numerals for an introduction and arabic numbers afterwards.
- **Full-bleed cover** scaled to the sheet with no white bands.
- **Paper sizes**: A5 (default), B5, A4, Letter, Legal, with mirrored margins sized for binding.
- **Fonts**: Google Fonts (searchable), installed fonts, or your own `.ttf`/`.otf`.

## Install

Requires Python 3.10+ (developed on 3.14).

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m playwright install chromium
```

Optional: install [Calibre](https://calibre-ebook.com/) for the most reliable AZW3/MOBI conversion. Without it, Libriva falls back to the `mobi` package (KindleUnpack).

## Usage

```bash
python libriva.py -i book.epub
python libriva.py -i '*.epub' -o out/              # quote patterns so Libriva expands them
python libriva.py -i books/ -o out/ --level 2 --font Lora -y
python libriva.py -i 'lib/**/*.azw3' -o out/       # ** recurses
```

`-o` must be a folder when there is more than one input. The output filename carries the paper size, e.g. `book_A5.pdf`.

When printing, use **100% / "Actual size"**.

### Options

| Flag | Description |
|---|---|
| `-i`, `--input` | Files, folders or globs. A literal filename containing `[ ] ?` is treated as a file. |
| `-o`, `--output` | Output file or folder. |
| `--size` | Paper size: `a5` (default), `b5`, `a4`, `letter`, `legal`. |
| `--level N\|auto` | TOC depth that counts as a chapter. Default `auto` (as deep as the book's TOC goes). |
| `--intro` / `--ask-intro` | Control introduction detection; `--ask-intro` brings the interactive menu back. |
| `--number-from N` | When no introduction is found, start page numbering at chapter N (`0` = first page). |
| `-ac` | Add an image page before the cover. |
| `--font NAME` | Body font (Google Fonts or installed family). |
| `--font-file PATH` | Embed a local `.ttf`/`.otf` as the body font. |
| `--font-size` | Body font size. |
| `--stamp-font NAME\|PATH` | Font for folios and running heads. |
| `-y`, `--yes` | Accept all defaults, no prompts. |
| `--skip-existing` | Skip books whose output already exists. |
| `--stop-on-error` | Abort the batch on the first failure. |
| `--debug` | Verbose output. |

Prompts only appear for a single input on a terminal. `-y` and non-interactive runs take the defaults silently.

**Exit codes:** `0` all built, `1` some failed, `2` bad invocation, `3` Chromium not found, `130` interrupted.

## Page numbering

- **Introduction found** (a chapter titled *Introduction* or *Preface* in the front half of the book): nothing before it, roman numerals inside it, arabic numbers restarting at 1 after it.
- **No introduction**: arabic numbers from 1, starting at the chapter given by `--number-from` (default: the first page).

## Fonts

A family name is resolved in this order: the Google Fonts catalogue (cached locally, so search works offline), then installed fonts, then a generic `Georgia, serif` stack.

- `--font NAME` is used immediately when it resolves.
- `--font-file PATH` embeds a local font.
- `--stamp-font` accepts a family name or file path; regular and italic are resolved separately, and anything unreadable falls back to Times.

Fonts picked from Google need internet access at run time. Installed fonts and `--font-file` work offline.

## Paper sizes and margins

Margins are mirrored for double-sided printing (mm).

| Size | Sheet | Top | Bottom | Inside | Outside |
|---|---|---|---|---|---|
| A5 (default) | 148 × 210 | 22 | 19 | 19 | 15 |
| B5 | 176 × 250 | 25 | 22 | 22 | 17 |
| A4 | 210 × 297 | 28 | 25 | 25 | 20 |
| Letter | 215.9 × 279.4 | 25.4 | 25.4 | 25.4 | 19 |
| Legal | 215.9 × 355.6 | 25.4 | 25.4 | 25.4 | 19 |

The same book runs about 146 pages on A5, 108 on B5 and 83 on Letter.

A5 suits home duplex printing and perfect-bound print-on-demand up to roughly 500 pages. For longer books (KDP requires a 19.05 mm gutter at 501–700 pages on A5), raise the inside margin to 21–22 mm or use B5/Letter.

## How it works

1. **Prepare**: unpack the input to a temp directory; convert AZW3/MOBI to EPUB if needed.
2. **Read**: parse the container, OPF, spine, cover and table of contents.
3. **Build HTML**: inline footnotes, rewrite internal links, split chapters at TOC anchors, and apply print CSS on top of the book's own styles.
4. **Render**: Chromium (Playwright) prints the body to PDF; the cover is rendered separately, full-bleed.
5. **Stamp**: locate chapter starts, then overlay folios and running headers with ReportLab.
6. **Merge**: `[image page] + cover + body` into the final PDF.

## Project layout

| Path | Purpose |
|---|---|
| `libriva.py` | Entry point |
| `libriva/cli.py` | Argument parsing, batch loop, error isolation, exit codes |
| `libriva/sources.py` | Input expansion and AZW3/MOBI → EPUB conversion |
| `libriva/epub.py` | EPUB container, OPF, spine, cover and TOC parsing |
| `libriva/document.py` | Footnotes, chapter splitting, CSS, HTML output |
| `libriva/render.py` | Playwright Chromium rendering |
| `libriva/stamp.py` | Page numbers, running headers, final merge |
| `libriva/pages.py` | Paper sizes and margins |
| `libriva/fonts.py` | Google Fonts search/download, installed-font lookup |
| `libriva/utils.py` | Shared helpers and constants |
| `libriva/errors.py` | `BookBuildError` (skip one book) and `RenderError` (abort run) |

## Known limitations

- **Mirrored margins can land on the wrong side** for some books. Chromium's `@page :left/:right` phase is not anchored to the physical pages of the merged PDF, and adding `-ac` shifts it again. Planned fix: render with symmetric side margins and shift each page ±2 mm during the stamp pass, where the physical page index is known.
- The footnote heuristic can misfire on books with very short real chapters.
- Chapter splitting only works when the TOC anchor sits in the flat body content.
- With `--level 2`, running heads on introduction sub-chapters show the sub-chapter title.
- No PDF bookmarks/outline yet (internal links do work).

## Checking output

```bash
pdftoppm -f 60 -l 63 -r 100 -gray "out/book_A5.pdf" /tmp/pg
```

Then measure the ink bounding box per page with Pillow (`ImageChops.invert(crop).getbbox()`; at 100 dpi, 3.937 px/mm). Crop out the header and folio bands to measure the text block alone.

## License

Add your license here.
