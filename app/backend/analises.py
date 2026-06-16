"""Análise completa de motor de foguete a partir de dados de teste estático.

Este módulo fornece a classe :class:`motor_analisys`, que recebe um arquivo CSV
gerado pelo *thrust stand* (firmware ESP32 + HX711 + sensor de pressão) e
produz:

* Cálculo de impulso total (integração numérica de Simpson);
* Empuxo médio, máximo e classe do motor (padrão NAR/TRA);
* Estatísticas de pressão da câmara;
* Curvas de spline cúbica para empuxo e pressão;
* Gráfico PNG com as curvas de empuxo e pressão;
* Relatório PDF profissional (via ReportLab) com cabeçalho, tabela de
  métricas, classificação do motor e gráfico embutido.

Formato de entrada esperado (CSV com cabeçalho)::

    Tempo,Empuxo,Pressao
    0,0.001,0.0
    100,0.002,0.1
    ...

Onde:
    * ``Tempo``  -- milissegundos desde o boot do microcontrolador (int);
    * ``Empuxo`` -- leitura da célula de carga em quilogramas (float);
    * ``Pressao`` -- pressão da câmara em MPa (float).
"""

from pathlib import Path
from typing import Optional, Union

import pandas as pd
from scipy import integrate
from scipy.interpolate import CubicSpline


# Tabela de classificação NAR/TRA: (impulso máximo em N·s, designação)
_MOTOR_CLASSES = [
    (0.625, "1/4A"),
    (1.25, "1/2A"),
    (2.5, "A"),
    (5, "B"),
    (10, "C"),
    (20, "D"),
    (40, "E"),
    (80, "F"),
    (160, "G"),
    (320, "H"),
    (640, "I"),
    (1280, "J"),
    (2560, "K"),
    (5120, "L"),
    (10240, "M"),
]


def _classify_motor(total_impulse: float, avg_thrust: float, duration: float) -> str:
    """Determina a classe do motor segundo o padrão NAR/TRA.

    A classificação é baseada no impulso total: encontra o primeiro limite na
    tabela ``_MOTOR_CLASSES`` que seja superior ao impulso e retorna a
    designação correspondente concatenada com o empuxo médio e a duração.

    Args:
        total_impulse: Impulso total em N·s.
        avg_thrust: Empuxo médio em N.
        duration: Duração do teste em segundos.

    Returns:
        str: Designação da classe (ex.: ``"B4.2-3.1"``) ou ``"ERRO"`` se o
        impulso exceder a classe M.
    """
    for limit, designation in _MOTOR_CLASSES:
        if total_impulse <= limit:
            return f"{designation}{avg_thrust:.1f}-{duration:.1f}"
    return "ERRO"


