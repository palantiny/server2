"""PDF에서 텍스트 추출 → 같은 이름의 .txt로 저장.

단일 파일용. 1~7권 일괄 처리는 scripts/prepare_monograph.py 를 사용하세요.
"""
import sys
from pathlib import Path

from pypdf import PdfReader


def extract_pdf_to_txt(pdf_path: str) -> None:
    path = Path(pdf_path)
    if not path.exists():
        print(f"파일 없음: {path}")
        return

    reader = PdfReader(path)
    pages_text = []
    for i, page in enumerate(reader.pages, 1):
        text = page.extract_text() or ""
        pages_text.append(f"--- Page {i} ---\n{text}")

    output_path = path.with_suffix(".txt")
    output_path.write_text("\n\n".join(pages_text), encoding="utf-8")
    print(f"추출 완료: {output_path} ({len(reader.pages)}페이지)")


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "data/kr_herb_monograph_1.pdf"
    extract_pdf_to_txt(target)
