from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from rotamap.models import Parada, Rota


class Agregacao(StrEnum):
    SOMA = "soma"
    MEDIA = "media"
    PONDERADA = "ponderada"
    RAZAO = "razao"
    CONTAGEM = "contagem"


class Formato(StrEnum):
    NUMERO = "numero"
    INTEIRO = "inteiro"
    MOEDA = "moeda"
    PERCENTUAL = "percentual"


@dataclass(frozen=True, slots=True)
class Metrica:
    """um kpi do slide: como agregar as paradas da rota e como exibir o resultado."""

    rotulo: str
    coluna: str | None = None
    agregacao: Agregacao = Agregacao.SOMA
    peso: str | None = None  # usado na media ponderada
    por: str | None = None  # denominador da razao
    formato: Formato = Formato.NUMERO
    casas: int = 0

    def __post_init__(self) -> None:
        if self.agregacao is not Agregacao.CONTAGEM and not self.coluna:
            raise ValueError(f"métrica {self.rotulo!r}: falta a coluna")
        if self.agregacao is Agregacao.PONDERADA and not self.peso:
            raise ValueError(f"métrica {self.rotulo!r}: média ponderada precisa de peso")
        if self.agregacao is Agregacao.RAZAO and not self.por:
            raise ValueError(f"métrica {self.rotulo!r}: razão precisa do denominador (por)")


MUNICIPIOS = Metrica("Municípios", agregacao=Agregacao.CONTAGEM, formato=Formato.INTEIRO)

# reproduz os totais do relatorio 914: medias saem das somas e o lucro é ponderado pelo valor
PRESETS: dict[str, list[Metrica]] = {
    "erp_914": [
        MUNICIPIOS,
        Metrica("Faturamento", "valor_total", formato=Formato.MOEDA),
        Metrica(
            "Margem",
            "lucro_pct",
            Agregacao.PONDERADA,
            peso="valor_total",
            formato=Formato.PERCENTUAL,
            casas=1,
        ),
        Metrica("Clientes atendidos", "atendidos", formato=Formato.INTEIRO),
        Metrica("Entregas", "entregas", formato=Formato.INTEIRO),
        Metrica(
            "Valor por entrega",
            "valor_total",
            Agregacao.RAZAO,
            por="entregas",
            formato=Formato.MOEDA,
        ),
    ],
}


def metricas_padrao(rotas: Iterable[Rota]) -> list[Metrica]:
    """sem configuracao: numero de municipios e a soma de cada coluna numerica."""
    colunas: dict[str, bool] = {}
    for rota in rotas:
        for parada in rota.paradas:
            for coluna, valor in parada.metricas.items():
                colunas[coluna] = colunas.get(coluna, True) and float(valor).is_integer()
    somas = [
        Metrica(_rotulo(coluna), coluna, casas=0 if inteira else 2)
        for coluna, inteira in colunas.items()
    ]
    return [MUNICIPIOS, *somas]


def agregar(paradas: list[Parada], metrica: Metrica) -> float | None:
    coluna = metrica.coluna or ""
    valores = [p.metricas[coluna] for p in paradas if coluna in p.metricas]
    match metrica.agregacao:
        case Agregacao.CONTAGEM:
            return float(len({_chave_municipio(p) for p in paradas if not p.ignorada}))
        case Agregacao.SOMA:
            return sum(valores) if valores else None
        case Agregacao.MEDIA:
            return sum(valores) / len(valores) if valores else None
        case Agregacao.PONDERADA:
            return _razao(paradas, coluna, metrica.peso or "", ponderar=True)
        case Agregacao.RAZAO:
            return _razao(paradas, coluna, metrica.por or "", ponderar=False)


def formatar(valor: float | None, metrica: Metrica) -> str:
    if valor is None:
        return "–"
    casas = 0 if metrica.formato is Formato.INTEIRO else metrica.casas
    # separadores no padrao brasileiro sem depender do locale da maquina
    texto = f"{abs(valor):,.{casas}f}".replace(",", "_").replace(".", ",").replace("_", ".")
    # round evita "-0" quando o valor arredondado é zero
    sinal = "-" if round(valor, casas) < 0 else ""
    match metrica.formato:
        case Formato.MOEDA:
            return f"{sinal}R$ {texto}"
        case Formato.PERCENTUAL:
            return f"{sinal}{texto}%"
        case Formato.NUMERO | Formato.INTEIRO:
            return f"{sinal}{texto}"


def calcular(paradas: list[Parada], metricas: Iterable[Metrica]) -> list[tuple[str, str]]:
    """pares (rotulo, valor formatado) prontos para o slide."""
    return [(m.rotulo, formatar(agregar(paradas, m), m)) for m in metricas]


def _razao(paradas: list[Parada], coluna: str, outra: str, *, ponderar: bool) -> float | None:
    pares = [
        (p.metricas[coluna], p.metricas[outra])
        for p in paradas
        if coluna in p.metricas and outra in p.metricas
    ]
    denominador = sum(b for _, b in pares)
    if not pares or denominador == 0:
        return None
    numerador = sum(a * b for a, b in pares) if ponderar else sum(a for a, _ in pares)
    return numerador / denominador


def _chave_municipio(parada: Parada) -> str:
    # bairros do mesmo municipio ("campinas norte" e "campinas sul") contam uma vez
    return parada.cod_ibge or f"{parada.municipio.casefold()}/{parada.uf}"


def _rotulo(coluna: str) -> str:
    return coluna.replace("_", " ").strip().capitalize()
