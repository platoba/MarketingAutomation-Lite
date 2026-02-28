"""Tests for CSV import module."""

import pytest


# ── Column mapping tests ─────────────────────────────────
def test_normalize_column_email():
    from app.api.import_export import normalize_column
    assert normalize_column("email") == "email"
    assert normalize_column("E-mail") == "email"
    assert normalize_column("Mail") == "email"
    assert normalize_column("邮箱") == "email"
    assert normalize_column("电子邮件") == "email"


def test_normalize_column_name():
    from app.api.import_export import normalize_column
    assert normalize_column("first_name") == "first_name"
    assert normalize_column("FirstName") == "first_name"
    assert normalize_column("First Name") == "first_name"
    assert normalize_column("名") == "first_name"
    assert normalize_column("last_name") == "last_name"
    assert normalize_column("LastName") == "last_name"
    assert normalize_column("姓") == "last_name"


def test_normalize_column_phone():
    from app.api.import_export import normalize_column
    assert normalize_column("phone") == "phone"
    assert normalize_column("telephone") == "phone"
    assert normalize_column("Tel") == "phone"
    assert normalize_column("手机") == "phone"
    assert normalize_column("电话") == "phone"


def test_normalize_column_country():
    from app.api.import_export import normalize_column
    assert normalize_column("country") == "country"
    assert normalize_column("国家") == "country"


def test_normalize_column_language():
    from app.api.import_export import normalize_column
    assert normalize_column("language") == "language"
    assert normalize_column("Lang") == "language"
    assert normalize_column("语言") == "language"


def test_normalize_column_unknown():
    from app.api.import_export import normalize_column
    assert normalize_column("random_field") is None
    assert normalize_column("foobar") is None


# ── Email validation ─────────────────────────────────────
def test_email_regex():
    from app.api.import_export import EMAIL_RE
    assert EMAIL_RE.match("user@example.com")
    assert EMAIL_RE.match("user+tag@example.co.uk")
    assert EMAIL_RE.match("a.b@c.de")
    assert not EMAIL_RE.match("invalid")
    assert not EMAIL_RE.match("@no-user.com")
    assert not EMAIL_RE.match("missing@")
    assert not EMAIL_RE.match("")


# ── ImportResult schema ──────────────────────────────────
def test_import_result_schema():
    from app.api.import_export import ImportResult
    r = ImportResult(total_rows=100, created=80, updated=10, skipped=10)
    assert r.total_rows == 100
    assert r.errors == []


def test_import_result_with_errors():
    from app.api.import_export import ImportResult
    r = ImportResult(
        total_rows=5,
        created=3,
        updated=0,
        skipped=2,
        errors=[{"row": 3, "email": "bad", "error": "Invalid email"}],
    )
    assert len(r.errors) == 1


def test_import_preview_schema():
    from app.api.import_export import ImportPreview
    p = ImportPreview(
        total_rows=100,
        columns=["email", "name", "phone"],
        sample_rows=[{"email": "a@b.com", "name": "Test", "phone": "123"}],
        detected_email_column="email",
    )
    assert p.detected_email_column == "email"
    assert len(p.sample_rows) == 1


# ── API endpoint tests ──────────────────────────────────
@pytest.mark.asyncio
async def test_import_csv_no_file(client):
    """Import without a file should fail."""
    resp = await client.post("/api/v1/import/csv")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_import_csv_non_csv_file(client):
    """Import with a non-CSV file should fail."""
    import io
    files = {"file": ("test.txt", io.BytesIO(b"hello"), "text/plain")}
    resp = await client.post("/api/v1/import/csv", files=files)
    assert resp.status_code in (400, 500)


@pytest.mark.asyncio
async def test_preview_csv_no_file(client):
    resp = await client.post("/api/v1/import/csv/preview")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_preview_csv_non_csv(client):
    import io
    files = {"file": ("test.json", io.BytesIO(b'{"a":1}'), "application/json")}
    resp = await client.post("/api/v1/import/csv/preview", files=files)
    assert resp.status_code in (400, 500)
