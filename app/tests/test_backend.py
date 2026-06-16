"""
Pytest suite for the rocketry analysis backend.

Modules under test (in app/backend/):
  - analises.py    -> motor_analisys
  - tratamento.py  -> data_treatment

Run from the app/ directory:
    python -m pytest tests/test_backend.py -v
"""

import os
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # headless backend, no display needed

import pytest

# Make sure the `backend` package is importable regardless of where pytest is
# invoked from. The app root is the parent of this tests/ directory.
APP_ROOT = Path(__file__).resolve().parent.parent
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from backend.analises import motor_analisys  # noqa: E402
from backend.tratamento import data_treatment  # noqa: E402


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
GRAVITY = 9.81


@pytest.fixture
def csv_file(tmp_path):
    """
    Create a realistic motor-test CSV in the firmware format:
        Tempo,Empuxo,Pressao
    - Tempo increments by 100 ms per row
    - Empuxo (kg) ramps 0 -> 2.0 and back down to 0 (clear thrust curve)
    - Pressao (MPa) ramps 0 -> 5 and back down

    Returns the Path to the written CSV.
    """
    n = 51  # odd number of points -> clean triangular curve, good for Simpson
    half = n // 2  # 25

    lines = ["Tempo,Empuxo,Pressao"]
    for i in range(n):
        tempo = i * 100  # ms
        if i <= half:
            frac = i / half
        else:
            frac = (n - 1 - i) / half
        empuxo = round(2.0 * frac, 4)   # kg
        pressao = round(5.0 * frac, 4)  # MPa
        lines.append(f"{tempo},{empuxo},{pressao}")

    csv_path = tmp_path / "motor_test.csv"
    csv_path.write_text("\n".join(lines) + "\n")
    return csv_path


@pytest.fixture
def analysis(csv_file):
    """motor_analisys instance built from the fixture CSV."""
    return motor_analisys(str(csv_file))


@pytest.fixture
def treatment(csv_file):
    """data_treatment instance built from the fixture CSV."""
    return data_treatment(str(csv_file))


# --------------------------------------------------------------------------- #
# motor_analisys: unit conversions
# --------------------------------------------------------------------------- #
def test_columns_created(analysis):
    df = analysis.get_data()
    for col in ("Empuxo_N", "Tempo_s", "Pressao_MPa", "Tempo_rel"):
        assert col in df.columns


def test_empuxo_conversion(analysis):
    df = analysis.get_data()
    # Empuxo_N == Empuxo * 9.81 (rounded to 4 decimals by the implementation)
    expected = (df["Empuxo"] * GRAVITY).round(4)
    assert df["Empuxo_N"].round(4).tolist() == pytest.approx(expected.tolist(), abs=1e-4)


def test_tempo_s_conversion(analysis):
    df = analysis.get_data()
    expected = (df["Tempo"] / 1000.0)
    assert df["Tempo_s"].tolist() == pytest.approx(expected.tolist(), abs=1e-9)


def test_tempo_rel_starts_at_zero(analysis):
    df = analysis.get_data()
    assert df["Tempo_rel"].iloc[0] == pytest.approx(0.0, abs=1e-9)
    # last relative time = (n-1)*100ms = 5.0 s for 51 points
    assert df["Tempo_rel"].iloc[-1] > 0


def test_pressao_mpa_passthrough(analysis):
    df = analysis.get_data()
    assert df["Pressao_MPa"].round(4).tolist() == pytest.approx(
        df["Pressao"].round(4).tolist(), abs=1e-4
    )


# --------------------------------------------------------------------------- #
# motor_analisys: get_result
# --------------------------------------------------------------------------- #
EXPECTED_RESULT_KEYS = {
    "Impulso [N*s]",
    "Empuxo max [N]",
    "Empuxo medio [N]",
    "Pressao max [MPa]",
    "Pressao media [MPa]",
    "Pontos amostrais",
    "Duracao [s]",
    "Classe",
}


def test_get_result_keys(analysis):
    result = analysis.get_result()
    assert set(result.keys()) == EXPECTED_RESULT_KEYS


def test_get_result_values(analysis):
    r = analysis.get_result()
    assert r["Impulso [N*s]"] > 0
    assert r["Empuxo max [N]"] > r["Empuxo medio [N]"]
    assert r["Duracao [s]"] > 0
    assert r["Pontos amostrais"] == len(analysis.get_data())
    assert r["Pressao max [MPa]"] > 0


def test_classe_is_nonempty_string(analysis):
    r = analysis.get_result()
    assert isinstance(r["Classe"], str)
    assert len(r["Classe"]) > 0
    assert r["Classe"] != "ERRO"


def test_empuxo_max_matches_dataframe(analysis):
    df = analysis.get_data()
    r = analysis.get_result()
    assert r["Empuxo max [N]"] == pytest.approx(df["Empuxo_N"].max(), abs=1e-4)


