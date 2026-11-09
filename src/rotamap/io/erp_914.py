"""adaptador do relatorio "914 - rentabilidade por rota" exportado pelo erp."""

# o relatorio é um layout de impressao salvo como csv: cabecalho de pagina repetido,
# um bloco por rota e as colunas das paradas em posicao fixa

import csv
import logging
import re
from collections import Counter
from pathlib import Path

from rotamap.io.base import EntradaInvalida, OpcoesEntrada, numero
from rotamap.models import UFS, Parada, Rota

log = logging.getLogger(__name__)

ENCODING = "mac_roman"
SEP = ";"

_COL_ROTA_ID = 2
_COL_ROTA_NOME = 3
_COL_ORDEM = 1
_COL_MUNICIPIO = 3
# so valores brutos; as medias por entrega e por kg sao recalculadas a partir deles
_COLUNAS_METRICAS = {
    "distancia": 6,
    "populacao": 7,
    "clientes": 9,
    "atendidos": 11,
    "cargas": 13,
    "entregas": 14,
    "valor_total": 15,
    "notas": 17,
    "peso_kg": 19,
    "lucro_pct": 24,
}
_MIN_COLUNAS = max(_COLUNAS_METRICAS.values()) + 1

# aparece como "BIRIGUI - SP", "SANTOPOLIS DO AGUAPEI- SP", "LAVRINHAS (SP)",
# "BONFIM PAULISTA - SP **" ou sem uf quando o nome foi cortado
_MUNICIPIO = re.compile(r"(?P<nome>.*?)\s*(?:-\s*(?P<uf>[A-Z]{2})|\((?P<uf_par>[A-Z]{2})\))?[\s*]*")


def ler_erp_914(caminho: Path, opcoes: OpcoesEntrada | None = None) -> list[Rota]:
    """le o relatorio 914 e devolve as rotas no modelo interno."""
    opcoes = opcoes or OpcoesEntrada()
    # o arquivo usa \r como quebra de linha; read_text ja normaliza
    texto = caminho.read_text(encoding=opcoes.encoding or ENCODING)

    rotas: list[Rota] = []
    sem_uf: list[Parada] = []
    problemas: list[str] = []
    atual: Rota | None = None
    for num, campos in enumerate(csv.reader(texto.splitlines(), delimiter=SEP), start=1):
        if _inicio_de_rota(campos):
            atual = Rota(id=campos[_COL_ROTA_ID].strip(), nome=campos[_COL_ROTA_NOME].strip())
            rotas.append(atual)
        elif _fim_de_rota(campos):
            atual = None
        elif atual is not None and _eh_parada(campos):
            try:
                parada = _converter(campos)
            except ValueError as erro:
                problemas.append(f"linha {num}: {erro}")
                continue
            atual.paradas.append(parada)
            if not parada.uf:
                sem_uf.append(parada)

    if not rotas:
        problemas.append("nenhuma rota encontrada; o arquivo é mesmo um relatório 914?")
    if problemas:
        raise EntradaInvalida(caminho, problemas)

    if sem_uf:
        _preencher_uf(sem_uf, rotas, opcoes.uf_padrao, caminho)
    return _descartar_vazias(rotas, caminho)


def _inicio_de_rota(campos: list[str]) -> bool:
    return len(campos) > _COL_ROTA_NOME and campos[0].startswith("ROTA:")


def _fim_de_rota(campos: list[str]) -> bool:
    return bool(campos) and campos[0].startswith("Qt. pra")


def _eh_parada(campos: list[str]) -> bool:
    return len(campos) > _COL_MUNICIPIO and not campos[0] and campos[_COL_ORDEM].strip().isdigit()


def _converter(campos: list[str]) -> Parada:
    if len(campos) < _MIN_COLUNAS:
        raise ValueError(f"{len(campos)} colunas, esperado ao menos {_MIN_COLUNAS}")
    nome, uf = separar_uf(campos[_COL_MUNICIPIO])
    if not nome:
        raise ValueError("município vazio")
    metricas: dict[str, float] = {}
    for chave, coluna in _COLUNAS_METRICAS.items():
        valor = numero(campos[coluna], decimal=",")
        if valor is not None:
            metricas[chave] = valor
    return Parada(municipio=nome, uf=uf, ordem=int(campos[_COL_ORDEM]), metricas=metricas)


def separar_uf(texto: str) -> tuple[str, str]:
    """separa "NOME - UF" em nome e uf; uf vazia quando o relatorio nao traz."""
    achado = _MUNICIPIO.fullmatch(texto.strip())
    if achado is None:
        return texto.strip(), ""
    uf = achado["uf"] or achado["uf_par"] or ""
    if uf not in UFS:
        return texto.strip(" *"), ""
    return achado["nome"], uf


def _preencher_uf(
    paradas: list[Parada], rotas: list[Rota], uf_padrao: str | None, caminho: Path
) -> None:
    uf = uf_padrao.upper() if uf_padrao else _uf_mais_comum(rotas)
    if uf is None or uf not in UFS:
        nomes = ", ".join(p.municipio for p in paradas[:5])
        raise EntradaInvalida(caminho, [f"municípios sem uf ({nomes}...); informe a uf padrão"])
    if not uf_padrao:
        log.info("%d municípios sem uf no relatório, assumindo %s", len(paradas), uf)
    for parada in paradas:
        parada.uf = uf


def _uf_mais_comum(rotas: list[Rota]) -> str | None:
    contagem = Counter(p.uf for r in rotas for p in r.paradas if p.uf)
    return contagem.most_common(1)[0][0] if contagem else None


def _descartar_vazias(rotas: list[Rota], caminho: Path) -> list[Rota]:
    vazias = [r.id for r in rotas if not r.paradas]
    if vazias:
        log.warning("rotas sem paradas ignoradas: %s", ", ".join(vazias))
    validas = [r for r in rotas if r.paradas]
    total = sum(len(r.paradas) for r in validas)
    log.info("%d rotas e %d paradas lidas de %s", len(validas), total, caminho.name)
    return validas
