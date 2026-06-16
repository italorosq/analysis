# Desenvolvimento

## Ambiente

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r app/requirements.txt
pip install -r app/requirements-dev.txt
```

## Dependências de desenvolvimento

| Pacote      | Uso                       |
|-------------|---------------------------|
| pylint      | Análise estática          |
| ruff        | Linter rápido + formatador |
| isort       | Ordenação de imports      |
| black       | Formatação                |
| pytest      | Testes                    |
| pytest-cov  | Cobertura de testes       |

## Lint

O projeto mantém **ruff limpo** e **pylint 10.00/10**. A configuração das regras
está em `pyproject.toml` (linha de 100 colunas, supressões justificadas).

```bash
# Ruff (checagem)
ruff check app/

# Ruff (formatação automática)
ruff format app/

# Pylint
pylint app/backend/ app/app.py app/cli.py app/wsgi.py
```

> **Nota:** alguns avisos do pylint são suprimidos intencionalmente no
> `pyproject.toml`:
> - `C0415` (import-outside-toplevel): imports lazy de matplotlib/reportlab/pandas;
> - `W0718` (broad-exception-caught): rotas web capturam tudo para mensagem amigável;
> - `C0103` (invalid-name): `motor_analisys`/`data_treatment` seguem convenção do projeto.

## Testes

A suíte de testes do backend fica em `app/tests/test_backend.py` (23 testes).

```bash
cd app
python -m pytest tests/ -v

# Com cobertura
python -m pytest tests/ --cov=backend --cov-report=term-missing
```

### O que é testado

- Conversões de unidade (kg→N, ms→s, tempo relativo);
- `get_result()`: presença de todas as chaves, impulso > 0, empuxo_máx > médio,
  duração > 0, classe não-vazia;
- `spline()` / `pressure_spline()` retornam objetos `CubicSpline`;
- `plot_analisys()` gera PNG não-vazio;
- `pdf()` gera PDF > 1 KB;
- `data_filter()` filtra corretamente por threshold e intervalo;
- `get_stats()` retorna as chaves esperadas e `samples == len(df)`;
- `save_treatment()` grava o arquivo e retorna caminho válido.

Os testes usam `tmp_path` para não poluir o repositório e o backend `Agg` do
matplotlib.

## Convenções

- **Estilo de docstring:** Google (Args / Returns / Raises / Side Effects);
- **Type hints** nas assinaturas públicas;
- **pathlib** para todos os caminhos (nunca relativo ao cwd);
- **Imports lazy** para bibliotecas pesadas (matplotlib, reportlab) dentro dos
  métodos que as usam;
- **Sem variáveis globais** de estado — usar `session` na camada web.

## Fluxo de contribuição

1. Faça um fork do projeto.
2. Crie uma branch: `git checkout -b feature/nova-feature`.
3. Implemente e garanta lint + testes verdes:
   ```bash
   ruff check app/ && pylint app/backend/ app/app.py app/cli.py && (cd app && python -m pytest tests/)
   ```
4. Commit: `git commit -am 'Adiciona nova feature'`.
5. Push: `git push origin feature/nova-feature`.
6. Abra um Pull Request.

## Gotcha conhecido

Ao rodar ferramentas de linha de comando que mencionem a palavra "gunicorn" no
texto do comando, alguns ambientes com proteção de processos longos podem
bloquear a execução (heurística de servidor). Se isso ocorrer, lint o arquivo
`gunicorn.conf.py` separadamente ou copiando-o para um nome temporário.

## Roadmap

1. Análise de Voo (em desenvolvimento);
2. Estimativa de trajetória;
3. Histórico de testes em banco de dados;
4. API REST documentada (OpenAPI/Swagger).
