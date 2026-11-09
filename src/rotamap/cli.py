import logging
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.logging import RichHandler

from rotamap import __version__

app = typer.Typer(
    name="rotamap",
    help="Gera mapas de rotas por município e uma apresentação PowerPoint interativa.",
    no_args_is_help=True,
    add_completion=False,
)

log = logging.getLogger("rotamap")
console = Console(stderr=True)

Entrada = Annotated[Path, typer.Argument(exists=True, dir_okay=False, help="CSV de entrada.")]
Saida = Annotated[Path, typer.Option("--out", "-o", help="Pasta de saída.")]
Uf = Annotated[str, typer.Option("--uf", help="Sigla da UF, ex.: SP.")]
Formato = Annotated[str, typer.Option("--formato", help="Formato da entrada: tidy ou erp_914.")]


def configurar_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=console, show_path=False)],
        force=True,
    )


def _mostrar_versao(valor: bool) -> None:
    if valor:
        typer.echo(f"rotamap {__version__}")
        raise typer.Exit


def _nao_implementado(etapa: str) -> None:
    log.error("a etapa '%s' ainda não foi implementada", etapa)
    raise typer.Exit(code=1)


@app.callback()
def principal(
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Log detalhado.")] = False,
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=_mostrar_versao,
            is_eager=True,
            help="Mostra a versão e sai.",
        ),
    ] = False,
) -> None:
    configurar_logging(verbose)


@app.command()
def run(
    entrada: Entrada,
    uf: Uf,
    out: Saida = Path("saida"),
    formato: Formato = "tidy",
    no_ppt: Annotated[bool, typer.Option("--no-ppt", help="Gera só os mapas.")] = False,
) -> None:
    """Roda o pipeline completo: parse, geo, maps e ppt."""
    _nao_implementado("run")


@app.command()
def parse(entrada: Entrada, out: Saida = Path("saida"), formato: Formato = "tidy") -> None:
    """Lê a entrada e grava rotas.json normalizado."""
    _nao_implementado("parse")


@app.command()
def geo(
    rotas: Annotated[Path, typer.Argument(exists=True, dir_okay=False, help="rotas.json.")],
    uf: Uf,
) -> None:
    """Associa os municípios à malha do IBGE e grava rotas_geo.gpkg."""
    _nao_implementado("geo")


@app.command()
def maps(
    rotas_geo: Annotated[Path, typer.Argument(exists=True, dir_okay=False, help="rotas_geo.gpkg.")],
) -> None:
    """Renderiza o mapa da capa, o do menu, os hotspots e um mapa por rota."""
    _nao_implementado("maps")


@app.command()
def ppt(
    pasta: Annotated[Path, typer.Argument(exists=True, file_okay=False, help="Pasta de saída.")],
) -> None:
    """Monta a apresentação a partir dos artefatos gerados."""
    _nao_implementado("ppt")
