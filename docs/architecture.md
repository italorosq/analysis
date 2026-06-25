# Arquitetura

## Visão geral

O sistema é composto por quatro camadas principais:

1. **Camada de aquisição** (externa): o firmware do *thrust stand* (`thrust-stand/firmware/firmware.ino`)
   roda em um ESP32 com célula de carga HX711 e sensor de pressão, gravando um CSV em
   cartão SD ou LittleFS.
2. **Camada de processamento** (`app/backend/`): classes Python que carregam o CSV,
   convertem unidades, calculam métricas e geram artefatos (gráficos, PDF).
3. **Camada de persistência** (`app/backend/biblioteca.py` + `data/biblioteca/`): metadados
   estruturados por motor, parser de `.eng` (RASP), migração de dados legados.
4. **Camadas de interface**: a aplicação web Flask (`app/app.py` + `app/biblioteca_bp.py`)
   e o CLI (`app/cli.py`), ambos consumindo as mesmas camadas.

```
                         ┌──────────────────────────────────────────────────┐
                         │              app/backend/                          │
                         │                                                  │
                         │  ┌──────────────┐  ┌────────────────┐             │
   ┌──────────┐          │  │ motor_analisys│  │ data_treatment │             │
   │  Web UI   │◄────────┼─►│ biblioteca.py │  │ parser_eng.py  │             │
   │ (Flask)  │          │  └──────────────┘  └────────────────┘             │
   └──────────┘          │         ▲                  ▲                      │
                         └─────────┼──────────────────┼──────────────────────┘
   ┌──────────┐                    │                  │
   │   CLI    │◄───────────────────┘                  │
   │ (cli.py) │                                        │
   └──────────┘                                        │
   ┌──────────┐                              ┌─────────────────┐
   │  Biblioteca│◄────────────────────────────│   pandas/scipy  │
   │  (web)    │                              │ matplotlib/RL   │
   └──────────┘                              └─────────────────┘
```

## Estrutura de diretórios

```
analysis/
├── app/
│   ├── app.py                # App factory + blueprint page + rotas
│   ├── biblioteca_bp.py      # Blueprint da biblioteca (/biblioteca)
│   ├── wsgi.py               # Entry point WSGI (gunicorn)
│   ├── cli.py                # CLI de análise rápida + biblioteca
│   ├── gunicorn.conf.py      # Config do gunicorn (bind, workers, reload)
│   ├── backend/
│   │   ├── __init__.py       # Exporta motor_analisys e data_treatment
│   │   ├── config.py         # Constantes (LIBRARY_DIR, extensões)
│   │   ├── analises.py       # Análise de motor + relatório PDF
│   │   ├── tratamento.py     # Limpeza/filtragem de dados brutos
│   │   ├── biblioteca.py     # CRUD da biblioteca + migração legacy
│   │   └── parser_eng.py     # Parser de arquivos .eng (RASP)
│   ├── templates/            # Templates Jinja2 (HTML)
│   ├── static/               # CSS, JS, assets (logos)
│   ├── data/
│   │   ├── biblioteca/       # Entradas da biblioteca (motor.json + arquivos)
│   │   ├── motor_result/     # Legado (anterior à biblioteca)
│   │   └── data_treatment/   # Legado (dados tratados)
│   ├── tests/                # Testes pytest
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
- Registra o blueprint `page` com o prefixo de URL `/serra-rocketry`;
- Registra o blueprint `biblioteca_bp` com o prefixo `/biblioteca`.

Todas as rotas principais vivem no blueprint `page`, enquanto as rotas da
biblioteca vivem no blueprint `biblioteca_bp`. As URLs efetivas têm o prefixo
correspondente (ex.: `http://localhost:5000/serra-rocketry/analises`,
`http://localhost:5000/biblioteca`).

### Biblioteca (`app/backend/biblioteca.py`)

Módulo responsável pelo CRUD de entradas na biblioteca de testes. Cada motor
é uma subpasta em `data/biblioteca/<nome>/` com `motor.json` como metadado central.

