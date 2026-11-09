from collections.abc import Mapping
from functools import cache
from math import inf

import geopandas as gpd
from matplotlib.colors import hsv_to_rgb, to_hex, to_rgb

from rotamap.models import chave_rota

_PHI = 0.618033988749895
# saturacao e brilho alternados para separar cores de matiz parecida
_NIVEIS = [(0.62, 0.88), (0.42, 0.97), (0.78, 0.70)]
_RODADAS = 5


def gerar_paleta(n: int) -> list[str]:
    """n cores distintas: matiz pelo angulo dourado, alternando saturacao e brilho."""
    cores = []
    for i in range(n):
        saturacao, brilho = _NIVEIS[i % len(_NIVEIS)]
        r, g, b = hsv_to_rgb(((i * _PHI) % 1, saturacao, brilho))
        cores.append(to_hex((float(r), float(g), float(b))))
    return cores


def vizinhanca(areas: gpd.GeoDataFrame, distancia: float) -> dict[str, set[str]]:
    """rotas a menos de `distancia` uma da outra, nas unidades do crs."""
    pares = gpd.sjoin(areas, areas, predicate="dwithin", distance=distancia)
    vizinhos: dict[str, set[str]] = {rid: set() for rid in areas["rota_id"]}
    for a, b in zip(pares["rota_id_left"], pares["rota_id_right"], strict=True):
        if a != b:
            vizinhos[a].add(b)
    return vizinhos


def atribuir_cores(vizinhos: Mapping[str, set[str]]) -> dict[str, str]:
    """da a cada rota uma cor da paleta, afastando ao maximo as cores de rotas vizinhas."""
    paleta = gerar_paleta(len(vizinhos))
    livres = list(paleta)
    cores: dict[str, str] = {}
    # as rotas com mais vizinhos escolhem primeiro, quando ainda ha opcoes
    ordem = sorted(vizinhos, key=lambda r: (-len(vizinhos[r]), chave_rota(r)))
    for rota in ordem:
        usadas = [cores[v] for v in vizinhos[rota] if v in cores]
        escolhida = max(livres, key=lambda c: min((_distancia(c, u) for u in usadas), default=0))
        cores[rota] = escolhida
        livres.remove(escolhida)
    _melhorar(cores, vizinhos)
    return cores


def _melhorar(cores: dict[str, str], vizinhos: Mapping[str, set[str]]) -> None:
    # o guloso deixa as ultimas rotas com a sobra da paleta; trocas de cor entre pares
    # corrigem isso sem nunca piorar o pior contraste entre vizinhas
    rotas = sorted(cores, key=chave_rota)

    def pior(rota: str) -> float:
        return min((_distancia(cores[rota], cores[v]) for v in vizinhos[rota]), default=inf)

    for _ in range(_RODADAS):
        trocou = False
        for i, a in enumerate(rotas):
            for b in rotas[i + 1 :]:
                antes = min(pior(a), pior(b))
                cores[a], cores[b] = cores[b], cores[a]
                if min(pior(a), pior(b)) > antes:
                    trocou = True
                else:
                    cores[a], cores[b] = cores[b], cores[a]
        if not trocou:
            return


@cache
def _distancia(a: str, b: str) -> float:
    # "redmean": aproximacao barata da diferenca percebida entre duas cores rgb
    r1, g1, b1 = (v * 255 for v in to_rgb(a))
    r2, g2, b2 = (v * 255 for v in to_rgb(b))
    media_r = (r1 + r2) / 2
    dr, dg, db = r1 - r2, g1 - g2, b1 - b2
    quadrado = (2 + media_r / 256) * dr**2 + 4 * dg**2 + (2 + (255 - media_r) / 256) * db**2
    return float(quadrado**0.5)
