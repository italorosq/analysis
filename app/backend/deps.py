"""Validação de dependências pesadas da aplicação (fail-fast no startup).

Os módulos abaixo são importados de forma *preguiçosa* (dentro de métodos de
plotagem e geração de PDF): o servidor sobe com sucesso mesmo sem eles e só
falha silenciosamente quando o usuário salva — tornando o diagnóstico difícil.
A checagem usa :func:`importlib.util.find_spec` (que **não** importa o módulo)
para detectar tudo logo na inicialização com uma mensagem objetiva.
"""

import importlib.util

_LAZY_DEPENDENCIES: dict[str, str] = {
    "numpy": "análise numérica",
    "pandas": "processamento de CSV",
    "scipy": "análise do motor",
    "matplotlib": "gráficos PNG",
    "reportlab": "relatório PDF",
}

INSTALL_COMMAND = "pip install -r app/requirements.txt"


def find_missing_dependencies(modules: list[str] | None = None) -> list[str]:
    """Retorna os módulos do conjunto verificado que não estão instalados.

    Args:
        modules: Subconjunto específico a checar (ex.: ``["reportlab"]``).
            ``None`` checa todas as :data:`_LAZY_DEPENDENCIES`.

    Returns:
        list[str]: Nomes dos módulos ausentes (vazio se tudo instalado).
    """
    alvo = list(_LAZY_DEPENDENCIES) if modules is None else list(modules)
    return [name for name in alvo if importlib.util.find_spec(name) is None]


def missing_dependencies_message(missing: list[str]) -> str:
    """Mensagem amigável (pt-BR) para os módulos ausentes.

    Args:
        missing: Nomes dos módulos não encontrados.

    Returns:
        str: Mensagem listando o que falta, para que serve e como instalar.
    """
    detalhes = ", ".join(
        f"{nome} ({_LAZY_DEPENDENCIES.get(nome, 'dependência do projeto')})"
        for nome in missing
    )
    return (
        f"Dependência(s) ausente(s): {detalhes}. "
        f"Instale-as com: {INSTALL_COMMAND}"
    )


def ensure_dependencies(modules: list[str] | None = None) -> None:
    """Lança erro claro se algum módulo do subconjunto estiver ausente.

    Args:
        modules: Subconjunto a validar (``None`` = todos).

    Raises:
        RuntimeError: Com a :func:`missing_dependencies_message` quando algo
            estiver faltando.
    """
    missing = find_missing_dependencies(modules)
    if missing:
        raise RuntimeError(missing_dependencies_message(missing))
