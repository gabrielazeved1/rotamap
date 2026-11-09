import logging
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.logging import RichHandler

from rotamap import __version__
from rotamap.config import Config, carregar_config
from rotamap.exemplo import OpcoesExemplo, gerar_exemplo, salvar_csv
from rotamap.geo import ErroIBGE, carregar_malha
from rotamap.pipeline import (
    ArtefatoAusente,
    Pasta,
    etapa_geo,
    etapa_maps,
    etapa_parse,
    etapa_ppt,
    executar,
)

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
ArquivoConfig = Annotated[
    Path | None,
    typer.Option("--config", "-c", exists=True, dir_okay=False, help="Arquivo TOML."),
]
Formato = Annotated[
    str | None, typer.Option("--formato", help="Formato da entrada: tidy ou erp_914.")
]
Uf = Annotated[
    str | None,
    typer.Option("--uf", help="UF para municípios sem UF na entrada; também entra no mapa."),
]


def configurar_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=console, show_path=False)],
        force=True,
    )
    # o pyogrio loga cada camada gravada; ruido para quem usa a cli
    logging.getLogger("pyogrio").setLevel(logging.WARNING)


def _mostrar_versao(valor: bool) -> None:
    if valor:
        typer.echo(f"rotamap {__version__}")
        raise typer.Exit


@contextmanager
def _erros_amigaveis() -> Generator[None, None, None]:
    """erros esperados viram uma mensagem e codigo 1, sem traceback."""
    try:
        yield
    except (ValueError, ErroIBGE, ArtefatoAusente) as erro:
        log.error("%s", erro)
        raise typer.Exit(code=1) from None


def _config(caminho: Path | None, formato: str | None = None, uf: str | None = None) -> Config:
    config = carregar_config(caminho)
    if formato:
        config = replace(config, entrada=replace(config.entrada, formato=formato))
    if uf:
        sigla = uf.upper()
        config = replace(
            config,
            entrada=replace(config.entrada, uf_padrao=sigla),
            geo=replace(config.geo, ufs=(*config.geo.ufs, sigla)),
        )
    return config


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
    out: Saida = Path("saida"),
    config: ArquivoConfig = None,
    formato: Formato = None,
    uf: Uf = None,
    no_ppt: Annotated[bool, typer.Option("--no-ppt", help="Gera só os mapas.")] = False,
) -> None:
    """Roda o pipeline completo: parse, geo, maps e ppt."""
    with _erros_amigaveis():
        executar(entrada, Pasta(out), _config(config, formato, uf), ppt=not no_ppt)
    console.print(f"[green]pronto:[/] {out}")


@app.command()
def parse(
    entrada: Entrada,
    out: Saida = Path("saida"),
    config: ArquivoConfig = None,
    formato: Formato = None,
    uf: Uf = None,
) -> None:
    """Lê a entrada e grava rotas.json."""
    with _erros_amigaveis():
        etapa_parse(entrada, Pasta(out), _config(config, formato, uf))


@app.command()
def geo(out: Saida = Path("saida"), config: ArquivoConfig = None, uf: Uf = None) -> None:
    """Associa os municípios à malha do IBGE: rotas_geo.json, rotas_geo.gpkg e matching.csv."""
    with _erros_amigaveis():
        etapa_geo(Pasta(out), _config(config, uf=uf))


@app.command()
def maps(out: Saida = Path("saida"), config: ArquivoConfig = None) -> None:
    """Renderiza capa, menu com números, hotspots.json e um mapa por rota."""
    with _erros_amigaveis():
        etapa_maps(Pasta(out), _config(config))


@app.command()
def ppt(out: Saida = Path("saida"), config: ArquivoConfig = None) -> None:
    """Monta a apresentação a partir dos artefatos das etapas anteriores."""
    with _erros_amigaveis():
        etapa_ppt(Pasta(out), _config(config))


@app.command()
def exemplo(
    out: Annotated[Path, typer.Option("--out", "-o", help="CSV a gerar.")] = Path(
        "examples/rotas_exemplo.csv"
    ),
    uf: Annotated[str, typer.Option("--uf", help="UF dos municípios.")] = "SP",
    rotas: Annotated[int, typer.Option("--rotas", min=1, help="Quantidade de rotas.")] = 40,
    seed: Annotated[int, typer.Option("--seed", help="Semente do sorteio.")] = 42,
    config: ArquivoConfig = None,
) -> None:
    """Gera um CSV sintético com municípios reais e rotas e métricas inventadas."""
    with _erros_amigaveis():
        geo = _config(config).geo
        malha = carregar_malha([uf.upper()], cache=geo.cache, qualidade=geo.qualidade)
        salvar_csv(gerar_exemplo(malha.geo, OpcoesExemplo(rotas=rotas, seed=seed)), out)
    console.print(f"[green]pronto:[/] {out}")
