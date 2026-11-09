import re
import unicodedata
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from difflib import SequenceMatcher, get_close_matches
from enum import StrEnum

from rotamap.geo.malha import Distrito, Municipio

CUTOFF_PADRAO = 0.85

_APOSTROFOS = re.compile(r"['`\u00b4\u2019]")
_NAO_ALFANUMERICO = re.compile(r"[^A-Z0-9]+")
_COD_IBGE = re.compile(r"\d{7}")


class Metodo(StrEnum):
    CODIGO = "codigo"
    ALIAS = "alias"
    EXATO = "exato"
    DISTRITO = "distrito"
    APROXIMADO = "aproximado"
    IGNORADO = "ignorado"
    NAO_ENCONTRADO = "nao_encontrado"


@dataclass(frozen=True, slots=True)
class Resultado:
    metodo: Metodo
    municipio: Municipio | None = None
    score: float | None = None
    detalhe: str = ""

    @property
    def encontrado(self) -> bool:
        return self.municipio is not None


def normalizar(nome: str) -> str:
    """deixa o nome comparavel: sem acento, apostrofo ou pontuacao, em maiusculas."""
    # o apostrofo sai antes do nfkd, que transformaria o acento agudo solto em espaco
    texto = _APOSTROFOS.sub("", nome)
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return " ".join(_NAO_ALFANUMERICO.sub(" ", texto.upper()).split())


class Matcher:
    """associa nomes de municipios da entrada aos municipios do ibge."""

    def __init__(
        self,
        municipios: Iterable[Municipio],
        distritos: Iterable[Distrito] = (),
        aliases: Mapping[str, str | None] | None = None,
        cutoff: float = CUTOFF_PADRAO,
    ) -> None:
        self._por_cod: dict[str, Municipio] = {}
        self._por_nome: dict[str, dict[str, Municipio]] = defaultdict(dict)
        for m in municipios:
            self._por_cod[m.cod_ibge] = m
            self._por_nome[m.uf][normalizar(m.nome)] = m

        self._distritos: dict[str, dict[str, set[Municipio]]] = defaultdict(
            lambda: defaultdict(set)
        )
        for d in distritos:
            self._distritos[d.municipio.uf][normalizar(d.nome)].add(d.municipio)

        # alias sem destino marca o que nao é municipio (ex.: retirada no balcao)
        self._aliases = {normalizar(k): (v or None) for k, v in (aliases or {}).items()}
        self._cutoff = cutoff

    def associar(self, municipio: str, uf: str, cod_ibge: str | None = None) -> Resultado:
        if cod_ibge:
            return self._por_codigo(cod_ibge)
        nome = normalizar(municipio)
        if nome in self._aliases:
            return self._por_alias(self._aliases[nome], uf)
        if achado := self._por_nome.get(uf, {}).get(nome):
            return Resultado(Metodo.EXATO, achado)
        return self._por_distrito(nome, uf) or self._aproximado(nome, uf)

    def _por_codigo(self, cod_ibge: str) -> Resultado:
        if achado := self._por_cod.get(cod_ibge):
            return Resultado(Metodo.CODIGO, achado)
        return Resultado(Metodo.NAO_ENCONTRADO, detalhe=f"cod_ibge {cod_ibge} fora da malha")

    def _por_alias(self, destino: str | None, uf: str) -> Resultado:
        if destino is None:
            return Resultado(Metodo.IGNORADO, detalhe="alias sem destino")
        if _COD_IBGE.fullmatch(destino):
            achado = self._por_cod.get(destino)
        else:
            achado = self._por_nome.get(uf, {}).get(normalizar(destino))
        if achado is None:
            return Resultado(
                Metodo.NAO_ENCONTRADO, detalhe=f"alias aponta para {destino!r}, que não existe"
            )
        return Resultado(Metodo.ALIAS, achado, detalhe=f"alias para {destino}")

    def _por_distrito(self, nome: str, uf: str) -> Resultado | None:
        candidatos = self._distritos.get(uf, {}).get(nome)
        if not candidatos:
            return None
        if len(candidatos) > 1:
            nomes = ", ".join(sorted(m.nome for m in candidatos))
            return Resultado(
                Metodo.NAO_ENCONTRADO, detalhe=f"distrito em mais de um município: {nomes}"
            )
        (achado,) = candidatos
        return Resultado(Metodo.DISTRITO, achado, detalhe=f"distrito de {achado.nome}")

    def _aproximado(self, nome: str, uf: str) -> Resultado:
        nomes = self._por_nome.get(uf, {})
        if not nomes:
            return Resultado(Metodo.NAO_ENCONTRADO, detalhe=f"uf {uf} fora da malha")
        (melhor,) = get_close_matches(nome, nomes, n=1, cutoff=0) or [""]
        score = round(SequenceMatcher(None, nome, melhor).ratio(), 3)
        if score >= self._cutoff:
            return Resultado(Metodo.APROXIMADO, nomes[melhor], score)
        if por_prefixo := _por_prefixo(nome, nomes):
            return por_prefixo
        sugestao = f"; mais parecido: {nomes[melhor].nome} ({score:.2f})" if melhor else ""
        return Resultado(
            Metodo.NAO_ENCONTRADO, score=score, detalhe=f"sem correspondência{sugestao}"
        )


def _por_prefixo(nome: str, nomes: dict[str, Municipio]) -> Resultado | None:
    # erps costumam anexar regiao ou filial ("CAMPINAS NORTE") ou cortar o fim do nome
    contidos = [n for n in nomes if nome.startswith(n + " ")]
    if contidos:
        achado = nomes[max(contidos, key=len)]
        return Resultado(Metodo.APROXIMADO, achado, detalhe=f"começa com {achado.nome}")
    estendidos = [n for n in nomes if n.startswith(nome + " ")]
    if len(estendidos) == 1:
        achado = nomes[estendidos[0]]
        return Resultado(Metodo.APROXIMADO, achado, detalhe=f"início de {achado.nome}")
    return None
