"""Tests for the CLI biblioteca subcommands."""

import sys
import pytest
from pathlib import Path

# Ensure app/ is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.cli import main


SAMPLE_ENG = """F32 24 124 5-10-15 .0377 .0695 RV
   0.01 50
   0.05 56
   0.10 48
   2.00 24
   2.20 19
   2.24  5
   2.72  0
"""


@pytest.fixture(autouse=True)
def clean_library(tmp_path, monkeypatch):
    """Use a temporary library directory for each test."""
    from backend import config as cfg

    fake_lib = tmp_path / "biblioteca"
    fake_lib.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(cfg, "LIBRARY_DIR", fake_lib)
    monkeypatch.setattr(cfg, "LEGACY_MOTOR_RESULT_DIR", tmp_path / "motor_result")
    yield


def test_biblioteca_list_empty(capsys):
    rv = main(["biblioteca", "list"])
    assert rv == 0
    captured = capsys.readouterr()
    assert "Biblioteca vazia" in captured.out


def test_biblioteca_list_with_motor(capsys):
    from backend.biblioteca import save_motor_metadata, MotorMetadata

    save_motor_metadata(
        "TestMotor",
        MotorMetadata(
            nome="TestMotor",
            impulso_total_Ns=100.0,
            classe="F31.2-1.9",
            data_teste="2025-06-15T14:30:00",
        ),
    )

    rv = main(["biblioteca", "list"])
    assert rv == 0
    captured = capsys.readouterr()
    assert "TestMotor" in captured.out
    assert "F31.2-1.9" in captured.out
    assert "100.000" in captured.out


def test_biblioteca_info_not_found(capsys):
    rv = main(["biblioteca", "info", "NonExistent"])
    assert rv == 1
    captured = capsys.readouterr()
    assert "encontrado" in captured.err.lower()


def test_biblioteca_info_exists(capsys, tmp_path):
    from backend.biblioteca import save_motor_metadata, MotorMetadata

    save_motor_metadata(
        "InfoMotor",
        MotorMetadata(
            nome="InfoMotor",
            impulso_total_Ns=249.81,
            empuxo_maximo_N=19.62,
            empuxo_medio_N=12.49,
            pressao_maxima_MPa=5.0,
            pressao_media_MPa=3.167,
            duracao_s=20.0,
            classe="H12.5-20.0",
            pontos_amostrais=200,
        ),
    )

    rv = main(["biblioteca", "info", "InfoMotor"])
    assert rv == 0
    captured = capsys.readouterr()
    assert "InfoMotor" in captured.out
    assert "H12.5-20.0" in captured.out
    assert "249.810" in captured.out


def test_biblioteca_info_with_eng(capsys, tmp_path):
    from backend.biblioteca import save_motor_metadata, MotorMetadata
    from backend.parser_eng import eng_to_dict, parse_eng_from_text

    eng_data = parse_eng_from_text(SAMPLE_ENG)
    save_motor_metadata(
        "EngMotor",
        MotorMetadata(
            nome="EngMotor",
            classe="F31.2-1.9",
            openmotor_eng="test.eng",
            openmotor_dados=eng_to_dict(eng_data),
        ),
    )

    rv = main(["biblioteca", "info", "EngMotor"])
    assert rv == 0
    captured = capsys.readouterr()
    assert "DADOS OPENMOTOR" in captured.out
    assert "F32" in captured.out
    assert "RV" in captured.out


def test_biblioteca_eng_preview(capsys, tmp_path):
    eng_file = tmp_path / "test.eng"
    eng_file.write_text(SAMPLE_ENG)

    rv = main(["biblioteca", "eng", str(eng_file)])
    assert rv == 0
    captured = capsys.readouterr()
    assert "PREVIEW .eng" in captured.out
    assert "F32" in captured.out
    assert "RV" in captured.out
    assert "56.0" in captured.out


def test_biblioteca_eng_file_not_found(capsys):
    rv = main(["biblioteca", "eng", "/nonexistent/file.eng"])
    assert rv == 1
    captured = capsys.readouterr()
    assert "encontrado" in captured.err.lower()


def test_biblioteca_eng_invalid(capsys, tmp_path):
    bad_file = tmp_path / "bad.eng"
    bad_file.write_text("invalid content")

    rv = main(["biblioteca", "eng", str(bad_file)])
    assert rv == 1
    captured = capsys.readouterr()
    assert "Erro" in captured.err


def test_biblioteca_no_subcommand(capsys):
    rv = main(["biblioteca"])
    assert rv == 1
    captured = capsys.readouterr()
    assert "Uso:" in captured.out


def test_biblioteca_unknown_subcommand(capsys):
    rv = main(["biblioteca", "unknown"])
    assert rv == 1
    captured = capsys.readouterr()
    assert "desconhecido" in captured.out


def test_biblioteca_info_missing_name(capsys):
    rv = main(["biblioteca", "info"])
    assert rv == 1
    captured = capsys.readouterr()
    assert "Uso:" in captured.out


def test_biblioteca_eng_missing_file(capsys):
    rv = main(["biblioteca", "eng"])
    assert rv == 1
    captured = capsys.readouterr()
    assert "Uso:" in captured.out
