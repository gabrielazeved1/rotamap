from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import box
from typer.testing import CliRunner

from rotamap.cli import app
from rotamap.exemplo import LINHA_BALCAO, OpcoesExemplo, gerar_exemplo, salvar_csv
from rotamap.io.tidy import ler_tidy


@pytest.fixture
def malha() -> gpd.GeoDataFrame:
    # grade 6x5 de municipios ficticios perto de campinas
    linhas = [
        {
            "nome": f"Município {i}-{j}",
            "uf": "SP",
            "geometry": box(-48 + i * 0.2, -23 + j * 0.2, -47.8 + i * 0.2, -22.8 + j * 0.2),
        }
        for i in range(6)
        for j in range(5)
    ]
    return gpd.GeoDataFrame(linhas, crs="EPSG:4674")


def test_mesma_seed_gera_o_mesmo_csv(malha: gpd.GeoDataFrame) -> None:
    opcoes = OpcoesExemplo(rotas=4, seed=7)

    assert gerar_exemplo(malha, opcoes) == gerar_exemplo(malha, opcoes)
    assert gerar_exemplo(malha, opcoes) != gerar_exemplo(malha, OpcoesExemplo(rotas=4, seed=8))


def test_csv_gerado_é_tidy_valido(malha: gpd.GeoDataFrame, tmp_path: Path) -> None:
    caminho = tmp_path / "exemplo.csv"

    salvar_csv(gerar_exemplo(malha, OpcoesExemplo(rotas=4, max_municipios=6)), caminho)
    rotas = ler_tidy(caminho)

    assert len(rotas) == 4
    for rota in rotas:
        assert [p.ordem for p in rota.paradas] == list(range(1, len(rota.paradas) + 1))
        for parada in rota.paradas:
            assert parada.metricas["atendidos"] <= parada.metricas["clientes"]
            assert 5 <= parada.metricas["lucro_pct"] <= 30


def test_sujeira_para_demonstrar_o_matching(malha: gpd.GeoDataFrame) -> None:
    linhas = gerar_exemplo(malha, OpcoesExemplo(rotas=3))
    municipios = [str(linha["municipio"]) for linha in linhas]

    assert LINHA_BALCAO in municipios
    assert any(m.endswith(" CENTRO") for m in municipios)

    limpas = gerar_exemplo(malha, OpcoesExemplo(rotas=3, sujeira=False))
    assert all(str(linha["municipio"]).startswith("Município") for linha in limpas)


def test_comando_exemplo(cache_sp: Path, tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text(f'[geo]\ncache = "{cache_sp}"\n', encoding="utf-8")
    saida = tmp_path / "exemplo.csv"

    resultado = CliRunner().invoke(
        app, ["exemplo", "-o", str(saida), "--rotas", "2", "-c", str(config)]
    )

    assert resultado.exit_code == 0, resultado.output
    assert len(ler_tidy(saida)) == 2


def test_avisa_quando_pede_mais_rotas_que_municipios(
    malha: gpd.GeoDataFrame, caplog: pytest.LogCaptureFixture
) -> None:
    linhas = gerar_exemplo(malha.iloc[:2], OpcoesExemplo(rotas=5, sujeira=False))

    assert len({linha["rota_id"] for linha in linhas}) == 2
    assert "só 2 município(s); gerando 2 rota(s) em vez de 5" in caplog.text
