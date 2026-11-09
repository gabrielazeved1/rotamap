import tomllib
from dataclasses import dataclass, field, fields, replace
from pathlib import Path
from typing import Any, TypeVar

from rotamap.geo.matching import CUTOFF_PADRAO
from rotamap.io import OpcoesEntrada
from rotamap.metricas import Agregacao, Formato, Metrica
from rotamap.ppt import Tema
from rotamap.render import OpcoesRender

T = TypeVar("T")


class ConfigInvalida(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ConfigEntrada:
    formato: str = "tidy"
    encoding: str | None = None
    sep: str = ","
    decimal: str = "."
    uf_padrao: str | None = None

    def opcoes(self) -> OpcoesEntrada:
        return OpcoesEntrada(self.encoding, self.uf_padrao, self.sep, self.decimal)


@dataclass(frozen=True, slots=True)
class ConfigGeo:
    malha: Path | None = None  # shapefile local em vez da api do ibge
    qualidade: str = "intermediaria"
    cutoff: float = CUTOFF_PADRAO
    cache: Path | None = None
    ufs: tuple[str, ...] = ()  # ufs extras no mapa, alem das que aparecem nos dados
    # nome -> municipio ou cod_ibge; texto vazio marca o que nao é municipio
    aliases: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Config:
    titulo: str = "Rotas de entrega"
    subtitulo: str = ""
    # rotulos das metricas que aparecem na capa; vazio usa as tres primeiras
    resumo: tuple[str, ...] = ()
    entrada: ConfigEntrada = field(default_factory=ConfigEntrada)
    geo: ConfigGeo = field(default_factory=ConfigGeo)
    render: OpcoesRender = field(default_factory=OpcoesRender)
    tema: Tema = field(default_factory=Tema)
    # vazio usa o preset do formato ou a soma de cada coluna
    metricas: tuple[Metrica, ...] = ()


def carregar_config(caminho: Path | None) -> Config:
    if caminho is None:
        return Config()
    try:
        dados = tomllib.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as erro:
        raise ConfigInvalida(f"{caminho}: {erro}") from erro
    try:
        return _config(dados, base=caminho.parent)
    except (TypeError, ValueError) as erro:
        raise ConfigInvalida(f"{caminho}: {erro}") from erro


def _config(dados: dict[str, Any], base: Path) -> Config:
    secoes = {"entrada", "geo", "render", "tema", "metricas"}
    _verificar(Config, dados, "raiz")
    geral = {k: v for k, v in dados.items() if k not in secoes}
    if "resumo" in geral:
        geral["resumo"] = tuple(geral["resumo"])
    return replace(
        Config(**geral),
        entrada=_secao(ConfigEntrada, dados.get("entrada", {}), "entrada"),
        geo=_geo(dados.get("geo", {}), base),
        render=_render(dados.get("render", {})),
        tema=_secao(Tema, dados.get("tema", {}), "tema"),
        metricas=tuple(_metrica(m, i) for i, m in enumerate(dados.get("metricas", []), 1)),
    )


def _geo(dados: dict[str, Any], base: Path) -> ConfigGeo:
    valores = dict(dados)
    for chave in ("malha", "cache"):
        if chave in valores:
            valores[chave] = (base / valores[chave]).resolve()
    if "ufs" in valores:
        valores["ufs"] = tuple(uf.upper() for uf in valores["ufs"])
    return _secao(ConfigGeo, valores, "geo")


def _render(dados: dict[str, Any]) -> OpcoesRender:
    valores = dict(dados)
    if "tamanho_rota" in valores:
        valores["tamanho_rota"] = tuple(valores["tamanho_rota"])
    return _secao(OpcoesRender, valores, "render")


def _metrica(dados: dict[str, Any], posicao: int) -> Metrica:
    valores = dict(dados)
    try:
        if "agregacao" in valores:
            valores["agregacao"] = Agregacao(valores["agregacao"])
        if "formato" in valores:
            valores["formato"] = Formato(valores["formato"])
    except ValueError as erro:
        raise ValueError(f"[[metricas]] nº {posicao}: {erro}") from None
    return _secao(Metrica, valores, f"[[metricas]] nº {posicao}")


def _secao(classe: type[T], dados: dict[str, Any], nome: str) -> T:
    _verificar(classe, dados, nome)
    return classe(**dados)


def _verificar(classe: type, dados: dict[str, Any], nome: str) -> None:
    conhecidas = {f.name for f in fields(classe)}
    desconhecidas = sorted(set(dados) - conhecidas)
    if desconhecidas:
        raise ValueError(
            f"chave(s) desconhecida(s) em {nome}: {', '.join(desconhecidas)}; "
            f"válidas: {', '.join(sorted(conhecidas))}"
        )
