"""Central configuration for the Serra Rocketry analysis app."""

from pathlib import Path

# --- Library ---
LIBRARY_DIR = Path(__file__).parent.parent / "data" / "biblioteca"
ALLOWED_ENG_EXTENSIONS = {".eng"}
ALLOWED_PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".png"}
ALLOWED_UPLOAD_EXTENSIONS = ALLOWED_ENG_EXTENSIONS | ALLOWED_PHOTO_EXTENSIONS
MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10 MB

# --- Legacy (to be removed after migration) ---
LEGACY_MOTOR_RESULT_DIR = Path(__file__).parent.parent / "data" / "motor_result"
LEGACY_DATA_TREATMENT_DIR = Path(__file__).parent.parent / "data" / "data_treatment"
