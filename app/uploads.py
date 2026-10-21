"""Checks on an uploaded file, and storing it under a generated name."""

import io
import secrets
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PyPdfError

MB = 1024 * 1024
MAX_FILE_BYTES = 10 * MB
MAX_IMAGE_BYTES = 7 * MB
MAX_PDF_PAGES = 20

EXTENSIONS = {"application/pdf": ".pdf", "image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}
WRONG_TYPE = "That file type isn't supported. Upload a PDF, PNG, JPEG or WebP file."
UNREADABLE_PDF = "We couldn't open this PDF. It may be damaged or password-protected."


class UploadRejected(Exception):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(message)


@dataclass
class UploadInfo:
    media_type: str
    page_count: int | None


def _media_type(data: bytes) -> str | None:
    """The type from the file's first bytes, never from its name."""
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def _pdf_pages(data: bytes) -> int:
    try:
        reader = PdfReader(io.BytesIO(data))
        # A PDF that only restricts printing or copying opens with an empty password; one that
        # needs a password to open does not.
        if reader.is_encrypted and not reader.decrypt(""):
            raise UploadRejected(422, UNREADABLE_PDF)
        pages = len(reader.pages)
    except (PyPdfError, ValueError, OSError) as err:
        raise UploadRejected(422, UNREADABLE_PDF) from err
    if pages == 0:
        raise UploadRejected(422, UNREADABLE_PDF)
    return pages


def check_upload(data: bytes, filename: str) -> UploadInfo:
    if len(data) > MAX_FILE_BYTES:
        raise UploadRejected(413, "The file is too large: uploads can be at most 10 MB.")
    media_type = _media_type(data)
    if media_type is None:
        raise UploadRejected(415, WRONG_TYPE)
    if media_type == "application/pdf":
        pages = _pdf_pages(data)
        if pages > MAX_PDF_PAGES:
            raise UploadRejected(413, f"The PDF has {pages} pages; invoices can be at most {MAX_PDF_PAGES} pages.")
        return UploadInfo(media_type, pages)
    if len(data) > MAX_IMAGE_BYTES:
        raise UploadRejected(413, "Images can be at most 7 MB.")
    return UploadInfo(media_type, None)


def store(data: bytes, media_type: str, data_dir: Path) -> str:
    """Save the file under a random name in the uploads folder and return that name."""
    name = secrets.token_hex(16) + EXTENSIONS[media_type]
    (data_dir / "uploads" / name).write_bytes(data)
    return name
