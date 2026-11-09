import csv
from dataclasses import replace
from pathlib import Path

import pytest
from pptx import Presentation

from rotamap.config import Config, ConfigGeo
from rotamap.io import carregar_rotas
from rotamap.pipeline import ArtefatoAusente, Pasta, etapa_maps, etapa_ppt, executar
from rotamap.render import OpcoesRender

CSV = """rota_id,rota_nome,municipio,uf,ordem,valor_total,entregas
10,Campinas e região,CAMPINAS NORTE,SP,1,1000,10
10,Campinas e região,Campinas Sul,SP,2,500,5
10,Campinas e região,Bonfim Paulista,SP,3,1500,10
2,Oeste,Euclides da Cunha,SP,1,2000,20
2,Oeste,Retirada no balcão,SP,2,100,1
2,Oeste,Atlântida,SP,3,50,1
"""


@pytest.fixture
def entrada(tmp_path: Path) -> Path:
    caminho = tmp_path / "rotas.csv"
    caminho.write_text(CSV, encoding="utf-8")
    return caminho


@pytest.fixture
def config(cache_sp: Path) -> Config:
    return Config(
        titulo="Teste",
        geo=ConfigGeo(cache=cache_sp, aliases={"Retirada no balcão": ""}),
        render=OpcoesRender(largura=4, dpi=40, tamanho_rota=(3, 2.5)),
    )


def test_ponta_a_ponta(entrada: Path, config: Config, tmp_path: Path) -> None:
    pasta = Pasta(tmp_path / "saida")

    executar(entrada, pasta, config)

    for artefato in (pasta.rotas, pasta.rotas_geo, pasta.gpkg, pasta.matching, pasta.hotspots):
        assert artefato.exists(), artefato
    assert sorted(p.name for p in (pasta.mapas / "rotas").iterdir()) == [
        "rota_10.png",
        "rota_2.png",
    ]

    rotas = {r.id: r for r in carregar_rotas(pasta.rotas_geo)}
    assert [p.nome_ibge for p in rotas["10"].paradas] == ["Campinas", "Campinas", "Ribeirão Preto"]
    assert [p.ignorada for p in rotas["2"].paradas] == [False, True, False]

    with pasta.matching.open(encoding="utf-8") as arquivo:
        metodos = {linha["municipio"]: linha["metodo"] for linha in csv.DictReader(arquivo)}
    assert metodos["Atlântida"] == "nao_encontrado"
    assert metodos["Retirada no balcão"] == "ignorado"
    assert metodos["Bonfim Paulista"] == "distrito"

    capa, _, rota_2, rota_10 = Presentation(str(pasta.apresentacao)).slides
    textos_capa = [s.text_frame.text for s in capa.shapes if s.has_text_frame]
    assert textos_capa[:2] == ["Teste", "SP"]
    textos_rota = [s.text_frame.text for s in rota_10.shapes if s.has_text_frame]
    # campinas norte e sul contam como um municipio; o kpi soma as duas
    assert "Municípios (2)" in textos_rota
    assert "Campinas\nRibeirão Preto" in textos_rota
    textos_oeste = [s.text_frame.text for s in rota_2.shapes if s.has_text_frame]
    assert "Municípios (1)" in textos_oeste


def test_sem_ppt(entrada: Path, config: Config, tmp_path: Path) -> None:
    pasta = Pasta(tmp_path / "saida")

    executar(entrada, pasta, config, ppt=False)

    assert pasta.hotspots.exists()
    assert not pasta.apresentacao.exists()


def test_etapa_sem_o_artefato_anterior(config: Config, tmp_path: Path) -> None:
    with pytest.raises(ArtefatoAusente, match="rode a etapa 'geo'"):
        etapa_maps(Pasta(tmp_path), config)


def test_resumo_com_metrica_inexistente(entrada: Path, config: Config, tmp_path: Path) -> None:
    pasta = Pasta(tmp_path / "saida")
    executar(entrada, pasta, config, ppt=False)

    with pytest.raises(ValueError, match="Lucro"):
        etapa_ppt(pasta, replace(config, resumo=("Lucro",)))
