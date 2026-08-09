"""Blueprint for the library (biblioteca) routes.

Provides endpoints for browsing uploaded motor tests, viewing details,
uploading .eng files and photos, and managing entries.
"""

from __future__ import annotations

import os

from backend.analises import TITULOS_CAMPOS, merge_titulos
from backend.biblioteca import (
    MotorMetadata,
    delete_motor,
    get_motor,
    list_files,
    migrate_legacy_motor_result,
    register_file,
    save_motor_metadata,
    scan_library,
    unregister_file,
)
from backend.config import (
    ALLOWED_ENG_EXTENSIONS,
    ALLOWED_PHOTO_EXTENSIONS,
    ALLOWED_UPLOAD_EXTENSIONS,
    LEGACY_MOTOR_RESULT_DIR,
    LIBRARY_DIR,
)
from backend.parser_eng import parse_eng_from_text
from flask import (
    Blueprint,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)

# ---------------------------------------------------------------------------
# Blueprint
# ---------------------------------------------------------------------------

blueprint = Blueprint(
    "biblioteca",
    __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path="/static",
)

project_name: str = "serra-rocketry"


def _safe_filename(filename: str) -> str:
    """Sanitize a filename to prevent path traversal.

    Strips directory components and rejects empty names.

    Args:
        filename: Original filename.

    Returns:
        str: Sanitized basename.
    """
    return os.path.basename(filename)


def _allowed_upload(filename: str) -> bool:
    """Check if a file has an allowed upload extension.

    Args:
        filename: The filename to check.

    Returns:
        bool: True if the extension is in the allowed set.
    """
    if "." not in filename:
        return False
    ext = "." + filename.rsplit(".", 1)[1].lower()
    return ext in ALLOWED_UPLOAD_EXTENSIONS


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@blueprint.route("/")
def index() -> str:
    """Render the library grid page with all motor entries.

    Query params:
        sort: ``data`` (default), ``impulso``, or ``classe``.

    Returns:
        str: Rendered ``biblioteca.html`` template.
    """
    sort_by = request.args.get("sort", "data")
    if sort_by not in ("data", "impulso", "classe"):
        sort_by = "data"

    motors = scan_library(sort_by=sort_by)
    return render_template(
        "biblioteca.html",
        motors=motors,
        sort_by=sort_by,
        legacy_exists=LEGACY_MOTOR_RESULT_DIR.exists()
        and any(LEGACY_MOTOR_RESULT_DIR.iterdir()),
    )


@blueprint.route("/<nome>")
def detalhe(nome: str) -> str:
    """Render the detail page for a specific motor.

    Args:
        nome: Motor name (URL-encoded).

    Returns:
        str: Rendered ``biblioteca_detalhe.html`` template.

    Raises:
        404: If the motor does not exist.
    """
    nome = _safe_filename(nome)
    motor = get_motor(nome)
    if motor is None:
        abort(404)

    files = list_files(nome)
    return render_template(
        "biblioteca_detalhe.html",
        motor=motor,
        files=files,
        titulo_campos=TITULOS_CAMPOS,
        titulos_atuais=merge_titulos(motor.graficos_titulos),
    )


