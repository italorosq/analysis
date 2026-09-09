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
from backend.deps import ensure_dependencies  # pylint: disable=wrong-import-position


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


def analyze(csv_path, as_json=False, save=None, no_color=False, units="kg", remove_outliers=False, out_dir=None):
    """Processa um CSV de teste estático e imprime/salva os insights.

    É a função central do CLI: carrega o arquivo via
    :class:`~backend.analises.motor_analisys`, calcula as métricas e emite o
    resultado em formato legível ou JSON, opcionalmente salvando a análise
    completa (CSV + gráfico + PDF).

    Args:
        csv_path: Caminho do arquivo CSV de teste estático.
        as_json: Se ``True``, imprime o resultado como JSON em vez do
            relatório formatado.
        save: Se informado, nome base para salvar a análise completa.
        no_color: Se ``True``, desativa as cores ANSI na saída.
        units: Unidade de medida do empuxo (``'kg'`` ou ``'g'``).
        remove_outliers: Se ``True``, remove outliers antes da análise.
        out_dir: Diretório de destino para ``save`` (padrão:
            ``data/motor_result`` ou biblioteca, se já registrado).

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
        motor = motor_analisys(csv_path, units=units)
    except Exception as e:  # pylint: disable=broad-except
        print(f"{C.RED}Erro ao processar o CSV: {e}{C.RESET}", file=sys.stderr)
        print(
            f"{C.DIM}Verifique se o arquivo tem o cabeçalho 'Tempo,Empuxo,Pressao'.{C.RESET}",
            file=sys.stderr,
        )
        return 1

    outliers_removed = 0
    if remove_outliers:
        outliers_removed = motor.remove_outliers()

    result = motor.get_result()
    df = motor.get_data()

    if as_json:
        if remove_outliers:
            result["Outliers removidos"] = outliers_removed
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        _print_report(csv_path, result, df, outliers_removed)

    if save:
        try:
            ensure_dependencies(["matplotlib", "reportlab"])
        except RuntimeError as e:
            print(
                f"{C.RED}Não foi possível salvar a análise completa.{C.RESET}",
                file=sys.stderr,
            )
            print(f"{C.DIM}{e}{C.RESET}", file=sys.stderr)
            return 1
        motor.save_analisys(save, output_dir=out_dir)
        if not as_json:
            print(
                f"\n{C.GREEN}✓ Análise completa salva (CSV + gráfico + PDF) "
                f"em {out_dir or 'data/motor_result'}/{C.RESET}"
            )

    return 0


def _print_report(csv_path, r, df, outliers_removed=0):
    """Imprime o relatório formatado e colorido no terminal.

    Args:
        csv_path: Caminho do CSV analisado (usado no cabeçalho).
        r: Dicionário de resultados retornado por
            :meth:`~backend.analises.motor_analisys.get_result`.
        df: DataFrame com os dados (usado para o sparkline da curva de empuxo).
        outliers_removed: Número de outliers removidos (opcional).
    """
    line = "─" * 56
    print()
    print(f"{C.MAGENTA}{C.BOLD}╔{'═' * 54}╗{C.RESET}")
    print(
        f"{C.MAGENTA}{C.BOLD}║   ANÁLISE RÁPIDA DE CAMPO · Serra Rocketry           ║{C.RESET}"
    )
    print(f"{C.MAGENTA}{C.BOLD}╚{'═' * 54}╝{C.RESET}")
    print(f"{C.DIM}Arquivo: {csv_path.name}{C.RESET}")
    if outliers_removed > 0:
        print(f"{C.YELLOW}⚠  Outliers removidos: {outliers_removed} pontos{C.RESET}")
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
    """Ponto de entrada do CLI. Analisa argumentos e executa o comando.

    Supports two modes:
        * ``analyze-campo <csv>`` -- analyze a CSV file (default mode).
        * ``analise-campo biblioteca list|info <nome>|eng <file>`` -- library operations.

    Args:
        argv: Lista de argumentos (padrão: ``sys.argv[1:]``).

    Returns:
        int: Código de saída.
    """
    # Garante UTF-8 no stdout/stderr (Windows usa cp1252 por padrão, que
    # quebra os caracteres Unicode do banner e de acentos em mensagens).
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    if argv is None:
        argv = sys.argv[1:]

    # Check if user invoked the "biblioteca" subcommand
    if len(argv) > 0 and argv[0] == "biblioteca":
        return _main_biblioteca(argv[1:])

    return _main_analyze(argv)


def _main_analyze(argv) -> int:
    """Main entry point for the original analyze-campo command.

    Args:
        argv: Argument list (excluding program name).

    Returns:
        int: Exit code.
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
        "--out",
        metavar="DIR",
        help="Diretório de destino para --save (padrão: data/motor_result)",
    )
    parser.add_argument(
        "--no-color", action="store_true", help="Desativa cores ANSI na saída"
    )
    parser.add_argument(
        "--units",
        choices=["kg", "g"],
        default="kg",
        help="Unidade do empuxo: kg (padrão) ou g (gramas)",
    )
    parser.add_argument(
        "--remove-outliers",
        action="store_true",
        help="Remove outliers via filtro percentil (P99) antes da análise",
    )
    args = parser.parse_args(argv)

    return analyze(
        args.csv,
        as_json=args.json,
        save=args.save,
        no_color=args.no_color,
        units=args.units,
        remove_outliers=args.remove_outliers,
        out_dir=args.out,
    )


