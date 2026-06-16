# CLI — Análise Rápida de Campo

O `app/cli.py` extrai os principais insights de um CSV de teste estático
**sem precisar subir o servidor web** — ideal para conferir resultados
rapidamente em campo.

## Uso básico

```bash
python app/cli.py teste.csv
```

Também funciona como módulo:

```bash
python -m app.cli teste.csv
```

## Opções

| Opção          | Descrição                                                        |
|----------------|------------------------------------------------------------------|
| `csv`          | (obrigatório) Caminho do arquivo CSV de teste estático           |
| `--json`       | Saída em JSON, para integração com outros scripts                |
| `--save NOME`  | Salva a análise completa (CSV + gráfico PNG + relatório PDF)     |
| `--no-color`   | Desativa as cores ANSI (útil para logs/redirecionamento)         |
| `-h`, `--help` | Mostra a ajuda                                                   |

## Exemplos

### Relatório no terminal

```bash
python app/cli.py teste.csv
```

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
  Pontos Amostrais......        201
  ────────────────────────────────────────────────────────
  Curva de empuxo:
  ▁▁▁▂▂▃▃▃▄▄▅▅▅▆▆▆▆▇▇▇▇▇▇▇▇█▇▇▇▇▇▇▇▇▆▆▆▆▅▅▅▄▄▃▃▃▂▂▁▁
  0s                                            20.0s
```

### Saída JSON

```bash
python app/cli.py teste.csv --json
```

```json
{
  "Impulso [N*s]": 249.81,
  "Empuxo max [N]": 19.62,
  "Empuxo medio [N]": 12.491,
  "Pressao max [MPa]": 5.0,
  "Pressao media [MPa]": 3.167,
  "Pontos amostrais": 201,
  "Duracao [s]": 20.0,
  "Classe": "H12.5-20.0"
}
```

Combinável com ferramentas como `jq`:

```bash
python app/cli.py teste.csv --json | jq '.Classe'
```

### Salvar análise completa

```bash
python app/cli.py teste.csv --save Motor_SR1500
```

Gera em `app/data/motor_result/`:

- `Motor_SR1500_resultados.csv`
- `Motor_SR1500_dados.csv`
- `Motor_SR1500_grafico.png`
- `Motor_SR1500.pdf`

## Códigos de saída

| Código | Significado                                       |
|--------|---------------------------------------------------|
| `0`    | Sucesso                                           |
| `1`    | Erro: arquivo não encontrado ou CSV inválido      |

Isso permite uso em scripts:

```bash
if python app/cli.py teste.csv --json > resultado.json; then
    echo "Análise concluída"
else
    echo "Falha na análise" >&2
fi
```

## Insights retornados

- **Classe do motor** (padrão NAR/TRA);
- **Impulso total** (integração de Simpson);
- **Empuxo médio** e **máximo**;
- **Pressão média** e **máxima**;
- **Tempo de queima** (duração);
- **Pontos amostrais**;
- **Sparkline** ASCII da curva de empuxo (apenas no modo terminal).

## Detecção automática de cores

As cores ANSI são desativadas automaticamente quando a saída **não** é um
terminal interativo (ex.: quando redirecionada para arquivo ou *pipe*). Use
`--no-color` para forçar a desativação mesmo em terminal.