# --------------------------------------------------------------------------- #
# motor_analisys: splines
# --------------------------------------------------------------------------- #
def test_spline_returns_callable(analysis):
    spl = analysis.spline()
    assert callable(spl)
    # Evaluate at a sample point -> numeric output
    val = float(spl(analysis.get_data()["Tempo_rel"].iloc[1]))
    assert isinstance(val, float)


def test_pressure_spline_returns_callable(analysis):
    spl = analysis.pressure_spline()
    assert callable(spl)
    val = float(spl(analysis.get_data()["Tempo_rel"].iloc[1]))
    assert isinstance(val, float)


def test_splines_are_cubicspline(analysis):
    from scipy.interpolate import CubicSpline
    assert isinstance(analysis.spline(), CubicSpline)
    assert isinstance(analysis.pressure_spline(), CubicSpline)


# --------------------------------------------------------------------------- #
# motor_analisys: plot_analisys (PNG)
# --------------------------------------------------------------------------- #
def test_plot_analisys_writes_png(analysis, tmp_path):
    out_dir = tmp_path / "plots"
    path = analysis.plot_analisys("UnitTestMotor", out_dir)
    path = Path(path)
    assert path.exists()
    assert path.suffix == ".png"
    assert path.stat().st_size > 0


# --------------------------------------------------------------------------- #
# motor_analisys: pdf
# --------------------------------------------------------------------------- #
def test_pdf_writes_file(analysis, tmp_path):
    out_dir = tmp_path / "pdf"
    # plot first so the PDF can embed the graph (and exercise that path)
    analysis.plot_analisys("UnitTestMotor", out_dir)
    path = analysis.pdf("UnitTestMotor", out_dir)
    path = Path(path)
    assert path.exists()
    assert path.suffix == ".pdf"
    assert path.stat().st_size > 1024  # > 1 KB


# --------------------------------------------------------------------------- #
# motor_analisys: save_analisys
# --------------------------------------------------------------------------- #
def test_save_analisys_writes_outputs(analysis, tmp_path):
    out_dir = tmp_path / "save"
    analysis.save_analisys("UnitTestMotor", out_dir)
    assert (out_dir / "UnitTestMotor_resultados.csv").exists()
    assert (out_dir / "UnitTestMotor_dados.csv").exists()
    assert (out_dir / "UnitTestMotor_grafico.png").exists()
    assert (out_dir / "UnitTestMotor.pdf").exists()


# --------------------------------------------------------------------------- #
# data_treatment
# --------------------------------------------------------------------------- #
def test_treatment_columns(treatment):
    df = treatment.get_data()
    for col in ("Tempo_s", "Empuxo_N", "Pressao_MPa", "Tempo_rel"):
        assert col in df.columns
    assert df["Tempo_rel"].iloc[0] == pytest.approx(0.0, abs=1e-9)


def test_treatment_empuxo_conversion(treatment):
    df = treatment.get_data()
    expected = (df["Empuxo"] * GRAVITY)
    assert df["Empuxo_N"].tolist() == pytest.approx(expected.tolist(), abs=1e-6)


def test_data_filter_threshold(treatment):
    df = treatment.get_data()
    threshold = 5.0  # Newtons
    filtered = treatment.data_filter(threshold)
    # Every retained row must exceed the threshold
    assert (filtered["Empuxo_N"] > threshold).all()
    # And it must be a proper subset (some rows are below threshold near 0)
    assert len(filtered) < len(df)
    assert len(filtered) > 0


def test_data_filter_interval(treatment):
    df = treatment.get_data()
    lo, hi = 1.0, 3.0
    filtered = treatment.data_filter(0.0, interval=[lo, hi])
    assert (filtered["Tempo_rel"] >= lo).all()
    assert (filtered["Tempo_rel"] <= hi).all()
    # Manually compute the expected count for the interval (threshold 0)
    expected = df[(df["Empuxo_N"] > 0.0) & (df["Tempo_rel"].between(lo, hi))]
    assert len(filtered) == len(expected)


def test_data_filter_combined(treatment):
    threshold = 5.0
    lo, hi = 1.0, 4.0
    filtered = treatment.data_filter(threshold, interval=[lo, hi])
    assert (filtered["Empuxo_N"] > threshold).all()
    assert (filtered["Tempo_rel"] >= lo).all()
    assert (filtered["Tempo_rel"] <= hi).all()


def test_get_stats_keys(treatment):
    stats = treatment.get_stats()
    assert set(stats.keys()) == {"thrust", "pressure", "duration_s", "samples"}


def test_get_stats_samples(treatment):
    stats = treatment.get_stats()
    assert stats["samples"] == len(treatment.get_data())
    assert stats["duration_s"] > 0
    assert isinstance(stats["thrust"], dict)
    assert isinstance(stats["pressure"], dict)


def test_save_treatment_writes_file(treatment, tmp_path):
    out_dir = tmp_path / "treatment"
    path = treatment.save_treatment("UnitTestMotor", data_dir=out_dir)
    assert os.path.exists(path)
    assert Path(path).suffix == ".csv"
    assert Path(path).stat().st_size > 0
