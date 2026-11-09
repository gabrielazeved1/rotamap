import csv
from pathlib import Path

import pytest

from rotamap.geo import (
    Matcher,
    associar,
    camada_rotas,
    carregar_geo,
    carregar_malha,
    salvar_geo,
    salvar_relatorio,
)
from rotamap.geo.malha import Malha
from rotamap.models import Parada, Rota


@pytest.fixture
def malha(cache_sp: Path) -> Malha:
    return carregar_malha(["SP"], cache=cache_sp)


@pytest.fixture
def rotas() -> list[Rota]:
    return [
        Rota(
            "1",
            "Campinas",
            [
                Parada("CAMPINAS NORTE", "SP"),
                Parada("CAMPINAS SUL", "SP"),
                Parada("Bonfim Paulista", "SP"),
            ],
        ),
        Rota("2", "Oeste", [Parada("Ribeirão Preto", "SP"), Parada("Atlantida", "SP")]),
    ]


def test_camada_tem_um_municipio_por_rota(malha: Malha, rotas: list[Rota]) -> None:
    associacoes = associar(rotas, Matcher(malha.municipios, malha.distritos))

    camada = camada_rotas(associacoes, malha)

    assert sorted(zip(camada["rota_id"], camada["nome"], strict=True)) == [
        ("1", "Campinas"),
        ("1", "Ribeirão Preto"),
        ("2", "Ribeirão Preto"),
    ]
    assert camada.crs == malha.geo.crs


def test_avisa_municipio_compartilhado_e_nao_encontrado(
    malha: Malha, rotas: list[Rota], caplog: pytest.LogCaptureFixture
) -> None:
    associar(rotas, Matcher(malha.municipios, malha.distritos))

    assert "Ribeirão Preto (1, 2)" in caplog.text
    assert "Atlantida/SP não encontrado" in caplog.text


def test_salva_e_carrega_o_gpkg(malha: Malha, rotas: list[Rota], tmp_path: Path) -> None:
    camada = camada_rotas(associar(rotas, Matcher(malha.municipios)), malha)
    caminho = tmp_path / "saida" / "rotas_geo.gpkg"

    salvar_geo(malha, camada, caminho)
    salvar_geo(malha, camada, caminho)
    malha_lida, rotas_lidas = carregar_geo(caminho)

    assert len(malha_lida) == len(malha.geo)
    assert len(rotas_lidas) == len(camada)


def test_relatorio_traz_problemas_primeiro(malha: Malha, rotas: list[Rota], tmp_path: Path) -> None:
    associacoes = associar(rotas, Matcher(malha.municipios, malha.distritos))
    caminho = tmp_path / "matching.csv"

    salvar_relatorio(associacoes, caminho)

    with caminho.open(encoding="utf-8") as arquivo:
        linhas = list(csv.DictReader(arquivo))
    assert [(r["municipio"], r["metodo"]) for r in linhas] == [
        ("Atlantida", "nao_encontrado"),
        ("CAMPINAS NORTE", "aproximado"),
        ("CAMPINAS SUL", "aproximado"),
        ("Bonfim Paulista", "distrito"),
        ("Ribeirão Preto", "exato"),
    ]
    assert linhas[1]["cod_ibge"] == "3509502"
