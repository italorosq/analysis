"""Tests for the library management module."""

import pytest

import backend.config as _backend_config
from backend.biblioteca import (
    MotorMetadata,
    scan_library,
    get_motor,
    save_motor_metadata,
    delete_motor,
    list_files,
    register_file,
    unregister_file,
    infer_date_from_legacy,
    migrate_legacy_motor_result,
)


@pytest.fixture(autouse=True)
def clean_library(tmp_path, monkeypatch):
    """Use a temporary library directory for each test."""
    fake_lib = tmp_path / "biblioteca"
    fake_lib.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(_backend_config, "LIBRARY_DIR", fake_lib)
    yield


def _lib():
    """Get the current library directory (respects monkeypatch)."""
    return _backend_config.LIBRARY_DIR


# ---------------------------------------------------------------------------
# CRUD operations
# ---------------------------------------------------------------------------

def test_scan_library_empty():
    motors = scan_library()
    assert motors == []


def test_save_and_get_motor():
    meta = MotorMetadata(
        nome="TestMotor",
        impulso_total_Ns=100.0,
        classe="F31.2-1.9",
    )
    save_motor_metadata("TestMotor", meta)

    result = get_motor("TestMotor")
    assert result is not None
    assert result.nome == "TestMotor"
    assert result.impulso_total_Ns == 100.0
    assert result.classe == "F31.2-1.9"


def test_get_motor_not_found():
    result = get_motor("NonExistent")
    assert result is None


def test_delete_motor():
    save_motor_metadata("ToDelete", MotorMetadata(nome="ToDelete"))
    assert get_motor("ToDelete") is not None

    assert delete_motor("ToDelete") is True
    assert get_motor("ToDelete") is None
    assert delete_motor("ToDelete") is False


def test_scan_library_sort_by_impulse():
    m1 = MotorMetadata(nome="Low", impulso_total_Ns=50.0)
    m2 = MotorMetadata(nome="High", impulso_total_Ns=500.0)
    m3 = MotorMetadata(nome="Mid", impulso_total_Ns=200.0)
    save_motor_metadata("Low", m1)
    save_motor_metadata("High", m2)
    save_motor_metadata("Mid", m3)

    motors = scan_library(sort_by="impulso")
    names = [m.nome for m in motors]
    assert names == ["High", "Mid", "Low"]


def test_scan_library_sort_by_data():
    m1 = MotorMetadata(nome="Old", data_teste="2024-01-01T00:00:00")
    m2 = MotorMetadata(nome="New", data_teste="2025-06-15T00:00:00")
    m3 = MotorMetadata(nome="Mid", data_teste="2024-06-01T00:00:00")
    save_motor_metadata("Old", m1)
    save_motor_metadata("New", m2)
    save_motor_metadata("Mid", m3)

    motors = scan_library(sort_by="data")
    assert [m.nome for m in motors] == ["New", "Mid", "Old"]


def test_scan_library_ignores_invalid_json():
    """Directories without motor.json or with invalid JSON are skipped."""
    lib_dir = _lib()
    (lib_dir / "BadDir").mkdir(parents=True, exist_ok=True)
    (lib_dir / "BadDir" / "motor.json").write_text("not valid json")

    motors = scan_library()
    assert motors == []


# ---------------------------------------------------------------------------
# File management
# ---------------------------------------------------------------------------

def test_list_files_empty():
    save_motor_metadata("EmptyFiles", MotorMetadata(nome="EmptyFiles"))
    files = list_files("EmptyFiles")
    assert files == {"csv": [], "png": [], "pdf": [], "eng": [], "fotos": [], "outros": []}


def test_list_files_categorizes_correctly():
    meta = MotorMetadata(
        nome="WithFiles",
        csv_original="data.csv",
        resultados_csv="results.csv",
        grafico_png="plot.png",
        relatorio_pdf="report.pdf",
        openmotor_eng="motor.eng",
        fotos=["photo1.jpg", "photo2.jpg"],
    )
    save_motor_metadata("WithFiles", meta)

    # Create actual files
    motor_dir = _lib() / "WithFiles"
    for fname in ["data.csv", "results.csv", "plot.png", "report.pdf", "motor.eng", "photo1.jpg", "photo2.jpg"]:
        (motor_dir / fname).touch()

    files = list_files("WithFiles")
    assert sorted(files["csv"]) == ["data.csv", "results.csv"]
    assert files["png"] == ["plot.png"]
    assert files["pdf"] == ["report.pdf"]
    assert files["eng"] == ["motor.eng"]
    assert sorted(files["fotos"]) == ["photo1.jpg", "photo2.jpg"]


def test_register_file():
    save_motor_metadata("RegFile", MotorMetadata(nome="RegFile"))
    register_file("RegFile", "test_resultados.csv", "csv")
    register_file("RegFile", "plot.png", "png")
    register_file("RegFile", "motor.eng", "eng")
    register_file("RegFile", "foto.jpg", "foto")
    register_file("RegFile", "raw_data.csv", "csv")

    meta = get_motor("RegFile")
    assert meta is not None
    # Second csv registration overwrites csv_original
    assert meta.csv_original == "raw_data.csv"
    assert meta.resultados_csv == "test_resultados.csv"
    assert meta.grafico_png == "plot.png"
    assert meta.openmotor_eng == "motor.eng"
    assert "foto.jpg" in meta.fotos


