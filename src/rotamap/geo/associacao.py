import csv
import logging
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import pandas as pd

from rotamap.geo.malha import CRS, Malha
from rotamap.geo.matching import Matcher, Metodo, Resultado
from rotamap.models import Parada, Rota

log = logging.getLogger(__name__)

CAMADA_MALHA = "malha"
CAMADA_ROTAS = "rotas"
COLUNAS_RELATORIO = [
    "rota_id",
    "municipio",
    "uf",
    "metodo",
    "cod_ibge",
    "nome_ibge",
    "score",
    "detalhe",
]
# o que precisa de revisao vem primeiro no relatorio
_PRIORIDADE = [
    Metodo.NAO_ENCONTRADO,
    Metodo.APROXIMADO,
    Metodo.IGNORADO,
    Metodo.DISTRITO,
    Metodo.ALIAS,
    Metodo.CODIGO,
    Metodo.EXATO,
]


@dataclass(frozen=True, slots=True)
class Associacao:
    rota: Rota
    parada: Parada
    resultado: Resultado


def associar(rotas: list[Rota], matcher: Matcher) -> list[Associacao]:
    associacoes = [
        Associacao(rota, parada, matcher.associar(parada.municipio, parada.uf, parada.cod_ibge))
        for rota in rotas
        for parada in rota.paradas
    ]
    _resumir(associacoes)
    return associacoes


def camada_rotas(associacoes: list[Associacao], malha: Malha) -> gpd.GeoDataFrame:
    """uma linha por municipio de cada rota, com a geometria da malha."""
    linhas = {
        (a.rota.id, a.resultado.municipio.cod_ibge): (
            a.rota.id,
            a.rota.nome,
            a.resultado.municipio.cod_ibge,
        )
        for a in associacoes
        if a.resultado.municipio is not None
    }
    tabela = pd.DataFrame(list(linhas.values()), columns=["rota_id", "rota_nome", "cod_ibge"])
    return gpd.GeoDataFrame(tabela.merge(malha.geo, on="cod_ibge"), geometry="geometry", crs=CRS)


def salvar_geo(malha: Malha, rotas: gpd.GeoDataFrame, caminho: Path) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.unlink(missing_ok=True)
    malha.geo.to_file(caminho, layer=CAMADA_MALHA, driver="GPKG")
    rotas.to_file(caminho, layer=CAMADA_ROTAS, driver="GPKG")


def carregar_geo(caminho: Path) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """devolve as camadas (malha, rotas) gravadas por salvar_geo."""
    malha = gpd.read_file(caminho, layer=CAMADA_MALHA)
    rotas = gpd.read_file(caminho, layer=CAMADA_ROTAS)
    return malha, rotas


def salvar_relatorio(associacoes: list[Associacao], caminho: Path) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    ordenadas = sorted(associacoes, key=lambda a: _PRIORIDADE.index(a.resultado.metodo))
    with caminho.open("w", encoding="utf-8", newline="") as arquivo:
        escritor = csv.writer(arquivo)
        escritor.writerow(COLUNAS_RELATORIO)
        escritor.writerows(_linha_relatorio(a) for a in ordenadas)


def _linha_relatorio(a: Associacao) -> list[str]:
    municipio = a.resultado.municipio
    return [
        a.rota.id,
        a.parada.municipio,
        a.parada.uf,
        a.resultado.metodo.value,
        municipio.cod_ibge if municipio else "",
        municipio.nome if municipio else "",
        "" if a.resultado.score is None else f"{a.resultado.score:.3f}",
        a.resultado.detalhe,
    ]


def _resumir(associacoes: list[Associacao]) -> None:
    contagem = Counter(a.resultado.metodo for a in associacoes)
    log.info(
        "matching: %s",
        ", ".join(f"{m.value}={contagem[m]}" for m in reversed(_PRIORIDADE) if contagem[m]),
    )
    for a in associacoes:
        if a.resultado.metodo is Metodo.NAO_ENCONTRADO:
            log.warning(
                "rota %s: %s/%s não encontrado (%s)",
                a.rota.id,
                a.parada.municipio,
                a.parada.uf,
                a.resultado.detalhe,
            )

    rotas_por_municipio: dict[str, set[str]] = defaultdict(set)
    for a in associacoes:
        if a.resultado.municipio is not None:
            rotas_por_municipio[a.resultado.municipio.nome].add(a.rota.id)
    compartilhados = {m: r for m, r in rotas_por_municipio.items() if len(r) > 1}
    if compartilhados:
        log.warning(
            "%d municípios aparecem em mais de uma rota: %s",
            len(compartilhados),
            "; ".join(f"{m} ({', '.join(sorted(r))})" for m, r in sorted(compartilhados.items())),
        )
