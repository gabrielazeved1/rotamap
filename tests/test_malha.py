from pathlib import Path

import pytest

from rotamap.geo import ibge
from rotamap.geo.malha import CRS, Municipio, carregar_malha, ler_malha_local


def test_carrega_malha_do_cache(cache_sp: Path) -> None:
    malha = carregar_malha(["SP", "SP"], cache=cache_sp)

    assert list(malha.geo.columns) == ["cod_ibge", "nome", "uf", "geometry"]
    assert malha.geo.crs == CRS
    assert Municipio("3543402", "Ribeirão Preto", "SP") in malha.municipios
    assert {(d.nome, d.municipio.nome) for d in malha.distritos} >= {
        ("Bonfim Paulista", "Ribeirão Preto")
    }


def test_aceita_gerador_de_ufs(cache_sp: Path) -> None:
    malha = carregar_malha((uf for uf in ["SP"]), cache=cache_sp)

    assert len(malha.geo) == 3
    assert len(malha.distritos) == 4


@pytest.mark.usefixtures("rede_fora")
def test_segue_sem_distritos_quando_a_api_falha(
    cache_sp: Path, caplog: pytest.LogCaptureFixture
) -> None:
    (cache_sp / "distritos_SP.json").unlink()

    malha = carregar_malha(["SP"], cache=cache_sp)

    assert malha.distritos == []
    assert len(malha.geo) == 3
    assert "distritos de SP indisponíveis" in caplog.text


def test_malha_local_no_formato_do_ibge(cache_sp: Path, tmp_path: Path) -> None:
    geo = carregar_malha(["SP"], cache=cache_sp).geo
    shapefile = geo.rename(columns={"cod_ibge": "CD_MUN", "nome": "NM_MUN", "uf": "SIGLA_UF"})
    caminho = tmp_path / "municipios.gpkg"
    shapefile.to_file(caminho, driver="GPKG")

    malha = ler_malha_local(caminho, ["SP"], cache=cache_sp)

    assert sorted(malha.geo["nome"]) == sorted(geo["nome"])
    assert malha.geo.crs == CRS
    assert len(malha.distritos) == 4


def test_malha_local_sem_as_colunas(cache_sp: Path, tmp_path: Path) -> None:
    caminho = tmp_path / "outra.gpkg"
    carregar_malha(["SP"], cache=cache_sp).geo.to_file(caminho, driver="GPKG")

    with pytest.raises(ValueError, match="CD_MUN"):
        ler_malha_local(caminho, ["SP"], cache=cache_sp)


def test_malha_local_sem_a_uf(cache_sp: Path, tmp_path: Path) -> None:
    geo = carregar_malha(["SP"], cache=cache_sp).geo
    caminho = tmp_path / "municipios.gpkg"
    geo.rename(columns={"cod_ibge": "CD_MUN", "nome": "NM_MUN", "uf": "SIGLA_UF"}).to_file(caminho)

    with pytest.raises(ValueError, match="nenhum município"):
        ler_malha_local(caminho, ["MG"], cache=cache_sp)


@pytest.mark.usefixtures("rede_fora")
def test_erro_de_rede_na_malha_propaga(tmp_path: Path) -> None:
    with pytest.raises(ibge.ErroIBGE):
        carregar_malha(["SP"], cache=tmp_path)
