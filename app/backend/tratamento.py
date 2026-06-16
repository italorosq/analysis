"""Tratamento e filtragem de dados brutos de teste estático.

Este módulo fornece a classe :class:`data_treatment`, responsável por carregar
os dados brutos gerados pelo *thrust stand* (firmware ESP32 + HX711 + sensor de
pressão), converter as unidades para o Sistema Internacional e aplicar filtros
interativos (limiar de empuxo e intervalo de tempo) usados na interface web de
tratamento de dados.

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


class data_treatment:  # pylint: disable=invalid-name
    """Carrega, converte e filtra dados brutos de um teste estático.

    A classe lê o CSV uma única vez no construtor, criando colunas derivadas
    em unidades do SI (segundos, Newtons, MPa) e um eixo de tempo relativo ao
    início da aquisição. Os métodos subsequentes operam sobre esse DataFrame
    já preparado.

    Attributes:
        data (pandas.DataFrame): DataFrame com as colunas originais
            (``Tempo``, ``Empuxo``, ``Pressao``) acrescido das colunas
            derivadas ``Tempo_s``, ``Empuxo_N``, ``Pressao_MPa`` e
            ``Tempo_rel``.
    """

    def __init__(self, archive: Union[str, Path, "object"]) -> None:
        """Lê o CSV e gera as colunas derivadas em unidades do SI.

        Args:
            archive: Caminho do arquivo CSV ou objeto file-like (por exemplo,
                o ``werkzeug.FileStorage`` recebido em um upload Flask). Deve
                conter o cabeçalho ``Tempo,Empuxo,Pressao``.

        Side Effects:
            Popula ``self.data`` com as colunas convertidas:
                * ``Tempo_s``    = ``Tempo`` / 1000      (ms -> s)
                * ``Empuxo_N``   = ``Empuxo`` * 9.81     (kg -> N)
                * ``Pressao_MPa``= ``Pressao``           (mantida em MPa)
                * ``Tempo_rel``  = ``Tempo_s`` - primeiro valor (tempo relativo)
        """
        self.data = pd.read_csv(archive)

        # Conversão de unidades para o SI
        self.data["Tempo_s"] = self.data["Tempo"] / 1000.0  # ms -> segundos
        self.data["Empuxo_N"] = self.data["Empuxo"] * 9.81  # kg -> Newtons
        self.data["Pressao_MPa"] = self.data["Pressao"]  # já está em MPa

        # Tempo relativo ao início da aquisição (zera o primeiro ponto)
        self.data["Tempo_rel"] = self.data["Tempo_s"] - self.data["Tempo_s"].iloc[0]

    def get_data(self) -> pd.DataFrame:
        """Retorna o DataFrame completo já convertido.

        Returns:
            pandas.DataFrame: Os dados carregados com as colunas derivadas.
        """
        return self.data

    def data_filter(
        self, threshold: float, interval: Optional[list] = None
    ) -> pd.DataFrame:
        """Filtra os dados por limiar de empuxo e, opcionalmente, por tempo.

        Mantém apenas as amostras cujo empuxo (em Newtons) supera ``threshold``.
        Quando ``interval`` é informado, também restringe as amostras à janela
        de tempo relativo indicada.

        Args:
            threshold: Empuxo mínimo, em Newtons. Amostras com
                ``Empuxo_N <= threshold`` são descartadas.
            interval: Par ``[min_tempo, max_tempo]`` em segundos (tempo
                relativo). Se ``None``, nenhum recorte temporal é aplicado.

        Returns:
            pandas.DataFrame: Cópia filtrada do DataFrame original.
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
            name: Nome base do arquivo (sem extensão). O arquivo gerado será
                ``{name}_processed.csv``.
            data_dir: Diretório de destino. Se ``None``, usa
                ``app/data/data_treatment`` (criado se não existir).

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
        """Calcula estatísticas descritivas de empuxo e pressão.

        Returns:
            dict: Dicionário com as chaves:
                * ``thrust``   -- ``describe()`` da coluna de empuxo (N);
                * ``pressure`` -- ``describe()`` da coluna de pressão (MPa);
                * ``duration_s`` -- duração total do teste em segundos;
                * ``samples`` -- número de amostras (linhas).
        """
        return {
            "thrust": self.data["Empuxo_N"].describe().to_dict(),
            "pressure": self.data["Pressao_MPa"].describe().to_dict(),
            "duration_s": float(self.data["Tempo_rel"].max()),
            "samples": len(self.data),
        }
