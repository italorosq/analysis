"""Tests for the RASP (.eng) file parser."""

import pytest
from pathlib import Path

from backend.parser_eng import (
    EngData,
    parse_eng_file,
    parse_eng_from_text,
    eng_to_dict,
    dict_to_eng_preview,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_ENG = """; Rocketvision F32
; from NAR data sheet updated 11/2000
; created by John Coker 5/2006
F32 24 124 5-10-15 .0377 .0695 RV
   0.01 50
   0.05 56
   0.10 48
   2.00 24
   2.20 19
   2.24  5
   2.72  0
;
"""

SAMPLE_ENG_NO_COMMENT = """F32 24 124 5-10-15 .0377 .0695 RV
   0.01 50
   0.05 56
   0.10 48
   2.00 24
   2.20 19
   2.24  5
   2.72  0
"""

SAMPLE_ENG_WITH_INLINE_COMMENTS = """F32 24 124 5-10-15 .0377 .0695 RV
   0.01 50
   ; mid-curve comment
   0.05 56
   0.10 48
   2.00 24
   2.20 19
   2.24  5
   2.72  0
"""


@pytest.fixture
def eng_file(tmp_path):
    """Write sample ENG to a temp file."""
    path = tmp_path / "test.eng"
    path.write_text(SAMPLE_ENG)
    return path


# ---------------------------------------------------------------------------
# Header parsing
# ---------------------------------------------------------------------------

def test_parse_valid_eng(eng_file):
    eng = parse_eng_file(eng_file)
    assert eng.designation == "F32"
    assert eng.diameter_mm == 24.0
    assert eng.length_mm == 124.0
    assert eng.delays == "5-10-15"
    assert abs(eng.propellant_mass_kg - 0.0377) < 1e-9
    assert abs(eng.total_mass_kg - 0.0695) < 1e-9
    assert eng.manufacturer == "RV"


def test_parse_from_text():
    eng = parse_eng_from_text(SAMPLE_ENG)
    assert eng.designation == "F32"
    assert len(eng.thrust_curve) == 7


def test_parse_without_leading_comments():
    eng = parse_eng_from_text(SAMPLE_ENG_NO_COMMENT)
    assert eng.designation == "F32"
    assert len(eng.thrust_curve) == 7


def test_parse_with_inline_comments():
    eng = parse_eng_from_text(SAMPLE_ENG_WITH_INLINE_COMMENTS)
    assert len(eng.thrust_curve) == 7


def test_header_too_few_fields():
    with pytest.raises(ValueError, match="7 fields"):
        parse_eng_from_text("F32 24 124 5-10-15 .0377")


def test_header_too_many_fields():
    with pytest.raises(ValueError, match="7 fields"):
        parse_eng_from_text("F32 24 124 5-10-15 .0377 .0695 RV extra")


def test_header_negative_diameter():
    with pytest.raises(ValueError, match="Diameter must be > 0"):
        parse_eng_from_text("F32 -24 124 5-10-15 .0377 .0695 RV")


def test_header_zero_mass():
    with pytest.raises(ValueError, match="Propellant mass must be > 0"):
        parse_eng_from_text("F32 24 124 5-10-15 0 .0695 RV")


# ---------------------------------------------------------------------------
# Data points
# ---------------------------------------------------------------------------

def test_data_points_count(eng_file):
    eng = parse_eng_file(eng_file)
    assert len(eng.thrust_curve) == 7


def test_data_points_values(eng_file):
    eng = parse_eng_file(eng_file)
    assert eng.thrust_curve[0] == (0.01, 50.0)
    assert eng.thrust_curve[-1] == (2.72, 0.0)


def test_insufficient_data_points():
    with pytest.raises(ValueError, match="at least 2 data points"):
        parse_eng_from_text("F32 24 124 5-10-15 .0377 .0695 RV\n0.01 50\n")


def test_non_monotonic_time():
    bad = "F32 24 124 5-10-15 .0377 .0695 RV\n0.01 50\n0.05 56\n0.03 48\n"
    with pytest.raises(ValueError, match="monotonically increasing"):
        parse_eng_from_text(bad)


def test_negative_thrust():
    bad = "F32 24 124 5-10-15 .0377 .0695 RV\n0.01 50\n0.05 -5\n"
    with pytest.raises(ValueError, match="Negative thrust"):
        parse_eng_from_text(bad)


# ---------------------------------------------------------------------------
# Derived metrics
# ---------------------------------------------------------------------------

def test_max_thrust(eng_file):
    eng = parse_eng_file(eng_file)
    assert eng.max_thrust_N == 56.0


def test_burn_time(eng_file):
    eng = parse_eng_file(eng_file)
    assert abs(eng.burn_time_s - 2.71) < 1e-9  # 2.72 - 0.01


def test_total_impulse_positive(eng_file):
    eng = parse_eng_file(eng_file)
    assert eng.total_impulse_Ns > 0


def test_avg_thrust(eng_file):
    eng = parse_eng_file(eng_file)
    assert eng.avg_thrust_N > 0
    assert eng.avg_thrust_N <= eng.max_thrust_N


def test_isp_computed(eng_file):
    eng = parse_eng_file(eng_file)
    assert eng.isp_seconds is not None
    assert eng.isp_seconds > 0


def test_isp_none_when_zero_prop_mass():
    """Isp should be None if propellant mass is 0 (edge case, though header rejects 0)."""
    eng = EngData(
        designation="X",
        diameter_mm=24,
        length_mm=124,
        delays="5",
        propellant_mass_kg=0,
        total_mass_kg=0.1,
        manufacturer="RV",
        thrust_curve=[(0, 10), (1, 10), (2, 0)],
    )
    eng.compute_derived()
    assert eng.isp_seconds is None


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------

def test_eng_to_dict(eng_file):
    eng = parse_eng_file(eng_file)
    d = eng_to_dict(eng)
    assert d["designation"] == "F32"
    assert d["diameter_mm"] == 24.0
    assert len(d["thrust_curve"]) == 7
    assert "max_thrust_N" in d
    assert "total_impulse_Ns" in d
    assert "isp_seconds" in d


def test_dict_to_eng_preview(eng_file):
    eng = parse_eng_file(eng_file)
    d = eng_to_dict(eng)
    preview = dict_to_eng_preview(d)
    assert preview.designation == eng.designation
    assert preview.diameter_mm == eng.diameter_mm
    assert preview.max_thrust_N == eng.max_thrust_N
    assert preview.total_impulse_Ns == eng.total_impulse_Ns
    assert preview.isp_seconds == eng.isp_seconds
    assert len(preview.thrust_curve) == len(eng.thrust_curve)


# ---------------------------------------------------------------------------
# File not found
# ---------------------------------------------------------------------------

def test_file_not_found():
    with pytest.raises(FileNotFoundError):
        parse_eng_file("/nonexistent/path.eng")


# ---------------------------------------------------------------------------
# Empty file
# ---------------------------------------------------------------------------

def test_empty_file():
    with pytest.raises(ValueError, match="No header line"):
        parse_eng_from_text("")


def test_only_comments():
    with pytest.raises(ValueError, match="No header line"):
        parse_eng_from_text("; comment 1\n; comment 2\n")
