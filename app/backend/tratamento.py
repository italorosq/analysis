"""Tratamento e filtragem de dados brutos de teste estÃ¡tico.

Este mÃ³dulo fornece a classe :class:`data_treatment`, responsÃ¡vel por carregar
os dados brutos gerados pelo *thrust stand* (firmware ESP32 + HX711 + sensor de
pressÃ£o), converter as unidades para o Sistema Internacional e aplicar filtros
interativos (limiar de empuxo e intervalo de tempo) usados na interface web de
tratamento de dados.

Formato de entrada esperado (CSV com cabeÃ§alho)::

    Tempo,Empuxo,Pressao
    0,0.001,0.0
    100,0.002,0.1
    ...

Onde:
    * ``Tempo``  -- milissegundos desde o boot do microcontrolador (int);
    * ``Empuxo`` -- leitura da cÃ©lula de carga em quilogramas (float);
    * ``Pressao`` -- pressÃ£o da cÃ¢mara em MPa (float).
"""

from pathlib import Path
from typing import Optional, Union

import numpy as np
import pandas as pd


def _hampel_mask(series: pd.Series, window: int = 5, n_sigma: float = 8.0) -> np.ndarray:
    """MÃ¡scara de outliers isolados (filtro Hampel) para uma sÃ©rie numÃ©rica.

    Um ponto Ã© considerado *spike* quando se desvia da mediana local (janela
    rolante) por mais de ``n_sigma`` vezes o desvio absoluto da mediana (MAD)
    local. O filtro Ã© robusto Ã  escala (funciona igualmente para dados em kg
    ou g) e preserva picos *sustentados* da queima real, pois um platÃ´ de
    vÃ¡rios pontos nÃ£o se desvia da prÃ³pria mediana local.

    Args:
        series: SÃ©rie numÃ©rica (ex.: ``Empuxo_N``).
        window: Tamanho da janela rolante (Ã­mpar). PadrÃ£o: 5.
        n_sigma: MÃºltiplo do MAD local considerado limite. PadrÃ£o: 8.0.

    Returns:
        np.ndarray: MÃ¡scara booleana â€” ``True`` para pontos *normais*,
        ``False`` para pontos marcados como spike.
    """
    n = len(series)
    if n == 0:
        return np.zeros(0, dtype=bool)

    half = max(1, int(window) // 2)
    values = series.to_numpy(dtype=float)
    good = np.ones(n, dtype=bool)

    for i in range(n):
        lo, hi = max(0, i - half), min(n, i + half + 1)
        window_vals = values[lo:hi]
        med = np.median(window_vals)
        mad = np.median(np.abs(window_vals - med))
        sigma = max(1.4826 * mad, np.finfo(float).eps)
        if abs(values[i] - med) > n_sigma * sigma:
            good[i] = False
    return good


def _clean_signal_mask(
    series: pd.Series, window: int = 5, n_sigma: float = 8.0
) -> np.ndarray:
    """MÃ¡scara de sinal limpo: remove spikes isolados e platÃ´s de saturaÃ§Ã£o.

    Combina dois mecanismos que **preservam a queima real** (mesmo o pico,
    que Ã© uma minoria das amostras):

    1. Filtro **Hampel** (mediana rolante + MAD local) â€” remove picos
       isolados de leitura. Como a queima Ã© um platÃ´/rampa *sustentado*
       (vÃ¡rios pontos vizinhos parecidos), ela nÃ£o Ã© desvio local e
       sobrevive; apenas os glitches isolados sÃ£o removidos.

    2. DetecÃ§Ã£o de **platÃ´ de saturaÃ§Ã£o** â€” sÃ³ ativada quando o valor
       mÃ¡ximo estÃ¡ *astronomicamente* acima do ruÃ­do (``> 50 Ã— (|med| + MAD)``).
       Nesse caso, remove apenas corridas longas (>= 8 amostras
       consecutivas) de valores "colados" no teto (dentro de 1% do mÃ¡ximo),
       caracterÃ­sticas de um ADC saturado. O pico real da queima Ã©
       *transitÃ³rio* (declina a cada amostra), entÃ£o nunca forma um platÃ´
       longo no teto e Ã© preservado.

    Importante: NÃƒO usa corte por percentil (P99Ã—fator), pois isso removeria
    o pico da queima quando a queima Ã© uma fraÃ§Ã£o pequena do total de
    amostras â€” exatamente o bug que afetava os testes reais.

    Args:
        series: SÃ©rie numÃ©rica (ex.: ``Empuxo_N``).
        window: Janela do filtro Hampel.
        n_sigma: MÃºltiplo do MAD local do filtro Hampel.

    Returns:
        np.ndarray: MÃ¡scara booleana â€” ``True`` para pontos considerados
        sinal vÃ¡lido.
    """
    good = _hampel_mask(series, window=window, n_sigma=n_sigma)
    values = series.to_numpy(dtype=float)
    clean = values[good]
    if len(clean) == 0:
        return good

    med = float(np.median(clean))
    mad = float(np.median(np.abs(clean - med)))
    ceil = float(np.max(clean))

    # SÃ³ investiga saturaÃ§Ã£o se o teto for astronomicamente maior que o ruÃ­do.
    if mad > 0 and ceil > 50.0 * (abs(med) + mad):
        lo = ceil - 0.01 * ceil  # janela de 1% abaixo do teto
        sat = (values >= lo) & good
        idxs = np.flatnonzero(sat)
        if len(idxs):
            splits = np.where(np.diff(idxs) > 1)[0]
            groups = np.split(idxs, splits + 1)
            flag = np.zeros(len(values), dtype=bool)
            for g in groups:
                if len(g) >= 8:  # platÃ´ longo
                    # SaturaÃ§Ã£o real do ADC: valores quase idÃªnticos
                    # (ex.: 980440, 980446 â†’ variaÃ§Ã£o < 0.1%). A queima real,
                    # mesmo no pico, tem variaÃ§Ã£o natural >> 0.5%.
                    gv = values[g]
                    gmean = float(np.mean(gv))
                    if gmean > 0:
                        cv = float(np.ptp(gv)) / gmean  # range / mÃ©dia
                        if cv < 0.005:  # < 0.5% de variaÃ§Ã£o = saturaÃ§Ã£o
                            flag[g] = True
            good = good & ~flag
    return good


def active_motor_window(df: pd.DataFrame, margin: int = 2) -> pd.DataFrame:
    """Extrai a janela em que o motor estÃ¡ ativo, de forma robusta a spikes.

    Este Ã© o algoritmo de recorte usado pela interface web e pelos relatÃ³rios.
    Diferente da abordagem antiga (que usava o pico global como referÃªncia e
    descartava quase toda a queima quando havia spikes de saturaÃ§Ã£o), a
    detecÃ§Ã£o aqui:

    1. Remove spikes isolados (filtro Hampel) para que o pico de referÃªncia
       seja o da queima real e nÃ£o um artefato de leitura;
    2. Calcula o limiar de atividade a partir da distribuiÃ§Ã£o robusta do sinal
       (mediana + fator do MAD), com piso absoluto de 0.2 N / 0.02 MPa;
    3. Junta pequenas lacunas (atÃ© 3 amostras) para nÃ£o fragmentar a queima;
    4. Seleciona o bloco contÃ­nuo de **maior impulso acumulado** (Ã¡rea sob a
       curva), em vez do bloco que contÃ©m o pico global;
    5. Aplica margem de ``margin`` amostras em cada lado e re-zero o tempo.

    Se nenhum bloco ativo for encontrado, retorna o DataFrame original.

    Args:
        df: DataFrame com as colunas derivadas ``Empuxo_N``, ``Pressao_MPa``
            e ``Tempo_rel`` (formato de ``motor_analisys``/``data_treatment``).
        margin: NÃºmero de amostras extras incluÃ­das em cada lado da janela.

    Returns:
        pandas.DataFrame: CÃ³pia do DataFrame restrito Ã  janela ativa, com
        ``Tempo_rel`` reiniciado em zero.
    """
    if df.empty:
        return df

    thrust = df["Empuxo_N"].to_numpy(dtype=float)
    pressure = df["Pressao_MPa"].to_numpy(dtype=float)
    tempo = df["Tempo_rel"].to_numpy(dtype=float)

    # 1) Remove spikes isolados E rajadas de saturaÃ§Ã£o antes de estimar os limiares
    good = _clean_signal_mask(pd.Series(thrust), window=5, n_sigma=8.0)
    clean_thrust = np.where(good, thrust, np.nan)

    # 2) Limiar robusto: percentil 95 do sinal limpo (ignorando spikes)
    finite = clean_thrust[~np.isnan(clean_thrust)]
    if len(finite) == 0:
        return df
    p95 = float(np.percentile(finite, 95))
    thr_signal = max(0.2, p95 * 0.3)

    # Complemento por pressÃ£o (quando o sensor estÃ¡ ativo)
    good_p = _clean_signal_mask(pd.Series(pressure), window=5, n_sigma=8.0)
    clean_pressure = np.where(good_p, pressure, np.nan)
    finite_p = clean_pressure[~np.isnan(clean_pressure)]
    if len(finite_p) > 0:
        p95_p = float(np.percentile(finite_p, 95))
        thr_p = max(0.02, p95_p * 0.3)
    else:
        thr_p = np.inf

    active_mask = ((thrust >= thr_signal) | (pressure >= thr_p)).tolist()
    if not any(active_mask):
        return df

    # 3) Preenche pequenas lacunas (atÃ© 3 amostras)
    gap_fill = 3
    i = 0
    n_points = len(active_mask)
    while i < n_points:
        if active_mask[i]:
            i += 1
            continue
        gap_start = i
        while i < n_points and not active_mask[i]:
            i += 1
        gap_end = i - 1
        gap_len = gap_end - gap_start + 1
        if gap_start > 0 and i < n_points and gap_len <= gap_fill:
            for j in range(gap_start, gap_end + 1):
                active_mask[j] = True

    # 4) Escolhe o bloco com maior impulso acumulado (Ã¡rea sob a curva >= 0)
    #    Usa o sinal LIMPO (spikes zerados) para que rajadas de saturaÃ§Ã£o
    #    nÃ£o dominem o critÃ©rio de seleÃ§Ã£o do bloco.
    clean_for_impulse = np.where(good, thrust, 0.0)

    blocks: list[tuple[int, int]] = []
    start = None
    for idx, active in enumerate(active_mask):
        if active and start is None:
            start = idx
        elif not active and start is not None:
            blocks.append((start, idx - 1))
            start = None
    if start is not None:
        blocks.append((start, n_points - 1))

    # Calcula o impulso (Ã¡rea limpa) de cada bloco.
    block_impulses = []
    for b_start, b_end in blocks:
        area = float(
            np.trapezoid(
                np.maximum(clean_for_impulse[b_start : b_end + 1], 0.0),
                tempo[b_start : b_end + 1],
            )
        )
        block_impulses.append(area)

# Escolhe o bloco de maior impulso (queima principal).
    best_idx = max(range(len(blocks)), key=lambda i: block_impulses[i])
    best_start, best_end = blocks[best_idx]
    best_impulse = block_impulses[best_idx]

    # Pico de referencia do bloco principal (sinal limpo).
    overall_peak = float(
        np.max(clean_for_impulse[best_start : best_end + 1])
    ) if len(clean_for_impulse[best_start : best_end + 1]) > 0 else 0.0
    peak_floor = overall_peak * 0.10  # >= 10% do pico principal

    # Estende a janela para incluir blocos VIZINHOS com impulso significativo
    # (>= 5% do principal) E pico >= 10% do pico principal.  Isso barra ruido
    # de baixo nivel que acumula impulso apenas pela duracao (ex.: 7 N por
    # 150 s), sem unir ruido distante (gaps >> 10s).
    if best_impulse > 0:
        threshold_impulse = 0.05 * best_impulse
        # Estende para tras
        i = best_idx - 1
        while i >= 0:
            blk_peak = float(np.max(clean_for_impulse[blocks[i][0] : blocks[i][1] + 1]))
            if block_impulses[i] >= threshold_impulse and blk_peak >= peak_floor:
                best_start = blocks[i][0]
                i -= 1
            else:
                gap = tempo[blocks[best_idx][0]] - tempo[blocks[i][1]]
                if gap > 10.0:
                    break
                i -= 1
        # Estende para frente
        i = best_idx + 1
        while i < len(blocks):
            blk_peak = float(np.max(clean_for_impulse[blocks[i][0] : blocks[i][1] + 1]))
            if block_impulses[i] >= threshold_impulse and blk_peak >= peak_floor:
                best_end = blocks[i][1]
                i += 1
            else:
                gap = tempo[blocks[i][0]] - tempo[blocks[best_idx][1]]
                if gap > 10.0:
                    break
                i += 1

    # 5) Margem e re-zero do tempo relativo
    start_idx = max(int(df.index.min()), best_start - margin)
    end_idx = min(int(df.index.max()), best_end + margin)

    window = df.loc[start_idx:end_idx].copy()
    # Filtra spikes residuais do Hampel que caÃ­ram dentro da janela
    good_window = good[start_idx - int(df.index.min()) : end_idx - int(df.index.min()) + 1]
    window = window[good_window].copy()
    window["Tempo_rel"] = (
        window["Tempo_rel"] - float(window["Tempo_rel"].iloc[0])
    ).round(4)
    return window


def default_filter_threshold(df: pd.DataFrame, fraction: float = 0.05) -> float:
    """Calcula um limiar padrÃ£o robusto para filtragem de dados.

    Diferente da mÃ©dia (facilmente inflada por spikes de saturaÃ§Ã£o), usa um
    pequeno percentil alto do sinal limpo de spikes como referÃªncia â€” o valor
    padrÃ£o de ``fraction`` (5% do P95) mantÃ©m praticamente todos os dados
    reais da queima e descarta apenas o ruÃ­do de fundo Ã³bvio.

    Args:
        df: DataFrame com a coluna ``Empuxo_N``.
        fraction: FraÃ§Ã£o do percentil 95 (apÃ³s remoÃ§Ã£o de spikes) usada como
            limiar padrÃ£o.

    Returns:
        float: Limiar em Newtons (mÃ­nimo 0.1 N).
    """
    if df.empty:
        return 0.1
    thrust = df["Empuxo_N"]
    good = thrust[_clean_signal_mask(thrust, window=5, n_sigma=8.0)]
    if len(good) == 0:
        good = thrust
    ref = float(good.quantile(0.95))
    return round(max(0.1, ref * fraction), 3)


class data_treatment:  # pylint: disable=invalid-name
    """Carrega, converte e filtra dados brutos de um teste estÃ¡tico.

    A classe lÃª o CSV uma Ãºnica vez no construtor, criando colunas derivadas
    em unidades do SI (segundos, Newtons, MPa) e um eixo de tempo relativo ao
    inÃ­cio da aquisiÃ§Ã£o. Os mÃ©todos subsequentes operam sobre esse DataFrame
    jÃ¡ preparado.

    Attributes:
        data (pandas.DataFrame): DataFrame com as colunas originais
            (``Tempo``, ``Empuxo``, ``Pressao``) acrescido das colunas
            derivadas ``Tempo_s``, ``Empuxo_N``, ``Pressao_MPa`` e
            ``Tempo_rel``.
    """

    def __init__(
        self, archive: Union[str, Path, "object"], units: str = "kg"
    ) -> None:
        """LÃª o CSV e gera as colunas derivadas em unidades do SI.

        Args:
            archive: Caminho do arquivo CSV ou objeto file-like (por exemplo,
                o ``werkzeug.FileStorage`` recebido em um upload Flask). Deve
                conter o cabeÃ§alho ``Tempo,Empuxo,Pressao``.
            units: Unidade de medida do empuxo. ``'kg'`` (padrÃ£o) ou ``'g'``
                (gramas). Quando ``'g'``, os valores sÃ£o divididos por 1000
                antes da conversÃ£o para Newtons.

        Side Effects:
            Popula ``self.data`` com as colunas convertidas:
                * ``Tempo_s``    = ``Tempo`` / 1000      (ms -> s)
                * ``Empuxo_N``   = ``Empuxo`` * 9.81     (kg -> N)
                * ``Pressao_MPa``= ``Pressao``           (mantida em MPa)
                * ``Tempo_rel``  = ``Tempo_s`` - primeiro valor (tempo relativo)
        """
        self.data = pd.read_csv(archive)

        # ConversÃ£o de unidades para o SI
        self.data["Tempo_s"] = self.data["Tempo"] / 1000.0  # ms -> segundos
        empuxo_kg = self.data["Empuxo"]
        if units == "g":
            empuxo_kg = empuxo_kg / 1000.0  # gramas -> quilogramas
        self.data["Empuxo_N"] = empuxo_kg * 9.81  # kg -> Newtons
        self.data["Pressao_MPa"] = self.data["Pressao"]  # jÃ¡ estÃ¡ em MPa

        # Tempo relativo ao inÃ­cio da aquisiÃ§Ã£o (zera o primeiro ponto)
        self.data["Tempo_rel"] = self.data["Tempo_s"] - self.data["Tempo_s"].iloc[0]

    def get_data(self) -> pd.DataFrame:
        """Retorna o DataFrame completo jÃ¡ convertido.

        Returns:
            pandas.DataFrame: Os dados carregados com as colunas derivadas.
        """
        return self.data

    def remove_outliers(
        self, method: str = "hampel", threshold: float = 8.0
    ) -> int:
        """Remove outliers (spikes isolados) preservando dados reais da queima.

        Por padrÃ£o usa o filtro **Hampel** (mediana rolante + MAD), que remove
        apenas picos isolados de leitura â€” artefatos do sensor que se desviam
        muito da vizinhanÃ§a local â€” sem tocar em platÃ´s sustentados da queima.
        O filtro Ã© robusto Ã  escala (funciona igual para kg ou g).

        O mÃ©todo antigo ``'percentile'`` (P99 * fator) continua disponÃ­vel como
        alternativa compatÃ­vel.

        Args:
            method: MÃ©todo de detecÃ§Ã£o â€” ``'hampel'`` (padrÃ£o) ou
                ``'percentile'``.
            threshold: ParÃ¢metro do filtro: para ``'hampel'``, mÃºltiplo do MAD
                local; para ``'percentile'``, fator multiplicativo sobre o P99.
                PadrÃ£o: 8.0.

        Returns:
            int: NÃºmero de outliers removidos.
        """
        n_before = len(self.data)

        if method == "percentile":
            p99 = self.data["Empuxo_N"].quantile(0.99)
            upper = p99 * threshold
            keep = self.data["Empuxo_N"] <= upper
        else:
            keep = _clean_signal_mask(self.data["Empuxo_N"], window=5, n_sigma=threshold)

        self.data = self.data[keep].copy()
        self.data.reset_index(drop=True, inplace=True)
        # Recalcula tempo relativo apÃ³s reset do Ã­ndice
        self.data["Tempo_rel"] = self.data["Tempo_s"] - self.data["Tempo_s"].iloc[0]
        return n_before - len(self.data)

    def data_filter(
        self, threshold: float, interval: Optional[list] = None
    ) -> pd.DataFrame:
        """Filtra os dados por limiar de empuxo e, opcionalmente, por tempo.

        MantÃ©m apenas as amostras cujo empuxo (em Newtons) supera ``threshold``.
        Quando ``interval`` Ã© informado, tambÃ©m restringe as amostras Ã  janela
        de tempo relativo indicada.

        Args:
            threshold: Empuxo mÃ­nimo, em Newtons. Amostras com
                ``Empuxo_N <= threshold`` sÃ£o descartadas.
            interval: Par ``[min_tempo, max_tempo]`` em segundos (tempo
                relativo). Se ``None``, nenhum recorte temporal Ã© aplicado.

        Returns:
            pandas.DataFrame: CÃ³pia filtrada do DataFrame original.
        """
        filtered = self.data[self.data["Empuxo_N"] > threshold].copy()
        if interval:
            min_interval, max_interval = interval
            filtered = filtered[
                filtered["Tempo_rel"].between(min_interval, max_interval)
            ]
        return filtered

    def save_treatment(
        self, name: str, data_dir: Optional[Union[str, Path]] = None
    ) -> str:
        """Salva o DataFrame tratado em CSV.

        Args:
            name: Nome base do arquivo (sem extensÃ£o). O arquivo gerado serÃ¡
                ``{name}_processed.csv``.
            data_dir: DiretÃ³rio de destino. Se ``None``, usa
                ``app/data/data_treatment`` (criado se nÃ£o existir).

        Returns:
            str: Caminho absoluto do arquivo CSV gravado.
        """
        if data_dir is None:
            data_dir = Path(__file__).parent.parent / "data" / "data_treatment"
        data_dir = Path(data_dir)
        data_dir.mkdir(parents=True, exist_ok=True)

        output_path = data_dir / f"{name}_processed.csv"
        self.data.to_csv(output_path, index=False)
        return str(output_path)

    def get_stats(self) -> dict:
        """Calcula estatÃ­sticas descritivas de empuxo e pressÃ£o.

        Returns:
            dict: DicionÃ¡rio com as chaves:
                * ``thrust``   -- ``describe()`` da coluna de empuxo (N);
                * ``pressure`` -- ``describe()`` da coluna de pressÃ£o (MPa);
                * ``duration_s`` -- duraÃ§Ã£o total do teste em segundos;
                * ``samples`` -- nÃºmero de amostras (linhas).
        """
        return {
            "thrust": self.data["Empuxo_N"].describe().to_dict(),
            "pressure": self.data["Pressao_MPa"].describe().to_dict(),
            "duration_s": float(self.data["Tempo_rel"].max()),
            "samples": len(self.data),
        }
