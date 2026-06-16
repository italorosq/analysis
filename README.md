# Análise Flask — Serra Rocketry

Aplicação web (Flask) + CLI para análise de dados de **testes estáticos de motores de foguete**, desenvolvida pela equipe Serra Rocketry (UERJ).

## Descrição

Permite o upload de arquivos CSV gerados pelo *thrust stand* (ESP32 + célula de carga HX711 + sensor de pressão), processa os dados e fornece:

- Cálculo de **impulso total** (integração de Simpson), empuxo médio/máximo, pressão média/máxima, duração de queima e **classe do motor** (padrão NAR/TRA: 1/4A → M).
- Visualização interativa de curvas de **empuxo** e **pressão**.
- Filtragem interativa de dados brutos (threshold + intervalo de tempo).
- Geração de **relatório PDF** profissional (via ReportLab), gráfico PNG e CSVs.
- **CLI de análise rápida de campo** para insights imediatos sem subir o servidor.

> 📚 **Documentação completa** em [`docs/`](docs/README.md): arquitetura, formato de dados,
> instalação, referência da API web, referência do backend, uso do CLI e guia de desenvolvimento.

## Formato de dados

O CSV gerado pelo firmware (`thrust-stand/firmware/firmware.ino`) tem o cabeçalho:

```
Tempo,Empuxo,Pressao
0,0.001,0.0
100,0.002,0.1
200,0.005,0.3
...
```

| Coluna  | Unidade no arquivo | Descrição                       | Conversão interna |
|---------|--------------------|---------------------------------|-------------------|
| Tempo   | milissegundos (ms) | Tempo desde o boot              | → segundos (/1000), tempo relativo ao início |
| Empuxo  | quilogramas (kg)   | Leitura da célula de carga      | → Newtons (×9.81) |
| Pressao | MPa                | Pressão da câmara               | mantida em MPa    |

## Estrutura do Projeto

```
analysis/
├── app/
│   ├── app.py                # Aplicação Flask (app factory + rotas)
│   ├── wsgi.py               # Entry point WSGI (gunicorn)
│   ├── cli.py                # CLI de análise rápida de campo
│   ├── gunicorn.conf.py      # Config do gunicorn
│   ├── backend/
│   │   ├── analises.py       # Análise de motor + relatório PDF (ReportLab)
│   │   └── tratamento.py     # Limpeza/filtragem de dados brutos
│   ├── templates/            # Templates HTML (layout responsivo)
│   ├── static/               # CSS, JS, assets
│   ├── data/                 # Resultados salvos (CSV, PNG, PDF)
│   ├── tests/                # Testes pytest do backend
│   ├── requirements.txt      # Dependências de produção
│   └── requirements-dev.txt  # Dependências de desenvolvimento
├── tests/                    # Notebooks e dados de exemplo
├── requirements.txt          # Dependências (raiz)
├── pyproject.toml            # Config ruff + pylint
├── Dockerfile / compose.yml
└── README.md
```

## Instalação

```bash
git clone https://github.com/SerraRocketry/Analise_Flask.git
cd Analise_Flask
python3 -m venv .venv
source .venv/bin/activate        # Linux/Mac
# .venv\Scripts\activate         # Windows
pip install -r app/requirements.txt
```

Para desenvolvimento (lint + testes):

```bash
pip install -r app/requirements-dev.txt
```

## Uso — Servidor Web

```bash
python app/app.py
```

A aplicação fica disponível em `http://127.0.0.1:5000/serra-rocketry`.

Em produção (Docker):

```bash
cd app
docker compose up --build
```

> Defina a variável de ambiente `SECRET_KEY` em produção.

## Uso — CLI de Análise Rápida de Campo

Para obter os principais insights de um teste rapidamente, sem subir o servidor:

```bash
# Relatório colorido no terminal (com sparkline da curva de empuxo)
python app/cli.py teste.csv

# Saída JSON (para integração com scripts)
python app/cli.py teste.csv --json

# Salva análise completa (CSV + gráfico PNG + relatório PDF)
python app/cli.py teste.csv --save nome_do_motor

# Sem cores ANSI
python app/cli.py teste.csv --no-color
```

Exemplo de saída:

```
╔══════════════════════════════════════════════════════╗
║   ANÁLISE RÁPIDA DE CAMPO · Serra Rocketry           ║
╚══════════════════════════════════════════════════════╝
Arquivo: teste.csv

  CLASSE DO MOTOR:  H12.5-20.0
  ────────────────────────────────────────────────────────
  Impulso Total.........    249.810 N·s
  Empuxo Médio..........     12.491 N
  Empuxo Máximo.........     19.620 N
  Pressão Média.........      3.167 MPa
  Pressão Máxima........      5.000 MPa
  Tempo de Queima.......      20.00 s
  ────────────────────────────────────────────────────────
  Curva de empuxo:
  ▁▁▁▂▂▃▃▄▄▅▅▆▆▆▇▇▇▇█▇▇▇▇▆▆▆▅▅▄▄▃▃▂▂▁▁
```

## Desenvolvimento

```bash
# Lint
ruff check app/backend/ app/app.py app/cli.py
pylint app/backend/ app/app.py app/cli.py

# Testes
cd app && python -m pytest tests/ -v
```

## Contribuição

1. Faça um fork do projeto.
2. Crie uma branch (`git checkout -b feature/nova-feature`).
3. Commit (`git commit -am 'Adiciona nova feature'`).
4. Push (`git push origin feature/nova-feature`).
5. Abra um Pull Request.

## Roadmap

1. Análise de Voo (em desenvolvimento).
2. Estimativa de trajetória.
3. Histórico de testes em banco de dados.
4. API REST documentada (OpenAPI/Swagger).
