# Formato de Dados

## CSV do firmware (entrada)

O arquivo de entrada é gerado pelo firmware do *thrust stand*
(`thrust-stand/firmware/firmware.ino`) e possui o seguinte cabeçalho:

```
Tempo,Empuxo,Pressao
0,0.001,0.0
100,0.002,0.1
200,0.005,0.3
...
```

### Colunas

| Coluna    | Tipo  | Unidade no arquivo   | Descrição                                  |
|-----------|-------|----------------------|--------------------------------------------|
| `Tempo`   | int   | milissegundos (ms)   | Tempo desde o boot do microcontrolador     |
| `Empuxo`  | float | quilogramas (kg)     | Leitura da célula de carga HX711           |
| `Pressao` | float | MPa                  | Pressão da câmara medida pelo sensor       |

> O firmware grava uma amostra a cada `INTERVALO` ms (padrão: 100 ms), via
> `String(millis) + "," + String(peso, 6) + "," + String(pressao)`.

## Conversões internas

Ao carregar o CSV, tanto `motor_analisys` quanto `data_treatment` criam colunas
derivadas em unidades do **Sistema Internacional**:

| Coluna derivada | Cálculo                              | Unidade |
|-----------------|--------------------------------------|---------|
| `Tempo_s`       | `Tempo / 1000`                       | s       |
| `Empuxo_N`      | `Empuxo * 9.81`                      | N       |
| `Pressao_MPa`   | `Pressao` (mantida)                  | MPa     |
| `Tempo_rel`     | `Tempo_s - Tempo_s[0]` (zera início) | s       |

A constante de conversão de empuxo é a aceleração da gravidade padrão
(g = 9.81 m/s²), convertendo a massa medida (kg) em força (N).

## Compatibilidade com o formato antigo

> **Atenção:** o formato atual (`Tempo,Empuxo,Pressao`, separado por vírgula) é
> diferente do formato legado usado em versões antigas, que era
> `Data;Hora;Empuxo;Tempo` separado por ponto e vírgula. Os dados de exemplo em
> `tests/SerraR/` e `tests/GFRJ/` usam o formato legado e **não** são compatíveis
> diretamente com o código atual. Use CSVs gerados pelo firmware atual.

## Artefatos de saída

### `{nome}_resultados.csv`

Métricas calculadas, separadas por `;`:

```
Impulso [N*s];Empuxo max [N];Empuxo medio [N];Pressao max [MPa];Pressao media [MPa];Pontos amostrais;Duracao [s];Classe
124.905;19.620;12.491;5.000;3.167;101;10.0;G12.5-10.0
```

### `{nome}_dados.csv`

Dados completos com todas as colunas (originais + derivadas), separados por `;`.

### `{nome}_grafico.png`

Figura combinada com dois subplots (empuxo e pressão × tempo), recortada na
**janela ativa da queima** (recorte robusto a spikes) e com o pico de empuxo
anotado. 150 DPI.

### Gráficos avulsos (`{nome}_forca_tempo.png`, `{nome}_impulso_tempo.png`, `{nome}_spline.png`)

Além do gráfico combinado, a análise gera **gráficos avulsos** individuais:

* `{nome}_forca_tempo.png` — Força × Tempo (principal), com pico anotado e
  área integrada (impulso) destacada;
* `{nome}_impulso_tempo.png` — Impulso acumulado × Tempo (N·s);
* `{nome}_spline.png` — Curva spline/suavizada sobreposta aos pontos brutos.

### `{nome}.pdf`

Relatório completo gerado via ReportLab, agora com **todas** as seções de
gráfico (combinado, Força × Tempo, Impulso acumulado e Spline). Veja
[backend.md](backend.md#pdf).

## Limpeza e recorte de dados

O pipeline de análise agora usa algoritmos robustos a spikes de saturação do
sensor (valores como ~980.000 no CSV bruto):

* **Remoção de outliers** (`remove_outliers`): filtro Hampel (mediana rolante +
  MAD local) com corte robusto global iterativo (P99×3). Remove apenas picos
  isolados e rajadas de saturação, preservando platôs sustentados da queima.
* **Janela ativa** (`active_motor_window`): detecta a queima pelo bloco de
  **maior impulso acumulado**, com limiar derivado do sinal limpo — sem
  descartar os dados reais da queima.
* **Limiar padrão do tratamento**: percentil alto do sinal limpo (5% do P95),
  em vez da média — que era inflada por spikes e removia toda a queima.

### `{nome}_processed.csv` (tratamento)

Saída de `data_treatment.save_treatment()` — DataFrame tratado, separado por vírgula.

## Classificação de motores (NAR/TRA)

A classe do motor é determinada pelo impulso total, segundo a tabela padrão:

| Classe | Impulso máx. (N·s) | Classe | Impulso máx. (N·s) |
|--------|--------------------|--------|--------------------|
| 1/4A   | 0.625              | G      | 160                |
| 1/2A   | 1.25               | H      | 320                |
| A      | 2.5                | I      | 640                |
| B      | 5                  | J      | 1280               |
| C      | 10                 | K      | 2560               |
| D      | 20                 | L      | 5120               |
| E      | 40                 | M      | 10240              |
| F      | 80                 |        |                    |

A designação final inclui o empuxo médio e a duração, no formato
`{Classe}{empuxo_médio}-{duração}` (ex.: `G12.5-10.0`).
