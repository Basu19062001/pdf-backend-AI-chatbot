from pathlib import Path


class PDFService:
    def validate_pdf_path(self, file_path: str) -> bool:
        path = Path(file_path)
        return path.exists() and path.suffix.lower() == ".pdf"
