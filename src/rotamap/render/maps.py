import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
from matplotlib import patheffects
from matplotlib.axes import Axes
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.patches import Circle
from matplotlib.transforms import Bbox

from rotamap.models import chave_rota
from rotamap.render.labels import pontos_candidatos, posicionar_rotulos
from rotamap.render.palette import atribuir_cores, vizinhanca

log = logging.getLogger(__name__)

# sirgas 2000 / policonica: metrica e vale para o brasil inteiro, sem distorcer o desenho
CRS_DESENHO = "EPSG:5880"

COR_FUNDO = "#e3e3e3"
COR_DIVISA = "#ffffff"
COR_CONTORNO = "#3a3a3a"
COR_ROTULO = "#1f1f1f"

ARQ_CAPA = "mapa_capa.png"
ARQ_MENU = "mapa_menu.png"
ARQ_HOTSPOTS = "hotspots.json"
PASTA_ROTAS = "rotas"
VERSAO_HOTSPOTS = 1
_TENTATIVAS_NOME = 60


@dataclass(frozen=True, slots=True)
class OpcoesRender:
    largura: float = 12.0  # polegadas do mapa geral
    dpi: int = 200
    margem: float = 0.02  # fracao da largura em volta do mapa geral
    # diametro do rotulo como fracao da largura da caixa onde o menu aparece no ppt
    rotulo: float = 0.022
    # largura sobre altura dessa caixa (ppt/layout.py: MENU_MAPA)
    proporcao_menu: float = 8.9 / 6.1
    tamanho_rota: tuple[float, float] = (6.5, 5.8)  # polegadas de cada mapa de rota
    margem_rota: float = 0.08


@dataclass(frozen=True, slots=True)
class Extensao:
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def largura(self) -> float:
        return self.x1 - self.x0

    @property
    def altura(self) -> float:
        return self.y1 - self.y0

    def relativo(self, x: float, y: float) -> tuple[float, float]:
        # o y do mapa cresce para cima e o da imagem para baixo
        return (x - self.x0) / self.largura, (self.y1 - y) / self.altura


def renderizar(
    malha: gpd.GeoDataFrame,
    rotas: gpd.GeoDataFrame,
    pasta: Path,
    opcoes: OpcoesRender | None = None,
) -> dict[str, str]:
    """gera capa, menu com numeros, hotspots.json e um mapa por rota; devolve as cores."""
    opcoes = opcoes or OpcoesRender()
    malha = malha.to_crs(CRS_DESENHO)
    rotas = rotas.to_crs(CRS_DESENHO)
    areas = rotas.dissolve(by="rota_id", as_index=False)[["rota_id", "geometry"]]

    extensao = _extensao(malha, opcoes.margem)
    cores = atribuir_cores(vizinhanca(areas, distancia=extensao.largura * 0.02))
    pasta.mkdir(parents=True, exist_ok=True)

    mapa_geral(malha, rotas, areas, cores, extensao, pasta, opcoes)
    (pasta / PASTA_ROTAS).mkdir(exist_ok=True)
    for rota_id in sorted(cores, key=chave_rota):
        mapa_rota(malha, rotas[rotas["rota_id"] == rota_id], cores[rota_id], pasta, opcoes)
    log.info("%d mapas de rota gravados em %s", len(cores), pasta / PASTA_ROTAS)
    return cores


