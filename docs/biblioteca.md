# Biblioteca de Testes

A **Biblioteca** é o sistema de persistência e organização dos testes estáticos.
Cada motor testado é armazenado como uma entrada na biblioteca, com metadados
estruturados e arquivos associados.

## Estrutura de diretórios

```
data/biblioteca/
├── H12.5-20.0_2025-06-15/          # pasta = nome do motor
│   ├── motor.json                   # metadados estruturados
│   ├── H12.5-20.0_resultados.csv    # métricas em CSV
│   ├── H12.5-20.0_dados.csv         # dados completos
│   ├── H12.5-20.0_grafico.png       # gráfico das curvas
│   ├── H12.5-20.0.pdf               # relatório PDF
│   ├── openmotor.eng                # arquivo .eng (upload opcional)
│   └── foto_20250615_143000.jpg     # foto do teste (upload opcional)
└── ...
```

## Schema do `motor.json`

O arquivo `motor.json` é a fonte de verdade para os metadados de um motor.
Ele é lido dinamicamente para popular a interface web e o CLI.

```json
{
  "nome": "H12.5-20.0",
  "data_teste": "2025-06-15T14:30:00",
  "impulso_total_Ns": 249.81,
  "empuxo_medio_N": 12.49,
  "empuxo_maximo_N": 19.62,
  "empuxo_minimo_N": null,
  "pressao_maxima_MPa": 5.0,
  "pressao_media_MPa": 3.167,
  "duracao_s": 20.0,
  "classe": "H12.5-20.0",
  "pontos_amostrais": 200,
  "csv_original": "H12.5-20.0_dados.csv",
  "resultados_csv": "H12.5-20.0_resultados.csv",
  "grafico_png": "H12.5-20.0_grafico.png",
  "relatorio_pdf": "H12.5-20.0.pdf",
  "openmotor_eng": "openmotor.eng",
  "openmotor_dados": {
    "designation": "F32",
    "diameter_mm": 24.0,
    "length_mm": 124.0,
    "delays": "5-10-15",
    "propellant_mass_kg": 0.0377,
    "total_mass_kg": 0.0695,
    "manufacturer": "RV",
    "thrust_curve": [{"time_s": 0.01, "thrust_N": 50.0}],
    "max_thrust_N": 56.0,
    "total_impulse_Ns": 78.891,
    "avg_thrust_N": 28.9,
    "burn_time_s": 2.72,
    "isp_seconds": 213.386
  },
  "fotos": ["foto_20250615_143000.jpg"],
  "notas": "Teste realizado com nozzle de aço"
}
```

### Campos

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `nome` | string | Nome do motor (usado como nome da pasta) |
| `data_teste` | string (ISO 8601) | Data/hora do teste |
| `impulso_total_Ns` | float | Impulso total em N·s |
| `empuxo_medio_N` | float | Empuxo médio em N |
| `empuxo_maximo_N` | float | Empuxo máximo em N |
| `pressao_maxima_MPa` | float | Pressão máxima em MPa |
| `pressao_media_MPa` | float | Pressão média em MPa |
| `duracao_s` | float | Duração da queima em s |
| `classe` | string | Classificação NAR/TRA |
| `pontos_amostrais` | int | Número de amostras |
| `csv_original` | string | Nome do arquivo CSV de dados |
| `resultados_csv` | string | Nome do arquivo CSV de resultados |
| `grafico_png` | string | Nome do arquivo PNG |
| `relatorio_pdf` | string | Nome do arquivo PDF |
| `openmotor_eng` | string | Nome do arquivo .eng (se existir) |
| `openmotor_dados` | object | Dados extraídos do .eng (ver abaixo) |
| `fotos` | string[] | Lista de fotos do teste |
| `notas` | string | Campo livre para observações |

### `openmotor_dados` (extraído do .eng)

Quando um arquivo `.eng` é carregado, o parser RASP extrai automaticamente:

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `designation` | string | Designação do motor (ex: "F32") |
| `diameter_mm` | float | Diâmetro em mm |
| `length_mm` | float | Comprimento em mm |
| `delays` | string | Tempos de delay |
| `propellant_mass_kg` | float | Massa de propelente em kg |
| `total_mass_kg` | float | Massa total em kg |
| `manufacturer` | string | Fabricante |
| `thrust_curve` | array | Curva de empuxo `[{time_s, thrust_N}]` |
| `max_thrust_N` | float | Empuxo máximo |
| `total_impulse_Ns` | float | Impulso total (Simpson) |
| `avg_thrust_N` | float | Empuxo médio |
| `burn_time_s` | float | Tempo de queima |
| `isp_seconds` | float | Isp teórico |

## Formato de entrada `.eng` (RASP)

O formato RASP é o padrão para intercâmbio de dados de motores de foguete.
Especificação: https://www.thrustcurve.org/info/raspformat.html

Exemplo:

```
; Comentários começam com ;
F32 24 124 5-10-15 .0377 .0695 RV
   0.01 50
   0.05 56
   0.10 48
   2.00 24
   2.20 19
   2.24  5
   2.72  0
```

**Header line** (7 campos separados por espaços):
1. Designação
2. Diâmetro (mm)
3. Comprimento (mm)
4. Delays
5. Massa propelente (kg)
6. Massa total (kg)
7. Fabricante

**Data points**: pares `tempo(s) empuxo(N)`, um por linha.

## Rotas da API

| Método | Path | Descrição |
|--------|------|-----------|
| GET | `/biblioteca` | Grid de motores (ordenado por data/impulso/classe) |
| GET | `/biblioteca/<nome>` | Detalhe do motor (tabela + arquivos + preview) |
| POST | `/biblioteca/<nome>/upload` | Upload de .eng ou foto |
| GET | `/biblioteca/<nome>/file/<filename>` | Download/preview de arquivo |
| POST | `/biblioteca/<nome>/delete` | Remover motor (pasta inteira) |
| POST | `/biblioteca/<nome>/delete_file/<filename>` | Remover arquivo individual |
| POST | `/biblioteca/<nome>/update_notes` | Atualizar notas (AJAX) |
| POST | `/biblioteca/migrate` | Migrar dados legados de `data/motor_result/` |

### Query parameters

- `sort`: `data` (padrão), `impulso`, `classe`

## CLI

```bash
# Listar todos os motores
python app/cli.py biblioteca list

# Detalhes de um motor
python app/cli.py biblioteca info "Motor_SR1500_Nozzle Aço"

# Preview de um .eng sem salvar
python app/cli.py biblioteca eng arquivo.eng
```

## Migração de dados legados

Os dados anteriores a 2025-06 eram salvos em `data/motor_result/` como arquivos
avulsos. A migração agrupa os arquivos por prefixo e cria entradas na biblioteca:

```bash
# Via web
curl -X POST http://localhost:5000/serra-rocketry/biblioteca/migrate

# Via CLI (usa o mesmo mecanismo)
python app/cli.py biblioteca migrate
```

A migração é idempotente: executar duas vezes não duplica dados.
