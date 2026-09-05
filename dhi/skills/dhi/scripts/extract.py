"""Per-file-type text + embedded-image extraction.

Each extractor returns (units, images):
  units  -> list of {"page_number": int|None, "section_label": str|None, "text": str}
  images -> list of {"page_number": int|None, "section_label": str|None, "image_path": Path}

Every unit maps to exactly one page/section so citations are unambiguous.
"""

from pathlib import Path

MIN_IMAGE_DIM = 80  # skip icons/bullets/dividers, not real content


def _drop_tiny_images(images: list[dict]) -> list[dict]:
    from PIL import Image

    kept = []
    for img in images:
        try:
            with Image.open(img["image_path"]) as im:
                if im.width < MIN_IMAGE_DIM and im.height < MIN_IMAGE_DIM:
                    img["image_path"].unlink(missing_ok=True)
                    continue
        except Exception:
            pass
        kept.append(img)
    return kept


def extract_pdf(path: Path, image_dir: Path):
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    units, images = [], []
    for i, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        if text:
            units.append({"page_number": i, "section_label": None, "text": text})
        for j, img in enumerate(page.images):
            ext = Path(img.name).suffix or ".png"
            img_path = image_dir / f"p{i}_{j}{ext}"
            img_path.write_bytes(img.data)
            images.append({"page_number": i, "section_label": None, "image_path": img_path})
    return units, images


def extract_docx(path: Path, image_dir: Path):
    import docx

    document = docx.Document(str(path))
    units = []
    current_section = None
    buffer: list[str] = []

    def flush():
        if buffer:
            units.append({"page_number": None, "section_label": current_section, "text": "\n".join(buffer)})
            buffer.clear()

    for para in document.paragraphs:
        if para.style and para.style.name.startswith("Heading"):
            flush()
            current_section = para.text.strip() or current_section
            continue
        if para.text.strip():
            buffer.append(para.text)
    flush()

    images = []
    for i, rel in enumerate(document.part.rels.values()):
        if "image" in rel.reltype:
            ext = Path(rel.target_ref).suffix or ".png"
            img_path = image_dir / f"img{i}{ext}"
            img_path.write_bytes(rel.target_part.blob)
            images.append({"page_number": None, "section_label": None, "image_path": img_path})
    return units, images


def extract_pptx(path: Path, image_dir: Path):
    from pptx import Presentation
    from pptx.enum.shapes import MSO_SHAPE_TYPE

    prs = Presentation(str(path))
    units, images = [], []
    for i, slide in enumerate(prs.slides, start=1):
        title = None
        try:
            if slide.shapes.title and slide.shapes.title.text.strip():
                title = slide.shapes.title.text.strip()
        except Exception:
            pass

        texts = []
        for shape in slide.shapes:
            if shape.has_text_frame and shape.text_frame.text.strip():
                texts.append(shape.text_frame.text)
            if shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
                img_path = image_dir / f"s{i}_{shape.shape_id}.png"
                img_path.write_bytes(shape.image.blob)
                images.append({"page_number": i, "section_label": title, "image_path": img_path})
        if texts:
            units.append({"page_number": i, "section_label": title, "text": "\n".join(texts)})
    return units, images


def extract_xlsx(path: Path, image_dir: Path):
    # Embedded chart/image extraction from xlsx is skipped in v1 (openpyxl's
    # image access is unofficial API); sheet text is fully covered.
    import openpyxl

    wb = openpyxl.load_workbook(str(path), data_only=True)
    units = []
    for sheet in wb.worksheets:
        rows = [r for r in sheet.iter_rows(values_only=True) if any(c is not None for c in r)]
        if not rows:
            continue
        headers, lines = rows[0], []
        for row in rows[1:]:
            line = " | ".join(f"{h}: {v}" for h, v in zip(headers, row) if v is not None)
            if line:
                lines.append(line)
        if lines:
            units.append({"page_number": None, "section_label": sheet.title, "text": "\n".join(lines)})
    return units, []


def extract_text_file(path: Path, image_dir: Path):
    text = path.read_text(errors="ignore")
    if path.suffix.lower() != ".md":
        return [{"page_number": None, "section_label": None, "text": text}], []

    units, section, buffer = [], None, []
    for line in text.splitlines():
        if line.startswith("#"):
            if buffer:
                units.append({"page_number": None, "section_label": section, "text": "\n".join(buffer)})
                buffer = []
            section = line.lstrip("#").strip()
        else:
            buffer.append(line)
    if buffer:
        units.append({"page_number": None, "section_label": section, "text": "\n".join(buffer)})
    return units, []


def extract_csv(path: Path, image_dir: Path):
    import csv

    with open(path, newline="", errors="ignore") as f:
        rows = list(csv.reader(f))
    if not rows:
        return [], []

    headers, units, batch, start = rows[0], [], [], 2
    for i, row in enumerate(rows[1:], start=2):
        line = " | ".join(f"{h}: {v}" for h, v in zip(headers, row) if v)
        if line:
            batch.append(line)
        if len(batch) >= 50:
            units.append({"page_number": None, "section_label": f"rows {start}-{i}", "text": "\n".join(batch)})
            batch, start = [], i + 1
    if batch:
        units.append({"page_number": None, "section_label": f"rows {start}-{len(rows)}", "text": "\n".join(batch)})
    return units, []


def extract_rtf(path: Path, image_dir: Path):
    from striprtf.striprtf import rtf_to_text

    text = rtf_to_text(path.read_text(errors="ignore"))
    return [{"page_number": None, "section_label": None, "text": text}], []


EXTRACTORS = {
    ".pdf": extract_pdf,
    ".docx": extract_docx,
    ".pptx": extract_pptx,
    ".xlsx": extract_xlsx,
    ".txt": extract_text_file,
    ".md": extract_text_file,
    ".csv": extract_csv,
    ".rtf": extract_rtf,
}


def extract(path: Path, image_dir: Path):
    fn = EXTRACTORS.get(path.suffix.lower())
    if fn is None:
        return [], []
    image_dir.mkdir(parents=True, exist_ok=True)
    units, images = fn(path, image_dir)
    return units, _drop_tiny_images(images)
