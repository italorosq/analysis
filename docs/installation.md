# Instalação e Deploy

## Requisitos

- Python 3.12+
- pip / venv
- (Opcional) Docker + Docker Compose para produção

## Instalação local

```bash
# 1. Clone o repositório
git clone https://github.com/SerraRocketry/Analise_Flask.git
cd Analise_Flask

# 2. Crie e ative um ambiente virtual
python3 -m venv .venv
source .venv/bin/activate        # Linux/Mac
# .venv\Scripts\activate         # Windows

# 3. Instale as dependências de produção
pip install -r app/requirements.txt
```

Para desenvolvimento (lint + testes), instale também:

```bash
pip install -r app/requirements-dev.txt
```

## Dependências de produção

| Pacote      | Versão    | Uso                                |
|-------------|-----------|------------------------------------|
| Flask       | 3.1.0     | Framework web                      |
| reportlab   | 4.2.5     | Geração de relatórios PDF          |
| matplotlib  | 3.10.1    | Gráficos PNG                       |
| pandas      | 2.2.3     | Manipulação de dados               |
| scipy       | 1.15.2    | Integração (Simpson) e splines     |
| gunicorn    | 23.0.0    | Servidor WSGI de produção          |

## Executando em desenvolvimento

```bash
python app/app.py
```

A aplicação fica disponível em:

```
http://127.0.0.1:5000/serra-rocketry
```

O modo debug está ativo, com reload automático ao alterar templates, CSS ou JS.

> Para acesso de outros dispositivos na rede, use o IP da máquina host
> (o servidor escuta em `0.0.0.0:5000`).

## Executando em produção (gunicorn)

```bash
cd app
gunicorn wsgi:app -c gunicorn.conf.py
```

A configuração (`app/gunicorn.conf.py`) define:

- `bind = "0.0.0.0:5000"`
- `workers = 2`
- Logs em `persistence/logs/access.log` e `persistence/logs/error.log`
- Reload automático observando templates/CSS/JS

> **Importante:** defina a variável de ambiente `SECRET_KEY` em produção:
> ```bash
> export SECRET_KEY="uma-chave-secreta-forte-e-aleatoria"
> ```

## Deploy com Docker

O `Dockerfile` usa build multi-estágio e roda como usuário não-root.

```bash
cd app
docker compose up --build
```

O `compose.yml`:

- Expõe a porta `5000`;
- Monta volumes `./persistence` e `./data` para persistência;
- Define `restart: unless-stopped`;
- Inclui *healthcheck* na rota raiz do app.

Para passar a `SECRET_KEY`, defina-a no ambiente antes de subir o compose ou
edite o `compose.yml`.

### Build manual da imagem

```bash
cd app
docker build -t serra-rocketry .
docker run -p 5000:5000 -e SECRET_KEY="..." serra-rocketry
```

## Verificação pós-instalação

```bash
# Rodar os testes do backend
cd app && python -m pytest tests/ -v

# Testar o CLI com um CSV de exemplo
python app/cli.py caminho/para/teste.csv
```
