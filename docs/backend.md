# Referência do Backend (`app/backend/`)

O pacote `backend` contém as duas classes de processamento de dados. Ambas
recebem um arquivo (caminho ou objeto file-like) e convertem as unidades para o
SI no construtor.

```python
from backend import motor_analisys, data_treatment
```

---

## `motor_analisys` (`analises.py`)

Análise completa de um teste estático: métricas, splines, gráfico e relatório PDF.

### Construtor

```python
motor = motor_analisys(archive)
```

| Parâmetro | Tipo                      | Descrição                                    |
|-----------|---------------------------|----------------------------------------------|
| `archive` | str \| Path \| file-like  | CSV `Tempo,Empuxo,Pressao`                   |

Cria colunas derivadas: `Empuxo_N` (kg→N), `Tempo_s` (ms→s), `Pressao_MPa`,
`Tempo_rel` (tempo relativo). Valores arredondados para 4 casas decimais.

### Atributos

| Atributo    | Tipo               | Descrição                                  |
|-------------|--------------------|--------------------------------------------|
| `df`        | `pandas.DataFrame` | Dados com colunas originais + derivadas    |
| `df_result` | `dict \| None`     | Resultados (preenchido por `get_result()`) |

### Métodos

#### `get_data() -> DataFrame`
Retorna o DataFrame completo já convertido.

#### `remove_outliers(method="hampel", threshold=8.0) -> int`
Remove outliers (spikes isolados) preservando os dados reais de queima. Por
padrão usa o filtro **Hampel** (mediana rolante + MAD local), com corte
robusto global iterativo (P99×3) que também elimina rajadas de saturação do
sensor. O filtro é robusto à escala (funciona igual para kg ou g). O método
`'percentile'` (P99×fator) permanece disponível como alternativa. Retorna o
número de pontos removidos.

#### `get_result() -> dict`
Calcula todas as métricas e popula `df_result`. As métricas são calculadas
sobre a **janela ativa da queima** (recorte robusto a spikes), evitando que
ruído de fundo pré/pós-teste distorça impulso e duração. Chaves retornadas:

```python
{
    "Impulso [N*s]":      float,  # integração de Simpson (janela de queima)
    "Empuxo max [N]":     float,
    "Empuxo medio [N]":   float,
    "Pressao max [MPa]":  float,
    "Pressao media [MPa]":float,
    "Pontos amostrais":   int,    # amostras na janela de queima
    "Duracao [s]":        float,  # duração da queima
    "Classe":             str,    # ex.: "G12.5-10.0"
}
```

#### `spline() -> CubicSpline`
Spline cúbica da curva de empuxo (`Tempo_rel` × `Empuxo_N`).

#### `pressure_spline() -> CubicSpline`
Spline cúbica da curva de pressão (`Tempo_rel` × `Pressao_MPa`).

#### `plot_analisys(name, output_dir=None) -> Path`
Gera o gráfico PNG combinado (empuxo + pressão) sobre a janela ativa da
queima, com anotação do pico de empuxo. Retorna o caminho do PNG.
Usa o backend `Agg` do matplotlib (sem GUI).

#### `plot_force_time(name, output_dir=None) -> Path`
Gera o gráfico **avulso** Força × Tempo (`{name}_forca_tempo.png`), com a
janela de queima, pico anotado e área integrada destacada.

#### `plot_impulse_time(name, output_dir=None) -> Path`
Gera o gráfico **avulso** Impulso acumulado × Tempo (`{name}_impulso_tempo.png`),
integrando numericamente a curva de empuxo (N·s).

#### `plot_spline(name, output_dir=None) -> Path`
Gera o gráfico **avulso** da curva spline/suavizada de empuxo
(`{name}_spline.png`), sobrepondo a spline cúbica aos pontos brutos da janela.

#### `pdf(name, output_dir=None) -> Path` <a name="pdf"></a>
Gera o relatório PDF profissional via **ReportLab**. Inclui:

- Cabeçalho com faixa, logos (Serra Rocketry + UERJ) e título;
- Nome do motor + metadados (data/hora se disponíveis, pontos amostrais);
- Caixa de destaque com a classificação do motor;
- Tabela formatada de parâmetros de desempenho;
- Gráfico PNG embutido (se já gerado por `plot_analisys`);
- Rodapé com número de página e data de geração.

Chama `get_result()` automaticamente se `df_result` ainda for `None`.

#### `save_analisys(name, output_dir=None) -> None`
Conveniência: grava `{name}_resultados.csv`, `{name}_dados.csv`,
`{name}_grafico.png` e `{name}.pdf`. Diretório padrão:
`app/data/motor_result/`.

### Exemplo

```python
from backend import motor_analisys

motor = motor_analisys("teste.csv")
resultado = motor.get_result()
print(resultado["Classe"])          # "G12.5-10.0"

motor.save_analisys("Motor_SR1500") # gera CSV + PNG + PDF
```

---

## `data_treatment` (`tratamento.py`)

Carrega, converte e filtra dados brutos. Usado pela interface de tratamento.

### Construtor

```python
data = data_treatment(archive)
```

| Parâmetro | Tipo                     | Descrição                  |
|-----------|--------------------------|----------------------------|
| `archive` | str \| Path \| file-like | CSV `Tempo,Empuxo,Pressao` |

Cria as colunas derivadas `Tempo_s`, `Empuxo_N`, `Pressao_MPa`, `Tempo_rel`.

### Atributos

| Atributo | Tipo               | Descrição                          |
|----------|--------------------|------------------------------------|
| `data`   | `pandas.DataFrame` | Dados originais + colunas derivadas |

### Métodos

#### `get_data() -> DataFrame`
Retorna o DataFrame completo.

#### `remove_outliers(method="hampel", threshold=8.0) -> int`
Remove outliers (spikes isolados e rajadas de saturação) preservando os dados
reais da queima. Usa o filtro **Hampel** (mediana rolante + MAD local) seguido
de corte robusto global iterativo (P99×3). O método `'percentile'` (P99×fator)
permanece disponível. Retorna o número de pontos removidos.

#### `data_filter(threshold, interval=None) -> DataFrame`
Filtra por empuxo e, opcionalmente, por janela de tempo.

| Parâmetro   | Tipo               | Descrição                                |
|-------------|--------------------|------------------------------------------|
| `threshold` | float              | Empuxo mínimo em N (descarta `<=`)       |
| `interval`  | `[min, max]`\|None | Janela de tempo relativo em segundos     |

Retorna uma **cópia** filtrada do DataFrame.

#### `get_stats() -> dict`
Estatísticas descritivas:

```python
{
    "thrust":     {...},  # describe() de Empuxo_N
    "pressure":   {...},  # describe() de Pressao_MPa
    "duration_s": float,  # duração total
    "samples":    int,    # número de linhas
}
```

#### `save_treatment(name, data_dir=None) -> str`
Grava `{name}_processed.csv`. Diretório padrão:
`app/data/data_treatment/`. Retorna o caminho absoluto gravado.

### Exemplo

```python
from backend import data_treatment

data = data_treatment("bruto.csv")
filtrado = data.data_filter(threshold=5.0, interval=[1.0, 8.0])
stats = data.get_stats()
caminho = data.save_treatment("teste_limpo")
```

---

## Função auxiliar

### `_classify_motor(total_impulse, avg_thrust, duration) -> str`
(Privada, em `analises.py`) Determina a classe NAR/TRA com base no impulso total.
Retorna a designação no formato `{Classe}{empuxo_médio}-{duração}`, ou `"ERRO"`
se o impulso exceder a classe M. Tabela em
[data-format.md](data-format.md#classificação-de-motores-nartra).