def mapa_geral(
    malha: gpd.GeoDataFrame,
    rotas: gpd.GeoDataFrame,
    areas: gpd.GeoDataFrame,
    cores: dict[str, str],
    extensao: Extensao,
    pasta: Path,
    opcoes: OpcoesRender,
) -> None:
    """capa sem numeros e menu com numeros, a partir do mesmo desenho."""
    tamanho = (opcoes.largura, opcoes.largura * extensao.altura / extensao.largura)
    fig, ax = _figura(tamanho, extensao)
    _desenhar_base(ax, malha, rotas, areas, cores)
    fig.savefig(pasta / ARQ_CAPA, dpi=opcoes.dpi, transparent=True)

    raio = _raio_rotulo(extensao, opcoes)
    geometrias = dict(zip(areas["rota_id"], areas.geometry, strict=True))
    posicoes = posicionar_rotulos(geometrias, raio)
    fonte = 2 * raio / extensao.largura * opcoes.largura * 72 * 0.38
    for rota_id, (x, y) in posicoes.items():
        ax.add_patch(Circle((x, y), raio, facecolor=COR_ROTULO, edgecolor="white", lw=0.8))
        ax.text(
            x, y, rota_id, ha="center", va="center", color="white", fontsize=fonte, weight="bold"
        )
    fig.savefig(pasta / ARQ_MENU, dpi=opcoes.dpi, transparent=True)

    _salvar_hotspots(posicoes, raio, cores, extensao, tamanho, opcoes.dpi, pasta / ARQ_HOTSPOTS)
    log.info("mapa geral com %d rotas gravado em %s", len(posicoes), pasta)


def mapa_rota(
    malha: gpd.GeoDataFrame,
    rota: gpd.GeoDataFrame,
    cor: str,
    pasta: Path,
    opcoes: OpcoesRender,
) -> Path:
    """mapa de uma rota com os municipios vizinhos em cinza para dar contexto."""
    rota_id = str(rota["rota_id"].iloc[0])
    extensao = _encaixar(rota, opcoes.tamanho_rota, opcoes.margem_rota)
    fig, ax = _figura(opcoes.tamanho_rota, extensao)
    entorno = malha.cx[extensao.x0 : extensao.x1, extensao.y0 : extensao.y1]
    area = rota.dissolve()

    entorno.plot(ax=ax, color=COR_FUNDO, edgecolor=COR_DIVISA, linewidth=0.6)
    rota.plot(ax=ax, color=cor, edgecolor=COR_DIVISA, linewidth=0.8)
    area.boundary.plot(ax=ax, color=COR_CONTORNO, linewidth=1.4)
    _travar(ax)
    _nomes(fig, ax, rota)

    caminho = caminho_mapa_rota(pasta, rota_id)
    fig.savefig(caminho, dpi=opcoes.dpi, transparent=True)
    return caminho


def _raio_rotulo(extensao: Extensao, opcoes: OpcoesRender) -> float:
    """raio em unidades do mapa para o rotulo ter o mesmo tamanho no slide em qualquer uf."""
    # mapa mais "em pe" que a caixa é encaixado pela altura e aparece mais estreito,
    # entao o rotulo cresce na mesma proporcao para nao encolher no slide
    aspecto = extensao.largura / extensao.altura
    return opcoes.rotulo / 2 * extensao.largura * max(1.0, opcoes.proporcao_menu / aspecto)


def _figura(tamanho: tuple[float, float], extensao: Extensao) -> tuple[Figure, Axes]:
    # figure sem pyplot: sem estado global e sem janela
    fig = Figure(figsize=tamanho)
    # eixo ocupando a figura inteira: posicao no mapa vira posicao na imagem
    ax = fig.add_axes((0, 0, 1, 1))
    ax.set_axis_off()
    ax.set_xlim(extensao.x0, extensao.x1)
    ax.set_ylim(extensao.y0, extensao.y1)
    return fig, ax


def _desenhar_base(
    ax: Axes,
    malha: gpd.GeoDataFrame,
    rotas: gpd.GeoDataFrame,
    areas: gpd.GeoDataFrame,
    cores: dict[str, str],
) -> None:
    malha.plot(ax=ax, color=COR_FUNDO, edgecolor=COR_DIVISA, linewidth=0.3)
    rotas.plot(ax=ax, color=rotas["rota_id"].map(cores), edgecolor=COR_DIVISA, linewidth=0.3)
    areas.boundary.plot(ax=ax, color=COR_CONTORNO, linewidth=0.7)
    malha.dissolve(by="uf").boundary.plot(ax=ax, color=COR_CONTORNO, linewidth=1.0)
    _travar(ax)


