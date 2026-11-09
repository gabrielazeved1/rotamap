import json
import logging
import math
from dataclasses import dataclass, field
from pathlib import Path

from matplotlib.colors import to_rgb
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.presentation import Presentation as Apresentacao
from pptx.shapes.autoshape import Shape
from pptx.slide import Slide
from pptx.text.text import Font, TextFrame
from pptx.util import Emu, Inches, Pt

from rotamap.ppt import layout as L
from rotamap.ppt.layout import Caixa, Tema

log = logging.getLogger(__name__)

Kpi = tuple[str, str]


@dataclass(frozen=True, slots=True)
class Hotspot:
    rota_id: str
    x: float  # 0 a 1 a partir da esquerda da imagem
    y: float  # 0 a 1 a partir do topo da imagem


@dataclass(frozen=True, slots=True)
class MapaMenu:
    imagem: Path
    largura_px: int
    altura_px: int
    raio: float  # relativo a largura da imagem
    hotspots: list[Hotspot]


@dataclass(frozen=True, slots=True)
class SlideRota:
    id: str
    nome: str
    cor: str
    cidades: list[str]
    kpis: list[Kpi] = field(default_factory=list)
    mapa: Path | None = None


@dataclass(frozen=True, slots=True)
class Conteudo:
    titulo: str
    rotas: list[SlideRota]
    menu: MapaMenu
    subtitulo: str = ""
    resumo: list[Kpi] = field(default_factory=list)


def ler_hotspots(caminho: Path) -> MapaMenu:
    """le o hotspots.json do render; usa a imagem sem numeros, que o ppt numera por cima."""
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    return MapaMenu(
        imagem=caminho.parent / dados["imagem_sem_rotulos"],
        largura_px=dados["largura_px"],
        altura_px=dados["altura_px"],
        raio=dados["raio"],
        hotspots=[Hotspot(h["rota_id"], h["x"], h["y"]) for h in dados["hotspots"]],
    )


def montar_apresentacao(conteudo: Conteudo, saida: Path, tema: Tema | None = None) -> Path:
    """capa, menu com o mapa clicavel e um slide por rota, todos ligados por links."""
    tema = tema or Tema()
    prs = Presentation()
    prs.slide_width = Inches(L.LARGURA)
    prs.slide_height = Inches(L.ALTURA)

    capa = _novo_slide(prs, tema)
    menu = _novo_slide(prs, tema)
    # os slides de rota existem antes dos links que apontam para eles
    slides = {r.id: _novo_slide(prs, tema) for r in conteudo.rotas}

    _capa(capa, conteudo, menu, tema)
    _menu(menu, conteudo, slides, tema)
    for i, rota in enumerate(conteudo.rotas):
        anterior = slides[conteudo.rotas[i - 1].id] if i > 0 else None
        proxima = slides[conteudo.rotas[i + 1].id] if i + 1 < len(conteudo.rotas) else None
        _slide_rota(slides[rota.id], rota, menu, anterior, proxima, tema)

    saida.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(saida))
    log.info("apresentação com %d slides gravada em %s", len(prs.slides), saida)
    return saida


def _capa(slide: Slide, conteudo: Conteudo, menu: Slide, tema: Tema) -> None:
    _texto(
        slide,
        L.CAPA_TITULO,
        conteudo.titulo,
        tema,
        tamanho=36,
        negrito=True,
        ancora=MSO_ANCHOR.BOTTOM,
    )
    if conteudo.subtitulo:
        _texto(slide, L.CAPA_SUBTITULO, conteudo.subtitulo, tema, tamanho=16, cor=tema.secundario)
    _resumo(slide, conteudo.resumo, tema)
    botao = _botao(slide, L.CAPA_BOTAO, "Explorar rotas  ›", tema.botao, tema, tamanho=14)
    botao.click_action.target_slide = menu
    _imagem(slide, conteudo.menu.imagem, L.CAPA_MAPA)


