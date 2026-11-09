import logging
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import pandas as pd

from rotamap.geo import ibge

log = logging.getLogger(__name__)

# sirgas 2000, o referencial das malhas do ibge
CRS = "EPSG:4674"
COLUNAS = ["cod_ibge", "nome", "uf", "geometry"]
# nomes das colunas nos shapefiles de municipios que o ibge distribui
_COLUNAS_SHAPEFILE = {"CD_MUN": "cod_ibge", "NM_MUN": "nome", "SIGLA_UF": "uf"}


@dataclass(frozen=True, slots=True)
class Municipio:
    cod_ibge: str
    nome: str
    uf: str


@dataclass(frozen=True, slots=True)
class Distrito:
    nome: str
    municipio: Municipio


@dataclass(slots=True)
class Malha:
    geo: gpd.GeoDataFrame
    distritos: list[Distrito]

    @property
    def municipios(self) -> list[Municipio]:
        return _municipios(self.geo)


def carregar_malha(
    ufs: Iterable[str], *, cache: Path | None = None, qualidade: str = "intermediaria"
) -> Malha:
    """baixa (ou le do cache) a malha municipal e os distritos das ufs."""
    siglas = sorted(set(ufs))
    cache = cache or ibge.cache_padrao()
    partes = [_malha_uf(uf, cache, qualidade) for uf in siglas]
    geo = gpd.GeoDataFrame(pd.concat(partes, ignore_index=True), crs=CRS)
    return Malha(geo=geo, distritos=_distritos(siglas, geo, cache))


def ler_malha_local(caminho: Path, ufs: Iterable[str], *, cache: Path | None = None) -> Malha:
    """le um shapefile ou gpkg de municipios do ibge (colunas cd_mun, nm_mun, sigla_uf)."""
    siglas = sorted(set(ufs))
    bruto = gpd.read_file(caminho)
    faltando = [c for c in _COLUNAS_SHAPEFILE if c not in bruto.columns]
    if faltando:
        raise ValueError(f"{caminho}: colunas ausentes na malha: {', '.join(faltando)}")
    geo = bruto.rename(columns=_COLUNAS_SHAPEFILE)[COLUNAS]
    geo = geo[geo["uf"].isin(siglas)].reset_index(drop=True).to_crs(CRS)
    if geo.empty:
        raise ValueError(f"{caminho}: nenhum município das ufs {', '.join(siglas)}")
    geo["cod_ibge"] = geo["cod_ibge"].astype(str)
    return Malha(geo=geo, distritos=_distritos(siglas, geo, cache or ibge.cache_padrao()))


def _malha_uf(uf: str, cache: Path, qualidade: str) -> gpd.GeoDataFrame:
    geo = gpd.read_file(ibge.malha_geojson(uf, cache, qualidade))
    geo = geo.rename(columns={"codarea": "cod_ibge"}).set_crs(CRS, allow_override=True)
    nomes = {str(m["municipio-id"]): m["municipio-nome"] for m in ibge.municipios(uf, cache)}
    geo["cod_ibge"] = geo["cod_ibge"].astype(str)
    geo["nome"] = geo["cod_ibge"].map(nomes)
    geo["uf"] = uf
    sem_nome = geo["nome"].isna()
    if sem_nome.any():
        log.warning("%s: %d áreas da malha sem município correspondente", uf, sem_nome.sum())
        geo = geo[~sem_nome]
    return geo[COLUNAS]


def _municipios(geo: gpd.GeoDataFrame) -> list[Municipio]:
    colunas = zip(geo["cod_ibge"], geo["nome"], geo["uf"], strict=True)
    return [Municipio(cod, nome, uf) for cod, nome, uf in colunas]


def _distritos(siglas: list[str], geo: gpd.GeoDataFrame, cache: Path) -> list[Distrito]:
    por_cod = {m.cod_ibge: m for m in _municipios(geo)}
    resultado: list[Distrito] = []
    for uf in siglas:
        try:
            dados = ibge.distritos(uf, cache)
        except ibge.ErroIBGE as erro:
            # distritos so melhoram o matching; sem eles o pipeline segue
            log.warning("distritos de %s indisponíveis: %s", uf, erro)
            continue
        for d in dados:
            municipio = por_cod.get(str(d["municipio-id"]))
            if municipio is not None:
                resultado.append(Distrito(d["distrito-nome"], municipio))
    return resultado
