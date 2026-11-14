
import os
import json
import uuid
import hashlib
import sqlite3
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_DIR = os.path.join(BASE_DIR, "database")
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
RESUME_DIR = os.path.join(UPLOAD_DIR, "resumes")
JD_DIR = os.path.join(UPLOAD_DIR, "job_descriptions")
DB_PATH = os.path.join(DATABASE_DIR, "screening.db")
os.makedirs(DATABASE_DIR, exist_ok=True)
os.makedirs(RESUME_DIR, exist_ok=True)
os.makedirs(JD_DIR, exist_ok=True)

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_connection() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS job_descriptions (
            jd_id TEXT PRIMARY KEY,
            jd_name TEXT NOT NULL,
            source TEXT,
            jd_text TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS candidates (
            candidate_id TEXT PRIMARY KEY,
            filename TEXT NOT NULL,
            source TEXT,
            original_path TEXT,
            file_hash TEXT,
            raw_text TEXT,
            extraction_status TEXT NOT NULL,
            extraction_error TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS screening_runs (
            run_id TEXT PRIMARY KEY,
            jd_id TEXT NOT NULL,
            criteria_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(jd_id) REFERENCES job_descriptions(jd_id)
        );

        CREATE TABLE IF NOT EXISTS screening_results (
            result_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            candidate_id TEXT NOT NULL,
            score REAL,
            classification TEXT,
            details_json TEXT,
            rank INTEGER,
            created_at TEXT NOT NULL,
            FOREIGN KEY(run_id) REFERENCES screening_runs(run_id),
            FOREIGN KEY(candidate_id) REFERENCES candidates(candidate_id)
        );

        CREATE TABLE IF NOT EXISTS verification_items (
            verification_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            candidate_id TEXT NOT NULL,
            criterion TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Pending',
            hr_notes TEXT,
            updated_at TEXT NOT NULL,
            UNIQUE(run_id, candidate_id, criterion)
        );
        """)
        
def save_jd(jd_name, source, jd_text):
    jd_id = uuid.uuid4().hex
    created_at = datetime.now().isoformat(timespec="seconds")
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO job_descriptions
            (jd_id, jd_name, source, jd_text, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (jd_id, jd_name, source, jd_text, created_at))
    return jd_id

def get_all_jds():
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT * FROM job_descriptions
            ORDER BY created_at DESC
        """).fetchall()
    return [dict(row) for row in rows]

def get_jd(jd_id):
    with get_connection() as conn:
        row = conn.execute("""
            SELECT * FROM job_descriptions WHERE jd_id = ?
        """, (jd_id,)).fetchone()
    return dict(row) if row else None

def save_candidate(filename, source, file_bytes, raw_text,
                   extraction_status, extraction_error=None):
    file_hash = hashlib.sha256(file_bytes).hexdigest()
    with get_connection() as conn:
        existing = conn.execute("""
            SELECT candidate_id
            FROM candidates
            WHERE file_hash = ?
            LIMIT 1
        """, (file_hash,)).fetchone()
    if existing:
        return existing["candidate_id"]

    candidate_id = uuid.uuid4().hex
    safe_name = os.path.basename(filename)
    candidate_folder = os.path.join(RESUME_DIR, candidate_id)
    os.makedirs(candidate_folder, exist_ok=True)
    original_path = os.path.join(candidate_folder, safe_name)
    with open(original_path, "wb") as f:
        f.write(file_bytes)
    created_at = datetime.now().isoformat(timespec="seconds")
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO candidates (
                candidate_id,
                filename,
                source,
                original_path,
                file_hash,
                raw_text,
                extraction_status,
                extraction_error,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            candidate_id,
            safe_name,
            source,
            original_path,
            file_hash,
            raw_text,
            extraction_status,
            extraction_error,
            created_at
        ))

    return candidate_id