def _resumo(slide: Slide, kpis: list[Kpi], tema: Tema) -> None:
    altura = 0.62
    for i, (rotulo, valor) in enumerate(kpis[: int(L.CAPA_RESUMO.altura // altura)]):
        y = L.CAPA_RESUMO.y + i * altura
        _texto(slide, Caixa(L.CAPA_RESUMO.x, y, 4.4, 0.36), valor, tema, tamanho=20, negrito=True)
        _texto(
            slide,
            Caixa(L.CAPA_RESUMO.x, y + 0.32, 4.4, 0.26),
            rotulo,
            tema,
            tamanho=11,
            cor=tema.secundario,
        )


def _menu(slide: Slide, conteudo: Conteudo, slides: dict[str, Slide], tema: Tema) -> None:
    _texto(slide, L.MENU_TITULO, "Selecione uma rota", tema, tamanho=24, negrito=True)
    mapa = conteudo.menu
    area = _imagem(slide, mapa.imagem, L.MENU_MAPA)

    diametro = 2 * mapa.raio * area.largura
    for h in mapa.hotspots:
        if h.rota_id not in slides:
            continue
        centro_x = area.x + h.x * area.largura
        centro_y = area.y + h.y * area.altura
        caixa = Caixa(centro_x - diametro / 2, centro_y - diametro / 2, diametro, diametro)
        circulo = _botao(
            slide,
            caixa,
            h.rota_id,
            tema.hotspot,
            tema,
            forma=MSO_SHAPE.OVAL,
            tamanho=diametro * 72 * 0.4,
            borda="#FFFFFF",
        )
        circulo.click_action.target_slide = slides[h.rota_id]

    cores = {r.id: r.cor for r in conteudo.rotas}
    for rota_id, caixa in zip(cores, _grade(len(cores), L.MENU_GRADE), strict=True):
        botao = _botao(
            slide, caixa, rota_id, cores[rota_id], tema, tamanho=min(11, caixa.altura * 72 * 0.42)
        )
        botao.click_action.target_slide = slides[rota_id]


def _slide_rota(
    slide: Slide,
    rota: SlideRota,
    menu: Slide,
    anterior: Slide | None,
    proxima: Slide | None,
    tema: Tema,
) -> None:
    voltar = _botao(slide, L.ROTA_VOLTAR, "‹  Mapa", tema.botao, tema, tamanho=12)
    voltar.click_action.target_slide = menu
    _texto(slide, L.ROTA_TITULO, f"Rota {rota.id} · {rota.nome}", tema, tamanho=24, negrito=True)
    _navegacao(slide, anterior, proxima, tema)
    _retangulo(slide, L.ROTA_FAIXA, rota.cor)

    if rota.mapa is not None and rota.mapa.exists():
        _imagem(slide, rota.mapa, L.ROTA_MAPA)
    else:
        _texto(
            slide,
            L.ROTA_MAPA,
            "Nenhum município desta rota foi encontrado na malha.",
            tema,
            tamanho=14,
            cor=tema.secundario,
            alinhamento=PP_ALIGN.CENTER,
            ancora=MSO_ANCHOR.MIDDLE,
        )

    _kpis(slide, rota.kpis, tema)
    _cidades(slide, rota.cidades, tema)


def _navegacao(slide: Slide, anterior: Slide | None, proxima: Slide | None, tema: Tema) -> None:
    caixa = L.ROTA_NAVEGACAO
    metade = (caixa.largura - 0.1) / 2
    for alvo, texto, x in (
        (anterior, "‹  Anterior", caixa.x),
        (proxima, "Próxima  ›", caixa.x + metade + 0.1),
    ):
        if alvo is None:
            continue
        botao = _botao(
            slide,
            Caixa(x, caixa.y, metade, caixa.altura),
            texto,
            tema.cartao,
            tema,
            tamanho=11,
            borda=tema.borda,
        )
        botao.click_action.target_slide = alvo


def _kpis(slide: Slide, kpis: list[Kpi], tema: Tema) -> None:
    if not kpis:
        return
    caixa = L.ROTA_KPIS
    colunas = 3 if len(kpis) > 4 else 2 if len(kpis) > 1 else 1
    linhas = math.ceil(len(kpis) / colunas)
    vao = 0.15
    largura = (caixa.largura - vao * (colunas - 1)) / colunas
    altura = min(1.0, (caixa.altura - vao * (linhas - 1)) / linhas)
    for i, (rotulo, valor) in enumerate(kpis):
        x = caixa.x + (i % colunas) * (largura + vao)
        y = caixa.y + (i // colunas) * (altura + vao)
        _retangulo(
            slide, Caixa(x, y, largura, altura), tema.cartao, borda=tema.borda, arredondado=True
        )
        # valores longos (moeda) encolhem para caber no cartao
        tamanho = min(20.0, largura * 72 / (max(len(valor), 1) * 0.58))
        _texto(
            slide,
            Caixa(x + 0.12, y + 0.08, largura - 0.24, altura * 0.55),
            valor,
            tema,
            tamanho=tamanho,
            negrito=True,
            ancora=MSO_ANCHOR.BOTTOM,
        )
        _texto(
            slide,
            Caixa(x + 0.12, y + altura * 0.6, largura - 0.24, altura * 0.35),
            rotulo,
            tema,
            tamanho=10,
            cor=tema.secundario,
            ancora=MSO_ANCHOR.TOP,
        )


def _cidades(slide: Slide, cidades: list[str], tema: Tema) -> None:
    caixa = L.ROTA_CIDADES
    _texto(
        slide,
        Caixa(caixa.x, caixa.y, caixa.largura, 0.35),
        f"Municípios ({len(cidades)})",
        tema,
        tamanho=13,
        negrito=True,
    )
    if not cidades:
        return
    lista = Caixa(caixa.x, caixa.y + 0.4, caixa.largura, caixa.altura - 0.4)
    colunas, tamanho = _colunas_cidades(len(cidades))
    linhas_por_coluna = int(lista.altura * 72 / (tamanho * 1.25))
    capacidade = colunas * linhas_por_coluna
    visiveis = cidades
    if len(cidades) > capacidade:
        visiveis = [*cidades[: capacidade - 1], f"… e mais {len(cidades) - capacidade + 1}"]
    quadro = _texto(slide, lista, "", tema, tamanho=tamanho)
    for i, cidade in enumerate(visiveis):
        paragrafo = quadro.paragraphs[0] if i == 0 else quadro.add_paragraph()
        paragrafo.text = cidade
        _fonte(paragrafo.font, tema, tamanho)
    _em_colunas(quadro, colunas, espaco=0.15)


def _colunas_cidades(quantidade: int) -> tuple[int, float]:
    if quantidade <= 12:
        return 2, 11
    if quantidade <= 30:
        return 3, 10
    return 4, 8


def _grade(quantidade: int, caixa: Caixa) -> list[Caixa]:
    """divide a caixa em botoes iguais, com o maior tamanho que comporta todos."""
    vao = 0.06
    proporcao = 1.5  # largura sobre altura de cada botao
    melhor: tuple[float, int] = (0.0, 1)
    for colunas in range(1, quantidade + 1):
        linhas = math.ceil(quantidade / colunas)
        largura = (caixa.largura - vao * (colunas - 1)) / colunas
        altura = min(largura / proporcao, (caixa.altura - vao * (linhas - 1)) / linhas)
        if altura > melhor[0]:
            melhor = (altura, colunas)
    altura, colunas = melhor
    altura = min(altura, 0.5)
    largura = altura * proporcao
    return [
        Caixa(
            caixa.x + (i % colunas) * (largura + vao),
            caixa.y + (i // colunas) * (altura + vao),
            largura,
            altura,
        )
        for i in range(quantidade)
    ]


def _novo_slide(prs: Apresentacao, tema: Tema) -> Slide:
    # layout 6 é o "em branco" do modelo padrao
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = _rgb(tema.fundo)
    return slide


def _imagem(slide: Slide, caminho: Path, caixa: Caixa) -> Caixa:
    """encaixa a imagem na caixa sem distorcer, centralizada; devolve onde ela ficou."""
    figura = slide.shapes.add_picture(str(caminho), Inches(caixa.x), Inches(caixa.y))
    escala = min(Inches(caixa.largura) / figura.width, Inches(caixa.altura) / figura.height)
    largura = figura.width * escala / Inches(1)
    altura = figura.height * escala / Inches(1)
    final = Caixa(
        caixa.x + (caixa.largura - largura) / 2,
        caixa.y + (caixa.altura - altura) / 2,
        largura,
        altura,
    )
    figura.left, figura.top = Inches(final.x), Inches(final.y)
    figura.width, figura.height = Emu(round(Inches(largura))), Emu(round(Inches(altura)))
    return final


def _texto(
    slide: Slide,
    caixa: Caixa,
    texto: str,
    tema: Tema,
    *,
    tamanho: float,
    negrito: bool = False,
    cor: str | None = None,
    alinhamento: PP_ALIGN = PP_ALIGN.LEFT,
    ancora: MSO_ANCHOR = MSO_ANCHOR.TOP,
) -> TextFrame:
    quadro = slide.shapes.add_textbox(*_emu(caixa)).text_frame
    quadro.word_wrap = True
    quadro.vertical_anchor = ancora
    for margem in ("margin_left", "margin_right", "margin_top", "margin_bottom"):
        setattr(quadro, margem, 0)
    paragrafo = quadro.paragraphs[0]
    paragrafo.text = texto
    paragrafo.alignment = alinhamento
    _fonte(paragrafo.font, tema, tamanho, negrito=negrito, cor=cor)
    return quadro


def _botao(
    slide: Slide,
    caixa: Caixa,
    texto: str,
    fundo: str,
    tema: Tema,
    *,
    tamanho: float,
    forma: MSO_SHAPE = MSO_SHAPE.ROUNDED_RECTANGLE,
    borda: str | None = None,
) -> Shape:
    botao = _retangulo(slide, caixa, fundo, borda=borda, forma=forma)
    quadro = botao.text_frame
    quadro.word_wrap = False
    quadro.vertical_anchor = MSO_ANCHOR.MIDDLE
    for margem in ("margin_left", "margin_right", "margin_top", "margin_bottom"):
        setattr(quadro, margem, 0)
    paragrafo = quadro.paragraphs[0]
    paragrafo.text = texto
    paragrafo.alignment = PP_ALIGN.CENTER
    _fonte(paragrafo.font, tema, tamanho, negrito=True, cor=_contraste(fundo, tema))
    return botao


def _retangulo(
    slide: Slide,
    caixa: Caixa,
    cor: str,
    *,
    borda: str | None = None,
    arredondado: bool = False,
    forma: MSO_SHAPE | None = None,
) -> Shape:
    if forma is None:
        forma = MSO_SHAPE.ROUNDED_RECTANGLE if arredondado else MSO_SHAPE.RECTANGLE
    shape = slide.shapes.add_shape(forma, *_emu(caixa))
    shape.shadow.inherit = False
    shape.fill.solid()
    shape.fill.fore_color.rgb = _rgb(cor)
    if borda is None:
        shape.line.fill.background()
    else:
        shape.line.color.rgb = _rgb(borda)
        shape.line.width = Pt(0.75)
    if forma is MSO_SHAPE.ROUNDED_RECTANGLE:
        # cantos discretos; o padrao do powerpoint arredonda demais
        shape.adjustments[0] = 0.12
    return shape


def _fonte(
    fonte: Font, tema: Tema, tamanho: float, *, negrito: bool = False, cor: str | None = None
) -> None:
    fonte.name = tema.fonte
    fonte.size = Pt(tamanho)
    fonte.bold = negrito
    fonte.color.rgb = _rgb(cor or tema.texto)


def _em_colunas(quadro: TextFrame, colunas: int, espaco: float) -> None:
    # python-pptx nao expoe colunas de texto; o atributo vai direto no bodyPr do xml
    corpo = quadro._txBody.bodyPr
    corpo.set("numCol", str(colunas))
    corpo.set("spcCol", str(int(Inches(espaco))))


def _contraste(fundo: str, tema: Tema) -> str:
    r, g, b = to_rgb(fundo)
    luminancia = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return "#FFFFFF" if luminancia < 0.55 else tema.texto


def _rgb(cor: str) -> RGBColor:
    return RGBColor.from_string(cor.lstrip("#").upper())


def _emu(caixa: Caixa) -> tuple[Emu, Emu, Emu, Emu]:
    return (
        Emu(Inches(caixa.x)),
        Emu(Inches(caixa.y)),
        Emu(Inches(caixa.largura)),
        Emu(Inches(caixa.altura)),
    )
