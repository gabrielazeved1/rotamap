from typer.testing import CliRunner

from rotamap import __version__
from rotamap.cli import app

runner = CliRunner()


def test_version() -> None:
    resultado = runner.invoke(app, ["--version"])
    assert resultado.exit_code == 0
    assert __version__ in resultado.output


def test_help_lista_as_etapas() -> None:
    resultado = runner.invoke(app, ["--help"])
    assert resultado.exit_code == 0
    for etapa in ("run", "parse", "geo", "maps", "ppt"):
        assert etapa in resultado.output
