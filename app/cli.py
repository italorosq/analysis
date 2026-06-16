#!/usr/bin/env python3
"""
Análise Rápida de Campo - Serra Rocketry

CLI para extrair rapidamente os principais insights de um arquivo CSV
de teste estático, sem precisar subir o servidor web.

Formato esperado do CSV (gerado pelo firmware do thrust stand):
    Tempo,Empuxo,Pressao
    - Tempo  = milissegundos desde o boot (int)
    - Empuxo = empuxo medido em kg (float)
    - Pressao = pressão da câmara em MPa (float)

Uso:
    python -m app.cli teste.csv
    python app/cli.py teste.csv --json
    python app/cli.py teste.csv --save analise_campo
"""

import argparse
import json
import sys
from pathlib import Path

# Allow running both as module (python -m app.cli) and as script (python app/cli.py)
sys.path.insert(0, str(Path(__file__).resolve().parent))

from backend import motor_analisys  # noqa: E402  # pylint: disable=wrong-import-position


# ANSI colors (disabled automatically when output is not a TTY)
class C:
    """Códigos de escape ANSI para colorir a saída no terminal.

    Os atributos de classe são strings de escape ANSI. Quando a saída não é um
    terminal interativo (ou ``--no-color`` é usado), :meth:`disable` zera todos
    os códigos, tornando a saída texto puro.
    """

    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    CYAN = "\033[36m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    RED = "\033[31m"

    @classmethod
    def disable(cls):
        """Zera todos os códigos de cor (saída em texto puro)."""
        for attr in dir(cls):
            if not attr.startswith("_") and attr.isupper():
                setattr(cls, attr, "")


def _sparkline(values, width=50):
    """Gera um *sparkline* unicode da curva de empuxo.

    Reamostra a série de valores para ``width`` colunas e mapeia cada valor
    para um dos 8 caracteres de bloco (``▁``..``█``) conforme sua amplitude
    relativa, produzindo um mini-gráfico de uma linha para o terminal.

    Args:
        values: Sequência de valores numéricos (ex.: empuxo em N).
        width: Número de colunas do sparkline.

    Returns:
        str: String de caracteres de bloco, ou string vazia se ``values``
        estiver vazio.
    """
    blocks = "▁▂▃▄▅▆▇█"
    if len(values) == 0:
        return ""
    vmin, vmax = min(values), max(values)
    span = (vmax - vmin) or 1
    # Reamostra para `width` colunas
    n = len(values)
    out = []
    for i in range(width):
        idx = int(i * n / width)
        v = values[idx]
        level = int((v - vmin) / span * (len(blocks) - 1))
        out.append(blocks[level])
    return "".join(out)


def analyze(csv_path, as_json=False, save=None, no_color=False):
    """Processa um CSV de teste estático e imprime/salva os insights.

    É a função central do CLI: carrega o arquivo via
    :class:`~backend.analises.motor_analisys`, calcula as métricas e emite o
    resultado em formato legível ou JSON, opcionalmente salvando a análise
    completa (CSV + gráfico + PDF).

    Args:
        csv_path: Caminho do arquivo CSV de teste estático.
        as_json: Se ``True``, imprime o resultado como JSON em vez do
            relatório formatado.
        save: Se informado, nome base para salvar a análise completa em
            ``data/motor_result/``.
        no_color: Se ``True``, desativa as cores ANSI na saída.

    Returns:
        int: Código de saída (0 em sucesso; 1 em erro de arquivo/parsing).
    """
    if no_color or not sys.stdout.isatty():
        C.disable()

    csv_path = Path(csv_path)
    if not csv_path.exists():
        print(
            f"{C.RED}Erro: arquivo não encontrado: {csv_path}{C.RESET}", file=sys.stderr
        )
        return 1

    try:
        motor = motor_analisys(csv_path)
    except Exception as e:  # pylint: disable=broad-except
        print(f"{C.RED}Erro ao processar o CSV: {e}{C.RESET}", file=sys.stderr)
        print(
            f"{C.DIM}Verifique se o arquivo tem o cabeçalho 'Tempo,Empuxo,Pressao'.{C.RESET}",
            file=sys.stderr,
        )
        return 1

    result = motor.get_result()
    df = motor.get_data()

    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        _print_report(csv_path, result, df)

    if save:
        motor.save_analisys(save)
        if not as_json:
            print(
                f"\n{C.GREEN}✓ Análise completa salva (CSV + gráfico + PDF) "
                f"em data/motor_result/{C.RESET}"
            )

    return 0


def _print_report(csv_path, r, df):
    """Imprime o relatório formatado e colorido no terminal.

    Args:
        csv_path: Caminho do CSV analisado (usado no cabeçalho).
        r: Dicionário de resultados retornado por
            :meth:`~backend.analises.motor_analisys.get_result`.
        df: DataFrame com os dados (usado para o sparkline da curva de empuxo).
    """
    line = "─" * 56
    print()
    print(f"{C.MAGENTA}{C.BOLD}╔{'═' * 54}╗{C.RESET}")
    print(
        f"{C.MAGENTA}{C.BOLD}║   ANÁLISE RÁPIDA DE CAMPO · Serra Rocketry           ║{C.RESET}"
    )
    print(f"{C.MAGENTA}{C.BOLD}╚{'═' * 54}╝{C.RESET}")
    print(f"{C.DIM}Arquivo: {csv_path.name}{C.RESET}")
    print()

    # Highlight: motor class
    print(
        f"  {C.BOLD}CLASSE DO MOTOR:{C.RESET}  {C.GREEN}{C.BOLD}{r['Classe']}{C.RESET}"
    )
    print(f"  {C.CYAN}{line}{C.RESET}")

    rows = [
        ("Impulso Total", f"{r['Impulso [N*s]']:.3f}", "N·s", C.YELLOW),
        ("Empuxo Médio", f"{r['Empuxo medio [N]']:.3f}", "N", C.BLUE),
        ("Empuxo Máximo", f"{r['Empuxo max [N]']:.3f}", "N", C.BLUE),
        ("Pressão Média", f"{r['Pressao media [MPa]']:.3f}", "MPa", C.CYAN),
        ("Pressão Máxima", f"{r['Pressao max [MPa]']:.3f}", "MPa", C.CYAN),
        ("Tempo de Queima", f"{r['Duracao [s]']:.2f}", "s", C.GREEN),
        ("Pontos Amostrais", f"{r['Pontos amostrais']}", "", C.DIM),
    ]
    for label, value, unit, color in rows:
        print(
            f"  {label:.<22} {color}{C.BOLD}{value:>10}{C.RESET} {C.DIM}{unit}{C.RESET}"
        )

    print(f"  {C.CYAN}{line}{C.RESET}")

    # Sparkline of thrust curve
    spark = _sparkline(df["Empuxo_N"].tolist(), width=50)
    print(f"  {C.DIM}Curva de empuxo:{C.RESET}")
    print(f"  {C.YELLOW}{spark}{C.RESET}")
    print(f"  {C.DIM}0s{' ' * 44}{r['Duracao [s]']:.1f}s{C.RESET}")
    print()


def main(argv=None):
    """Ponto de entrada do CLI. Analisa argumentos e executa :func:`analyze`.

    Args:
        argv: Lista de argumentos (padrão: ``sys.argv[1:]``).

    Returns:
        int: Código de saída passado por :func:`analyze`.
    """
    parser = argparse.ArgumentParser(
        prog="analise-campo",
        description="Análise rápida de campo de um CSV de teste estático (Serra Rocketry).",
    )
    parser.add_argument("csv", help="Caminho do arquivo CSV de teste estático")
    parser.add_argument(
        "--json", action="store_true", help="Saída em JSON (para integração/scripts)"
    )
    parser.add_argument(
        "--save",
        metavar="NOME",
        help="Salva análise completa (CSV + gráfico + PDF) com o nome dado",
    )
    parser.add_argument(
        "--no-color", action="store_true", help="Desativa cores ANSI na saída"
    )
    args = parser.parse_args(argv)

    return analyze(args.csv, as_json=args.json, save=args.save, no_color=args.no_color)


if __name__ == "__main__":
    sys.exit(main())