def test_unregister_file():
    meta = MotorMetadata(
        nome="Unreg",
        csv_original="data.csv",
        grafico_png="plot.png",
        fotos=["pic.jpg"],
    )
    save_motor_metadata("Unreg", meta)

    unregister_file("Unreg", "data.csv")
    unregister_file("Unreg", "plot.png")
    unregister_file("Unreg", "pic.jpg")

    result = get_motor("Unreg")
    assert result is not None
    assert result.csv_original is None
    assert result.grafico_png is None
    assert "pic.jpg" not in result.fotos


# ---------------------------------------------------------------------------
# Legacy migration
# ---------------------------------------------------------------------------

def test_infer_date_from_legacy(tmp_path):
    csv_content = "Data;Hora;Empuxo;Tempo\n6/9/2024;8:15:13;3.718;0.0\n"
    csv_path = tmp_path / "legacy_dados.csv"
    csv_path.write_text(csv_content)

    result = infer_date_from_legacy(csv_path)
    assert result is not None
    assert "2024-09-06" in result
    assert "08:15:13" in result


def test_infer_date_from_legacy_missing_file(tmp_path):
    result = infer_date_from_legacy(tmp_path / "nonexistent.csv")
    assert result is None


def test_infer_date_from_legacy_bad_format(tmp_path):
    csv_path = tmp_path / "bad.csv"
    csv_path.write_text("no date here\n")
    result = infer_date_from_legacy(csv_path)
    assert result is None


def test_migrate_legacy_dry_run(tmp_path, monkeypatch):
    """Dry run should not modify anything."""
    legacy_dir = tmp_path / "motor_result"
    legacy_dir.mkdir()

    import backend.config as cfg
    import importlib
    import backend.biblioteca as bib_mod
    monkeypatch.setattr(cfg, "LEGACY_MOTOR_RESULT_DIR", legacy_dir)
    importlib.reload(bib_mod)

    (legacy_dir / "MotorX_resultados.csv").write_text(
        "Impulso [N*s];Empuxo max [N];Empuxo medio [N];Pontos amostrais;Duração [s];Classe\n"
        "59.27;53.88;31.19;20;1.9;F31.2-1.9\n"
    )
    (legacy_dir / "MotorX_dados.csv").write_text(
        "Data;Hora;Empuxo;Tempo\n6/9/2024;8:15:13;3.718;0.0\n"
    )

    result = migrate_legacy_motor_result(dry_run=True)
    assert "MotorX" in result
    # Files should still be in legacy dir
    assert (legacy_dir / "MotorX_resultados.csv").exists()


def test_migrate_legacy_full(tmp_path, monkeypatch):
    """Full migration should move files to library."""
    legacy_dir = tmp_path / "motor_result"
    legacy_dir.mkdir()

    import backend.config as cfg
    import importlib
    import backend.biblioteca as bib_mod
    monkeypatch.setattr(cfg, "LEGACY_MOTOR_RESULT_DIR", legacy_dir)
    importlib.reload(bib_mod)

    (legacy_dir / "MotorX_resultados.csv").write_text(
        "Impulso [N*s];Empuxo max [N];Empuxo medio [N];Pontos amostrais;Duração [s];Classe\n"
        "59.27;53.88;31.19;20;1.9;F31.2-1.9\n"
    )
    (legacy_dir / "MotorX_dados.csv").write_text(
        "Data;Hora;Empuxo;Tempo\n6/9/2024;8:15:13;3.718;0.0\n"
    )

    result = bib_mod.migrate_legacy_motor_result(dry_run=False)
    assert "MotorX" in result

    # Files should be in library
    motor_dir = _lib() / "MotorX"
    assert (motor_dir / "MotorX_resultados.csv").exists()
    assert (motor_dir / "MotorX_dados.csv").exists()
    assert (motor_dir / "motor.json").exists()

    # Metadata should be correct
    meta = bib_mod.get_motor("MotorX")
    assert meta is not None
    assert meta.impulso_total_Ns == 59.27
    assert meta.classe == "F31.2-1.9"
    assert meta.data_teste is not None
    assert "2024-09-06" in meta.data_teste


def test_migrate_legacy_idempotent(tmp_path, monkeypatch):
    """Running migration twice should not duplicate data."""
    legacy_dir = tmp_path / "motor_result"
    legacy_dir.mkdir()

    import backend.config as cfg
    import importlib
    import backend.biblioteca as bib_mod
    monkeypatch.setattr(cfg, "LEGACY_MOTOR_RESULT_DIR", legacy_dir)
    importlib.reload(bib_mod)

    (legacy_dir / "MotorX_resultados.csv").write_text(
        "Impulso [N*s];Empuxo max [N];Empuxo medio [N];Pontos amostrais;Duração [s];Classe\n"
        "59.27;53.88;31.19;20;1.9;F31.2-1.9\n"
    )

    first_result = bib_mod.migrate_legacy_motor_result()
    assert "MotorX" in first_result

    # Second run returns empty (files already moved)
    second_result = bib_mod.migrate_legacy_motor_result()
    assert not second_result

    # The motor entry exists only once
    assert bib_mod.get_motor("MotorX") is not None


def test_migrate_legacy_no_resultados_skipped(tmp_path, monkeypatch):
    """Files without a _resultados.csv should be skipped."""
    legacy_dir = tmp_path / "motor_result"
    legacy_dir.mkdir()

    import backend.config as cfg
    import importlib
    import backend.biblioteca as bib_mod
    monkeypatch.setattr(cfg, "LEGACY_MOTOR_RESULT_DIR", legacy_dir)
    importlib.reload(bib_mod)

    (legacy_dir / "MotorX_dados.csv").write_text("Data;Hora;Empuxo;Tempo\n")
    (legacy_dir / "MotorX_grafico.png").touch()

    result = migrate_legacy_motor_result()
    assert result == []