@blueprint.route("/<nome>/upload", methods=["POST"])
def upload(nome: str) -> str:
    """Handle upload of .eng files or photos to a motor entry.

    Accepts multipart/form-data with a ``file`` field.

    Args:
        nome: Motor name.

    Returns:
        str: Redirect to the motor detail page.

    Raises:
        404: If the motor does not exist.
    """
    nome = _safe_filename(nome)
    motor = get_motor(nome)
    if motor is None:
        # Create new motor entry
        motor = MotorMetadata(nome=nome)
        save_motor_metadata(nome, motor)

    if "file" not in request.files:
        flash("Nenhum arquivo enviado!", "error")
        return redirect(url_for("biblioteca.detalhe", nome=nome))

    uploaded = request.files["file"]
    if uploaded.filename == "":
        flash("Nenhum arquivo selecionado!", "error")
        return redirect(url_for("biblioteca.detalhe", nome=nome))

    if not _allowed_upload(uploaded.filename):
        flash("Formato de arquivo nao permitido!", "error")
        return redirect(url_for("biblioteca.detalhe", nome=nome))

    # Determine category and save
    filename = _safe_filename(uploaded.filename)
    ext = "." + filename.rsplit(".", 1)[1].lower()

    motor_dir = LIBRARY_DIR / nome

    if ext in ALLOWED_ENG_EXTENSIONS:
        # Parse .eng file
        try:
            content = uploaded.read().decode("utf-8")
            eng_data = parse_eng_from_text(content)

            # Save file
            # Avoid overwriting: append timestamp if exists
            eng_path = motor_dir / filename
            if eng_path.exists():
                from datetime import datetime

                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"{eng_path.stem}_{ts}{eng_path.suffix}"
                eng_path = motor_dir / filename

            eng_path.write_text(content, encoding="utf-8")

            # Update metadata
            from backend.parser_eng import eng_to_dict

            motor.openmotor_eng = filename
            motor.openmotor_dados = eng_to_dict(eng_data)
            save_motor_metadata(nome, motor)

            flash(
                f"Arquivo .eng carregado e dados extraidos: {eng_data.designation}",
                "success",
            )
        except Exception as exc:
            flash(f"Erro ao processar .eng: {exc}", "error")
    elif ext in ALLOWED_PHOTO_EXTENSIONS:
        # Save photo with timestamp to avoid collisions
        from datetime import datetime

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        photo_name = f"foto_{ts}{ext}"
        photo_path = motor_dir / photo_name
        uploaded.save(str(photo_path))

        register_file(nome, photo_name, "foto")
        flash("Foto adicionada com sucesso!", "success")
    else:
        flash("Formato nao suportado!", "error")

    return redirect(url_for("biblioteca.detalhe", nome=nome))


@blueprint.route("/<nome>/file/<path:filename>")
def file_download(nome: str, filename: str):
    """Serve a file from a motor's library directory for inline preview.

    Permite caminhos relativos (ex.: ``graficos/motor_forca_tempo.png``),
    limitando sempre ao diretório do motor.

    Args:
        nome: Motor name.
        filename: File to serve (pode incluir subpasta).

    Raises:
        404: If the motor or file does not exist.
    """
    nome = _safe_filename(nome)

    if get_motor(nome) is None:
        abort(404)

    motor_dir = LIBRARY_DIR / nome
    file_path = (motor_dir / filename).resolve()
    motor_root = motor_dir.resolve()
    if not str(file_path).startswith(str(motor_root)) or not file_path.is_file():
        abort(404)

    return send_from_directory(str(motor_root), filename, as_attachment=False)


@blueprint.route("/<nome>/delete", methods=["POST"])
def delete(nome: str) -> str:
    """Delete a motor entry and all its files.

    Args:
        nome: Motor name.

    Returns:
        str: Redirect to the library index.
    """
    nome = _safe_filename(nome)

    if delete_motor(nome):
        flash("Motor removido da biblioteca.", "success")
    else:
        flash("Motor nao encontrado.", "error")

    return redirect(url_for("biblioteca.index"))


@blueprint.route("/<nome>/delete_file/<path:filename>", methods=["POST"])
def delete_file(nome: str, filename: str) -> str:
    """Delete a specific file from a motor entry.

    Args:
        nome: Motor name.
        filename: File to delete (pode incluir subpasta).

    Returns:
        str: Redirect to the motor detail page.
    """
    nome = _safe_filename(nome)

    if get_motor(nome) is None:
        abort(404)

    motor_dir = LIBRARY_DIR / nome
    file_path = (motor_dir / filename).resolve()
    motor_root = motor_dir.resolve()
    if not str(file_path).startswith(str(motor_root)):
        abort(404)

    if file_path.exists():
        file_path.unlink()
        unregister_file(nome, filename)
        flash(f"Arquivo {filename} removido.", "success")
    else:
        flash("Arquivo nao encontrado.", "error")

    return redirect(url_for("biblioteca.detalhe", nome=nome))