def _main_biblioteca(argv) -> int:
    """Main entry point for the ``biblioteca`` subcommand.

    Args:
        argv: Argument list after ``biblioteca``.

    Returns:
        int: Exit code.
    """
    if len(argv) == 0:
        print("Uso: analise-campo biblioteca <list|info NOME|eng ARQUIVO>")
        return 1

    subcmd = argv[0]

    if subcmd == "list":
        return _biblioteca_list()
    elif subcmd == "info":
        if len(argv) < 2:
            print("Uso: analise-campo biblioteca info <NOME>")
            return 1
        return _biblioteca_info(argv[1])
    elif subcmd == "eng":
        if len(argv) < 2:
            print("Uso: analise-campo biblioteca eng <ARQUIVO>")
            return 1
        return _biblioteca_eng(argv[1])
    else:
        print(f"Comando desconhecido: {subcmd}")
        return 1


def _biblioteca_list() -> int:
    """List all motors in the library.

    Returns:
        int: Exit code (0 on success).
    """
    from backend.biblioteca import scan_library

    motors = scan_library(sort_by="data")

    if not motors:
        print("Biblioteca vazia.")
        return 0

    line = "─" * 70
    print()
    print(f"{C.MAGENTA}{C.BOLD}╔{'═' * 68}╗{C.RESET}")
    print(f"{C.MAGENTA}{C.BOLD}║   BIBLIOTECA DE TESTES · Serra Rocketry{' ' * 27}║{C.RESET}")
    print(f"{C.MAGENTA}{C.BOLD}╚{'═' * 68}╝{C.RESET}")
    print()
    print(f"  {'Nome':<30} {'Data':<12} {'Classe':<14} {'Impulso [N·s]':>14}")
    print(f"  {C.CYAN}{line}{C.RESET}")

    for m in motors:
        date_str = m.data_teste[:10] if m.data_teste else "---"
        print(
            f"  {m.nome:<30} {C.DIM}{date_str:<12}{C.RESET} "
            f"{m.classe:<14} {C.YELLOW}{m.impulso_total_Ns:>14.3f}{C.RESET}"
        )

    print(f"  {C.CYAN}{line}{C.RESET}")
    print(f"  {C.DIM}{len(motors)} motor(es) encontrado(s){C.RESET}")
    print()
    return 0


