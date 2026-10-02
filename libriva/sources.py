"""Input discovery (globs, folders) and conversion of non-EPUB formats."""
import glob as _glob
import os, shutil, subprocess, zipfile

from .errors import ConversionError, UnsupportedFormatError

EPUB_EXT = {".epub"}
MOBI_EXT = {".azw3", ".azw", ".mobi", ".prc", ".kf8"}
SUPPORTED_EXT = EPUB_EXT | MOBI_EXT

_GLOB_CHARS = "*?["


def ext_of(path):
    return os.path.splitext(path)[1].lower()


def is_supported(path):
    return ext_of(path) in SUPPORTED_EXT


def expand_inputs(patterns):
    """Turn CLI -i values (files, folders, shell-style globs) into a file list.

    Returns (books, skipped) where skipped is a list of (path, reason).
    The shell usually expands an unquoted *; quoted patterns are expanded here,
    so both `-i *.epub` and `-i '*.epub'` behave the same.
    """
    books, skipped, seen = [], [], set()

    def add(p):
        p = os.path.abspath(p)
        if p in seen:
            return
        seen.add(p)
        if os.path.isdir(p):
            skipped.append((p, "is a folder - use a pattern like 'folder/*.epub'"))
        elif not is_supported(p):
            skipped.append((p, f"unsupported file type '{ext_of(p) or 'none'}'"))
        else:
            books.append(p)

    for pat in patterns:
        if os.path.isfile(pat):          # a real file wins, even if the name holds [ ] or ?
            add(pat)
        elif os.path.isdir(pat):
            try:                          # listdir, not glob: folder names may hold [ ] too
                entries = sorted(os.listdir(pat))
            except OSError as e:
                skipped.append((pat, f"cannot read folder: {e}"))
                continue
            found = [os.path.join(pat, f) for f in entries if is_supported(f)]
            if not found:
                skipped.append((pat, "folder contains no ebooks"))
            for f in found:
                add(f)
        elif any(c in pat for c in _GLOB_CHARS):
            found = sorted(_glob.glob(pat, recursive=True))
            if not found:
                skipped.append((pat, "pattern matched nothing"))
            for f in found:
                if os.path.isdir(f):
                    continue
                if is_supported(f):
                    add(f)
                else:
                    skipped.append((os.path.abspath(f), f"unsupported file type '{ext_of(f) or 'none'}'"))
        elif not os.path.exists(pat):
            skipped.append((pat, "file not found"))
        else:
            add(pat)
    return books, skipped


# ------------------------------------------------------------------ unpacking
def _unzip_epub(src, dest):
    try:
        with zipfile.ZipFile(src) as z:
            bad = z.testzip()
            if bad:
                raise ConversionError(f"damaged EPUB (corrupt entry {bad})")
            z.extractall(dest)
    except zipfile.BadZipFile:
        raise ConversionError("not a valid EPUB (file is not a zip archive)")
    except (OSError, RuntimeError) as e:
        raise ConversionError(f"cannot unpack EPUB: {e}")
    return dest


def _ebook_convert(src, dst):
    """Calibre's converter, if it is installed."""
    exe = shutil.which("ebook-convert")
    if not exe:
        return False
    try:
        subprocess.run([exe, src, dst], check=True, capture_output=True, timeout=900)
    except subprocess.TimeoutExpired:
        raise ConversionError("ebook-convert timed out")
    except subprocess.CalledProcessError as e:
        tail = (e.stderr or b"").decode("utf-8", "replace").strip().splitlines()
        raise ConversionError("ebook-convert failed: " + (tail[-1] if tail else "unknown error"))
    return os.path.exists(dst)


def _check_mobi_header(src):
    """PDB header: bytes 60-68 name the format. Fail early with a clear message."""
    try:
        with open(src, "rb") as f:
            magic = f.read(68)[60:68]
    except OSError as e:
        raise ConversionError(f"cannot read file: {e}")
    if magic not in (b"BOOKMOBI", b"TEXtREAd"):
        raise ConversionError("not a Kindle file (no MOBI header) - the extension is misleading")


def _kindleunpack(src, workdir):
    """The `mobi` package (KindleUnpack). Returns a path to an .epub or a folder."""
    try:
        import mobi
    except ImportError:
        return None
    try:
        tmpdir, path = mobi.extract(src)
    except Exception as e:
        raise ConversionError(f"cannot unpack Kindle file: {e}")
    shutil.move(tmpdir, workdir)
    return os.path.join(workdir, os.path.relpath(path, tmpdir))


def prepare(src, workdir):
    """Unpack any supported ebook into workdir and return the EPUB root folder."""
    ext = ext_of(src)
    root = os.path.join(workdir, "epub")
    if ext in EPUB_EXT:
        return _unzip_epub(src, root)
    if ext not in MOBI_EXT:
        raise UnsupportedFormatError(f"unsupported file type '{ext or 'none'}'")

    _check_mobi_header(src)
    converted = os.path.join(workdir, "converted.epub")
    if _ebook_convert(src, converted):
        return _unzip_epub(converted, root)

    unpacked = _kindleunpack(src, os.path.join(workdir, "kindle"))
    if unpacked is None:
        raise ConversionError(
            f"{ext} needs a converter - install one with 'pip install mobi' "
            "or install Calibre (provides ebook-convert)")
    if os.path.isfile(unpacked) and unpacked.lower().endswith(".epub"):
        return _unzip_epub(unpacked, root)
    # KindleUnpack produced a loose folder (old MOBI): use it as the EPUB root
    base = unpacked if os.path.isdir(unpacked) else os.path.dirname(unpacked)
    for dirpath, _, names in os.walk(base):
        if any(n.lower().endswith(".opf") for n in names):
            return base
    raise ConversionError("converted file has no OPF package - cannot read it")
