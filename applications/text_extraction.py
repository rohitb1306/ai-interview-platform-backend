from pathlib import Path

import docx
from pypdf import PdfReader


def extract_resume_text(file_path: str) -> str:
    suffix = Path(file_path).suffix.lower()
    if suffix == ".pdf":
        reader = PdfReader(file_path)
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    if suffix == ".docx":
        document = docx.Document(file_path)
        return "\n".join(paragraph.text for paragraph in document.paragraphs)
    raise ValueError(f"Unsupported resume file type: {suffix}")
