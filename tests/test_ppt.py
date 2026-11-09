import json
from pathlib import Path

import numpy as np
import pytest
from matplotlib.image import imsave
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.slide import Slide

from rotamap.ppt import Conteudo, Hotspot, MapaMenu, SlideRota, ler_hotspots, montar_apresentacao


def _png(caminho: Path, largura: int, altura: int) -> Path:
    imsave(caminho, np.ones((altura, largura, 3)))
    return caminho


@pytest.fixture
def conteudo(tmp_path: Path) -> Conteudo:
    capa = _png(tmp_path / "capa.png", 300, 200)
    mapa = _png(tmp_path / "rota.png", 130, 116)
    menu = MapaMenu(
        imagem=capa,
        raio=0.02,
        hotspots=[Hotspot("2", 0.25, 0.5), Hotspot("10", 0.75, 0.25)],
    )
    muitas = [f"Cidade {i}" for i in range(200)]
    rotas = [
        SlideRota(
            "2", "Oeste", "#E15759", ["Birigui", "Araçatuba"], [("Faturamento", "R$ 1.000")], mapa
        ),
        SlideRota("10", "Leste", "#4E79A7", muitas, [], mapa),
        SlideRota("999", "Balcão", "#BAB0AC", [], [], None),
    ]
    return Conteudo("Rotas de teste", rotas, menu, "SP · 2026", [("Rotas", "3")])


def _ler(caminho: Path) -> list[Slide]:
    return list(Presentation(str(caminho)).slides)


def _textos(slide: Slide) -> list[str]:
    return [s.text_frame.text for s in slide.shapes if s.has_text_frame]


def _links(slide: Slide, slides: list[Slide]) -> dict[str, list[int]]:
    """texto do botao para os indices dos slides de destino."""
    indices = {s.slide_id: i for i, s in enumerate(slides)}
    resultado: dict[str, list[int]] = {}
    for shape in slide.shapes:
        alvo = shape.click_action.target_slide if shape.has_text_frame else None
        if alvo is not None:
            resultado.setdefault(shape.text_frame.text, []).append(indices[alvo.slide_id])
    return resultado


def test_estrutura_e_links(conteudo: Conteudo, tmp_path: Path) -> None:
    caminho = montar_apresentacao(conteudo, tmp_path / "saida" / "apresentacao.pptx")

    slides = _ler(caminho)
    capa, menu, oeste, leste, balcao = slides
    assert "Rotas de teste" in _textos(capa)
    assert _links(capa, slides) == {"Explorar rotas  ›": [1]}
    # rota com hotspot tem circulo e botao na grade; a sem mapa so o botao
    assert _links(menu, slides) == {"2": [2, 2], "10": [3, 3], "999": [4]}
    assert _links(oeste, slides) == {"‹  Mapa": [1], "Próxima  ›": [3]}
    assert _links(leste, slides) == {"‹  Mapa": [1], "‹  Anterior": [2], "Próxima  ›": [4]}
    assert "Rota 2 · Oeste" in _textos(oeste)
    assert "R$ 1.000" in _textos(oeste)
    assert any("Nenhum município" in t for t in _textos(balcao))


def test_hotspots_ficam_sobre_o_ponto_certo_do_mapa(conteudo: Conteudo, tmp_path: Path) -> None:
    menu = _ler(montar_apresentacao(conteudo, tmp_path / "a.pptx"))[1]

    (mapa,) = [s for s in menu.shapes if s.shape_type == MSO_SHAPE_TYPE.PICTURE]
    circulos = {
        s.text_frame.text: s for s in menu.shapes if s.has_text_frame and s.width == s.height
    }
    for hotspot in conteudo.menu.hotspots:
        circulo = circulos[hotspot.rota_id]
        centro_x = circulo.left + circulo.width / 2
        centro_y = circulo.top + circulo.height / 2
        assert centro_x == pytest.approx(mapa.left + hotspot.x * mapa.width, abs=2)
        assert centro_y == pytest.approx(mapa.top + hotspot.y * mapa.height, abs=2)
        assert circulo.width == pytest.approx(2 * conteudo.menu.raio * mapa.width, abs=2)


def test_imagem_mantem_a_proporcao(conteudo: Conteudo, tmp_path: Path) -> None:
    menu = _ler(montar_apresentacao(conteudo, tmp_path / "a.pptx"))[1]

    (mapa,) = [s for s in menu.shapes if s.shape_type == MSO_SHAPE_TYPE.PICTURE]
    assert mapa.width / mapa.height == pytest.approx(300 / 200, rel=1e-3)


def test_lista_longa_de_cidades_é_cortada_em_colunas(conteudo: Conteudo, tmp_path: Path) -> None:
    leste = _ler(montar_apresentacao(conteudo, tmp_path / "a.pptx"))[3]

    assert "Municípios (200)" in _textos(leste)
    (lista,) = [s for s in leste.shapes if s.has_text_frame and "Cidade 0" in s.text_frame.text]
    paragrafos = [p.text for p in lista.text_frame.paragraphs]
    assert paragrafos[-1].startswith("… e mais ")
    assert len(paragrafos) - 1 + int(paragrafos[-1].split()[-1]) == 200
    assert lista.text_frame._txBody.bodyPr.get("numCol") == "4"


def test_ler_hotspots_usa_a_imagem_sem_numeros(tmp_path: Path) -> None:
    dados = {
        "versao": 1,
        "imagem": "mapa_menu.png",
        "imagem_sem_rotulos": "mapa_capa.png",
        "largura_px": 100,
        "altura_px": 50,
        "raio": 0.01,
        "hotspots": [{"rota_id": "7", "x": 0.1, "y": 0.2, "cor": "#000000"}],
    }
    (tmp_path / "hotspots.json").write_text(json.dumps(dados), encoding="utf-8")

    menu = ler_hotspots(tmp_path / "hotspots.json")

    assert menu.imagem == tmp_path / "mapa_capa.png"
    assert menu.hotspots == [Hotspot("7", 0.1, 0.2, "#000000")]
