import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pytest
from matplotlib.colors import to_rgb
from matplotlib.image import imread
from shapely.geometry import Polygon, box

from rotamap.models import chave_rota
from rotamap.ppt.layout import MENU_MAPA
from rotamap.render import (
    ARQ_CAPA,
    ARQ_HOTSPOTS,
    ARQ_MENU,
    PASTA_ROTAS,
    OpcoesRender,
    atribuir_cores,
    gerar_paleta,
    posicionar_rotulos,
    renderizar,
    vizinhanca,
)
from rotamap.render.labels import ponto_central
from rotamap.render.maps import COR_ROTULO
from rotamap.render.palette import _distancia

# grade 4x3 de municipios de 0.2 grau perto de campinas
LADO = 0.2
ORIGEM = (-48.0, -23.0)


def _grade() -> gpd.GeoDataFrame:
    linhas = []
    for i in range(4):
        for j in range(3):
            x, y = ORIGEM[0] + i * LADO, ORIGEM[1] + j * LADO
            geometria = box(x, y, x + LADO, y + LADO)
            linhas.append(
                {"cod_ibge": f"35{i}{j}000", "nome": f"M{i}{j}", "uf": "SP", "geometry": geometria}
            )
    return gpd.GeoDataFrame(linhas, crs="EPSG:4674")


@pytest.fixture
def malha() -> gpd.GeoDataFrame:
    return _grade()


