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

# Títulos padrão dos gráficos e do relatório. Podem ser sobrescritos por motor
# (armazenados em ``motor.json`` -> ``graficos_titulos``) ou via parâmetro
# ``titulos`` nos métodos de plotagem/PDF.
DEFAULT_TITULOS = {
    "pdf_titulo": "Static Test Report",
    "secao_combinado": "Thrust and Pressure Curves",
    "secao_forca": "Force × Time",
    "secao_impulso": "Cumulative Impulse × Time",
    "secao_spline": "Smoothed Spline Curve",
    "grafico_forca": "Force × Time",
    "grafico_impulso": "Cumulative Impulse × Time",
    "grafico_spline": "Smoothed Spline Curve",
    "grafico_empuxo": "Motor Thrust",
    "grafico_pressao": "Chamber Pressure",
    "rotulo_tempo": "Time [s]",
    "rotulo_empuxo": "Thrust [N]",
    "rotulo_pressao": "Pressure [MPa]",
    "rotulo_impulso": "Impulse [N·s]",
}

# Ordem exibida no formulário da biblioteca (chave -> rótulo em pt-BR).
TITULOS_CAMPOS = [
    ("pdf_titulo", "Título do relatório (cabeçalho do PDF)"),
    ("secao_combinado", "Seção: Curvas de Empuxo e Pressão"),
    ("secao_forca", "Seção: Força × Tempo"),
    ("secao_impulso", "Seção: Impulso × Tempo"),
    ("secao_spline", "Seção: Spline"),
    ("grafico_forca", "Título do gráfico Força × Tempo"),
    ("grafico_impulso", "Título do gráfico Impulso × Tempo"),
    ("grafico_spline", "Título do gráfico Spline"),
    ("grafico_empuxo", "Título do subplot de empuxo"),
    ("grafico_pressao", "Título do subplot de pressão"),
    ("rotulo_tempo", "Rótulo do eixo X (tempo)"),
    ("rotulo_empuxo", "Rótulo do eixo Y (empuxo)"),
    ("rotulo_pressao", "Rótulo do eixo Y (pressão)"),
    ("rotulo_impulso", "Rótulo do eixo Y (impulso)"),
]


def merge_titulos(titulos: Optional[dict]) -> dict:
    """Mescla títulos customizados sobre os padrão, ignorando vazios.

    Args:
        titulos: Dicionário com chaves de :data:`DEFAULT_TITULOS`.

    Returns:
        dict: Títulos resolvidos (padrão + customizados).
    """
    base = dict(DEFAULT_TITULOS)
    if titulos:
        base.update({k: v for k, v in titulos.items() if v is not None and str(v).strip()})
    return base

