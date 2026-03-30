"""
한약자원 모노그래프 PDF(1~7권) → 텍스트 추출 → 병합 → 권별 목차 기준 한약재 .txt 분할.

실행 (프로젝트 루트):
  python scripts/prepare_monograph.py

출력:
  - data/kr_herb_monograph_{1..7}.txt   (PDF가 있을 때만 생성)
  - data/kr_herb_monograph_merged.txt   (존재하는 권 txt 순서대로 병합)
  - data/herb_monograph_chapters/vol{NN}/{한약재}.txt
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


VOLUME_IDS = tuple(range(1, 8))  # 1 .. 7
MERGED_NAME = "kr_herb_monograph_merged.txt"
CHAPTERS_SUBDIR = "herb_monograph_chapters"


def extract_pdf_to_text(pdf_path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(pdf_path))
    pages_text = []
    for i, page in enumerate(reader.pages, 1):
        text = page.extract_text() or ""
        pages_text.append(f"--- Page {i} ---\n{text}")
    return "\n\n".join(pages_text)


def extract_all_volumes(data_dir: Path, volumes: tuple[int, ...]) -> list[Path]:
    written: list[Path] = []
    for n in volumes:
        pdf = data_dir / f"kr_herb_monograph_{n}.pdf"
        if not pdf.is_file():
            print(f"[건너뜀] PDF 없음: {pdf}")
            continue
        body = extract_pdf_to_text(pdf)
        out = data_dir / f"kr_herb_monograph_{n}.txt"
        out.write_text(body, encoding="utf-8")
        written.append(out)
        print(f"[추출] {pdf.name} → {out.name} ({body.count('--- Page ')} 페이지 구간)")
    return written


def merge_volume_txts(data_dir: Path, volumes: tuple[int, ...]) -> Path | None:
    parts: list[str] = []
    any_file = False
    for n in volumes:
        txt = data_dir / f"kr_herb_monograph_{n}.txt"
        if not txt.is_file():
            continue
        any_file = True
        sep = (
            f"\n\n{'=' * 80}\n"
            f"# VOLUME {n}\n"
            f"# source: {txt.name}\n"
            f"{'=' * 80}\n\n"
        )
        parts.append(sep)
        parts.append(txt.read_text(encoding="utf-8"))
    if not any_file:
        print("[병합] 병합할 kr_herb_monograph_*.txt 가 없습니다.")
        return None
    merged = data_dir / MERGED_NAME
    merged.write_text("".join(parts), encoding="utf-8")
    print(f"[병합] → {merged}")
    return merged


def _fix_toc_pdf_artifacts(line: str) -> str:
    """추출 오류로 붙는 페이지·항목 번호 보정."""
    s = line
    # "...245" + "10. 황련" → "24510."
    s = re.sub(r"(\d{2,3})(10)(\.)", r"\1 \2\3", s)
    s = re.sub(r"(\d{2,3})(11)(\.)", r"\1 \2\3", s)
    s = re.sub(r"(\d{2,3})(12)(\.)", r"\1 \2\3", s)
    s = re.sub(r"(\d)(10\.)", r"\1 \2", s)
    s = re.sub(r"(\d)(11\.)", r"\1 \2", s)
    s = re.sub(r"(\d)(12\.)", r"\1 \2", s)
    return s


def normalize_herb_name(raw: str) -> str:
    """목차에 '길 경'처럼 띄어쓴 표기 → 본문 마커 '길경'과 맞추기."""
    s = raw.strip()
    s = re.sub(r"[\s\u3000\xa0]+", "", s)
    return s


# 장 내부 소목차(1. 이름 2. 약성 …)와 구분
_INNER_TOC_FIRST = frozenset(
    {"이름", "약성", "기원", "감별", "이화학", "전임상", "임상응용", "생산및가공", "유통", "참고문헌"},
)


def _parse_toc_entries_from_line(line: str) -> list[tuple[str, int]]:
    """
    한 줄 목차에서 항목 추출.
    형식: N. 약재명 [·····] 시작페이지 (다음 항목 앞까지)
    약재명에 공백 허용 (예: 길 경, 대 추).
    """
    toc = _fix_toc_pdf_artifacts(line)
    entries: list[tuple[str, int]] = []
    # 약재명은 비탐욕적으로, 이름과 페이지 사이는 점/가운뎃점 2개 이상 또는 공백+점 혼합
    for m in re.finditer(
        r"(\d+)\.\s*(.+?)\s*(?:[·．.]{2,}|\s[·．.]{1,})\s*(\d+)(?=\s*\d+\.|\s*$)",
        toc,
    ):
        raw_name = m.group(2).strip()
        page = int(m.group(3))
        key = normalize_herb_name(raw_name)
        if not key:
            continue
        entries.append((key, page))
    return entries


def _find_volume_toc_line(volume_text: str) -> str | None:
    """본 권 약재 목차 줄만 선택 (장 내부 '목 차' 소목차 제외)."""
    lines = volume_text.splitlines()
    candidates: list[tuple[int, str, list[tuple[str, int]]]] = []

    for line in lines:
        if "목" not in line or "차" not in line:
            continue
        if "일러두기" not in line:
            continue
        if not re.search(r"\d+\.\s*", line):
            continue
        entries = _parse_toc_entries_from_line(line)
        if len(entries) < 5:
            continue
        first_key = entries[0][0]
        if first_key in _INNER_TOC_FIRST:
            continue
        candidates.append((len(entries), line, entries))

    if candidates:
        candidates.sort(key=lambda x: -x[0])
        return candidates[0][1]

    # 폴백: 일러두기 없는 구판/변형 PDF
    best: tuple[int, str] | None = None
    for line in lines:
        if "목" not in line or "차" not in line:
            continue
        if not re.search(r"\d+\.\s*", line):
            continue
        entries = _parse_toc_entries_from_line(line)
        if len(entries) < 5:
            continue
        if entries[0][0] in _INNER_TOC_FIRST:
            continue
        if best is None or len(entries) > best[0]:
            best = (len(entries), line)

    return best[1] if best else None


def parse_main_toc_entries(volume_text: str) -> list[tuple[str, int]]:
    """
    본 권 '목 차 + 일러두기' 줄에서 약재별 시작 인쇄 페이지를 파싱.
    반환: (정규화된 약재명, 시작페이지).
    본문 마커는 '길경_1' 또는 '치 자_183'처럼 권마다 공백 유무가 달라
    정규화 비교로 매칭한다.
    """
    toc_line = _find_volume_toc_line(volume_text)
    if not toc_line:
        return []
    return _parse_toc_entries_from_line(toc_line)


# 본문 장 시작 줄: 약재명(공백 허용)_인쇄페이지
_MARKER_LINE_RE = re.compile(r"^(.+)_(\d+)$")


def _find_chapter_start_line(
    lines: list[str],
    herb_key: str,
    page: int,
    search_from: int,
) -> int | None:
    """herb_key는 정규화된 약재명. 본문은 '치 자_183' / '길경_1' 등 변형 가능."""
    for i in range(search_from, len(lines)):
        raw = lines[i].rstrip("\r\n")
        m = _MARKER_LINE_RE.match(raw)
        if not m:
            continue
        try:
            p = int(m.group(2))
        except ValueError:
            continue
        if p != page:
            continue
        if normalize_herb_name(m.group(1)) == herb_key:
            return i
    return None


def split_volume_by_toc(
    volume_text: str,
    vol_num: int,
    out_root: Path,
) -> int:
    entries = parse_main_toc_entries(volume_text)
    if not entries:
        print(f"  [분할] 권 {vol_num}: 목차 파싱 실패 - 건너뜀")
        return 0

    lines = volume_text.splitlines(keepends=True)
    lines_stripped = [ln.rstrip("\r\n") for ln in lines]

    # 동일 약재·페이지 마커가 본문에 중복될 수 있으므로, 이전 구간 이후부터만 검색
    indices: list[int] = []
    search_from = 0
    for name, page in entries:
        found = _find_chapter_start_line(lines_stripped, name, page, search_from)
        if found is None:
            print(f"  [분할] 권 {vol_num}: 장 시작 줄 없음 ({name}, p.{page}) - 건너뜀")
            return 0
        indices.append(found)
        search_from = found + 1

    vol_dir = out_root / f"vol{vol_num:02d}"
    vol_dir.mkdir(parents=True, exist_ok=True)

    count = 0
    for i, (name, _page) in enumerate(entries):
        start = indices[i]
        end = indices[i + 1] if i + 1 < len(indices) else len(lines)
        chunk = "".join(lines[start:end])
        header = (
            f"# 권: {vol_num}\n"
            f"# 한약재: {name}\n"
            f"# 출처: kr_herb_monograph_{vol_num}.txt\n"
            f"{'=' * 60}\n\n"
        )
        out_file = vol_dir / f"{name}.txt"
        out_file.write_text(header + chunk, encoding="utf-8")
        count += 1
    print(f"  [분할] 권 {vol_num}: {count}개 파일 → {vol_dir}")
    return count


def split_all_volumes(data_dir: Path, volumes: tuple[int, ...]) -> None:
    out_root = data_dir / CHAPTERS_SUBDIR
    total = 0
    for n in volumes:
        txt = data_dir / f"kr_herb_monograph_{n}.txt"
        if not txt.is_file():
            continue
        body = txt.read_text(encoding="utf-8")
        total += split_volume_by_toc(body, n, out_root)
    print(f"[분할] 합계 {total}개 한약재 파일 ({out_root})")


def main() -> None:
    parser = argparse.ArgumentParser(description="모노그래프 PDF 추출·병합·한약재 분할")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="data 폴더 경로 (기본: 프로젝트 루트/data)",
    )
    parser.add_argument(
        "--skip-extract",
        action="store_true",
        help="PDF 추출 생략 (기존 .txt만 병합·분할)",
    )
    parser.add_argument(
        "--skip-merge",
        action="store_true",
        help="병합 파일 생성 생략",
    )
    parser.add_argument(
        "--skip-split",
        action="store_true",
        help="한약재별 분할 생략",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent
    data_dir = args.data_dir if args.data_dir else root / "data"

    if not data_dir.is_dir():
        print(f"data 폴더 없음: {data_dir}", file=sys.stderr)
        sys.exit(1)

    if not args.skip_extract:
        extract_all_volumes(data_dir, VOLUME_IDS)

    if not args.skip_merge:
        merge_volume_txts(data_dir, VOLUME_IDS)

    if not args.skip_split:
        split_all_volumes(data_dir, VOLUME_IDS)

    print("완료.")


if __name__ == "__main__":
    main()
