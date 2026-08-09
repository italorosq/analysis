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
from backend.tratamento import active_motor_window, data_treatment  # noqa: E402


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
    # Métricas são calculadas sobre a janela ativa da queima (recorte robusto),
    # que é um subconjunto do DataFrame completo.
    assert 0 < r["Pontos amostrais"] <= len(analysis.get_data())
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


def test_get_result_is_json_serializable(analysis):
    """O resultado precisa ser serializável (ex.: sessão Flask/cookie).

    Valores ``numpy`` (np.float64/np.int64) quebram a serialização da sessão
    e impedem o salvamento do relatório na web.
    """
    import json

    r = analysis.get_result()
    payload = json.dumps(r, ensure_ascii=False)
    assert json.loads(payload) == r
    for v in r.values():
        assert isinstance(v, (int, float, str))



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
    assert (out_dir / "dados" / "UnitTestMotor_resultados.csv").exists()
    assert (out_dir / "dados" / "UnitTestMotor_dados.csv").exists()
    assert (out_dir / "graficos" / "UnitTestMotor_grafico.png").exists()
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


# --------------------------------------------------------------------------- #
# Recorte de janela ativa do motor
# --------------------------------------------------------------------------- #
def test_active_motor_window_trims_idle_segments():
    import pandas as pd

    # Longo perÃ­odo de coleta ociosa antes/depois da queima.
    df = pd.DataFrame(
        {
            "Tempo_rel": [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
            "Empuxo_N": [0, 0, 0, 8, 10, 7, 0, 0, 0, 0],
            "Pressao_MPa": [0, 0, 0, 0.3, 0.4, 0.25, 0, 0, 0, 0],
        }
    )

    window = active_motor_window(df)

    # Com margem de 2 amostras, espera-se manter o intervalo [1, 7].
    assert len(window) == 7
    assert window["Empuxo_N"].tolist() == [0, 0, 8, 10, 7, 0, 0]
    assert window["Tempo_rel"].iloc[0] == pytest.approx(0.0, abs=1e-9)
    assert window["Tempo_rel"].iloc[-1] == pytest.approx(6.0, abs=1e-9)


def test_active_motor_window_fallback_when_no_activity():
    import pandas as pd

    df = pd.DataFrame(
        {
            "Tempo_rel": [0, 1, 2],
            "Empuxo_N": [0.0, 0.0, 0.0],
            "Pressao_MPa": [0.0, 0.0, 0.0],
        }
    )

    window = active_motor_window(df)
    assert len(window) == len(df)


# --------------------------------------------------------------------------- #
# Janela robusta com spikes (preserva queima real)
# --------------------------------------------------------------------------- #
def test_active_motor_window_preserves_burn_with_spikes():
    """A janela deve manter o bloco de maior impulso (queima real), não o spike."""
    import pandas as pd

    # Ruído pré/queima/pós/satélite: spike de saturação isolado + queima sustentada.
    n = 200
    t = [i * 0.1 for i in range(n)]
    thrust = [0.0] * n  # ruído zero
    for i in range(60, 150):
        thrust[i] = 10.0 + 5.0 * ((i - 60) / 90)  # queima sustentada 10-15 N
    thrust[30] = 5000.0  # spike isolado (1 ponto)
    thrust[31] = 5000.0  # spike vizinho (2 pontos)
    df = pd.DataFrame({"Tempo_rel": t, "Empuxo_N": thrust, "Pressao_MPa": [0.0] * n})

    window = active_motor_window(df)

    # Deve manter a queima (t≈6-15s original), NÃO o spike (t≈3s).
    # O Tempo_rel é re-zerado no início da janela.
    assert window["Tempo_rel"].iloc[0] == pytest.approx(0.0, abs=1e-9)
    # A janela deve abranger a queima (originalmente t=6-15s → ~9s de duração).
    assert window["Tempo_rel"].max() > 8.0
    # O spike de 5000 N NÃO deve estar na janela (filtrado pelo Hampel).
    assert (window["Empuxo_N"] < 100).all()
    # O pico da queima (10-15 N) deve estar presente.
    assert window["Empuxo_N"].max() > 10.0


def test_active_motor_window_margin():
    """Margem de ±2 amostras deve ser aplicada corretamente."""
    import pandas as pd

    df = pd.DataFrame(
        {
            "Tempo_rel": list(range(20)),
            "Empuxo_N": [0.0] * 5 + [20.0] * 10 + [0.0] * 5,
            "Pressao_MPa": [0.0] * 20,
        }
    )
    window = active_motor_window(df, margin=2)
    # Margem: 2 antes + 10 burn + 2 depois = 14 pontos.
    assert len(window) == 14


# --------------------------------------------------------------------------- #
# remove_outliers preserva pico da queima
# --------------------------------------------------------------------------- #
def test_remove_outliers_preserves_burn_peak():
    """O filtro Hampel deve remover spikes isolados mas manter o pico real."""
    import pandas as pd
    import numpy as np

    n = 300
    t = np.arange(n) * 0.1
    thrust = np.random.default_rng(42).normal(0, 0.5, n)
    # Injeta queima sustentada (t=10-20s) pico 50 N.
    for i in range(100, 200):
        thrust[i] = 50.0 - 0.2 * (i - 100)
    # Injeta spike isolado em t=5s = 900 N.
    thrust[50] = 900.0

    df = pd.DataFrame(
        {
            "Tempo": (t * 1000).astype(int),
            "Empuxo": thrust,
            "Pressao": [0.0] * n,
        }
    )

    from backend.analises import motor_analisys

    m = motor_analisys.__new__(motor_analisys)
    m.df = df.copy()
    m.df["Empuxo_N"] = pd.Series(thrust, dtype=float)
    m.df["Tempo_s"] = pd.Series(t)
    m.df["Pressao_MPa"] = pd.Series([0.0] * n)
    m.df["Tempo_rel"] = pd.Series(t) - t[0]
    m.df_result = None

    n_out = m.remove_outliers()

    assert n_out >= 1  # spike removido
    assert m.df["Empuxo_N"].max() > 40  # pico da queima (~50) preservado


# --------------------------------------------------------------------------- #
# Novos gráficos avulso
# --------------------------------------------------------------------------- #
def test_plot_force_time_writes_png(analysis, tmp_path):
    path = analysis.plot_force_time("TestMotor", tmp_path)
    assert Path(path).exists()
    assert Path(path).suffix == ".png"
    assert Path(path).stat().st_size > 0


def test_plot_impulse_time_writes_png(analysis, tmp_path):
    path = analysis.plot_impulse_time("TestMotor", tmp_path)
    assert Path(path).exists()
    assert Path(path).stat().st_size > 0


def test_plot_spline_writes_png(analysis, tmp_path):
    path = analysis.plot_spline("TestMotor", tmp_path)
    assert Path(path).exists()
    assert Path(path).stat().st_size > 0


def test_save_analisys_writes_all_avulso(analysis, tmp_path):
    analysis.save_analisys("UnitTestMotor", tmp_path)
    graficos = tmp_path / "graficos"
    dados = tmp_path / "dados"
    for suffix in ["_grafico.png", "_forca_tempo.png", "_impulso_tempo.png", "_spline.png"]:
        assert (graficos / f"UnitTestMotor{suffix}").exists(), f"Faltou grafico: {suffix}"
    for suffix in ["_resultados.csv", "_dados.csv"]:
        assert (dados / f"UnitTestMotor{suffix}").exists(), f"Faltou csv: {suffix}"
    assert (tmp_path / "UnitTestMotor.pdf").exists()


# --------------------------------------------------------------------------- #
# default_filter_threshold
# --------------------------------------------------------------------------- #
def test_default_filter_threshold_robust():
    from backend.tratamento import default_filter_threshold
    import pandas as pd

    # Série com spike de saturação + queima sustentada.
    thrust = pd.Series([0.0] * 100 + [50.0] * 100 + [0.0] * 100)
    thrust.iloc[5] = 9000.0  # spike
    df = pd.DataFrame({"Empuxo_N": thrust})
    thr = default_filter_threshold(df)

    # O limiar deve ser baixo (fração do P95 limpo), não a média (que seria ~16).
    assert thr < 10.0
    assert thr > 0.0
