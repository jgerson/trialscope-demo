"""Create and update patient notes. A saved note is one upsert to the patient's namespace."""
from __future__ import annotations

import time
import uuid
from datetime import date

import config
import tp_client


def save_note(patient_id: str, title: str, body: str, note_type: str = "Visit note",
              visit_date: str | None = None, author: str = "Dr. Rivera (Oncology)", note_id: str | None = None) -> dict:
    """Upsert a note, then measure how long until a strongly consistent query returns it."""
    note_id = note_id or f"{patient_id}-{uuid.uuid4().hex[:8]}"
    row = {
        "id": note_id,
        "title": title.strip() or "Untitled note",
        "body": body,
        "text": f"{title}\n{body}",
        "note_type": note_type,
        "visit_date": visit_date or date.today().isoformat(),
        "author": author,
    }
    namespace = config.patient_ns(patient_id)
    write_s = tp_client.upsert(namespace, [row], kind="notes")

    # Freshness: queries are strongly consistent by default, so the note should be visible at once.
    t0 = time.perf_counter()
    for _ in range(20):
        res = tp_client.ns(namespace).query(filters=("id", "Eq", note_id), top_k=1, include_attributes=["title"])
        if res.rows:
            break
        time.sleep(0.05)
    visible_s = time.perf_counter() - t0
    return {"id": note_id, "write_s": write_s, "visible_s": visible_s}


def delete_note(patient_id: str, note_id: str) -> None:
    tp_client.ns(config.patient_ns(patient_id)).write(deletes=[note_id])
