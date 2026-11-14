
from pathlib import Path
from io import BytesIO
import zipfile
import re
import pymupdf
from docx import Document
import pandas as pd
import json
from storage import save_candidate

SUPPORTED = {".pdf",".docx",".txt"}
def clean_text(text):
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+"," ",text)
    text = re.sub(r"\n{3,}","\n\n",text)
    return text.strip()
def extract_document(filename, data):
    extension = Path(filename).suffix.lower()
    if extension == ".pdf":
        with pymupdf.open(stream=data,filetype="pdf") as pdf:
            text = "\n".join(page.get_text("text") for page in pdf)
    elif extension == ".docx":
        document = Document(BytesIO(data))
        parts = [paragraph.text for paragraph in document.paragraphs]
        for table in document.tables:
            for row in table.rows:
                parts.append(" | ".join(cell.text for cell in row.cells))
        text = "\n".join(parts)
    elif extension == ".txt":
        text = data.decode("utf-8-sig",errors="replace")
    else:
        raise ValueError(f"Unsupported file extension: {extension}")
    return clean_text(text)

def process_one(filename, data, source="Upload"):
    try:
        text = extract_document(filename, data)
        if len(text) < 40:
            raise ValueError(
                "No sufficient readable text. "
                "Document may be scanned, blank or corrupt."
            )
        candidate_id = save_candidate(
            filename=filename,
            source=source,
            file_bytes=data,
            raw_text=text,
            extraction_status="READABLE",
            extraction_error=None
        )
        return {
            "candidate_id": candidate_id,
            "filename": Path(filename).name,
            "source": source,
            "raw_text": text,
            "status": "READABLE"
        }, None
    except Exception as error:
        error_message = (f"{type(error).__name__}: {error}")
        candidate_id = save_candidate(
            filename=filename,
            source=source,
            file_bytes=data,
            raw_text="",
            extraction_status="UNREADABLE",
            extraction_error=error_message
        )
        return None, {
            "candidate_id": candidate_id,
            "filename": Path(filename).name,
            "source": source,
            "error": error_message
        }

def process_zip_bytes(zip_bytes,source_name="Resume archive"):
    candidates = []
    errors = []
    with zipfile.ZipFile(BytesIO(zip_bytes)) as archive:
        for name in archive.namelist():
            if name.endswith("/"):
                continue
            if Path(name).suffix.lower() not in SUPPORTED:
                continue
            try:
                data = archive.read(name)
            except Exception as error:
                errors.append({
                    "filename": Path(name).name,
                    "source": name,
                    "error": str(error)
                })
                continue

            candidate, issue = process_one(
                Path(name).name,
                data,
                f"{source_name} :: {name}"
            )
            if candidate:
                candidates.append(candidate)
            if issue:
                errors.append(issue)
    return candidates, errors

def save_candidate_results(results,output_path):
    output_path = Path(output_path)
    output_path.mkdir(parents=True,exist_ok=True)
    rows = []
    for item in results:
        rows.append({
            "Rank": item["rank"],
            "Resume": item["filename"],
            "Source": item["source"],
            "Score": item["score"],
            "Classification": item["classification"],
            "Criteria passed": sum(1 for x in item["criterion_results"] if x["points_awarded"] > 0),
            "Criteria assessed": len(item["criterion_results"])
        })

    pd.DataFrame(rows).to_csv(
        output_path / "dynamic_ranking.csv",
        index=False,
        encoding="utf-8-sig"
    )
    (
        output_path / "dynamic_evidence.json"
    ).write_text(
        json.dumps(
            results,
            indent=2,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )

def save_errors(errors, output_path):
    output_path = Path(output_path)
    output_path.mkdir(parents=True,exist_ok=True)
    pd.DataFrame(errors).to_csv(
        output_path / "processing_errors.csv",
        index=False,
        encoding="utf-8-sig"
    )
