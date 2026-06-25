"""Parser for RASP (.eng) motor data files.

RASP (Rocket Altitude Simulation Program) is the standard format for motor
data interchange. Format specification: https://www.thrustcurve.org/info/raspformat.html

The file format:
    - Lines starting with ';' are comments (ignored)
    - Blank lines at the beginning are ignored
    - First non-comment line is the header (7 space-separated fields):
        1. designation      -- motor name (e.g. "F32")
        2. diameter_mm      -- motor diameter in mm
        3. length_mm        -- motor length in mm
        4. delays           -- ejection delay times (e.g. "5-10-15")
        5. propellant_mass_kg -- propellant mass in kg
        6. total_mass_kg    -- total motor mass in kg
        7. manufacturer     -- manufacturer abbreviation
    - Remaining non-comment lines are data points: "time_s thrust_N"
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from io import StringIO
from pathlib import Path
from typing import Union

GRAVITY = 9.80665  # m/s^2


@dataclass
class EngData:
    """Parsed RASP motor data.

    Attributes:
        designation: Motor designation string (e.g. "F32").
        diameter_mm: Motor diameter in millimeters.
        length_mm: Motor length in millimeters.
        delays: Ejection delay specification string.
        propellant_mass_kg: Propellant mass in kilograms.
        total_mass_kg: Total motor mass in kilograms.
        manufacturer: Manufacturer abbreviation.
        thrust_curve: List of (time_s, thrust_N) data points.
        max_thrust_N: Maximum thrust in Newtons (computed).
        total_impulse_Ns: Total impulse in N·s, computed via Simpson integration.
        avg_thrust_N: Average thrust in Newtons (computed).
        burn_time_s: Total burn time in seconds (computed).
        isp_seconds: Specific impulse in seconds (computed, None if prop_mass is 0).
    """

    designation: str
    diameter_mm: float
    length_mm: float
    delays: str
    propellant_mass_kg: float
    total_mass_kg: float
    manufacturer: str
    thrust_curve: list[tuple[float, float]] = field(default_factory=list)

    # Computed fields
    max_thrust_N: float = 0.0
    total_impulse_Ns: float = 0.0
    avg_thrust_N: float = 0.0
    burn_time_s: float = 0.0
    isp_seconds: float | None = None

    def compute_derived(self) -> None:
        """Compute derived metrics from thrust curve data.

        Calculates max thrust, total impulse (Simpson rule), average thrust,
        burn time, and specific impulse (Isp).
        """
        if not self.thrust_curve:
            return

        times = [t for t, _ in self.thrust_curve]
        thrusts = [f for _, f in self.thrust_curve]

        self.max_thrust_N = max(thrusts)
        self.burn_time_s = times[-1] - times[0]

        # Total impulse via Simpson's rule
        n = len(times)
        if n >= 3 and n % 2 == 1:
            h = (times[-1] - times[0]) / (n - 1)
            impulse = thrusts[0] + thrusts[-1]
            for i in range(1, n - 1):
                impulse += 4 * thrusts[i] if i % 2 == 1 else 2 * thrusts[i]
            impulse *= h / 3
            self.total_impulse_Ns = round(impulse, 4)
        elif n >= 2:
            # Fallback: trapezoidal rule
            self.total_impulse_Ns = round(
                sum(
                    (thrusts[i] + thrusts[i + 1]) * (times[i + 1] - times[i]) / 2
                    for i in range(n - 1)
                ),
                4,
            )

        if self.burn_time_s > 0:
            self.avg_thrust_N = round(self.total_impulse_Ns / self.burn_time_s, 4)

        if self.propellant_mass_kg > 0:
            self.isp_seconds = round(
                self.total_impulse_Ns / (self.propellant_mass_kg * GRAVITY), 4
            )


def parse_eng_file(path: Union[str, Path]) -> EngData:
    """Parse a RASP (.eng) file and return structured motor data.

    Args:
        path: Path to the .eng file.

    Returns:
        EngData: Parsed motor data with computed metrics.

    Raises:
        ValueError: If the file is malformed or missing required fields.
        FileNotFoundError: If the file does not exist.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"ENG file not found: {path}")

    text = path.read_text(encoding="utf-8", errors="replace")
    return parse_eng_from_text(text)