def _biblioteca_info(nome: str) -> int:
    """Show detailed info for a specific motor.

    Args:
        nome: Motor name.

    Returns:
        int: Exit code (0 on success, 1 on error).
    """
    from backend.biblioteca import get_motor, list_files

    motor = get_motor(nome)
    if motor is None:
        print(f"{C.RED}Motor não encontrado: {nome}{C.RESET}", file=sys.stderr)
        return 1

    files = list_files(nome)

    line = "─" * 56
    print()
    print(f"{C.MAGENTA}{C.BOLD}╔{'═' * 54}╗{C.RESET}")
    print(f"{C.MAGENTA}{C.BOLD}║   {motor.nome:^48}   ║{C.RESET}")
    print(f"{C.MAGENTA}{C.BOLD}╚{'═' * 54}╝{C.RESET}")
    print()

    # Results table
    print(f"  {C.BOLD}CLASSE:{C.RESET}  {C.GREEN}{motor.classe}{C.RESET}")
    print(f"  {C.CYAN}{line}{C.RESET}")

    rows = [
        ("Impulso Total", f"{motor.impulso_total_Ns:.3f}", "N·s"),
        ("Empuxo Médio", f"{motor.empuxo_medio_N:.3f}", "N"),
        ("Empuxo Máximo", f"{motor.empuxo_maximo_N:.3f}", "N"),
        ("Pressão Média", f"{motor.pressao_media_MPa:.3f}", "MPa"),
        ("Pressão Máxima", f"{motor.pressao_maxima_MPa:.3f}", "MPa"),
        ("Duração", f"{motor.duracao_s:.2f}", "s"),
        ("Pontos Amostrais", str(motor.pontos_amostrais), ""),
    ]
    for label, value, unit in rows:
        print(f"  {label:.<22} {C.YELLOW}{value:>10}{C.RESET} {C.DIM}{unit}{C.RESET}")

    # OpenMotor data
    if motor.openmotor_dados:
        eng = motor.openmotor_dados
        print()
        print(f"  {C.BOLD}DADOS OPENMOTOR:{C.RESET}")
        print(f"  {C.CYAN}{line}{C.RESET}")
        eng_rows = [
            ("Designação", eng.get("designation", "---")),
            ("Fabricante", eng.get("manufacturer", "---")),
            ("Diâmetro", f"{eng.get('diameter_mm', 0):.0f} mm"),
            ("Comprimento", f"{eng.get('length_mm', 0):.0f} mm"),
            ("Massa Propelente", f"{eng.get('propellant_mass_kg', 0):.4f} kg"),
            ("Massa Total", f"{eng.get('total_mass_kg', 0):.4f} kg"),
            ("Isp Teórico", f"{eng.get('isp_seconds', '---')} s"),
            ("Impulso (ENG)", f"{eng.get('total_impulse_Ns', 0):.3f} N·s"),
        ]
        for label, value in eng_rows:
            print(f"  {label:.<22} {C.YELLOW}{value}{C.RESET}")

    # Files
    print()
    print(f"  {C.BOLD}ARQUIVOS:{C.RESET}")
    print(f"  {C.CYAN}{line}{C.RESET}")
    all_files = []
    for category in ("csv", "png", "pdf", "eng", "fotos"):
        all_files.extend(files.get(category, []))
    if all_files:
        for fname in all_files:
            print(f"  • {fname}")
    else:
        print(f"  {C.DIM}(nenhum){C.RESET}")

    print(f"  {C.CYAN}{line}{C.RESET}")
    print()
    return 0


def _biblioteca_eng(filepath: str) -> int:
    """Preview data from an .eng file without saving.

    Args:
        filepath: Path to the .eng file.

    Returns:
        int: Exit code (0 on success, 1 on error).
    """
    from pathlib import Path

    from backend.parser_eng import parse_eng_file

    path = Path(filepath)
    if not path.exists():
        print(f"{C.RED}Arquivo não encontrado: {filepath}{C.RESET}", file=sys.stderr)
        return 1

    try:
        eng = parse_eng_file(path)
    except (ValueError, FileNotFoundError) as e:
        print(f"{C.RED}Erro ao ler .eng: {e}{C.RESET}", file=sys.stderr)
        return 1

    line = "─" * 44
    print()
    print(f"{C.MAGENTA}{C.BOLD}╔{'═' * 42}╗{C.RESET}")
    print(f"{C.MAGENTA}{C.BOLD}║   PREVIEW .eng · Serra Rocketry{' ' * 10}║{C.RESET}")
    print(f"{C.MAGENTA}{C.BOLD}╚{'═' * 42}╝{C.RESET}")
    print()
    print(f"  Designação:      {C.GREEN}{eng.designation}{C.RESET}")
    print(f"  Fabricante:      {eng.manufacturer}")
    print(f"  Diâmetro:        {eng.diameter_mm} mm")
    print(f"  Comprimento:     {eng.length_mm} mm")
    print(f"  Delays:          {eng.delays}")
    print(f"  {C.CYAN}{line}{C.RESET}")
    print(f"  Massa Propelente: {eng.propellant_mass_kg:.4f} kg")
    print(f"  Massa Total:      {eng.total_mass_kg:.4f} kg")
    print(f"  {C.CYAN}{line}{C.RESET}")
    print(f"  Empuxo Máximo:    {C.YELLOW}{eng.max_thrust_N:.1f} N{C.RESET}")
    print(f"  Impulso Total:    {C.YELLOW}{eng.total_impulse_Ns:.3f} N·s{C.RESET}")
    print(f"  Isp Teórico:      {eng.isp_seconds or '---'} s")
    print(f"  Pontos de dados:  {len(eng.thrust_curve)}")
    print(f"  {C.CYAN}{line}{C.RESET}")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