Funções principais:
- `scan_library()` — lista todos os motores, ordenado por data/impulso/classe;
- `get_motor(nome)` — lê `motor.json` e retorna `MotorMetadata`;
- `save_motor_metadata(nome, metadata)` — persiste `motor.json`;
- `delete_motor(nome)` — remove pasta inteira;
- `list_files(nome)` — categoriza arquivos da pasta;
- `register_file()` / `unregister_file()` — atualiza referências em `motor.json`;
- `migrate_legacy_motor_result()` — migra dados de `data/motor_result/` para a biblioteca.

### Parser RASP (`app/backend/parser_eng.py`)

Parser de arquivos `.eng` no formato RASP (Rocket Altitude Simulation Program).
Extrai header (7 campos) e data points (tempo × empuxo), calcula métricas derivadas
(impulso via Simpson, Isp teórico) e serializa para dict (armazenado em `motor.json`).

### Gerenciamento de estado (sessão)

Como a aplicação pode atender múltiplos usuários simultaneamente, **não há variáveis
globais** guardando o DataFrame em processamento. Em vez disso:

- Após o upload, o DataFrame é serializado para JSON e guardado em `session`
  (`session["motor_data"]` ou `session["treatment_data"]`);
- Ao salvar ou filtrar, o objeto é recriado a partir desse JSON.

Isso torna o fluxo *stateless* entre requisições e seguro para concorrência.

### Camada de processamento (`app/backend/`)

Três classes independentes, todas recebendo um arquivo (caminho ou file-like):

- **`motor_analisys`** — análise completa: métricas, splines, gráfico e PDF;
- **`data_treatment`** — tratamento: conversão de unidades, filtragem e estatísticas;
- **`parser_eng`** (dataclass `EngData`) — parse de `.eng`: header, curva, métricas.

Detalhes em [backend.md](backend.md).

## Fluxo de dados — Análise de Motor

```
1. Usuário faz upload do CSV  ──►  POST /serra-rocketry/motor_upload
2. motor_analisys(arquivo)         lê CSV, converte unidades
3. get_result()                    calcula métricas + classe
4. session["motor_data"] = {...}   serializa para reuso
5. render graficos_motor.html      exibe curvas + tabela
6. Usuário clica "Salvar"     ──►  POST /serra-rocketry/save_motor
7. save_analisys(nome)             grava na biblioteca (se motor existe)
                                   ou em data/motor_result/ (legacy)
```

## Fluxo de dados — Biblioteca

```
1. Usuário acessa /biblioteca      ──►  GET /biblioteca
2. scan_library()                   lê motor.json de cada pasta
3. Render biblioteca.html           grid de cards com resumo
4. Usuário clica no motor      ──►  GET /biblioteca/<nome>
5. get_motor() + list_files()       lê metadados + arquivos
6. Render biblioteca_detalhe.html   tabela + preview + arquivos
7. Upload de .eng ou foto      ──►  POST /biblioteca/<nome>/upload
8. parser_eng ou save file          processa e atualiza motor.json
```

## Fluxo de dados — Tratamento

```
1. Upload do CSV bruto        ──►  POST /serra-rocketry/data_upload
2. data_treatment(arquivo)         lê CSV, converte unidades
3. data_filter() + get_stats()     filtro inicial (média)
4. render graficos_tratamento.html sliders interativos
5. Sliders disparam fetch     ──►  POST /serra-rocketry/update_filters (AJAX)
6. data_filter(threshold, [t])     refiltra e retorna JSON
7. Frontend atualiza gráficos      sem recarregar a página
8. Usuário salva              ──►  POST /serra-rocketry/save_treatment
```

## Decisões de projeto

- **Imports lazy** de `matplotlib`, `reportlab` e `pandas` dentro dos métodos que os
  usam, para reduzir o tempo de *cold start* da aplicação web.
- **Backend `Agg` do matplotlib** (sem GUI), apropriado para servidor.
- **Caminhos resolvidos via `pathlib`** relativos ao arquivo, nunca ao diretório de
  trabalho — funciona igual em dev, Docker e gunicorn.
- **Conversão de unidades centralizada** no construtor de cada classe (ms→s, kg→N).
- **Persistência estruturada** via `motor.json` em vez de arquivos avulsos — permite
  busca, ordenação e exibição sem re-parsear CSVs.
