"""Per-file-type text + embedded-image extraction, operating entirely on
in-memory bytes -- the source document is never written to disk. Embedded
images are the one exception: each gets written to a transient temp
directory just long enough for Claude's vision to caption it during
/dhi index; the caller is responsible for deleting that directory once
captioning finishes.

Each extractor returns (units, images):
  units  -> list of {"page_number": int|None, "section_label": str|None, "text": str}
  images -> list of {"page_number": int|None, "section_label": str|None, "image_path": Path}

Every unit maps to exactly one page/section so citations are unambiguous.
"""

import io
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


def extract_pdf(data: bytes, image_dir: Path):
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    units, images = [], []
    for i, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        if text:
            units.append({"page_number": i, "section_label": None, "text": text})
        for j, img in enumerate(page.images):
            ext = Path(img.name).suffix or ".png"
            image_dir.mkdir(parents=True, exist_ok=True)
            img_path = image_dir / f"p{i}_{j}{ext}"
            img_path.write_bytes(img.data)
            images.append({"page_number": i, "section_label": None, "image_path": img_path})
    return units, images


def extract_docx(data: bytes, image_dir: Path):
    import docx

    document = docx.Document(io.BytesIO(data))
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
            image_dir.mkdir(parents=True, exist_ok=True)
            img_path = image_dir / f"img{i}{ext}"
            img_path.write_bytes(rel.target_part.blob)
            images.append({"page_number": None, "section_label": None, "image_path": img_path})
    return units, images


def extract_pptx(data: bytes, image_dir: Path):
    from pptx import Presentation
    from pptx.enum.shapes import MSO_SHAPE_TYPE

    prs = Presentation(io.BytesIO(data))
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
                image_dir.mkdir(parents=True, exist_ok=True)
                img_path = image_dir / f"s{i}_{shape.shape_id}.png"
                img_path.write_bytes(shape.image.blob)
                images.append({"page_number": i, "section_label": title, "image_path": img_path})
        if texts:
            units.append({"page_number": i, "section_label": title, "text": "\n".join(texts)})
    return units, images


def extract_xlsx(data: bytes, image_dir: Path):
    # Embedded chart/image extraction from xlsx is skipped in v1 (openpyxl's
    # image access is unofficial API); sheet text is fully covered.
    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True)
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


def extract_text_file(data: bytes, image_dir: Path):
    text = data.decode("utf-8", errors="ignore")
    return [{"page_number": None, "section_label": None, "text": text}], []


def extract_md(data: bytes, image_dir: Path):
    text = data.decode("utf-8", errors="ignore")
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


def extract_csv(data: bytes, image_dir: Path):
    import csv
    import io as _io

    text = data.decode("utf-8", errors="ignore")
    rows = list(csv.reader(_io.StringIO(text)))
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


def extract_rtf(data: bytes, image_dir: Path):
    from striprtf.striprtf import rtf_to_text

    text = rtf_to_text(data.decode("utf-8", errors="ignore"))
    return [{"page_number": None, "section_label": None, "text": text}], []


EXTRACTORS = {
    "pdf": extract_pdf,
    "docx": extract_docx,
    "pptx": extract_pptx,
    "xlsx": extract_xlsx,
    "txt": extract_text_file,
    "md": extract_md,
    "csv": extract_csv,
    "rtf": extract_rtf,
}


def extract_bytes(ext: str, data: bytes, image_dir: Path):
    fn = EXTRACTORS.get(ext.lower().lstrip("."))
    if fn is None:
        return [], []
    units, images = fn(data, image_dir)
    return units, _drop_tiny_images(images)