import numpy as np
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

    def __init__(
        self, archive: Union[str, Path, "object"], units: str = "kg"
    ) -> None:
        """Lê o CSV e gera as colunas derivadas em unidades do SI.

        Args:
            archive: Caminho do arquivo CSV ou objeto file-like (por exemplo,
                o ``werkzeug.FileStorage`` recebido em um upload Flask). Deve
                conter o cabeçalho ``Tempo,Empuxo,Pressao``.
            units: Unidade de medida do empuxo. ``'kg'`` (padrão) ou ``'g'``
                (gramas). Quando ``'g'``, os valores são divididos por 1000
                antes da conversão para Newtons.

        Side Effects:
            Popula ``self.df`` com as colunas convertidas:
                * ``Empuxo_N``   = ``Empuxo`` * 9.81     (kg -> N)
                * ``Tempo_s``    = ``Tempo`` / 1000      (ms -> s)
                * ``Pressao_MPa``= ``Pressao``           (mantida em MPa)
                * ``Tempo_rel``  = ``Tempo_s`` - primeiro valor (tempo relativo)
        """
        self.df = pd.read_csv(archive)

        # Conversão de unidades para o SI
        empuxo_kg = self.df["Empuxo"]
        if units == "g":
            empuxo_kg = empuxo_kg / 1000.0  # gramas -> quilogramas
        self.df["Empuxo_N"] = empuxo_kg * 9.81  # kg -> Newtons
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

    def remove_outliers(
        self, method: str = "hampel", threshold: float = 8.0
    ) -> int:
        """Remove outliers (spikes isolados) preservando dados reais da queima.

        Por padrão usa o filtro **Hampel** (mediana rolante + MAD), que remove
        apenas picos isolados de leitura — artefatos do sensor que se desviam
        muito da vizinhança local — sem tocar em platôs sustentados da queima.
        O filtro é robusto à escala (funciona igual para kg ou g).

        O método antigo ``'percentile'`` (P99 * fator) continua disponível como
        alternativa compatível.

        Args:
            method: Método de detecção — ``'hampel'`` (padrão) ou
                ``'percentile'``.
            threshold: Parâmetro do filtro: para ``'hampel'``, múltiplo do MAD
                local; para ``'percentile'``, fator multiplicativo sobre o P99.
                Padrão: 8.0.

        Returns:
            int: Número de outliers removidos.
        """
        from backend.tratamento import _clean_signal_mask

        n_before = len(self.df)

        if method == "percentile":
            p99 = self.df["Empuxo_N"].quantile(0.99)
            upper = p99 * threshold
            keep = self.df["Empuxo_N"] <= upper
        else:
            keep = _clean_signal_mask(self.df["Empuxo_N"], window=5, n_sigma=threshold)

        self.df = self.df[keep].copy()
        self.df.reset_index(drop=True, inplace=True)
        # Recalcula tempo relativo após reset do índice
        self.df["Tempo_rel"] = self.df["Tempo_s"] - self.df["Tempo_s"].iloc[0]
        self.df["Tempo_rel"] = self.df["Tempo_rel"].round(4)
        return n_before - len(self.df)

    def get_result(self) -> dict:
        """Calcula todas as métricas do teste estático.

        As métricas são calculadas sobre a **janela ativa da queima** (recorte
        robusto a spikes via :func:`~backend.tratamento.active_motor_window`),
        de modo que o impulso, a duração e o empuxo médio reflitam apenas o
        período de queima real — e não o tempo de gravação pré/pós-teste. O
        DataFrame persistido (``self.df``) não é alterado, mantendo
        compatibilidade com os testes.

        Returns:
            dict: Dicionário com as seguintes chaves:
                * ``"Impulso [N*s]"``   -- impulso total da queima (N·s);
                * ``"Empuxo max [N]"``   -- empuxo máximo (N);
                * ``"Empuxo medio [N]"`` -- empuxo médio durante a queima (N);
                * ``"Pressao max [MPa]"`` -- pressão máxima (MPa);
                * ``"Pressao media [MPa]"`` -- pressão média (MPa);
                * ``"Pontos amostrais"`` -- número de amostras da janela;
                * ``"Duracao [s]"``      -- duração da queima (s);
                * ``"Classe"``           -- classificação NAR/TRA (ex.: ``"B4.2-3.1"``).

        Side Effects:
            Armazena o resultado em ``self.df_result`` para uso posterior por
            :meth:`pdf`.
        """
        from backend.tratamento import active_motor_window

        janela = active_motor_window(self.df)
        if janela.empty or len(janela) < 4:
            janela = self.df

        # Integração de Simpson para o impulso total (sobre a janela de queima)
        impulso = float(
            round(integrate.simpson(y=janela["Empuxo_N"], x=janela["Tempo_rel"]), 4)
        )

        empuxo_max = float(round(janela["Empuxo_N"].max(), 4))
        empuxo_medio = float(
            round(
                (1 / (janela["Tempo_rel"].iloc[-1] - janela["Tempo_rel"].iloc[0]))
                * impulso,
                4,
            )
        )
        pontos_amostrais = len(janela)
        duracao = float(
            round(janela["Tempo_rel"].iloc[-1] - janela["Tempo_rel"].iloc[0], 4)
        )

        # Estatísticas de pressão (sobre a janela de queima)
        pressao_max = float(round(janela["Pressao_MPa"].max(), 4))
        pressao_media = float(round(janela["Pressao_MPa"].mean(), 4))

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

    def _burn_window(self) -> pd.DataFrame:
        """Retorna o DataFrame recortado na janela ativa da queima.

        Usa o recorte robusto :func:`~backend.tratamento.active_motor_window`,
        que preserva os dados reais de queima mesmo com spikes de saturação.

        Returns:
            pandas.DataFrame: Dados restritos à janela ativa.
        """
        from backend.tratamento import active_motor_window

        return active_motor_window(self.df)

    @staticmethod
    def _smooth(values, window: int = 11) -> np.ndarray:
        """Suaviza uma série 1-D com média móvel centrada (preserva extremidades).

        Args:
            values: Array 1-D numérico.
            window: Tamanho da janela (ímpar). Padrão: 11.

        Returns:
            np.ndarray: Série suavizada.
        """
        if len(values) < window:
            return np.asarray(values, dtype=float)
        w = max(3, int(window) | 1)  # garante ímpar >= 3
        pad = w // 2
        padded = np.concatenate(
            [np.full(pad, values[0]), values, np.full(pad, values[-1])]
        )
        kernel = np.ones(w) / w
        return np.convolve(padded, kernel, mode="valid")

    @staticmethod
    def _zoom_xlim(t, f, frac=0.02, pad=0.15):
        """Calcula limites do eixo X para dar zoom na curva real de queima.

        Em vez de mostrar toda a janela (que pode incluir longa cauda de ruído
        após a queima), recorta o eixo X para a região onde o empuxo é
        significativo (>= ``frac`` do pico), com uma pequena margem
        (``pad`` segundos) de cada lado.

        Args:
            t: Array de tempos (Tempo_rel).
            f: Array de valores de empuxo.
            frac: Fração do pico usada como piso (ex.: 0.02 = 2%).
            pad: Margem em segundos adicionada de cada lado.

        Returns:
            tuple: ``(xmin, xmax)`` para ``ax.set_xlim()``.
        """
        if len(f) == 0:
            return (float(t[0]), float(t[-1]))
        peak = float(np.max(f))
        if peak <= 0:
            return (float(t[0]), float(t[-1]))
        thr = peak * frac
        above = np.where(f >= thr)[0]
        if len(above) == 0:
            return (float(t[0]), float(t[-1]))
        x0 = float(t[above[0]]) - pad
        x1 = float(t[above[-1]]) + pad
        x0 = max(float(t[0]), x0)
        x1 = min(float(t[-1]), x1)
        # garante um mínimo de 1 segundo de largura
        if x1 - x0 < 1.0:
            mid = 0.5 * (x0 + x1)
            x0 = max(float(t[0]), mid - 0.5)
            x1 = min(float(t[-1]), mid + 0.5)
        return (x0, x1)

    def _figure_style(
        self, ax, xlabel="Tempo [s]", ylabel="Empuxo [N]", title=None
    ):
        """Aplica o estilo padrão dos gráficos da análise.

        Args:
            ax: Eixo matplotlib.
            xlabel: Rótulo do eixo X.
            ylabel: Rótulo do eixo Y.
            title: Título opcional do subplot.
        """
        if title:
            ax.set_title(title, fontsize=13, fontweight="bold", pad=10)
        ax.set_xlabel(xlabel, fontsize=11, fontweight="bold")
        ax.set_ylabel(ylabel, fontsize=11, fontweight="bold")
        ax.grid(True, alpha=0.4, linestyle="--", linewidth=0.5)
        ax.set_facecolor("#fafbfd")
        ax.tick_params(labelsize=10)

    def plot_analisys(
        self, name: str, output_dir: Optional[Union[str, Path]] = None,
        titulos: Optional[dict] = None,
    ) -> Path:
        """Gera o gráfico PNG com as curvas de empuxo e pressão.

        Cria uma figura com dois subplots compartilhando o eixo X (tempo):
        empuxo (superior) e pressão (inferior). Os dados são recortados na
        janela ativa da queima (recorte robusto a spikes) para que a curva
        represente apenas o intervalo de interesse. O pico de empuxo é
        anotado no gráfico.

        Args:
            name: Nome do motor/teste (usado no título e no nome do arquivo).
            output_dir: Diretório de destino. Se ``None``, usa
                ``app/data/motor_result`` (criado se não existir).
            titulos: Títulos customizados (chaves de
                :data:`DEFAULT_TITULOS`).

        Returns:
            pathlib.Path: Caminho do arquivo PNG gerado.
        """
        import matplotlib

        matplotlib.use("Agg")  # backend sem GUI
        import matplotlib.pyplot as plt

        titulos = merge_titulos(titulos)

        if output_dir is None:
            output_dir = Path(__file__).parent.parent / "data" / "motor_result"
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        window = self._burn_window()
        if window.empty:
            window = self.df

        t = window["Tempo_rel"].to_numpy(dtype=float)
        f_raw = window["Empuxo_N"].to_numpy(dtype=float)
        f_smooth = self._smooth(f_raw, window=11)
        p_raw = window["Pressao_MPa"].to_numpy(dtype=float)
        p_smooth = self._smooth(p_raw, window=11)

        _fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8), sharex=True)

        # --- Curva de empuxo ---
        ax1.plot(
            t, f_raw,
            color="#a0a8c0", linewidth=0.6, alpha=0.7, label="Bruto",
            zorder=1,
        )
        ax1.plot(
            t, f_smooth,
            color="#002196", linewidth=2.2, label="Suavizado", zorder=2,
        )
        peak_idx = int(np.argmax(f_smooth))
        peak_t, peak_f = t[peak_idx], f_smooth[peak_idx]
        ax1.plot(peak_t, peak_f, "o", color="#e63946", markersize=8, zorder=3)
        ax1.annotate(
            f"Pico: {peak_f:.1f} N\n@ {peak_t:.2f} s",
            xy=(peak_t, peak_f),
            xytext=(peak_t + max(t) * 0.05, peak_f * 0.80),
            arrowprops=dict(arrowstyle="->", color="#2b124c", lw=1.5),
            fontsize=9, color="#2b124c", fontweight="bold",
        )
        self._figure_style(
            ax1, ylabel=titulos["rotulo_empuxo"],
            title=f"{titulos['grafico_empuxo']} — {name}",
        )
        ax1.legend(loc="upper right", fontsize=9, framealpha=0.9)
        ax1.set_ylim(bottom=min(0, f_smooth.min() * 1.1))

        # --- Curva de pressão ---
        ax2.plot(
            t, p_raw,
            color="#a0a8c0", linewidth=0.6, alpha=0.7, label="Bruto", zorder=1,
        )
        ax2.plot(
            t, p_smooth,
            color="#0064C8", linewidth=2.2, label="Suavizado", zorder=2,
        )
        self._figure_style(
            ax2, xlabel=titulos["rotulo_tempo"], ylabel=titulos["rotulo_pressao"],
            title=f"{titulos['grafico_pressao']} — {name}",
        )
        ax2.legend(loc="upper right", fontsize=9, framealpha=0.9)

        # Zoom na região de queima (corta cauda de ruído que achata a curva)
        xlim = self._zoom_xlim(t, f_smooth)
        ax2.set_xlim(*xlim)

        plt.tight_layout(pad=1.5)
        graph_path = output_dir / f"{name}_grafico.png"
        plt.savefig(graph_path, dpi=150, bbox_inches="tight", facecolor="white")
        plt.close()
        return graph_path

    def plot_force_time(
        self, name: str, output_dir: Optional[Union[str, Path]] = None,
        titulos: Optional[dict] = None,
    ) -> Path:
        """Gera o gráfico avulso Força × Tempo (empuxo em Newtons).

        O gráfico mostra a curva de empuxo sobre a janela ativa da queima,
        destacando o pico e a área integrada (impulso) com preenchimento.

        Args:
            name: Nome do motor/teste (usado no título e no nome do arquivo).
            output_dir: Diretório de destino. Se ``None``, usa
                ``app/data/motor_result`` (criado se não existir).
            titulos: Títulos customizados (chaves de
                :data:`DEFAULT_TITULOS`).

        Returns:
            pathlib.Path: Caminho do arquivo PNG gerado.
        """
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        titulos = merge_titulos(titulos)

        if output_dir is None:
            output_dir = Path(__file__).parent.parent / "data" / "motor_result"
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        window = self._burn_window()
        if window.empty:
            window = self.df

        t = window["Tempo_rel"].to_numpy(dtype=float)
        f_raw = window["Empuxo_N"].to_numpy(dtype=float)
        f_smooth = np.maximum(self._smooth(f_raw, window=11), 0.0)

        _fig, ax = plt.subplots(figsize=(10, 6))
        ax.fill_between(
            t, f_smooth, color="#002196", alpha=0.18, label="Impulso (área)",
            zorder=1,
        )
        ax.plot(
            t, f_raw, color="#a0a8c0", linewidth=0.6, alpha=0.7,
            label="Bruto", zorder=2,
        )
        ax.plot(
            t, f_smooth, color="#002196", linewidth=2.4, label="Suavizado", zorder=3,
        )
        peak_idx = int(np.argmax(f_smooth))
        peak_t, peak_f = t[peak_idx], f_smooth[peak_idx]
        ax.plot(peak_t, peak_f, "o", color="#e63946", markersize=9, zorder=4)
        ax.axvline(peak_t, color="#2b124c", linestyle="--", alpha=0.6, zorder=2)
        ax.annotate(
            f"Pico: {peak_f:.1f} N @ {peak_t:.2f} s",
            xy=(peak_t, peak_f),
            xytext=(peak_t + max(t) * 0.04, peak_f * 0.80),
            arrowprops=dict(arrowstyle="->", color="#2b124c", lw=1.5),
            fontsize=10, color="#2b124c", fontweight="bold",
        )
        self._figure_style(
            ax, xlabel=titulos["rotulo_tempo"], ylabel=titulos["rotulo_empuxo"],
            title=f"{titulos['grafico_forca']} — {name}",
        )
        ax.legend(loc="upper right", fontsize=9, framealpha=0.9)
        ax.set_ylim(bottom=min(0, f_smooth.min() * 1.1))
        ax.set_xlim(*self._zoom_xlim(t, f_smooth))

        plt.tight_layout(pad=1.5)
        path = output_dir / f"{name}_forca_tempo.png"
        plt.savefig(path, dpi=150, bbox_inches="tight", facecolor="white")
        plt.close()
        return path

    def plot_impulse_time(
        self, name: str, output_dir: Optional[Union[str, Path]] = None,
        titulos: Optional[dict] = None,
    ) -> Path:
        """Gera o gráfico avulso Impulso acumulado × Tempo (N·s).

        Integra numericamente a curva de empuxo sobre a janela ativa da
        queima, produzindo a curva de impulso acumulado. O impulso total é
        anotado no gráfico.

        Args:
            name: Nome do motor/teste (usado no título e no nome do arquivo).
            output_dir: Diretório de destino. Se ``None``, usa
                ``app/data/motor_result`` (criado se não existir).
            titulos: Títulos customizados (chaves de
                :data:`DEFAULT_TITULOS`).

        Returns:
            pathlib.Path: Caminho do arquivo PNG gerado.
        """
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        titulos = merge_titulos(titulos)

        if output_dir is None:
            output_dir = Path(__file__).parent.parent / "data" / "motor_result"
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        window = self._burn_window()
        if window.empty:
            window = self.df

        t = window["Tempo_rel"].to_numpy(dtype=float)
        f_raw = window["Empuxo_N"].to_numpy(dtype=float)
        # usa curva suavizada para integrar — impulso mais estável
        f = np.maximum(self._smooth(f_raw, window=11), 0.0)
        impulse = np.cumsum(0.5 * (f[:-1] + f[1:]) * np.diff(t))
        t_mid = 0.5 * (t[:-1] + t[1:])
        total = float(impulse[-1]) if len(impulse) > 0 else 0.0

        _fig, ax = plt.subplots(figsize=(10, 6))
        if len(impulse) > 0:
            ax.fill_between(t_mid, impulse, color="#e07b00", alpha=0.2)
            ax.plot(
                t_mid, impulse, color="#e07b00", linewidth=2.6,
                label="Impulso acumulado (N·s)",
            )
            ax.plot(
                t_mid[-1], impulse[-1], "o", color="#e63946", markersize=9,
            )
            ax.annotate(
                f"Impulso total: {total:.2f} N·s",
                xy=(t_mid[-1], impulse[-1]),
                xytext=(t_mid[-1] * 0.45, impulse[-1] * 0.55),
                arrowprops=dict(arrowstyle="->", color="#2b124c", lw=1.5),
                fontsize=11, color="#2b124c", fontweight="bold",
            )
        self._figure_style(
            ax, xlabel=titulos["rotulo_tempo"], ylabel=titulos["rotulo_impulso"],
            title=f"{titulos['grafico_impulso']} — {name}",
        )
        ax.legend(loc="lower right", fontsize=9, framealpha=0.9)
        ax.set_xlim(*self._zoom_xlim(t_mid, impulse, frac=0.01))

        plt.tight_layout(pad=1.5)
        path = output_dir / f"{name}_impulso_tempo.png"
        plt.savefig(path, dpi=150, bbox_inches="tight", facecolor="white")
        plt.close()
        return path
    def plot_spline(
        self, name: str, output_dir: Optional[Union[str, Path]] = None,
        titulos: Optional[dict] = None,
    ) -> Path:
        """Gera o gráfico avulso da curva spline/suavizada de empuxo.

        Sobre os pontos brutos da janela ativa, plota a spline cúbica
        suavizada da curva de empuxo.

        Args:
            name: Nome do motor/teste (usado no título e no nome do arquivo).
            output_dir: Diretório de destino. Se ``None``, usa
                ``app/data/motor_result`` (criado se não existir).
            titulos: Títulos customizados (chaves de
                :data:`DEFAULT_TITULOS`).

        Returns:
            pathlib.Path: Caminho do arquivo PNG gerado.
        """
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        titulos = merge_titulos(titulos)

        if output_dir is None:
            output_dir = Path(__file__).parent.parent / "data" / "motor_result"
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        window = self._burn_window()
        if window.empty or len(window) < 4:
            window = self.df
        if len(window) < 4:
            raise ValueError("Dados insuficientes para gerar a spline.")

        xi = window["Tempo_rel"].to_numpy(dtype=float)
        yi = window["Empuxo_N"].to_numpy(dtype=float)
        yi_smooth = self._smooth(yi, window=11)

        # Spline sobre os dados SUAVIZADOS (spline sobre pontos ruidosos oscila).
        curve = self.spline_curve(xi, yi_smooth)

        xs = np.linspace(xi.min(), xi.max(), 400)
        _fig, ax = plt.subplots(figsize=(10, 6))
        # Pontos brutos: decima se há muitos, para não poluir.
        if len(xi) > 600:
            step = max(1, len(xi) // 300)
            ax.scatter(
                xi[::step], yi[::step], color="#a0a8c0", s=12, alpha=0.5,
                label="Pontos brutos (decimados)",
            )
        else:
            ax.scatter(
                xi, yi, color="#b0b0b0", s=14, alpha=0.5, label="Pontos brutos",
            )
        # Curva suavizada (média móvel) — guia visual
        ax.plot(
            xi, yi_smooth, color="#8ecae6", linewidth=1.0, alpha=0.8,
            label="Média móvel",
        )
        # Spline sobre a suavizada — curva principal
        ax.plot(
            xs, curve(xs), color="#d62728", linewidth=2.6,
            label="Spline cúbica (suavizada)",
        )
        # Marca o pico da spline
        peak_idx = int(np.argmax(curve(xs)))
        ax.plot(
            xs[peak_idx], curve(xs)[peak_idx], "o", color="#e63946",
            markersize=8,
        )
        self._figure_style(
            ax, xlabel=titulos["rotulo_tempo"], ylabel=titulos["rotulo_empuxo"],
            title=f"{titulos['grafico_spline']} — {name}",
        )
        ax.legend(loc="upper right", fontsize=9, framealpha=0.9)
        ax.set_xlim(*self._zoom_xlim(xi, yi_smooth, frac=0.02))

        plt.tight_layout(pad=1.5)
        path = output_dir / f"{name}_spline.png"
        plt.savefig(path, dpi=150, bbox_inches="tight", facecolor="white")
        plt.close()
        return path

    def spline_curve(self, xi, yi) -> CubicSpline:
        """Gera a spline cúbica para coordenadas arbitrárias.

        Args:
            xi: Coordenadas X (tempo).
            yi: Coordenadas Y (empuxo).

        Returns:
            scipy.interpolate.CubicSpline: Interpolador da curva.
        """
        return CubicSpline(xi, yi)

    def pdf(
        self, name: str, output_dir: Optional[Union[str, Path]] = None,
        graficos_dir: Optional[Union[str, Path]] = None,
        titulos: Optional[dict] = None,
    ) -> Path:
        """Gera o relatório PDF do teste estático usando ReportLab.

        O relatório inclui:
            * Cabeçalho com logos (Serra Rocketry + UERJ) e título;
            * Nome do motor e metadados (data, hora, pontos amostrais);
            * Caixa de destaque com a classificação do motor;
            * Tabela formatada com todos os parâmetros de desempenho;
            * Gráficos PNG embutidos (combinado, Força × Tempo, Impulso,
              Spline);
            * Rodapé com número de página e data de geração.

        Args:
            name: Nome do motor/teste (usado no título e no nome do arquivo).
            output_dir: Diretório base para o PDF. Se ``None``, usa
                ``app/data/motor_result`` (criado se não existir).
            graficos_dir: Diretório onde buscar/gerar os PNGs dos gráficos.
                Se ``None``, usa ``output_dir``. Se forem organizados em
                subpastas (ex.: ``graficos/``), informe o caminho correto.
            titulos: Títulos customizados (chaves de
                :data:`DEFAULT_TITULOS`).

        Returns:
            pathlib.Path: Caminho do arquivo PDF gerado.

        Raises:
            RuntimeError: Se :meth:`get_result` não foi chamado antes e o
                resultado não puder ser calculado.
        """
        titulos = merge_titulos(titulos)
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
                A4[0] / 2, A4[1] - 16 * mm, titulos["pdf_titulo"]
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
            title=f"{titulos['pdf_titulo']} - {name}",
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

        # Gráficos (gerados sob demanda se ainda não existirem)
        gdir = Path(graficos_dir) if graficos_dir else output_dir
        graph_path = gdir / f"{name}_grafico.png"
        if not graph_path.exists():
            self.plot_analisys(name, gdir)
        force_path = gdir / f"{name}_forca_tempo.png"
        if not force_path.exists():
            self.plot_force_time(name, gdir)
        impulse_path = gdir / f"{name}_impulso_tempo.png"
        if not impulse_path.exists():
            self.plot_impulse_time(name, gdir)
        spline_path = gdir / f"{name}_spline.png"
        if not spline_path.exists():
            self.plot_spline(name, gdir)

        def _add_chart(title: str, path: Path) -> None:
            """Adiciona uma seção com gráfico ao relatório."""
            story.append(Paragraph(title, styles["SectionTitle"]))
            img = Image(str(path), width=180 * mm, height=120 * mm)
            img.hAlign = "CENTER"
            story.append(img)
            story.append(Spacer(1, 4 * mm))

        _add_chart(f"{titulos['secao_combinado']}", graph_path)
        _add_chart(f"{titulos['secao_forca']}", force_path)
        _add_chart(f"{titulos['secao_impulso']}", impulse_path)
        _add_chart(f"{titulos['secao_spline']}", spline_path)

        doc.build(story, onFirstPage=_header_footer, onLaterPages=_header_footer)
        return pdf_path

    def save_analisys(
        self, name: str, output_dir: Optional[Union[str, Path]] = None,
        titulos: Optional[dict] = None,
    ) -> None:
        """Salva a análise completa: CSVs, gráficos PNG avulso e relatório PDF.

        Os artefatos são organizados em subpastas:

        ``{output_dir}/``
            * ``{name}.pdf``               -- relatório PDF com todos os gráficos;
            * ``graficos/`` -- PNGs avulsos (combinado, Força × Tempo,
              Impulso × Tempo, Spline);
            * ``dados/``    -- CSVs (métricas e dados completos).

        Args:
            name: Nome base para os arquivos gerados.
            output_dir: Diretório base. Se ``None``, usa ``data/motor_result``
                (legacy) ou a biblioteca se o motor já estiver registrado nela.
            titulos: Títulos customizados (chaves de
                :data:`DEFAULT_TITULOS`) para os gráficos e o PDF.
        """
        if output_dir is None:
            from backend.biblioteca import _get_library_dir, get_motor

            existing = get_motor(name)
            if existing is not None:
                output_dir = _get_library_dir() / name
            else:
                output_dir = Path(__file__).parent.parent / "data" / "motor_result"
        output_dir = Path(output_dir)
        graficos_dir = output_dir / "graficos"
        dados_dir = output_dir / "dados"
        graficos_dir.mkdir(parents=True, exist_ok=True)
        dados_dir.mkdir(parents=True, exist_ok=True)

        result = self.get_result()
        pd.DataFrame([result]).to_csv(
            dados_dir / f"{name}_resultados.csv", sep=";", index=False
        )
        self.df.to_csv(dados_dir / f"{name}_dados.csv", sep=";", index=False)
        self.plot_analisys(name, graficos_dir, titulos=titulos)
        self.plot_force_time(name, graficos_dir, titulos=titulos)
        self.plot_impulse_time(name, graficos_dir, titulos=titulos)
        self.plot_spline(name, graficos_dir, titulos=titulos)
        self.pdf(name, output_dir, graficos_dir=graficos_dir, titulos=titulos)
