"""CSV file upload import for contacts — validates, deduplicates, and bulk inserts."""

import csv
import io
import json
import re
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Contact

router = APIRouter(prefix="/import", tags=["import"])

EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")

# Max file size: 5 MB
MAX_FILE_SIZE = 5 * 1024 * 1024
# Max rows per import
MAX_ROWS = 10_000


class ImportResult(BaseModel):
    total_rows: int
    created: int
    updated: int
    skipped: int
    errors: list[dict] = Field(default_factory=list)


class ImportPreview(BaseModel):
    total_rows: int
    columns: list[str]
    sample_rows: list[dict]
    detected_email_column: Optional[str] = None


COLUMN_MAP = {
    "email": "email",
    "e-mail": "email",
    "mail": "email",
    "电子邮件": "email",
    "邮箱": "email",
    "first_name": "first_name",
    "firstname": "first_name",
    "first name": "first_name",
    "名": "first_name",
    "last_name": "last_name",
    "lastname": "last_name",
    "last name": "last_name",
    "姓": "last_name",
    "phone": "phone",
    "telephone": "phone",
    "tel": "phone",
    "电话": "phone",
    "手机": "phone",
    "country": "country",
    "国家": "country",
    "language": "language",
    "lang": "language",
    "语言": "language",
}


def normalize_column(col: str) -> Optional[str]:
    """Map CSV column header to a known field name."""
    key = col.strip().lower()
    return COLUMN_MAP.get(key)


@router.post("/csv/preview", response_model=ImportPreview)
async def preview_csv(file: UploadFile = File(...)):
    """Preview a CSV file before importing — show columns, sample rows, and detected fields."""
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(400, "Only CSV files are supported")

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(400, f"File too large. Max size: {MAX_FILE_SIZE // 1024 // 1024} MB")

    text = content.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    columns = reader.fieldnames or []

    sample = []
    for i, row in enumerate(reader):
        if i >= 5:
            break
        sample.append(dict(row))

    # Detect email column
    email_col = None
    for col in columns:
        if normalize_column(col) == "email":
            email_col = col
            break
    if not email_col:
        for col in columns:
            for row in sample:
                val = row.get(col, "")
                if val and EMAIL_RE.match(val.strip()):
                    email_col = col
                    break
            if email_col:
                break

    total = sum(1 for _ in csv.DictReader(io.StringIO(text)))

    return ImportPreview(
        total_rows=total,
        columns=columns,
        sample_rows=sample,
        detected_email_column=email_col,
    )


@router.post("/csv", response_model=ImportResult)
async def import_csv(
    file: UploadFile = File(...),
    update_existing: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """
    Import contacts from a CSV file.

    - Auto-detects email column
    - Maps common column names (first_name, last_name, phone, country, language)
    - Unmapped columns stored as custom_fields
    - Validates emails
    - Skips or updates existing contacts based on `update_existing` flag
    """
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(400, "Only CSV files are supported")

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(400, f"File too large. Max: {MAX_FILE_SIZE // 1024 // 1024} MB")

    text = content.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    columns = reader.fieldnames or []

    # Build column mapping
    mapping = {}
    custom_cols = []
    for col in columns:
        mapped = normalize_column(col)
        if mapped:
            mapping[col] = mapped
        else:
            custom_cols.append(col)

    if "email" not in mapping.values():
        # Try to find email column by content
        sample_reader = csv.DictReader(io.StringIO(text))
        first_row = next(sample_reader, None)
        if first_row:
            for col in columns:
                val = first_row.get(col, "")
                if val and EMAIL_RE.match(val.strip()):
                    mapping[col] = "email"
                    if col in custom_cols:
                        custom_cols.remove(col)
                    break

    if "email" not in mapping.values():
        raise HTTPException(400, "Could not detect an email column. Please ensure a column named 'email' exists.")

    result = ImportResult(total_rows=0, created=0, updated=0, skipped=0)
    errors = []

    reader = csv.DictReader(io.StringIO(text))
    batch = []

    for i, row in enumerate(reader):
        if i >= MAX_ROWS:
            break
        result.total_rows += 1

        # Extract known fields
        data = {}
        custom = {}
        for col, val in row.items():
            mapped = mapping.get(col)
            if mapped:
                data[mapped] = val.strip() if val else ""
            elif col in custom_cols:
                custom[col] = val.strip() if val else ""

        email = data.get("email", "").lower()
        if not email or not EMAIL_RE.match(email):
            errors.append({"row": i + 2, "email": email, "error": "Invalid email"})
            result.skipped += 1
            continue

        # Check existing
        existing_result = await db.execute(select(Contact).where(Contact.email == email))
        existing = existing_result.scalar_one_or_none()

        if existing:
            if update_existing:
                for field in ("first_name", "last_name", "phone", "country", "language"):
                    val = data.get(field)
                    if val:
                        setattr(existing, field, val)
                if custom:
                    old_custom = {}
                    if existing.custom_fields:
                        try:
                            old_custom = json.loads(existing.custom_fields)
                        except (json.JSONDecodeError, TypeError):
                            pass
                    old_custom.update(custom)
                    existing.custom_fields = json.dumps(old_custom)
                result.updated += 1
            else:
                result.skipped += 1
        else:
            contact = Contact(
                email=email,
                first_name=data.get("first_name", ""),
                last_name=data.get("last_name", ""),
                phone=data.get("phone", ""),
                country=data.get("country", ""),
                language=data.get("language", "en"),
                custom_fields=json.dumps(custom) if custom else "{}",
                subscribed=True,
            )
            db.add(contact)
            result.created += 1

    await db.commit()
    result.errors = errors[:50]  # Cap error list
    return result