def _travar(ax: Axes) -> None:
    # o geopandas forca aspect igual; a figura ja tem a proporcao exata, entao volta para auto
    # para o eixo nao encolher e desalinhar os hotspots
    ax.set_aspect("auto")


def _nomes(fig: Figure, ax: Axes, rota: gpd.GeoDataFrame) -> None:
    """escreve o nome de cada municipio sem sobrepor; o que nao couber fica so na lista do slide."""
    quantidade = len(rota)
    fonte = 9 if quantidade <= 10 else 7.5 if quantidade <= 25 else 6
    contorno = [patheffects.withStroke(linewidth=2.5, foreground="white")]
    # canvas agg para medir o texto sem pyplot
    FigureCanvasAgg(fig)
    ocupadas: list[Bbox] = []
    omitidos: list[str] = []
    # os maiores primeiro: tem mais espaco e ficam com o nome centralizado
    for nome, geometria in sorted(
        zip(rota["nome"], rota.geometry, strict=True), key=lambda par: -par[1].area
    ):
        texto = ax.text(
            0, 0, nome, ha="center", va="center", fontsize=fonte, color=COR_ROTULO,
            path_effects=contorno,
        )  # fmt: skip
        raio = (geometria.area**0.5) / 6
        for x, y in pontos_candidatos(geometria, raio)[:_TENTATIVAS_NOME]:
            texto.set_position((x, y))
            caixa = texto.get_window_extent().expanded(1.04, 1.2)
            if not any(caixa.overlaps(o) for o in ocupadas):
                ocupadas.append(caixa)
                break
        else:
            texto.remove()
            omitidos.append(nome)
    if omitidos:
        log.debug("rota %s: nomes sem espaço no mapa: %s", rota["rota_id"].iloc[0], omitidos)


def _extensao(gdf: gpd.GeoDataFrame, margem: float) -> Extensao:
    x0, y0, x1, y1 = gdf.total_bounds
    folga = (x1 - x0) * margem
    return Extensao(x0 - folga, y0 - folga, x1 + folga, y1 + folga)


def _encaixar(gdf: gpd.GeoDataFrame, tamanho: tuple[float, float], margem: float) -> Extensao:
    """extensao com margem e com a mesma proporcao da figura, centrada na rota."""
    base = _extensao(gdf, 0)
    largura = max(base.largura, 1.0) * (1 + 2 * margem)
    altura = max(base.altura, 1.0) * (1 + 2 * margem)
    proporcao = tamanho[0] / tamanho[1]
    if largura / altura < proporcao:
        largura = altura * proporcao
    else:
        altura = largura / proporcao
    cx, cy = (base.x0 + base.x1) / 2, (base.y0 + base.y1) / 2
    return Extensao(cx - largura / 2, cy - altura / 2, cx + largura / 2, cy + altura / 2)


def _salvar_hotspots(
    posicoes: dict[str, tuple[float, float]],
    raio: float,
    cores: dict[str, str],
    extensao: Extensao,
    tamanho: tuple[float, float],
    dpi: int,
    caminho: Path,
) -> None:
    hotspots = []
    for rota_id in sorted(posicoes, key=chave_rota):
        x, y = extensao.relativo(*posicoes[rota_id])
        hotspots.append({"rota_id": rota_id, "x": x, "y": y, "cor": cores[rota_id]})
    dados = {
        "versao": VERSAO_HOTSPOTS,
        "imagem": ARQ_MENU,
        # a capa sai do mesmo desenho, sem os numeros: os hotspots valem para as duas
        "imagem_sem_rotulos": ARQ_CAPA,
        "largura_px": round(tamanho[0] * dpi),
        "altura_px": round(tamanho[1] * dpi),
        # coordenadas de 0 a 1 a partir do canto superior esquerdo; raio relativo a largura
        "raio": raio / extensao.largura,
        "hotspots": hotspots,
    }
    caminho.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")


def caminho_mapa_rota(pasta: Path, rota_id: str) -> Path:
    seguro = re.sub(r"[^A-Za-z0-9_-]+", "_", rota_id)
    return pasta / PASTA_ROTAS / f"rota_{seguro}.png"
