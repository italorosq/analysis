"""Aplicação Flask — Serra Rocketry.

Este módulo define a *app factory* :func:`create_app`, o blueprint ``page``
com todas as rotas da aplicação e o ponto de entrada :func:`main` para
execução em modo desenvolvimento.

Rotas principais:
    * ``/`` e ``/home``         -- dashboard;
    * ``/analises``              -- upload e análise de motor;
    * ``/tratamento``            -- upload e filtragem de dados brutos;
    * ``/motor_upload`` (POST)   -- processa CSV e exibe gráficos;
    * ``/save_motor`` (POST)     -- persiste análise (CSV + PNG + PDF);
    * ``/data_upload`` (POST)    -- processa CSV e exibe gráficos filtráveis;
    * ``/save_treatment`` (POST) -- persiste dados tratados;
    * ``/update_filters`` (POST) -- endpoint AJAX para filtros interativos.

Formato de dados:
    CSV com cabeçalho ``Tempo,Empuxo,Pressao`` (ms, kg, MPa).
"""

import os
from pathlib import Path

from flask import Flask, Blueprint, render_template, request, jsonify, session

from backend import motor_analisys, data_treatment

# Nome do projeto — usado como prefixo de URL no blueprint
project_name: str = "serra-rocketry"

# ---------------------------------------------------------------------------
# Diretórios de dados (criados automaticamente se não existirem)
# ---------------------------------------------------------------------------
BASE_DIR: Path = Path(__file__).parent
DATA_DIR: Path = BASE_DIR / "data"
MOTOR_RESULT_DIR: Path = DATA_DIR / "motor_result"
DATA_TREATMENT_DIR: Path = DATA_DIR / "data_treatment"

MOTOR_RESULT_DIR.mkdir(parents=True, exist_ok=True)
DATA_TREATMENT_DIR.mkdir(parents=True, exist_ok=True)

# Extensões de arquivo permitidas para upload
ALLOWED_EXTENSIONS: set[str] = {"csv", "txt"}

# Limite de upload (16 MB, sobrescritável via app.config)
_MAX_CONTENT_LENGTH: int = 16 * 1024 * 1024


def allowed_file(filename: str) -> bool:
    """Verifica se a extensão do arquivo está na lista permitida.

    Args:
        filename: Nome do arquivo enviado pelo usuário.

    Returns:
        bool: ``True`` se a extensão for ``.csv`` ou ``.txt``.
    """
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# ---------------------------------------------------------------------------
# Blueprint com todas as rotas
# ---------------------------------------------------------------------------
page = Blueprint(
    name="page",
    import_name=__name__,
    template_folder="templates",
    static_folder="static",
    static_url_path="/static",
)


# ---------------------------------------------------------------------------
# Rotas principais (páginas)
# ---------------------------------------------------------------------------


@page.route("/")
def index() -> str:
    """Renderiza o dashboard (página inicial)."""
    return render_template("index.html")


@page.route("/home")
def indexhome() -> str:
    """Alias para o dashboard."""
    return render_template("index.html")


@page.route("/analises")
def analise() -> str:
    """Renderiza a página de análise de motor (formulário de upload)."""
    return render_template("analises.html", displayopt="none")


@page.route("/tratamento")
def tratamento() -> str:
    """Renderiza a página de tratamento de dados (formulário de upload)."""
    return render_template("tratamento.html", displayopt="none")


# ---------------------------------------------------------------------------
# Tratamento de erros
# ---------------------------------------------------------------------------


@page.errorhandler(404)
def not_found(e: Exception) -> tuple:
    """Página 404 personalizada.

    Args:
        e: Exceção original (não utilizada no template).

    Returns:
        tuple: Tupla ``(html, status_code)``.
    """
    return render_template("404.html"), 404


@page.errorhandler(500)
def internal_error(e: Exception) -> tuple:
    """Página 500 personalizada.

    Args:
        e: Exceção original (não utilizada no template).

    Returns:
        tuple: Tupla ``(html, status_code)``.
    """
    return render_template("500.html"), 500


# ---------------------------------------------------------------------------
# Rotas de Análise de Motor
# ---------------------------------------------------------------------------


