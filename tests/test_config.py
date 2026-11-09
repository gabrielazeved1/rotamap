from pathlib import Path

import pytest

from rotamap.config import Config, ConfigInvalida, carregar_config
from rotamap.metricas import Agregacao, Formato

RAIZ = Path(__file__).parent.parent


def _toml(tmp_path: Path, texto: str) -> Path:
    caminho = tmp_path / "config.toml"
    caminho.write_text(texto, encoding="utf-8")
    return caminho


def test_sem_arquivo_usa_o_padrao() -> None:
    assert carregar_config(None) == Config()


def test_exemplo_do_repositorio_é_valido() -> None:
    config = carregar_config(RAIZ / "config.example.toml")

    assert config.entrada.formato == "tidy"
    assert config.geo.aliases["RETIRADA NO BALCAO"] == ""
    assert config.render.tamanho_rota == (6.5, 5.8)
    assert config.metricas[2].agregacao is Agregacao.PONDERADA
    assert config.metricas[3].formato is Formato.MOEDA


def test_caminhos_relativos_ao_arquivo(tmp_path: Path) -> None:
    caminho = _toml(tmp_path, '[geo]\ncache = "cache"\nmalha = "malha/sp.shp"\nufs = ["mg"]\n')

    geo = carregar_config(caminho).geo

    assert geo.cache == (tmp_path / "cache").resolve()
    assert geo.malha == (tmp_path / "malha" / "sp.shp").resolve()
    assert geo.ufs == ("MG",)


@pytest.mark.parametrize(
    ("texto", "mensagem"),
    [
        ('titlo = "x"', "desconhecida.*titlo"),
        ("[entrada]\nformat = 'tidy'", "entrada.*format"),
        ("[[metricas]]\nrotulo = 'x'\ncoluna = 'a'\nagregacao = 'mediana'", "nº 1.*mediana"),
        ("[[metricas]]\nrotulo = 'x'", "falta a coluna"),
        ("titulo = ", "config.toml"),
    ],
)
def test_erros_apontam_o_problema(tmp_path: Path, texto: str, mensagem: str) -> None:
    with pytest.raises(ConfigInvalida, match=mensagem):
        carregar_config(_toml(tmp_path, texto))
