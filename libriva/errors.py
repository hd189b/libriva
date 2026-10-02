"""Exceptions used to skip a single book without killing the batch."""


class BookBuildError(Exception):
    """Anything that makes one input file unusable; the batch continues."""


class UnsupportedFormatError(BookBuildError):
    pass


class ConversionError(BookBuildError):
    pass


class ParseError(BookBuildError):
    pass


class RenderError(Exception):
    """Environment problem (no browser, etc.) - aborts the whole run."""