@pytest.fixture
def rotas(malha: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    rotas_por_cod = {
        "3500000": "10",
        "3510000": "10",
        "3530000": "2",
        "3532000": "2",
        "3522000": "7",
    }
    selecao = malha[malha["cod_ibge"].isin(rotas_por_cod)].copy()
    selecao["rota_id"] = selecao["cod_ibge"].map(rotas_por_cod)
    selecao["rota_nome"] = "Rota " + selecao["rota_id"]
    return selecao


def test_chave_rota_ordena_como_numero() -> None:
    assert sorted(["10", "2", "B1", "1", "A"], key=chave_rota) == ["1", "2", "10", "A", "B1"]


def test_paleta_sem_cores_repetidas() -> None:
    paleta = gerar_paleta(81)

    assert len(set(paleta)) == 81


def test_vizinhanca(rotas: gpd.GeoDataFrame) -> None:
    areas = rotas.to_crs("EPSG:5880").dissolve(by="rota_id", as_index=False)

    vizinhos = vizinhanca(areas, distancia=1)

    assert vizinhos == {"10": set(), "2": {"7"}, "7": {"2"}}


def test_vizinhos_recebem_cores_bem_diferentes() -> None:
    # anel de 12 rotas, cada uma vizinha das duas do lado
    ids = [str(i) for i in range(12)]
    vizinhos = {r: {ids[(i - 1) % 12], ids[(i + 1) % 12]} for i, r in enumerate(ids)}

    cores = atribuir_cores(vizinhos)

    assert len(set(cores.values())) == 12
    menor = min(_distancia(cores[a], cores[b]) for a in ids for b in vizinhos[a])
    paleta = gerar_paleta(12)
    media_paleta = np.mean([_distancia(a, b) for a in paleta for b in paleta if a != b])
    assert menor > media_paleta * 0.6
    assert atribuir_cores(vizinhos) == cores


def test_ponto_central_fica_dentro_de_forma_concava() -> None:
    u = Polygon([(0, 0), (10, 0), (10, 10), (8, 10), (8, 2), (2, 2), (2, 10), (0, 10)])

    x, y = ponto_central(u)

    assert u.contains(gpd.points_from_xy([x], [y])[0])


def test_rotulos_sem_sobreposicao_e_dentro_da_area() -> None:
    # tres areas coladas com centros muito proximos
    areas = {"a": box(0, 0, 4, 4), "b": box(4, 0, 8, 4), "c": box(0, 4, 8, 5)}
    raio = 1.0

    posicoes = posicionar_rotulos(areas, raio)

    pontos = list(posicoes.values())
    for i, p in enumerate(pontos):
        for q in pontos[i + 1 :]:
            assert np.hypot(p[0] - q[0], p[1] - q[1]) >= 2 * raio
    for chave, (x, y) in posicoes.items():
        assert areas[chave].contains(gpd.points_from_xy([x], [y])[0])


def test_renderiza_e_hotspots_batem_com_a_imagem(
    malha: gpd.GeoDataFrame, rotas: gpd.GeoDataFrame, tmp_path: Path
) -> None:
    opcoes = OpcoesRender(largura=6, dpi=60, tamanho_rota=(4, 3))

    cores = renderizar(malha, rotas, tmp_path, opcoes)

    assert set(cores) == {"2", "7", "10"}
    dados = json.loads((tmp_path / ARQ_HOTSPOTS).read_text(encoding="utf-8"))
    assert [h["rota_id"] for h in dados["hotspots"]] == ["2", "7", "10"]
    assert sorted(p.name for p in (tmp_path / PASTA_ROTAS).iterdir()) == [
        "rota_10.png",
        "rota_2.png",
        "rota_7.png",
    ]

    menu = imread(tmp_path / ARQ_MENU)
    capa = imread(tmp_path / ARQ_CAPA)
    assert menu.shape[:2] == (dados["altura_px"], dados["largura_px"])
    for h in dados["hotspots"]:
        assert 0 < h["x"] < 1 and 0 < h["y"] < 1
        linha, coluna = int(h["y"] * menu.shape[0]), int(h["x"] * menu.shape[1])
        assert np.allclose(capa[linha, coluna, :3], to_rgb(h["cor"]), atol=0.05)
        # o centro tem o numero em branco; o circulo escuro aparece logo acima do texto
        acima = linha - int(dados["raio"] * menu.shape[1] * 0.75)
        assert np.allclose(menu[acima, coluna, :3], to_rgb(COR_ROTULO), atol=0.05)


def _grade_retangular(colunas: int, linhas: int) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    quadrados = [
        box(
            ORIGEM[0] + i * LADO,
            ORIGEM[1] + j * LADO,
            ORIGEM[0] + (i + 1) * LADO,
            ORIGEM[1] + (j + 1) * LADO,
        )
        for i in range(colunas)
        for j in range(linhas)
    ]
    malha = gpd.GeoDataFrame(
        {"cod_ibge": [str(k) for k in range(len(quadrados))], "nome": "M", "uf": "SP"},
        geometry=quadrados,
        crs="EPSG:4674",
    )
    rotas = malha.iloc[:2].copy()
    rotas["rota_id"] = ["1", "2"]
    rotas["rota_nome"] = "R"
    return malha, rotas


@pytest.mark.parametrize(("colunas", "linhas"), [(6, 2), (2, 6)])
def test_rotulo_tem_o_mesmo_tamanho_no_slide_em_qualquer_formato(
    colunas: int, linhas: int, tmp_path: Path
) -> None:
    malha, rotas = _grade_retangular(colunas, linhas)
    opcoes = OpcoesRender(largura=4, dpi=30, tamanho_rota=(2, 2))

    renderizar(malha, rotas, tmp_path, opcoes)

    dados = json.loads((tmp_path / ARQ_HOTSPOTS).read_text(encoding="utf-8"))
    aspecto = dados["largura_px"] / dados["altura_px"]
    # largura que a imagem ocupa quando encaixada na caixa do menu, com a caixa valendo 1
    largura_exibida = min(1.0, aspecto / opcoes.proporcao_menu)
    diametro_no_slide = 2 * dados["raio"] * largura_exibida
    assert diametro_no_slide == pytest.approx(opcoes.rotulo, rel=0.02)


def test_proporcao_do_menu_acompanha_o_layout_do_ppt() -> None:
    assert OpcoesRender().proporcao_menu == pytest.approx(MENU_MAPA.largura / MENU_MAPA.altura)
