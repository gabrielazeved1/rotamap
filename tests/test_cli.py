from pathlib import Path

from typer.testing import CliRunner

from rotamap import __version__
from rotamap.cli import app

runner = CliRunner()

CSV = """rota_id,rota_nome,municipio,uf,valor
1,Norte,Campinas,SP,10
2,Sul,Ribeirão Preto,SP,20
"""


def _preparar(tmp_path: Path, cache: Path) -> tuple[Path, Path]:
    entrada = tmp_path / "rotas.csv"
    entrada.write_text(CSV, encoding="utf-8")
    config = tmp_path / "config.toml"
    config.write_text(
        f'titulo = "CLI"\n[geo]\ncache = "{cache}"\n[render]\nlargura = 4\ndpi = 40\n',
        encoding="utf-8",
    )
    return entrada, config


def test_version() -> None:
    resultado = runner.invoke(app, ["--version"])
    assert resultado.exit_code == 0
    assert __version__ in resultado.output


def test_help_lista_as_etapas() -> None:
    resultado = runner.invoke(app, ["--help"])
    assert resultado.exit_code == 0
    for etapa in ("run", "parse", "geo", "maps", "ppt"):
        assert etapa in resultado.output


def test_run(tmp_path: Path, cache_sp: Path) -> None:
    entrada, config = _preparar(tmp_path, cache_sp)
    saida = tmp_path / "saida"

    resultado = runner.invoke(app, ["run", str(entrada), "-c", str(config), "-o", str(saida)])

    assert resultado.exit_code == 0, resultado.output
    assert (saida / "apresentacao.pptx").exists()


def test_etapas_separadas(tmp_path: Path, cache_sp: Path) -> None:
    entrada, config = _preparar(tmp_path, cache_sp)
    saida = tmp_path / "saida"
    comum = ["-c", str(config), "-o", str(saida)]

    for argumentos in (["parse", str(entrada)], ["geo"], ["maps"], ["ppt"]):
        resultado = runner.invoke(app, [*argumentos, *comum])
        assert resultado.exit_code == 0, resultado.output

    assert (saida / "apresentacao.pptx").exists()


def test_erro_vira_mensagem_sem_traceback(tmp_path: Path) -> None:
    resultado = runner.invoke(app, ["ppt", "-o", str(tmp_path)])

    assert resultado.exit_code == 1
    assert "rode a etapa 'geo' antes" in resultado.output
    assert "Traceback" not in resultado.output


def test_entrada_invalida(tmp_path: Path) -> None:
    entrada = tmp_path / "ruim.csv"
    entrada.write_text("rota_id,municipio\n1,Campinas\n", encoding="utf-8")

    resultado = runner.invoke(app, ["parse", str(entrada), "-o", str(tmp_path)])

    assert resultado.exit_code == 1
    assert "coluna obrigatória ausente" in resultado.output
