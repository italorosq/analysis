# Referência da API Web (HTTP)

Todas as rotas estão sob o prefixo de blueprint `/serra-rocketry`.
Base URL em desenvolvimento: `http://127.0.0.1:5000/serra-rocketry`.

## Rotas de páginas (GET)

| Método | Rota          | Descrição                                | Resposta            |
|--------|---------------|------------------------------------------|---------------------|
| GET    | `/`           | Dashboard (página inicial)               | `index.html`        |
| GET    | `/home`       | Alias do dashboard                       | `index.html`        |
| GET    | `/analises`   | Formulário de upload p/ análise de motor | `analises.html`     |
| GET    | `/tratamento` | Formulário de upload p/ tratamento       | `tratamento.html`   |

## Análise de Motor

### `POST /motor_upload`

Processa um CSV de teste estático e exibe gráficos + métricas.

**Request** (`multipart/form-data`):

| Campo  | Tipo | Descrição                            |
|--------|------|--------------------------------------|
| `file` | file | CSV `Tempo,Empuxo,Pressao` (.csv/.txt) |

**Respostas:**

- **Sucesso:** renderiza `graficos_motor.html` com as curvas e a tabela de
  resultados. Os dados são guardados em `session["motor_data"]`.
- **Erro:** renderiza `analises.html` com mensagem (arquivo ausente, formato
  inválido ou erro de processamento).

Limite de upload: **16 MB** (`MAX_CONTENT_LENGTH`).

### `POST /save_motor`

Persiste a análise atual (da sessão) em disco.

**Request** (`application/x-www-form-urlencoded`):

| Campo  | Tipo   | Descrição                |
|--------|--------|--------------------------|
| `name` | string | Nome base dos arquivos   |

**Efeito:** gera `{name}_resultados.csv`, `{name}_dados.csv`,
`{name}_grafico.png` e `{name}.pdf` em `app/data/motor_result/`.

**Respostas:** `analises.html` com mensagem de sucesso ou erro (sem análise na
sessão, nome vazio, falha de escrita).

## Tratamento de Dados

### `POST /data_upload`

Processa um CSV bruto e exibe gráficos filtráveis.

**Request** (`multipart/form-data`):

| Campo  | Tipo | Descrição                            |
|--------|------|--------------------------------------|
| `file` | file | CSV `Tempo,Empuxo,Pressao` (.csv/.txt) |

**Sucesso:** renderiza `graficos_tratamento.html` com sliders de threshold e
intervalo de tempo. Dados guardados em `session["treatment_data"]`.

### `POST /update_filters`

Endpoint **AJAX** chamado pelos sliders no frontend. Refiltra os dados sem
recarregar a página.

**Request** (`application/x-www-form-urlencoded`):

| Campo       | Tipo  | Descrição                       |
|-------------|-------|---------------------------------|
| `threshold` | float | Empuxo mínimo (N)               |
| `tmin`      | float | Tempo mínimo (s, relativo)      |
| `tmax`      | float | Tempo máximo (s, relativo)      |

**Resposta** (`application/json`):

```json
{
  "x": [0.0, 0.1, 0.2, ...],
  "y": [12.1, 13.4, ...],
  "y_pressure": [3.1, 3.3, ...],
  "result": {
    "thrust": { "count": ..., "mean": ..., ... },
    "pressure": { "count": ..., "mean": ..., ... },
    "duration_s": 20.0,
    "samples": 201
  }
}
```

**Erros:**

| Status | Corpo                          | Causa                          |
|--------|--------------------------------|--------------------------------|
| 400    | `{"error": "No data loaded"}`  | Sem dados na sessão            |
| 500    | `{"error": "<mensagem>"}`      | Falha ao filtrar/processar     |

### `POST /save_treatment`

Persiste os dados tratados (da sessão) em CSV.

**Request** (`application/x-www-form-urlencoded`):

| Campo  | Tipo   | Descrição              |
|--------|--------|------------------------|
| `name` | string | Nome base do arquivo   |

**Efeito:** gera `{name}_processed.csv` em `app/data/data_treatment/`.

## Tratamento de erros

| Código | Página           |
|--------|------------------|
| 404    | `404.html`       |
| 500    | `500.html`       |

## Notas sobre sessão e concorrência

A aplicação não usa variáveis globais para o estado de processamento. O
DataFrame em uso é serializado em `session` (cookie assinado) entre requisições,
o que permite atendimento concorrente de múltiplos usuários. Veja
[architecture.md](architecture.md#gerenciamento-de-estado-sessão).