@blueprint.route("/<nome>/update_notes", methods=["POST"])
def update_notes(nome: str):
    """Update the notes field of a motor entry (AJAX endpoint).

    Args:
        nome: Motor name.

    Returns:
        JSON: Response with success status.
    """
    nome = _safe_filename(nome)
    motor = get_motor(nome)
    if motor is None:
        return jsonify({"error": "Motor not found"}), 404

    notes = request.form.get("notes", "")
    motor.notas = notes
    save_motor_metadata(nome, motor)

    return jsonify({"success": True})


@blueprint.route("/<nome>/opcoes", methods=["POST"])
def update_opcoes(nome: str) -> str:
    """Atualiza as opções de títulos dos gráficos/PDF do motor.

    Lê os campos de formulário definidos em :data:`TITULOS_CAMPOS`, persiste
    no ``motor.json`` e regenera o relatório (PDF + PNGs avulsos) com os novos
    títulos — no mesmo formato da pasta ``relatorios`` (``graficos/``,
    ``dados/`` e ``{nome}.pdf``).

    Args:
        nome: Motor name.

    Returns:
        str: Redirect to the motor detail page.

    Raises:
        404: If the motor does not exist.
    """
    nome = _safe_filename(nome)
    motor = get_motor(nome)
    if motor is None:
        abort(404)

    titulos = {
        key: request.form.get(key, "").strip() for key, _ in TITULOS_CAMPOS
    }
    titulos = {k: v for k, v in titulos.items() if v}
    motor.graficos_titulos = titulos or None
    save_motor_metadata(nome, motor)

    try:
        from backend.analises import motor_analisys

        fonte = LIBRARY_DIR / nome / "dados" / f"{nome}_dados.csv"
        if not fonte.exists():
            flash(
                "Opções salvas, mas não há dados salvos para regenerar o relatório. "
                "Envie o teste pela página de Análises primeiro.",
                "warning",
            )
            return redirect(url_for("biblioteca.detalhe", nome=nome))

        motor_obj = motor_analisys.__new__(motor_analisys)
        motor_obj.df = _read_saved_data(fonte)
        motor_obj.df_result = None
        motor_obj.get_result()
        motor_obj.save_analisys(nome, titulos=titulos)
        flash("Opções salvas e relatório regenerado com sucesso!", "success")
    except Exception as exc:  # pylint: disable=broad-except
        flash(f"Opções salvas, mas erro ao regenerar relatório: {exc}", "warning")

    return redirect(url_for("biblioteca.detalhe", nome=nome))


def _read_saved_data(path) -> object:
    """Relê o CSV salvo pela análise, preservando as colunas de origem.

    O CSV ``{nome}_dados.csv`` é gravado pela ``save_analisys`` e mantém as
    colunas brutas ``Tempo``/``Empuxo``/``Pressao`` além das derivadas
    (``Empuxo_N`` etc.). Para não reaplicar a conversão de unidades já feita,
    reconstruímos o objeto ``motor_analisys`` diretamente com esse DataFrame.

    Args:
        path: Caminho do CSV salvo (separador ``;``).

    Returns:
        pandas.DataFrame: DataFrame com as colunas da análise.
    """
    import pandas as pd

    raw = pd.read_csv(path, sep=";")
    required = {"Tempo", "Empuxo", "Pressao"}
    if not required.issubset(raw.columns):
        raise ValueError("Arquivo de dados não contém as colunas esperadas.")
    return raw


@blueprint.route("/migrate", methods=["POST"])
def migrate() -> str:
    """Trigger migration of legacy motor_result data to the library.

    Returns:
        str: Redirect to the library index with a flash message.
    """
    try:
        migrated = migrate_legacy_motor_result(dry_run=False)
        if migrated:
            flash(
                f"Migracao concluida: {len(migrated)} motor(es) migrado(s).",
                "success",
            )
        else:
            flash("Nenhum dado legado encontrado para migrar.", "info")
    except Exception as exc:
        flash(f"Erro na migracao: {exc}", "error")

    return redirect(url_for("biblioteca.index"))