class motor_analisys:  # pylint: disable=invalid-name
    """Analisa os dados de um teste estático de motor de foguete.

    O construtor lê o CSV, converte as unidades para o SI e prepara o
    DataFrame interno. Os métodos subsequentes calculam métricas, geram curvas
    de spline, produzem gráficos e relatórios PDF.

    Attributes:
        df (pandas.DataFrame): Dados carregados com colunas derivadas
            (``Empuxo_N``, ``Tempo_s``, ``Pressao_MPa``, ``Tempo_rel``).
        df_result (dict | None): Dicionário de resultados populado por
            :meth:`get_result` e usado por :meth:`pdf`.
    """

    def __init__(self, archive: Union[str, Path, "object"]) -> None:
        """Lê o CSV e gera as colunas derivadas em unidades do SI.

        Args:
            archive: Caminho do arquivo CSV ou objeto file-like (por exemplo,
                o ``werkzeug.FileStorage`` recebido em um upload Flask). Deve
                conter o cabeçalho ``Tempo,Empuxo,Pressao``.

        Side Effects:
            Popula ``self.df`` com as colunas convertidas:
                * ``Empuxo_N``   = ``Empuxo`` * 9.81     (kg -> N)
                * ``Tempo_s``    = ``Tempo`` / 1000      (ms -> s)
                * ``Pressao_MPa``= ``Pressao``           (mantida em MPa)
                * ``Tempo_rel``  = ``Tempo_s`` - primeiro valor (tempo relativo)
        """
        self.df = pd.read_csv(archive)

        # Conversão de unidades para o SI
        self.df["Empuxo_N"] = self.df["Empuxo"] * 9.81  # kg -> Newtons
        self.df["Tempo_s"] = self.df["Tempo"] / 1000.0  # ms -> segundos
        self.df["Pressao_MPa"] = self.df["Pressao"]  # já está em MPa

        # Tempo relativo ao início da aquisição
        self.df["Tempo_rel"] = self.df["Tempo_s"] - self.df["Tempo_s"].iloc[0]

        # Arredondamento para exibição
        self.df["Empuxo_N"] = self.df["Empuxo_N"].round(4)
        self.df["Tempo_rel"] = self.df["Tempo_rel"].round(4)
        self.df["Pressao_MPa"] = self.df["Pressao_MPa"].round(4)

        self.df_result: Optional[dict] = None

    def get_data(self) -> pd.DataFrame:
        """Retorna o DataFrame completo já convertido.

        Returns:
            pandas.DataFrame: Os dados carregados com as colunas derivadas.
        """
        return self.df

    def get_result(self) -> dict:
        """Calcula todas as métricas do teste estático.

        Executa a integração numérica (regra de Simpson) sobre a curva de
        empuxo para obter o impulso total, deriva o empuxo médio e máximo,
        calcula estatísticas de pressão e classifica o motor.

        Returns:
            dict: Dicionário com as seguintes chaves:
                * ``"Impulso [N*s]"``   -- impulso total (N·s);
                * ``"Empuxo max [N]"``   -- empuxo máximo (N);
                * ``"Empuxo medio [N]"`` -- empuxo médio (N);
                * ``"Pressao max [MPa]"`` -- pressão máxima (MPa);
                * ``"Pressao media [MPa]"`` -- pressão média (MPa);
                * ``"Pontos amostrais"`` -- número de amostras;
                * ``"Duracao [s]"``      -- duração do teste (s);
                * ``"Classe"``           -- classificação NAR/TRA (ex.: ``"B4.2-3.1"``).

        Side Effects:
            Armazena o resultado em ``self.df_result`` para uso posterior por
            :meth:`pdf`.
        """
        # Integração de Simpson para o impulso total
        impulso = round(
            integrate.simpson(y=self.df["Empuxo_N"], x=self.df["Tempo_rel"]), 4
        )

        empuxo_max = round(self.df["Empuxo_N"].max(), 4)
        empuxo_medio = round(
            (1 / (self.df["Tempo_rel"].iloc[-1] - self.df["Tempo_rel"].iloc[0]))
            * impulso,
            4,
        )
        pontos_amostrais = len(self.df)
        duracao = round(
            self.df["Tempo_rel"].iloc[-1] - self.df["Tempo_rel"].iloc[0], 4
        )

        # Estatísticas de pressão
        pressao_max = round(self.df["Pressao_MPa"].max(), 4)
        pressao_media = round(self.df["Pressao_MPa"].mean(), 4)

        classe_motor = _classify_motor(impulso, empuxo_medio, duracao)

        dados_result = {
            "Impulso [N*s]": impulso,
            "Empuxo max [N]": empuxo_max,
            "Empuxo medio [N]": empuxo_medio,
            "Pressao max [MPa]": pressao_max,
            "Pressao media [MPa]": pressao_media,
            "Pontos amostrais": pontos_amostrais,
            "Duracao [s]": duracao,
            "Classe": classe_motor,
        }
        self.df_result = dados_result
        return self.df_result

    def spline(self) -> CubicSpline:
        """Gera a spline cúbica da curva de empuxo.

        Returns:
            scipy.interpolate.CubicSpline: Interpolador para a curva
            ``Tempo_rel`` × ``Empuxo_N``.
        """
        x = self.df["Tempo_rel"].tolist()
        y = self.df["Empuxo_N"].tolist()
        return CubicSpline(x, y)

    def pressure_spline(self) -> CubicSpline:
        """Gera a spline cúbica da curva de pressão.

        Returns:
            scipy.interpolate.CubicSpline: Interpolador para a curva
            ``Tempo_rel`` × ``Pressao_MPa``.
        """
        x = self.df["Tempo_rel"].tolist()
        y = self.df["Pressao_MPa"].tolist()
        return CubicSpline(x, y)

    def plot_analisys(
        self, name: str, output_dir: Optional[Union[str, Path]] = None
    ) -> Path:
        """Gera o gráfico PNG com as curvas de empuxo e pressão.

        Cria uma figura com dois subplots compartilhando o eixo X (tempo):
        empuxo (superior) e pressão (inferior). Cada subplot mostra os pontos
        de amostragem e a curva de spline cúbica.

        Args:
            name: Nome do motor/teste (usado no título e no nome do arquivo).
            output_dir: Diretório de destino. Se ``None``, usa
                ``app/data/motor_result`` (criado se não existir).

        Returns:
            pathlib.Path: Caminho do arquivo PNG gerado.
        """
        import matplotlib

        matplotlib.use("Agg")  # backend sem GUI
        import matplotlib.pyplot as plt

        if output_dir is None:
            output_dir = Path(__file__).parent.parent / "data" / "motor_result"
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        _fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8), sharex=True)

        # --- Curva de empuxo ---
        ax1.scatter(
            self.df["Tempo_rel"],
            self.df["Empuxo_N"],
            label="Pontos de Amostragem",
            color="red",
            s=10,
            alpha=0.6,
        )
        curve = self.spline()
        xi = self.df["Tempo_rel"].tolist()
        ax1.plot(
            xi,
            curve(xi),
            label="Curva de Empuxo (Spline)",
            color="black",
            linewidth=1.5,
        )
        ax1.set_ylabel("Empuxo [N]", fontsize=12)
        ax1.set_title(f"Empuxo do Motor - {name}", fontsize=14)
        ax1.grid(True, alpha=0.3)
        ax1.legend()

        # --- Curva de pressão ---
        ax2.scatter(
            self.df["Tempo_rel"],
            self.df["Pressao_MPa"],
            label="Pontos de Amostragem",
            color="blue",
            s=10,
            alpha=0.6,
        )
        p_curve = self.pressure_spline()
        ax2.plot(
            xi,
            p_curve(xi),
            label="Curva de Pressão (Spline)",
            color="darkblue",
            linewidth=1.5,
        )
        ax2.set_xlabel("Tempo [s]", fontsize=12)
        ax2.set_ylabel("Pressão [MPa]", fontsize=12)
        ax2.set_title(f"Pressão da Câmara - {name}", fontsize=14)
        ax2.grid(True, alpha=0.3)
        ax2.legend()

        plt.tight_layout()
        graph_path = output_dir / f"{name}_grafico.png"
        plt.savefig(graph_path, dpi=150, bbox_inches="tight")
        plt.close()
        return graph_path

    def pdf(
        self, name: str, output_dir: Optional[Union[str, Path]] = None
    ) -> Path:
        """Gera o relatório PDF do teste estático usando ReportLab.

        O relatório inclui:
            * Cabeçalho com logos (Serra Rocketry + UERJ) e título;
            * Nome do motor e metadados (data, hora, pontos amostrais);
            * Caixa de destaque com a classificação do motor;
            * Tabela formatada com todos os parâmetros de desempenho;
            * Gráfico PNG embutido (se já gerado por :meth:`plot_analisys`);
            * Rodapé com número de página e data de geração.

        Args:
            name: Nome do motor/teste (usado no título e no nome do arquivo).
            output_dir: Diretório de destino. Se ``None``, usa
                ``app/data/motor_result`` (criado se não existir).

        Returns:
            pathlib.Path: Caminho do arquivo PDF gerado.

        Raises:
            RuntimeError: Se :meth:`get_result` não foi chamado antes e o
                resultado não puder ser calculado.
        """
        from datetime import datetime

        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER, TA_LEFT
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            HRFlowable,
            Image,
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )

        if output_dir is None:
            output_dir = Path(__file__).parent.parent / "data" / "motor_result"
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        assets_dir = Path(__file__).parent.parent / "static" / "assets"
        logo_uerj = assets_dir / "logomarca-uerj-300x300.png"
        logo_alt = assets_dir / "LOGO - ALTERNATIVA.png"

        if self.df_result is None:
            self.get_result()

        # Cores da marca
        brand_purple = colors.HexColor("#2b124c")
        brand_blue = colors.HexColor("#002196")
        light_grey = colors.HexColor("#f0f0f4")

        pdf_path = output_dir / f"{name}.pdf"

        def _header_footer(canvas, doc):
            """Desenha cabeçalho e rodapé em todas as páginas."""
            canvas.saveState()
            # Faixa do cabeçalho
            canvas.setFillColor(brand_purple)
            canvas.rect(0, A4[1] - 28 * mm, A4[0], 28 * mm, fill=1, stroke=0)
            # Logos
            if logo_uerj.exists():
                canvas.drawImage(
                    str(logo_uerj),
                    12 * mm,
                    A4[1] - 25 * mm,
                    width=20 * mm,
                    height=20 * mm,
                    mask="auto",
                    preserveAspectRatio=True,
                )
            if logo_alt.exists():
                canvas.drawImage(
                    str(logo_alt),
                    A4[0] - 42 * mm,
                    A4[1] - 24 * mm,
                    width=32 * mm,
                    height=18 * mm,
                    mask="auto",
                    preserveAspectRatio=True,
                )
            # Título no cabeçalho
            canvas.setFillColor(colors.white)
            canvas.setFont("Helvetica-Bold", 16)
            canvas.drawCentredString(
                A4[0] / 2, A4[1] - 16 * mm, "Relatório de Teste Estático"
            )
            # Faixa do rodapé
            canvas.setFillColor(brand_purple)
            canvas.rect(0, 0, A4[0], 12 * mm, fill=1, stroke=0)
            canvas.setFillColor(colors.white)
            canvas.setFont("Helvetica", 8)
            canvas.drawString(12 * mm, 4.5 * mm, "Equipe Serra Rocketry - UERJ")
            canvas.drawCentredString(
                A4[0] / 2, 4.5 * mm, datetime.now().strftime("%d/%m/%Y %H:%M")
            )
            canvas.drawRightString(
                A4[0] - 12 * mm, 4.5 * mm, f"Página {doc.page}"
            )
            canvas.restoreState()

        # Configuração do documento
        doc = SimpleDocTemplate(
            str(pdf_path),
            pagesize=A4,
            topMargin=34 * mm,
            bottomMargin=18 * mm,
            leftMargin=15 * mm,
            rightMargin=15 * mm,
            title=f"Relatório de Teste Estático - {name}",
            author="Equipe Serra Rocketry",
        )

        # Estilos customizados
        styles = getSampleStyleSheet()
        styles.add(
            ParagraphStyle(
                name="MotorName",
                parent=styles["Title"],
                fontName="Helvetica-Bold",
                fontSize=22,
                textColor=brand_blue,
                alignment=TA_CENTER,
                spaceAfter=4,
            )
        )
        styles.add(
            ParagraphStyle(
                name="SubInfo",
                parent=styles["Normal"],
                fontSize=10,
                textColor=colors.grey,
                alignment=TA_CENTER,
                spaceAfter=2,
            )
        )
        styles.add(
            ParagraphStyle(
                name="SectionTitle",
                parent=styles["Heading2"],
                fontName="Helvetica-Bold",
                fontSize=13,
                textColor=brand_purple,
                spaceBefore=10,
                spaceAfter=6,
                alignment=TA_LEFT,
            )
        )
        styles.add(
            ParagraphStyle(
                name="ClasseBig",
                parent=styles["Normal"],
                fontName="Helvetica-Bold",
                fontSize=34,
                textColor=brand_blue,
                alignment=TA_CENTER,
            )
        )

        story = []
        r = self.df_result

        # Nome do motor + metadados
        story.append(Paragraph(name, styles["MotorName"]))
        test_date = getattr(self, "test_date", None)
        test_time = getattr(self, "test_time", None)
        meta = []
        if test_date:
            meta.append(f"Data do teste: {test_date}")
        if test_time:
            meta.append(f"Horário: {test_time}")
        meta.append(f"Pontos amostrais: {r['Pontos amostrais']}")
        story.append(Paragraph("  |  ".join(meta), styles["SubInfo"]))
        story.append(Spacer(1, 4 * mm))
        story.append(HRFlowable(width="100%", thickness=1.2, color=brand_purple))
        story.append(Spacer(1, 6 * mm))

        # Caixa de classificação
        classe_table = Table(
            [
                [Paragraph("CLASSIFICAÇÃO DO MOTOR", styles["SubInfo"])],
                [Paragraph(str(r["Classe"]), styles["ClasseBig"])],
            ],
            colWidths=[180 * mm],
        )
        classe_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), light_grey),
                    ("BOX", (0, 0), (-1, -1), 1, brand_blue),
                    ("TOPPADDING", (0, 0), (-1, 0), 6),
                    ("BOTTOMPADDING", (0, 1), (-1, 1), 10),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ]
            )
        )
        story.append(classe_table)
        story.append(Spacer(1, 8 * mm))

        # Tabela de métricas
        story.append(Paragraph("Parâmetros de Desempenho", styles["SectionTitle"]))
        metrics = [
            ["Parâmetro", "Valor", "Unidade"],
            ["Impulso Total", f"{r['Impulso [N*s]']:.3f}", "N·s"],
            ["Empuxo Médio", f"{r['Empuxo medio [N]']:.3f}", "N"],
            ["Empuxo Máximo", f"{r['Empuxo max [N]']:.3f}", "N"],
            ["Pressão Média", f"{r['Pressao media [MPa]']:.3f}", "MPa"],
            ["Pressão Máxima", f"{r['Pressao max [MPa]']:.3f}", "MPa"],
            ["Tempo de Queima", f"{r['Duracao [s]']:.2f}", "s"],
            ["Pontos Amostrais", f"{r['Pontos amostrais']}", "-"],
        ]
        metrics_table = Table(metrics, colWidths=[80 * mm, 60 * mm, 40 * mm])
        metrics_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), brand_blue),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 10),
                    ("ALIGN", (1, 0), (-1, -1), "CENTER"),
                    ("ALIGN", (0, 0), (0, -1), "LEFT"),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, light_grey]),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        story.append(metrics_table)
        story.append(Spacer(1, 8 * mm))

        # Gráfico (se já gerado)
        graph_path = output_dir / f"{name}_grafico.png"
        if graph_path.exists():
            story.append(
                Paragraph("Curvas de Empuxo e Pressão", styles["SectionTitle"])
            )
            img = Image(str(graph_path), width=180 * mm, height=144 * mm)
            img.hAlign = "CENTER"
            story.append(img)

        doc.build(story, onFirstPage=_header_footer, onLaterPages=_header_footer)
        return pdf_path

    def save_analisys(self, name: str, output_dir: Optional[Union[str, Path]] = None) -> None:
        """Salva a análise completa: CSVs, gráfico PNG e relatório PDF.

        Este é o método de conveniência usado pela interface web e pelo CLI
        para persistir todos os resultados de uma análise.

        Args:
            name: Nome base para os arquivos gerados.
            output_dir: Diretório de destino. Se ``None``, usa
                ``app/data/motor_result`` (criado se não existir).

        Side Effects:
            Gera os seguintes arquivos em ``output_dir``:
                * ``{name}_resultados.csv`` -- métricas em CSV;
                * ``{name}_dados.csv``      -- dados completos em CSV;
                * ``{name}_grafico.png``    -- gráfico das curvas;
                * ``{name}.pdf``            -- relatório PDF.
        """
        if output_dir is None:
            output_dir = Path(__file__).parent.parent / "data" / "motor_result"
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        result = self.get_result()
        pd.DataFrame([result]).to_csv(
            output_dir / f"{name}_resultados.csv", sep=";", index=False
        )
        self.df.to_csv(output_dir / f"{name}_dados.csv", sep=";", index=False)
        self.plot_analisys(name, output_dir)
        self.pdf(name, output_dir)