@page.route("/motor_upload", methods=["POST"])
def upload_motor() -> str:
    """Processa o upload de um CSV de teste estático e exibe os resultados.

    Valida a presença e a extensão do arquivo, cria uma instância de
    :class:`~backend.analises.motor_analisys`, calcula as métricas e armazena
    os dados na sessão para posterior persistência via :func:`save_motor`.

    Returns:
        str: Template ``graficos_motor.html`` com os dados do gráfico e a
        tabela de resultados, ou ``analises.html`` com mensagem de erro.
    """
    if "file" not in request.files:
        return render_template(
            "analises.html", msg="Nenhum arquivo enviado!", displayopt="block"
        )

    uploaded_file = request.files["file"]
    if uploaded_file.filename == "":
        return render_template(
            "analises.html", msg="Nenhum arquivo selecionado!", displayopt="block"
        )

    if not allowed_file(uploaded_file.filename):
        return render_template(
            "analises.html",
            msg="Formato inválido! Use .csv ou .txt",
            displayopt="block",
        )

    try:
        motor = motor_analisys(uploaded_file)
        data = motor.get_data()
        result = motor.get_result()
        # Armazena na sessão para que save_motor possa recriar o objeto
        session["motor_data"] = {
            "name": uploaded_file.filename.replace(".csv", "").replace(".txt", ""),
            "result": result,
            "df_json": data.to_json(orient="records"),
        }
        return render_template(
            "graficos_motor.html",
            x=data["Tempo_rel"].to_list(),
            y=data["Empuxo_N"].to_list(),
            result=result,
        )
    except Exception as exc:  # pylint: disable=broad-except
        return render_template(
            "analises.html",
            msg=f"Erro ao processar arquivo: {str(exc)}",
            displayopt="block",
        )


@page.route("/save_motor", methods=["POST"])
def save_motor() -> str:
    """Persiste a análise de motor na sessão (CSV + gráfico + PDF).

    Recria o objeto :class:`~backend.analises.motor_analisys` a partir dos
    dados serializados na sessão e chama
    :meth:`~backend.analises.motor_analisys.save_analisys`.

    Returns:
        str: Template ``analises.html`` com mensagem de sucesso ou erro.
    """
    name = request.form.get("name", "").strip()
    if not name:
        return render_template(
            "analises.html", msg="Nome do motor não informado!", displayopt="block"
        )

    if "motor_data" not in session:
        return render_template(
            "analises.html", msg="Nenhuma análise para salvar!", displayopt="block"
        )

    try:
        import pandas as pd  # import lazy para reduzir tempo de cold start

        motor = motor_analisys.__new__(motor_analisys)
        motor.df = pd.read_json(session["motor_data"]["df_json"], orient="records")
        motor.df_result = session["motor_data"]["result"]
        motor.save_analisys(name)
        session.pop("motor_data", None)
        return render_template(
            "analises.html", msg="Análise salva com sucesso!", displayopt="block"
        )
    except Exception as exc:  # pylint: disable=broad-except
        return render_template(
            "analises.html", msg=f"Erro ao salvar: {str(exc)}", displayopt="block"
        )


# ---------------------------------------------------------------------------
# Rotas de Tratamento de Dados
# ---------------------------------------------------------------------------


@page.route("/data_upload", methods=["POST"])
def upload_data() -> str:
    """Processa o upload de um CSV bruto e exibe os gráficos filtráveis.

    Valida o arquivo, cria uma instância de
    :class:`~backend.tratamento.data_treatment`, calcula os limites iniciais
    dos sliders (tempo e empuxo) e aplica o filtro padrão (threshold = média
    do empuxo). Armazena os dados na sessão para uso por
    :func:`update_filters` e :func:`save_treatment`.

    Returns:
        str: Template ``graficos_tratamento.html`` com gráficos e controles,
        ou ``tratamento.html`` com mensagem de erro.
    """
    if "file" not in request.files:
        return render_template(
            "tratamento.html", msg="Nenhum arquivo enviado!", displayopt="block"
        )

    uploaded_file = request.files["file"]
    if uploaded_file.filename == "":
        return render_template(
            "tratamento.html", msg="Nenhum arquivo selecionado!", displayopt="block"
        )

    if not allowed_file(uploaded_file.filename):
        return render_template(
            "tratamento.html",
            msg="Formato inválido! Use .csv ou .txt",
            displayopt="block",
        )

    try:
        data = data_treatment(uploaded_file)
        data_raw = data.get_data()
        time_slider_min = float(data_raw["Tempo_rel"].min())
        time_slider_max = float(data_raw["Tempo_rel"].max())
        force_slider_min = float(data_raw["Empuxo_N"].min())
        force_slider_max = float(data_raw["Empuxo_N"].max())
        pressure_slider_min = float(data_raw["Pressao_MPa"].min())
        pressure_slider_max = float(data_raw["Pressao_MPa"].max())

        table_info = data.get_stats()
        threshold = round(data_raw["Empuxo_N"].mean(), 3)
        data_filtered = data.data_filter(threshold, [time_slider_min, time_slider_max])

        # Armazena na sessão para update_filters e save_treatment
        session["treatment_data"] = {
            "filename": uploaded_file.filename,
            "df_json": data_raw.to_json(orient="records"),
        }

        return render_template(
            "graficos_tratamento.html",
            x=data_filtered["Tempo_rel"].to_list(),
            y=data_filtered["Empuxo_N"].to_list(),
            y_pressure=data_filtered["Pressao_MPa"].to_list(),
            result=table_info,
            fmin=force_slider_min,
            fmax=force_slider_max,
            pmin=pressure_slider_min,
            pmax=pressure_slider_max,
            threshold=threshold,
            tmin=time_slider_min,
            tmax=time_slider_max,
        )
    except Exception as exc:  # pylint: disable=broad-except
        return render_template(
            "tratamento.html",
            msg=f"Erro ao processar arquivo: {str(exc)}",
            displayopt="block",
        )