def get_all_candidates():
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT *
            FROM candidates
            ORDER BY created_at ASC
        """).fetchall()
    unique_candidates = []
    seen_hashes = set()

    for row in rows:
        candidate = dict(row)
        file_hash = candidate.get("file_hash")
        if file_hash and file_hash in seen_hashes:
            continue
        if file_hash:
            seen_hashes.add(file_hash)
        unique_candidates.append(candidate)
    return unique_candidates

def get_candidate(candidate_id):
    with get_connection() as conn:
        row = conn.execute("""
            SELECT * FROM candidates WHERE candidate_id = ?
        """, (candidate_id,)).fetchone()
    return dict(row) if row else None

def save_screening_run(jd_id, criteria):
    run_id = uuid.uuid4().hex
    created_at = datetime.now().isoformat(timespec="seconds")
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO screening_runs
            (run_id, jd_id, criteria_json, created_at)
            VALUES (?, ?, ?, ?)
        """, (
            run_id,
            jd_id,
            json.dumps(criteria, ensure_ascii=False),
            created_at
        ))
    return run_id

def save_screening_results(run_id, results):
    created_at = datetime.now().isoformat(timespec="seconds")
    with get_connection() as conn:
        for index, result in enumerate(results, start=1):
            result_id = uuid.uuid4().hex
            criterion_results = result["criterion_results"]
            conn.execute("""
                INSERT INTO screening_results (
                    result_id,
                    run_id,
                    candidate_id,
                    score,
                    classification,
                    details_json,
                    rank,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                result_id,
                run_id,
                result["candidate_id"],
                result["score"],
                result["classification"],
                json.dumps(criterion_results, ensure_ascii=False),
                index,
                created_at
            ))

            for item in criterion_results:
                if item.get("mandatory_check"):
                    conn.execute("""
                        INSERT OR IGNORE INTO verification_items (
                            verification_id,
                            run_id,
                            candidate_id,
                            criterion,
                            status,
                            hr_notes,
                            updated_at
                        )
                        VALUES (?, ?, ?, ?, 'Pending', '', ?)
                    """, (
                        uuid.uuid4().hex,
                        run_id,
                        result["candidate_id"],
                        item["criterion"],
                        created_at
                    ))

def get_run_results(run_id):
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT
                r.*,
                c.filename,
                c.source,
                c.original_path,
                c.extraction_status
            FROM screening_results r
            JOIN candidates c
                ON r.candidate_id = c.candidate_id
            WHERE r.run_id = ?
            ORDER BY r.score DESC, r.rank ASC
        """, (run_id,)).fetchall()
    output = []
    for row in rows:
        item = dict(row)
        item["details"] = json.loads(item.pop("details_json"))
        output.append(item)
    return output

def get_all_runs():
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT
                sr.*,
                jd.jd_name
            FROM screening_runs sr
            JOIN job_descriptions jd
                ON sr.jd_id = jd.jd_id
            ORDER BY sr.created_at DESC
        """).fetchall()
    return [dict(row) for row in rows]

def get_verification_items(run_id=None):
    query = """
        SELECT
            v.*,
            c.filename,
            c.original_path
        FROM verification_items v
        JOIN candidates c
            ON v.candidate_id = c.candidate_id
    """
    params = ()
    if run_id:
        query += " WHERE v.run_id = ?"
        params = (run_id,)
    query += " ORDER BY v.updated_at DESC"
    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()

    return [dict(row) for row in rows]

def update_verification(run_id, candidate_id, criterion,
                        status, hr_notes=""):

    updated_at = datetime.now().isoformat(timespec="seconds")
    with get_connection() as conn:
        conn.execute("""
            UPDATE verification_items
            SET status = ?,
                hr_notes = ?,
                updated_at = ?
            WHERE run_id = ?
              AND candidate_id = ?
              AND criterion = ?
        """, (
            status,
            hr_notes,
            updated_at,
            run_id,
            candidate_id,
            criterion
        ))

def get_unreadable_candidates():
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT *
            FROM candidates
            WHERE extraction_status = 'UNREADABLE'
            ORDER BY created_at DESC
        """).fetchall()
    return [dict(row) for row in rows]
