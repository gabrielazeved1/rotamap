import logging
from dataclasses import dataclass
from pathlib import Path

from rotamap.config import Config
from rotamap.geo import (
    Associacao,
    Matcher,
    Metodo,
    associar,
    camada_rotas,
    carregar_geo,
    carregar_malha,
    ler_malha_local,
    salvar_geo,
    salvar_relatorio,
)
from rotamap.geo.malha import Malha
from rotamap.io import carregar_rotas, ler_entrada, ler_formato, salvar_rotas
from rotamap.metricas import PRESETS, Metrica, calcular, metricas_padrao
from rotamap.models import Rota, chave_rota
from rotamap.ppt import Conteudo, SlideRota, ler_hotspots, montar_apresentacao
from rotamap.render import ARQ_HOTSPOTS, caminho_mapa_rota, renderizar

log = logging.getLogger(__name__)

COR_SEM_MAPA = "#BAB0AC"


class ArtefatoAusente(FileNotFoundError):
    pass


@dataclass(frozen=True, slots=True)
class Pasta:
    """onde cada etapa grava o que a proxima vai ler."""

    raiz: Path

    @property
    def rotas(self) -> Path:
        return self.raiz / "rotas.json"

    @property
    def rotas_geo(self) -> Path:
        return self.raiz / "rotas_geo.json"

    @property
    def gpkg(self) -> Path:
        return self.raiz / "rotas_geo.gpkg"

    @property
    def matching(self) -> Path:
        return self.raiz / "matching.csv"

    @property
    def mapas(self) -> Path:
        return self.raiz / "mapas"

    @property
    def hotspots(self) -> Path:
        return self.mapas / ARQ_HOTSPOTS

    @property
    def apresentacao(self) -> Path:
        return self.raiz / "apresentacao.pptx"


def executar(entrada: Path, pasta: Pasta, config: Config, *, ppt: bool = True) -> None:
    etapa_parse(entrada, pasta, config)
    etapa_geo(pasta, config)
    etapa_maps(pasta, config)
    if ppt:
        etapa_ppt(pasta, config)


def etapa_parse(entrada: Path, pasta: Pasta, config: Config) -> list[Rota]:
    rotas = ler_entrada(entrada, config.entrada.formato, config.entrada.opcoes())
    salvar_rotas(rotas, pasta.rotas, config.entrada.formato)
    log.info("parse: %s", pasta.rotas)
    return rotas


def etapa_geo(pasta: Pasta, config: Config) -> None:
    rotas = carregar_rotas(_exigir(pasta.rotas, "parse"))
    ufs = {p.uf for r in rotas for p in r.paradas} | set(config.geo.ufs)
    malha = _malha(ufs, config)
    matcher = Matcher(malha.municipios, malha.distritos, config.geo.aliases, config.geo.cutoff)
    associacoes = associar(rotas, matcher)
    _enriquecer(associacoes)

    salvar_relatorio(associacoes, pasta.matching)
    camada = camada_rotas(associacoes, malha)
    if camada.empty:
        raise ValueError(f"nenhum município foi associado à malha; veja {pasta.matching}")
    salvar_rotas(rotas, pasta.rotas_geo, ler_formato(pasta.rotas))
    salvar_geo(malha, camada, pasta.gpkg)
    log.info("geo: %s, %s e %s", pasta.rotas_geo, pasta.gpkg, pasta.matching)


def etapa_maps(pasta: Pasta, config: Config) -> dict[str, str]:
    malha, rotas = carregar_geo(_exigir(pasta.gpkg, "geo"))
    return renderizar(malha, rotas, pasta.mapas, config.render)


def etapa_ppt(pasta: Pasta, config: Config) -> Path:
    rotas = sorted(carregar_rotas(_exigir(pasta.rotas_geo, "geo")), key=lambda r: chave_rota(r.id))
    menu = ler_hotspots(_exigir(pasta.hotspots, "maps"))
    metricas = _metricas(rotas, ler_formato(pasta.rotas_geo), config)
    cores = {h.rota_id: h.cor for h in menu.hotspots}

    slides = [
        SlideRota(
            id=r.id,
            nome=r.nome,
            cor=cores.get(r.id, COR_SEM_MAPA),
            cidades=_cidades(r),
            kpis=calcular(r.paradas, metricas),
            mapa=caminho_mapa_rota(pasta.mapas, r.id) if r.id in cores else None,
        )
        for r in rotas
    ]
    todas = [p for r in rotas for p in r.paradas]
    resumo = [("Rotas", str(len(rotas))), *calcular(todas, _resumo(metricas, config))]
    ufs = sorted({p.uf for p in todas})
    conteudo = Conteudo(
        titulo=config.titulo,
        rotas=slides,
        menu=menu,
        subtitulo=config.subtitulo or " · ".join(ufs),
        resumo=resumo,
    )
    return montar_apresentacao(conteudo, pasta.apresentacao, config.tema)


def _malha(ufs: set[str], config: Config) -> Malha:
    if config.geo.malha is not None:
        return ler_malha_local(config.geo.malha, ufs, cache=config.geo.cache)
    return carregar_malha(ufs, cache=config.geo.cache, qualidade=config.geo.qualidade)


def _enriquecer(associacoes: list[Associacao]) -> None:
    for a in associacoes:
        municipio = a.resultado.municipio
        a.parada.ignorada = a.resultado.metodo is Metodo.IGNORADO
        if municipio is not None:
            a.parada.cod_ibge = municipio.cod_ibge
            a.parada.nome_ibge = municipio.nome


def _cidades(rota: Rota) -> list[str]:
    # nomes oficiais, sem repetir bairros do mesmo municipio
    return list(dict.fromkeys(p.nome_ibge for p in rota.paradas if p.nome_ibge))


def _metricas(rotas: list[Rota], formato: str, config: Config) -> list[Metrica]:
    if config.metricas:
        return list(config.metricas)
    return PRESETS.get(formato) or metricas_padrao(rotas)


def _resumo(metricas: list[Metrica], config: Config) -> list[Metrica]:
    if not config.resumo:
        return metricas[:3]
    por_rotulo = {m.rotulo: m for m in metricas}
    faltando = [r for r in config.resumo if r not in por_rotulo]
    if faltando:
        raise ValueError(
            f"resumo cita métricas que não existem: {', '.join(faltando)}; "
            f"disponíveis: {', '.join(por_rotulo)}"
        )
    return [por_rotulo[r] for r in config.resumo]


def _exigir(caminho: Path, etapa: str) -> Path:
    if not caminho.exists():
        raise ArtefatoAusente(f"{caminho} não existe; rode a etapa '{etapa}' antes")
    return caminho
