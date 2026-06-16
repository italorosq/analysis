# Arquitetura

## Visão geral

O sistema é composto por três camadas principais:

1. **Camada de aquisição** (externa): o firmware do *thrust stand* (`thrust-stand/firmware/firmware.ino`)
   roda em um ESP32 com célula de carga HX711 e sensor de pressão, gravando um CSV em
   cartão SD ou LittleFS.
2. **Camada de processamento** (`app/backend/`): classes Python que carregam o CSV,
   convertem unidades, calculam métricas e geram artefatos (gráficos, PDF).
3. **Camadas de interface**: a aplicação web Flask (`app/app.py`) e o CLI (`app/cli.py`),
   ambos consumindo a mesma camada de processamento.

```
                         ┌───────────────────────────────────────┐
                         │              app/backend/              │
                         │                                        │
   ┌──────────┐          │  ┌──────────────┐  ┌────────────────┐ │
   │  Web UI   │◄────────┼─►│ motor_analisys│  │ data_treatment │ │
   │ (Flask)  │          │  └──────────────┘  └────────────────┘ │
   └──────────┘          │         ▲                  ▲          │
                         └─────────┼──────────────────┼──────────┘
   ┌──────────┐                    │                  │
   │   CLI    │◄───────────────────┘                  │
   │ (cli.py) │                                        │
   └──────────┘                                        │
                                              ┌─────────────────┐
                                              │   pandas/scipy  │
                                              │ matplotlib/RL   │
                                              └─────────────────┘
```

## Estrutura de diretórios

```
analysis/
├── app/
│   ├── app.py                # App factory + blueprint + rotas
│   ├── wsgi.py               # Entry point WSGI (gunicorn)
│   ├── cli.py                # CLI de análise rápida de campo
│   ├── gunicorn.conf.py      # Config do gunicorn (bind, workers, reload)
│   ├── backend/
│   │   ├── __init__.py       # Exporta motor_analisys e data_treatment
│   │   ├── analises.py       # Análise de motor + relatório PDF
│   │   └── tratamento.py     # Limpeza/filtragem de dados brutos
│   ├── templates/            # Templates Jinja2 (HTML)
│   ├── static/               # CSS, JS, assets (logos)
│   ├── data/
│   │   ├── motor_result/     # Resultados de análise (CSV, PNG, PDF)
│   │   └── data_treatment/   # Dados tratados (CSV)
│   ├── tests/                # Testes pytest do backend
│   ├── requirements.txt      # Dependências de produção
│   └── requirements-dev.txt  # Dependências de desenvolvimento
├── tests/                    # Notebooks e dados de exemplo
├── docs/                     # Esta documentação
├── requirements.txt          # Dependências (raiz)
├── pyproject.toml            # Config ruff + pylint
├── Dockerfile / compose.yml
└── README.md
```

## Componentes

### App factory (`app/app.py`)

A aplicação usa o padrão **application factory** (`create_app()`), que:

- Cria a instância `Flask`;
- Define a `secret_key` (via variável de ambiente `SECRET_KEY`);
- Configura o limite de upload (`MAX_CONTENT_LENGTH` = 16 MB);
- Registra o blueprint `page` com o prefixo de URL `/serra-rocketry`.

Todas as rotas vivem no blueprint `page`, então as URLs efetivas têm o prefixo
`/serra-rocketry` (ex.: `http://localhost:5000/serra-rocketry/analises`).

### Gerenciamento de estado (sessão)

Como a aplicação pode atender múltiplos usuários simultâneos, **não há variáveis
globais** guardando o DataFrame em processamento. Em vez disso:

- Após o upload, o DataFrame é serializado para JSON e guardado em `session`
  (`session["motor_data"]` ou `session["treatment_data"]`);
- Ao salvar ou filtrar, o objeto é recriado a partir desse JSON.

Isso torna o fluxo *stateless* entre requisições e seguro para concorrência.

### Camada de processamento (`app/backend/`)

Duas classes independentes, ambas recebendo um arquivo (caminho ou file-like):

- **`motor_analisys`** — análise completa: métricas, splines, gráfico e PDF;
- **`data_treatment`** — tratamento: conversão de unidades, filtragem e estatísticas.

Detalhes em [backend.md](backend.md).

## Fluxo de dados — Análise de Motor

```
1. Usuário faz upload do CSV  ──►  POST /motor_upload
2. motor_analisys(arquivo)         lê CSV, converte unidades
3. get_result()                    calcula métricas + classe
4. session["motor_data"] = {...}   serializa para reuso
5. render graficos_motor.html      exibe curvas + tabela
6. Usuário clica "Salvar"     ──►  POST /save_motor
7. save_analisys(nome)             grava CSV + PNG + PDF
```

## Fluxo de dados — Tratamento

```
1. Upload do CSV bruto        ──►  POST /data_upload
2. data_treatment(arquivo)         lê CSV, converte unidades
3. data_filter() + get_stats()     filtro inicial (média)
4. render graficos_tratamento.html sliders interativos
5. Sliders disparam fetch     ──►  POST /update_filters (AJAX)
6. data_filter(threshold, [t])     refiltra e retorna JSON
7. Frontend atualiza gráficos      sem recarregar a página
8. Usuário salva              ──►  POST /save_treatment
```

## Decisões de projeto

- **Imports lazy** de `matplotlib`, `reportlab` e `pandas` dentro dos métodos que os
  usam, para reduzir o tempo de *cold start* da aplicação web.
- **Backend `Agg` do matplotlib** (sem GUI), apropriado para servidor.
- **Caminhos resolvidos via `pathlib`** relativos ao arquivo, nunca ao diretório de
  trabalho — funciona igual em dev, Docker e gunicorn.
- **Conversão de unidades centralizada** no construtor de cada classe (ms→s, kg→N).
