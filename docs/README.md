# Documentação — Análise Flask (Serra Rocketry)

Documentação técnica do sistema de análise de testes estáticos de motores de foguete
desenvolvido pela equipe **Serra Rocketry (UERJ)**.

## Índice

| Documento | Descrição |
|-----------|-----------|
| [architecture.md](architecture.md) | Visão geral da arquitetura, componentes e fluxo de dados |
| [data-format.md](data-format.md) | Formato do CSV gerado pelo firmware do *thrust stand* |
| [installation.md](installation.md) | Instalação local e deploy via Docker |
| [cli.md](cli.md) | Uso do CLI de análise rápida de campo |
| [api.md](api.md) | Referência das rotas web (HTTP) |
| [backend.md](backend.md) | Referência dos módulos de processamento (`backend/`) |
| [development.md](development.md) | Lint, testes, convenções e contribuição |

## O que é o projeto

Aplicação **web (Flask) + CLI** para análise de dados de testes estáticos de motores
de foguete. A partir de um CSV gerado pela bancada de empuxo (*thrust stand* com
ESP32 + célula de carga HX711 + sensor de pressão), o sistema:

- Calcula **impulso total** (integração de Simpson), empuxo médio/máximo, pressão
  média/máxima, duração de queima e a **classe do motor** (padrão NAR/TRA: 1/4A → M);
- Gera **visualizações interativas** das curvas de empuxo e pressão;
- Permite **filtragem interativa** de dados brutos (limiar + intervalo de tempo);
- Produz **relatório PDF** profissional (ReportLab), gráfico PNG e CSVs;
- Oferece um **CLI** para insights imediatos em campo, sem subir o servidor.

## Diagrama rápido

```
┌─────────────────┐     CSV      ┌──────────────────────┐
│  Thrust Stand   │ ───────────► │   Análise Flask      │
│ ESP32 + HX711   │ Tempo,Empuxo │                      │
│ + sensor pressão│   ,Pressao   │  ┌────────────────┐  │
└─────────────────┘              │  │  Web (Flask)   │  │
                                 │  │  porta 5000    │  │
                                 │  └────────────────┘  │
                                 │  ┌────────────────┐  │
                                 │  │  CLI (cli.py)  │  │
                                 │  └────────────────┘  │
                                 │           │          │
                                 │           ▼          │
                                 │  CSV · PNG · PDF      │
                                 └──────────────────────┘
```

Para começar rapidamente, veja [installation.md](installation.md).