@page.route("/save_treatment", methods=["POST"])
def save_treatment() -> str:
    """Persiste os dados tratados (CSV) a partir da sessão.

    Returns:
        str: Template ``tratamento.html`` com mensagem de sucesso ou erro.
    """
    name = request.form.get("name", "").strip()
    if not name:
        return render_template(
            "tratamento.html", msg="Nome do arquivo não informado!", displayopt="block"
        )

    if "treatment_data" not in session:
        return render_template(
            "tratamento.html", msg="Nenhum tratamento para salvar!", displayopt="block"
        )

    try:
        import pandas as pd  # import lazy

        data = data_treatment.__new__(data_treatment)
        data.data = pd.read_json(session["treatment_data"]["df_json"], orient="records")
        saved_path = data.save_treatment(name)
        session.pop("treatment_data", None)
        return render_template(
            "tratamento.html",
            msg=f"Tratamento salvo em: {saved_path}",
            displayopt="block",
        )
    except Exception as exc:  # pylint: disable=broad-except
        return render_template(
            "tratamento.html", msg=f"Erro ao salvar: {str(exc)}", displayopt="block"
        )


# ---------------------------------------------------------------------------
# Endpoint AJAX para filtros interativos
# ---------------------------------------------------------------------------


@page.route("/update_filters", methods=["POST"])
def update_filters() -> tuple:
    """Atualiza os dados filtrados via AJAX (chamado pelos sliders no frontend).

    Lê ``threshold``, ``tmin`` e ``tmax`` do formulário, recria o objeto
    :class:`~backend.tratamento.data_treatment` a partir da sessão e retorna
    JSON com os novos pontos de empuxo, pressão e estatísticas.

    Returns:
        tuple: ``(jsonify(dados), 200)`` em sucesso ou
        ``(jsonify({"error": msg}), 400/500)`` em erro.
    """
    if "treatment_data" not in session:
        return jsonify({"error": "No data loaded"}), 400

    try:
        threshold = float(request.form["threshold"])
        tmin = float(request.form["tmin"])
        tmax = float(request.form["tmax"])

        import pandas as pd  # import lazy

        data = data_treatment.__new__(data_treatment)
        data.data = pd.read_json(session["treatment_data"]["df_json"], orient="records")

        data_filtered = data.data_filter(threshold, [tmin, tmax])
        table_info = data.get_stats()

        return jsonify(
            {
                "x": data_filtered["Tempo_rel"].to_list(),
                "y": data_filtered["Empuxo_N"].to_list(),
                "y_pressure": data_filtered["Pressao_MPa"].to_list(),
                "result": table_info,
            }
        )
    except Exception as exc:  # pylint: disable=broad-except
        return jsonify({"error": str(exc)}), 500


# ---------------------------------------------------------------------------
# App Factory
# ---------------------------------------------------------------------------


def create_app() -> Flask:
    """Cria e configura a aplicação Flask (padrão *application factory*).

    Configura a chave secreta (via variável de ambiente ``SECRET_KEY`` ou
    valor padrão para desenvolvimento), o limite de upload e registra o
    blueprint :data:`page` com o prefixo ``/serra-rocketry``.

    Returns:
        Flask: Instância da aplicação pronta para uso.
    """
    app = Flask(__name__)
    app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-in-production")
    app.config["MAX_CONTENT_LENGTH"] = _MAX_CONTENT_LENGTH
    app.register_blueprint(page, url_prefix=f"/{project_name}")
    return app


# Instância global (usada por wsgi.py e pelo modo debug)
app = create_app()


# ---------------------------------------------------------------------------
# Ponto de entrada para desenvolvimento
# ---------------------------------------------------------------------------


def main() -> None:
    """Inicia o servidor Flask em modo debug com reload automático.

    Observa mudanças em templates, CSS e JS para recarregar a aplicação
    automaticamente durante o desenvolvimento.
    """
    host = "0.0.0.0"
    port = 5000
    extra_files: list[str] = []

    print("")
    print("* Watched:")
    for path in ["./templates", "./static/css", "./static/js"]:
        full_path = BASE_DIR / path.lstrip("./")
        if full_path.exists():
            for file in full_path.iterdir():
                print(f"\t{path}/{file.name}")
                extra_files.append(f"{path}/{file.name}")
    print("")

    app.run(
        host=host,
        port=port,
        debug=True,
        extra_files=extra_files,
    )


if __name__ == "__main__":
    main()
