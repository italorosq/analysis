"""Library management for motor test data.

This module provides functions to scan, create, read, and delete motor
entries in the library directory. Each motor is stored as a subdirectory
containing a `motor.json` metadata file plus associated data files
(CSV, PNG, PDF, ENG, photos).

See docs/biblioteca.md for the full specification.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from backend import config as _config


def _get_library_dir() -> Path:
    """Get the library directory path (reads from config at call time)."""
    return _config.LIBRARY_DIR


@dataclass
class MotorMetadata:
    """Metadata for a motor test entry in the library.

    Attributes:
        nome: Motor name (used as directory name).
        data_teste: ISO 8601 datetime string of the test.
        impulso_total_Ns: Total impulse in N·s.
        empuxo_medio_N: Average thrust in N.
        empuxo_maximo_N: Maximum thrust in N.
        empuxo_minimo_N: Minimum thrust in N (optional).
        pressao_maxima_MPa: Maximum chamber pressure in MPa.
        pressao_media_MPa: Average chamber pressure in MPa.
        duracao_s: Burn duration in seconds.
        classe: NAR/TRA motor classification (e.g. "H12.5-20.0").
        pontos_amostrais: Number of data samples.
        csv_original: Filename of the original data CSV.
        resultados_csv: Filename of the results CSV.
        grafico_png: Filename of the plot PNG.
        relatorio_pdf: Filename of the PDF report.
        openmotor_eng: Filename of the uploaded .eng file.
        openmotor_dados: Parsed data from the .eng file (dict).
        fotos: List of photo filenames.
        notas: Free-form notes field.
        graficos_titulos: Custom chart/PDF titles (keys from the
            ``DEFAULT_TITULOS`` dict in :mod:`backend.analises`).
    """

    nome: str
    data_teste: str | None = None
    impulso_total_Ns: float = 0.0
    empuxo_medio_N: float = 0.0
    empuxo_maximo_N: float = 0.0
    empuxo_minimo_N: float | None = None
    pressao_maxima_MPa: float = 0.0
    pressao_media_MPa: float = 0.0
    duracao_s: float = 0.0
    classe: str = ""
    pontos_amostrais: int = 0
    csv_original: str | None = None
    resultados_csv: str | None = None
    grafico_png: str | None = None
    relatorio_pdf: str | None = None
    openmotor_eng: str | None = None
    openmotor_dados: dict | None = None
    fotos: list[str] = field(default_factory=list)
    notas: str = ""
    graficos_titulos: dict | None = None


# ---------------------------------------------------------------------------
# Directory operations
# ---------------------------------------------------------------------------

def init_library_dir() -> Path:
    """Ensure the library directory exists.

    Returns:
        Path: The library directory path.
    """
    lib_dir = _get_library_dir()
    lib_dir.mkdir(parents=True, exist_ok=True)
    return lib_dir


def _motor_dir(nome: str) -> Path:
    """Get the directory path for a motor entry.

    Args:
        nome: Motor name.

    Returns:
        Path: The motor's library subdirectory.
    """
    return _get_library_dir() / nome


# ---------------------------------------------------------------------------
# CRUD operations
# ---------------------------------------------------------------------------

def scan_library(sort_by: str = "data") -> list[MotorMetadata]:
    """Scan the library directory and return all motor metadata.

    Reads the ``motor.json`` file from each subdirectory and returns
    a list of ``MotorMetadata`` objects sorted by the requested field.

    Args:
        sort_by: Sort field — ``"data"``, ``"impulso"``, or ``"classe"``.

    Returns:
        list[MotorMetadata]: Sorted list of motor entries.
    """
    lib_dir = _get_library_dir()
    lib_dir.mkdir(parents=True, exist_ok=True)
    motors: list[MotorMetadata] = []

    for entry in sorted(lib_dir.iterdir()):
        if not entry.is_dir():
            continue
        json_path = entry / "motor.json"
        if not json_path.exists():
            continue
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
            motors.append(MotorMetadata(**data))
        except (json.JSONDecodeError, TypeError):
            continue

    # Sort
    if sort_by == "impulso":
        motors.sort(key=lambda m: m.impulso_total_Ns, reverse=True)
    elif sort_by == "classe":
        motors.sort(key=lambda m: m.classe)
    else:  # "data" (default)
        motors.sort(
            key=lambda m: m.data_teste or "",
            reverse=True,
        )
    return list(motors)


def get_motor(nome: str) -> MotorMetadata | None:
    """Retrieve metadata for a specific motor.

    Args:
        nome: Motor name (directory name).

    Returns:
        MotorMetadata: The motor data, or ``None`` if not found.
    """
    json_path = _motor_dir(nome) / "motor.json"
    if not json_path.exists():
        return None
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
        return MotorMetadata(**data)
    except (json.JSONDecodeError, TypeError):
        return None


def save_motor_metadata(nome: str, metadata: MotorMetadata) -> None:
    """Save motor metadata to ``motor.json``.

    Creates the motor directory if it doesn't exist.

    Args:
        nome: Motor name (used as directory name).
        metadata: The metadata to serialize.
    """
    motor_dir = _get_library_dir() / nome
    motor_dir.mkdir(parents=True, exist_ok=True)
    json_path = motor_dir / "motor.json"
    json_path.write_text(
        json.dumps(asdict(metadata), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def delete_motor(nome: str) -> bool:
    """Delete a motor entry and all its files.

    Args:
        nome: Motor name (directory name).

    Returns:
        bool: ``True`` if deleted, ``False`` if not found.
    """
    motor_dir = _motor_dir(nome)
    if not motor_dir.exists():
        return False
    shutil.rmtree(motor_dir)
    return True


def update_quality_metadata(
    nome: str,
    result: dict | None,
    *,
    csv_original: str | None = None,
    resultados_csv: str | None = None,
    grafico_png: str | None = None,
    relatorio_pdf: str | None = None,
    data_teste: str | None = None,
) -> MotorMetadata:
    """Atualiza o ``motor.json`` com as métricas da análise e as referências
    dos arquivos gerados.

    Cria o registro se ainda não existir e **preserva** os campos já salvos
    (``notas``, ``fotos``, ``openmotor_*``, ``graficos_titulos``).

    Os valores são lidos do dicionário produzido por
    :meth:`backend.analises.motor_analisys.get_result` (chaves em pt-BR,
    ex.: ``"Impulso [N*s]"``), com fallback para os valores atuais quando a
    chave não estiver presente.

    Args:
        nome: Motor name (directory name).
        result: Dicionário de resultados da análise (pode ser ``None``).
        csv_original: Nome do CSV de dados completos (ex.: ``dados/x.csv``).
        resultados_csv: Nome do CSV de resultados.
        grafico_png: Nome do PNG principal (combinado).
        relatorio_pdf: Nome do PDF do relatório.
        data_teste: Data do teste em ISO 8601 (se ``None``, não altera).

    Returns:
        MotorMetadata: Metadados persistidos.
    """
    meta = get_motor(nome)
    if meta is None:
        meta = MotorMetadata(nome=nome)

    if result:
        meta.impulso_total_Ns = float(result.get("Impulso [N*s]", meta.impulso_total_Ns) or 0)
        meta.empuxo_maximo_N = float(result.get("Empuxo max [N]", meta.empuxo_maximo_N) or 0)
        meta.empuxo_medio_N = float(result.get("Empuxo medio [N]", meta.empuxo_medio_N) or 0)
        if result.get("Empuxo min [N]") is not None:
            meta.empuxo_minimo_N = float(result["Empuxo min [N]"])
        meta.pressao_maxima_MPa = float(
            result.get("Pressao max [MPa]", meta.pressao_maxima_MPa) or 0
        )
        meta.pressao_media_MPa = float(
            result.get("Pressao media [MPa]", meta.pressao_media_MPa) or 0
        )
        meta.duracao_s = float(result.get("Duracao [s]", meta.duracao_s) or 0)
        meta.classe = str(result.get("Classe", meta.classe) or "")
        meta.pontos_amostrais = int(result.get("Pontos amostrais", meta.pontos_amostrais) or 0)

    if csv_original is not None:
        meta.csv_original = csv_original
    if resultados_csv is not None:
        meta.resultados_csv = resultados_csv
    if grafico_png is not None:
        meta.grafico_png = grafico_png
    if relatorio_pdf is not None:
        meta.relatorio_pdf = relatorio_pdf
    if data_teste is not None:
        meta.data_teste = data_teste

    save_motor_metadata(nome, meta)
    return meta


# ---------------------------------------------------------------------------
# File management
# ---------------------------------------------------------------------------

def list_files(nome: str) -> dict[str, list[str]]:
    """List all files in a motor's library directory.

    Categorizes files by type (csv, png, pdf, eng, fotos, outros).

    Args:
        nome: Motor name.

    Returns:
        dict: Dictionary with category keys and filename lists as values.
    """
    motor_dir = _motor_dir(nome)
    if not motor_dir.exists():
        return {"csv": [], "png": [], "pdf": [], "eng": [], "fotos": [], "outros": []}

    result: dict[str, list[str]] = {
        "csv": [],
        "png": [],
        "pdf": [],
        "eng": [],
        "fotos": [],
        "outros": [],
    }

    for f in sorted(motor_dir.iterdir()):
        if f.name == "motor.json":
            continue
        if f.is_dir():
            # Pastas no formato "relatorios" (graficos/ e dados/),
            # prefixando a categoria com a subpasta.
            for sub in sorted(f.iterdir()):
                if not sub.is_file():
                    continue
                _classify(file=f"{f.name}/{sub.name}", result=result)
            continue
        _classify(file=f.name, result=result)

    return result


def _classify(file: str, result: dict[str, list[str]]) -> None:
    """Adiciona um arquivo à categoria correta de :func:`list_files`.

    Args:
        file: Nome do arquivo (pode incluir subpasta, ex.: ``graficos/x.png``).
        result: Dicionário de categorias a preencher.
    """
    ext = Path(file).suffix.lower()
    if ext == ".csv":
        result["csv"].append(file)
    elif ext == ".png":
        result["png"].append(file)
    elif ext == ".pdf":
        result["pdf"].append(file)
    elif ext == ".eng":
        result["eng"].append(file)
    elif ext in (".jpg", ".jpeg"):
        result["fotos"].append(file)
    else:
        result["outros"].append(file)


def register_file(nome: str, filename: str, category: str) -> None:
    """Register a file in the motor's metadata.

    Args:
        nome: Motor name.
        filename: The file name to register.
        category: File category — ``"csv"``, ``"png"``, ``"pdf"``,
            ``"eng"``, or ``"foto"``.
    """
    metadata = get_motor(nome)
    if metadata is None:
        return

    if category == "csv":
        if filename.endswith("resultados.csv"):
            metadata.resultados_csv = filename
        else:
            metadata.csv_original = filename
    elif category == "png":
        metadata.grafico_png = filename
    elif category == "pdf":
        metadata.relatorio_pdf = filename
    elif category == "eng":
        metadata.openmotor_eng = filename
    elif category == "foto":
        if filename not in metadata.fotos:
            metadata.fotos.append(filename)

    save_motor_metadata(nome, metadata)


def unregister_file(nome: str, filename: str) -> None:
    """Unregister a file from the motor's metadata.

    Removes the reference from the appropriate field without deleting
    the actual file.

    Args:
        nome: Motor name.
        filename: The file name to unregister.
    """
    metadata = get_motor(nome)
    if metadata is None:
        return

    if metadata.csv_original == filename:
        metadata.csv_original = None
    if metadata.resultados_csv == filename:
        metadata.resultados_csv = None
    if metadata.grafico_png == filename:
        metadata.grafico_png = None
    if metadata.relatorio_pdf == filename:
        metadata.relatorio_pdf = None
    if metadata.openmotor_eng == filename:
        metadata.openmotor_eng = None
        metadata.openmotor_dados = None
    if filename in metadata.fotos:
        metadata.fotos.remove(filename)

    save_motor_metadata(nome, metadata)


# ---------------------------------------------------------------------------
# Encoding helpers (arquivos legados podem estar em cp1252 no Windows)
# ---------------------------------------------------------------------------

def _read_text_any_encoding(path: Path) -> str:
    """Lê um arquivo de texto tolerando a codificação real do disco.

    Arquivos legados gerados no Windows podem estar em cp1252 (a codificação
    padrão de ``Path.write_text`` na época). Tenta UTF-8 (com BOM, se houver)
    primeiro e cai para cp1252/latin-1 — que nunca falha — garantindo a leitura
    de qualquer arquivo legado.
    """
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return path.read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="latin-1")


def _read_csv_any_encoding(path: Path):
    """Lê um CSV legado (separador ``;``) tolerando a codificação do disco. """
    import pandas as pd

    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return pd.read_csv(path, sep=";", encoding=enc)
        except UnicodeDecodeError:
            continue
    return pd.read_csv(path, sep=";", encoding="latin-1")


# ---------------------------------------------------------------------------
# Legacy migration
# ---------------------------------------------------------------------------

def infer_date_from_legacy(dados_csv_path: Path) -> str | None:
    """Infer test date from a legacy format data CSV.

    Legacy format: ``Data;Hora;Empuxo;Tempo`` (date in D/M/YYYY, time in H:MM:SS).

    Args:
        dados_csv_path: Path to the legacy data CSV.

    Returns:
        str | None: ISO 8601 datetime string, or ``None`` if parsing fails.
    """
    if not dados_csv_path.exists():
        return None

    try:
        lines = _read_text_any_encoding(dados_csv_path).splitlines()

        # Skip header line, find first data line with a date
        for line in lines[1:]:
            line = line.strip()
            if not line:
                continue
            parts = line.split(";")
            if len(parts) >= 2:
                date_str = parts[0].strip()
                time_str = parts[1].strip()
                # Parse D/M/YYYY H:MM:SS
                dt = datetime.strptime(f"{date_str} {time_str}", "%d/%m/%Y %H:%M:%S")
                return dt.isoformat()
    except (ValueError, IndexError):
        pass

    return None


def migrate_legacy_motor_result(dry_run: bool = False) -> list[str]:
    """Migrate legacy motor_result data into the new library structure.

    Scans ``data/motor_result/`` for result CSVs, groups files by motor
    name prefix, and creates corresponding entries in the library.

    Args:
        dry_run: If ``True``, only logs what would be done without making changes.

    Returns:
        list[str]: List of motor names that were (or would be) migrated.
    """
    from backend import config as _config_legacy
    legacy_dir = _config_legacy.LEGACY_MOTOR_RESULT_DIR

    if not legacy_dir.exists():
        return []

    # Group files by prefix (everything before _resultados, _dados, _grafico, .pdf)
    prefixes: dict[str, dict[str, Path]] = {}

    for f in sorted(legacy_dir.iterdir()):
        if not f.is_file():
            continue
        name = f.stem
        suffix = f.suffix.lower()

        # Determine prefix and file type
        if name.endswith("_resultados"):
            prefix = name[: -len("_resultados")]
            file_type = "resultados"
        elif name.endswith("_dados"):
            prefix = name[: -len("_dados")]
            file_type = "dados"
        elif name.endswith("_grafico"):
            prefix = name[: -len("_grafico")]
            file_type = "grafico"
        elif suffix == ".pdf":
            prefix = name
            file_type = "pdf"
        else:
            continue

        if prefix not in prefixes:
            prefixes[prefix] = {}
        prefixes[prefix][file_type] = f

    migrated: list[str] = []

    for prefix, files in prefixes.items():
        if "resultados" not in files:
            continue  # Need at least the results CSV

        if not dry_run:
            # Create library entry
            metadata = MotorMetadata(nome=prefix)

            # Parse results CSV
            try:
                df = _read_csv_any_encoding(files["resultados"])
                if len(df) > 0:
                    row = df.iloc[0]
                    metadata.impulso_total_Ns = float(row.get("Impulso [N*s]", 0))
                    metadata.empuxo_maximo_N = float(row.get("Empuxo max [N]", 0))
                    metadata.empuxo_medio_N = float(row.get("Empuxo medio [N]", 0))
                    metadata.pontos_amostrais = int(row.get("Pontos amostrais", 0))
                    metadata.duracao_s = float(row.get("Duração [s]", 0))
                    metadata.classe = str(row.get("Classe", ""))
            except Exception:
                pass

            # Infer date from data CSV
            if "dados" in files:
                metadata.data_teste = infer_date_from_legacy(files["dados"])

            # Register files
            if "resultados" in files:
                metadata.resultados_csv = files["resultados"].name
            if "dados" in files:
                metadata.csv_original = files["dados"].name
            if "grafico" in files:
                metadata.grafico_png = files["grafico"].name
            if "pdf" in files:
                metadata.relatorio_pdf = files["pdf"].name

            # Save metadata
            save_motor_metadata(prefix, metadata)

            # Move files to library
            motor_dir = _motor_dir(prefix)
            motor_dir.mkdir(parents=True, exist_ok=True)
            for src in files.values():
                dst = motor_dir / src.name
                if not dst.exists():
                    shutil.move(str(src), str(dst))

        migrated.append(prefix)

    return migrated
