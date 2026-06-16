"""Pacote *backend* da aplicação Serra Rocketry.

Expõe as duas classes principais de processamento de dados de teste estático:

* :class:`~backend.analises.motor_analisys` -- análise completa do motor
  (impulso, empuxo, classe, gráficos e relatório PDF);
* :class:`~backend.tratamento.data_treatment` -- limpeza e filtragem
  interativa de dados brutos.
"""

from .analises import motor_analisys
from .tratamento import data_treatment

__all__ = ["motor_analisys", "data_treatment"]
