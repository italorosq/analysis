"""Integration tests for the biblioteca blueprint routes."""

import io
import sys
from pathlib import Path

import pytest

SAMPLE_ENG = """F32 24 124 5-10-15 .0377 .0695 RV
   0.01 50
   0.05 56
   0.10 48
   2.00 24
   2.20 19
   2.24  5
   2.72  0
"""


@pytest.fixture
def app(tmp_path, monkeypatch):
    """Create test Flask app with temporary library directory."""
    monkeypatch.setenv("SECRET_KEY", "test-secret")

    # Import create_app lazily
    PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
    APP_DIR = PROJECT_ROOT / "app"
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    if str(APP_DIR) not in sys.path:
        sys.path.insert(0, str(APP_DIR))

    from app.app import create_app

    from backend import config as cfg

    fake_lib = tmp_path / "biblioteca"
    fake_lib.mkdir()
    monkeypatch.setattr(cfg, "LIBRARY_DIR", fake_lib)

    fake_legacy = tmp_path / "motor_result"
    fake_legacy.mkdir()
    monkeypatch.setattr(cfg, "LEGACY_MOTOR_RESULT_DIR", fake_legacy)

    app = create_app()
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()


# ---------------------------------------------------------------------------
# GET /biblioteca
# ---------------------------------------------------------------------------


def test_biblioteca_index_empty(client):
    rv = client.get("/biblioteca/")
    assert rv.status_code == 200
    assert b"Nenhum teste salvo" in rv.data


def test_biblioteca_index_with_motor(client):
    """Test library index page shows motor cards after upload."""
    # Create a test motor directly via API
    rv = client.post(
        "/biblioteca/TestMotor/upload",
        data={"file": (io.BytesIO(SAMPLE_ENG.encode()), "test.eng")},
        content_type="multipart/form-data",
    )
    assert rv.status_code == 302  # redirect after success

    rv = client.get("/biblioteca/")
    assert rv.status_code == 200
    assert b"TestMotor" in rv.data


def test_biblioteca_sort_invalid(client):
    rv = client.get("/biblioteca/?sort=invalid")
    assert rv.status_code == 200  # Falls back to data


# ---------------------------------------------------------------------------
# GET /biblioteca/<nome>
# ---------------------------------------------------------------------------


def test_biblioteca_detalhe_not_found(client):
    rv = client.get("/biblioteca/NonExistent")
    assert rv.status_code == 404


def test_biblioteca_detalhe_exists(client):
    # Create motor first
    client.post(
        "/biblioteca/TestMotor/upload",
        data={"file": (io.BytesIO(SAMPLE_ENG.encode()), "test.eng")},
        content_type="multipart/form-data",
    )
    rv = client.get("/biblioteca/TestMotor")
    assert rv.status_code == 200
    assert b"TestMotor" in rv.data
    assert b"F32" in rv.data  # designation from eng


# ---------------------------------------------------------------------------
# POST /biblioteca/<nome>/upload
# ---------------------------------------------------------------------------


def test_upload_eng(client):
    rv = client.post(
        "/biblioteca/NewMotor/upload",
        data={"file": (io.BytesIO(SAMPLE_ENG.encode()), "test.eng")},
        content_type="multipart/form-data",
    )
    assert rv.status_code == 302

    # Check motor was created
    rv = client.get("/biblioteca/NewMotor")
    assert rv.status_code == 200


def test_upload_no_file(client):
    rv = client.post(
        "/biblioteca/SomeMotor/upload",
        content_type="multipart/form-data",
    )
    assert rv.status_code == 302


def test_upload_empty_filename(client):
    rv = client.post(
        "/biblioteca/SomeMotor/upload",
        data={"file": (io.BytesIO(b""), "")},
        content_type="multipart/form-data",
    )
    assert rv.status_code == 302


def test_upload_invalid_extension(client):
    rv = client.post(
        "/biblioteca/SomeMotor/upload",
        data={"file": (io.BytesIO(b"malicious"), "hack.exe")},
        content_type="multipart/form-data",
    )
    assert rv.status_code == 302


# ---------------------------------------------------------------------------
# DELETE /biblioteca/<nome>/delete_file/<filename>
# ---------------------------------------------------------------------------


def test_delete_file(client):
    # Upload first
    client.post(
        "/biblioteca/DelMotor/upload",
        data={"file": (io.BytesIO(SAMPLE_ENG.encode()), "test.eng")},
        content_type="multipart/form-data",
    )

    # Delete the file
    rv = client.post("/biblioteca/DelMotor/delete_file/test.eng")
    assert rv.status_code == 302


# ---------------------------------------------------------------------------
# DELETE /biblioteca/<nome>
# ---------------------------------------------------------------------------


def test_delete_motor(client):
    # Create motor
    client.post(
        "/biblioteca/DelAll/upload",
        data={"file": (io.BytesIO(SAMPLE_ENG.encode()), "test.eng")},
        content_type="multipart/form-data",
    )

    # Delete it
    rv = client.post("/biblioteca/DelAll/delete")
    assert rv.status_code == 302

    # Verify 404
    rv = client.get("/biblioteca/DelAll")
    assert rv.status_code == 404


# ---------------------------------------------------------------------------
# POST /biblioteca/migrate
# ---------------------------------------------------------------------------


def test_migrate_legacy(client, app, tmp_path):
    # Create legacy data
    legacy_dir = tmp_path / "motor_result"
    (legacy_dir / "MigMotor_resultados.csv").write_text(
        "Impulso [N*s];Empuxo max [N];Empuxo medio [N];Pontos amostrais;Duração [s];Classe\n"
        "59.27;53.88;31.19;20;1.9;F31.2-1.9\n"
    )
    (legacy_dir / "MigMotor_dados.csv").write_text(
        "Data;Hora;Empuxo;Tempo\n6/9/2024;8:15:13;3.718;0.0\n"
    )

    rv = client.post("/biblioteca/migrate")
    assert rv.status_code == 302

    # Verify motor was created in library
    rv = client.get("/biblioteca/MigMotor")
    assert rv.status_code == 200


def test_migrate_legacy_empty(client, tmp_path):
    rv = client.post("/biblioteca/migrate")
    assert rv.status_code == 302  # Redirects even if nothing to migrate
