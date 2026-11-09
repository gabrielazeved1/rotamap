import logging
from collections.abc import Mapping

import numpy as np
import numpy.typing as npt
import shapely
from shapely.geometry.base import BaseGeometry

log = logging.getLogger(__name__)

Ponto = tuple[float, float]


def ponto_central(geometria: BaseGeometry) -> Ponto:
    """centro do maior circulo que cabe na geometria; fica dentro mesmo em formas concavas."""
    tolerancia = max(np.sqrt(geometria.area) / 200, 1e-9)
    centro = shapely.maximum_inscribed_circle(geometria, tolerancia).coords[0]
    return float(centro[0]), float(centro[1])


def posicionar_rotulos(areas: Mapping[str, BaseGeometry], raio: float) -> dict[str, Ponto]:
    """posiciona um rotulo circular por area, sem sobreposicao e dentro da propria area."""
    colocados: dict[str, Ponto] = {}
    # as menores tem menos espaco livre, entao escolhem primeiro
    for chave in sorted(areas, key=lambda k: areas[k].area):
        candidatos = pontos_candidatos(areas[chave], raio)
        ocupados = np.array(list(colocados.values())).reshape(-1, 2)
        livre = next((c for c in candidatos if _cabe(c, ocupados, raio)), None)
        if livre is None:
            log.debug("sem espaço livre para o rótulo %s; ficou sobreposto", chave)
            livre = candidatos[0]
        colocados[chave] = (float(livre[0]), float(livre[1]))
    return colocados


def _cabe(ponto: npt.NDArray[np.float64], ocupados: npt.NDArray[np.float64], raio: float) -> bool:
    if not len(ocupados):
        return True
    return bool(np.min(np.hypot(*(ocupados - ponto).T)) >= 2 * raio)


def pontos_candidatos(area: BaseGeometry, raio: float) -> npt.NDArray[np.float64]:
    """pontos da area: primeiro onde o circulo cabe inteiro, depois os mais perto do centro."""
    centro = np.array(ponto_central(area))
    x0, y0, x1, y1 = area.bounds
    passo = raio / 2
    grade_x, grade_y = np.meshgrid(
        np.arange(x0, x1 + passo, passo), np.arange(y0, y1 + passo, passo)
    )
    xs, ys = grade_x.ravel(), grade_y.ravel()
    dentro = shapely.contains_xy(area, xs, ys)
    pontos = np.column_stack([xs[dentro], ys[dentro]])
    if not len(pontos):
        return centro.reshape(1, 2)

    folga = shapely.distance(area.boundary, shapely.points(pontos))
    distancia = np.hypot(*(pontos - centro).T)
    ordem = np.lexsort((distancia, folga < raio * 0.8))
    return np.vstack([centro, pontos[ordem]])