def parse_eng_from_text(text: str) -> EngData:
    """Parse RASP motor data from a string.

    Args:
        text: Contents of an .eng file.

    Returns:
        EngData: Parsed motor data with computed metrics.

    Raises:
        ValueError: If the content is malformed.
    """
    lines = text.splitlines()

    # Filter: skip blank lines and comments at the beginning
    data_lines: list[str] = []
    header_found = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(";"):
            continue

        if not header_found:
            # First non-comment, non-blank line is the header
            _parse_header(stripped)
            header_found = True
        else:
            data_lines.append(stripped)

    if not header_found:
        raise ValueError("No header line found in ENG file")

    # Re-parse header to get the EngData object
    eng = _parse_header(
        next(
            l.strip()
            for l in lines
            if l.strip() and not l.strip().startswith(";")
        )
    )

    # Parse data points
    thrust_curve: list[tuple[float, float]] = []
    for line in data_lines:
        if line.startswith(";"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        try:
            t = float(parts[0])
            f = float(parts[1])
        except ValueError:
            continue
        if f < 0:
            raise ValueError(f"Negative thrust value: {f} at t={t}")
        thrust_curve.append((t, f))

    if len(thrust_curve) < 2:
        raise ValueError(
            f"ENG file must have at least 2 data points, got {len(thrust_curve)}"
        )

    # Validate monotonic time
    times = [t for t, _ in thrust_curve]
    for i in range(1, len(times)):
        if times[i] <= times[i - 1]:
            raise ValueError(
                f"Time must be monotonically increasing: {times[i - 1]} -> {times[i]}"
            )

    eng.thrust_curve = thrust_curve
    eng.compute_derived()
    return eng


def _parse_header(header_line: str) -> EngData:
    """Parse the 7-field header line of an ENG file.

    Args:
        header_line: The first non-comment line of the file.

    Returns:
        EngData: Partially populated (no thrust curve yet).

    Raises:
        ValueError: If the header does not have exactly 7 fields.
    """
    parts = header_line.split()
    if len(parts) != 7:
        raise ValueError(
            f"ENG header must have exactly 7 fields, got {len(parts)}: {header_line}"
        )

    try:
        diameter = float(parts[1])
        length = float(parts[2])
        prop_mass = float(parts[4])
        total_mass = float(parts[5])
    except ValueError as e:
        raise ValueError(f"Numeric conversion error in header: {e}") from e

    if diameter <= 0:
        raise ValueError(f"Diameter must be > 0, got {diameter}")
    if length <= 0:
        raise ValueError(f"Length must be > 0, got {length}")
    if prop_mass <= 0:
        raise ValueError(f"Propellant mass must be > 0, got {prop_mass}")
    if total_mass <= 0:
        raise ValueError(f"Total mass must be > 0, got {total_mass}")

    return EngData(
        designation=parts[0],
        diameter_mm=diameter,
        length_mm=length,
        delays=parts[3],
        propellant_mass_kg=prop_mass,
        total_mass_kg=total_mass,
        manufacturer=parts[6],
    )


def eng_to_dict(eng: EngData) -> dict:
    """Serialize EngData to a dictionary for JSON storage.

    Args:
        eng: Parsed ENG data.

    Returns:
        dict: Serialized data.
    """
    return {
        "designation": eng.designation,
        "diameter_mm": eng.diameter_mm,
        "length_mm": eng.length_mm,
        "delays": eng.delays,
        "propellant_mass_kg": eng.propellant_mass_kg,
        "total_mass_kg": eng.total_mass_kg,
        "manufacturer": eng.manufacturer,
        "thrust_curve": [
            {"time_s": t, "thrust_N": f} for t, f in eng.thrust_curve
        ],
        "max_thrust_N": eng.max_thrust_N,
        "total_impulse_Ns": eng.total_impulse_Ns,
        "avg_thrust_N": eng.avg_thrust_N,
        "burn_time_s": eng.burn_time_s,
        "isp_seconds": eng.isp_seconds,
    }


def dict_to_eng_preview(d: dict) -> EngData:
    """Deserialize a dictionary back to EngData for preview.

    Args:
        d: Dictionary from eng_to_dict.

    Returns:
        EngData: Reconstructed object.
    """
    curve = [(p["time_s"], p["thrust_N"]) for p in d.get("thrust_curve", [])]
    eng = EngData(
        designation=d["designation"],
        diameter_mm=d["diameter_mm"],
        length_mm=d["length_mm"],
        delays=d["delays"],
        propellant_mass_kg=d["propellant_mass_kg"],
        total_mass_kg=d["total_mass_kg"],
        manufacturer=d["manufacturer"],
        thrust_curve=curve,
    )
    eng.max_thrust_N = d.get("max_thrust_N", 0.0)
    eng.total_impulse_Ns = d.get("total_impulse_Ns", 0.0)
    eng.avg_thrust_N = d.get("avg_thrust_N", 0.0)
    eng.burn_time_s = d.get("burn_time_s", 0.0)
    eng.isp_seconds = d.get("isp_seconds")
    return eng
