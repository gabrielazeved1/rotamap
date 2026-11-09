import csv
import logging
import re
from pathlib import Path

from rotamap.io.base import EntradaInvalida, OpcoesEntrada, numero
from rotamap.models import UFS, Parada, Rota

log = logging.getLogger(__name__)

OBRIGATORIAS = ("rota_id", "rota_nome", "municipio", "uf")
OPCIONAIS = ("cod_ibge", "ordem")

_COD_IBGE = re.compile(r"\d{7}")


def ler_tidy(caminho: Path, opcoes: OpcoesEntrada | None = None) -> list[Rota]:
    """le o csv no formato oficial: uma linha por municipio de cada rota."""
    opcoes = opcoes or OpcoesEntrada()
    colunas, linhas = _ler_linhas(caminho, opcoes)
    metricas = [c for c in colunas if c not in OBRIGATORIAS + OPCIONAIS]

    rotas: dict[str, Rota] = {}
    vistos: set[tuple[str, str, str]] = set()
    problemas: list[str] = []
    for num, valores in linhas:
        try:
            rota_id, rota_nome, parada = _converter(colunas, valores, metricas, opcoes.decimal)
            rota = rotas.setdefault(rota_id, Rota(id=rota_id, nome=rota_nome))
            if rota.nome != rota_nome:
                raise ValueError(f"rota {rota_id} com nome {rota_nome!r}, antes era {rota.nome!r}")
            chave = (rota_id, parada.municipio.casefold(), parada.uf)
            if chave in vistos:
                raise ValueError(f"{parada.municipio}/{parada.uf} repetido na rota {rota_id}")
        except ValueError as erro:
            problemas.append(f"linha {num}: {erro}")
            continue
        vistos.add(chave)
        rota.paradas.append(parada)

    if not linhas:
        problemas.append("nenhuma linha de dados")
    if problemas:
        raise EntradaInvalida(caminho, problemas)

    for rota in rotas.values():
        _ordenar(rota)
    log.info("%d rotas e %d paradas lidas de %s", len(rotas), len(vistos), caminho.name)
    return list(rotas.values())


def _ler_linhas(
    caminho: Path, opcoes: OpcoesEntrada
) -> tuple[list[str], list[tuple[int, list[str]]]]:
    # utf-8-sig aceita o bom que o excel coloca no inicio
    with caminho.open(encoding=opcoes.encoding or "utf-8-sig", newline="") as arquivo:
        leitor = csv.reader(arquivo, delimiter=opcoes.sep)
        cabecalho = next(leitor, [])
        colunas = [c.strip().lower() for c in cabecalho]
        faltando = [c for c in OBRIGATORIAS if c not in colunas]
        if faltando:
            raise EntradaInvalida(caminho, [f"coluna obrigatória ausente: {c}" for c in faltando])
        linhas = [
            (leitor.line_num, valores) for valores in leitor if any(v.strip() for v in valores)
        ]
    return colunas, linhas


def _converter(
    colunas: list[str], valores: list[str], metricas: list[str], decimal: str
) -> tuple[str, str, Parada]:
    if len(valores) != len(colunas):
        raise ValueError(f"{len(valores)} colunas, esperado {len(colunas)}")
    registro = {c: v.strip() for c, v in zip(colunas, valores, strict=True)}

    vazias = [c for c in OBRIGATORIAS if not registro[c]]
    if vazias:
        raise ValueError(f"coluna(s) vazia(s): {', '.join(vazias)}")

    uf = registro["uf"].upper()
    if uf not in UFS:
        raise ValueError(f"uf inválida: {registro['uf']!r}")

    cod_ibge = registro.get("cod_ibge") or None
    if cod_ibge is not None and not _COD_IBGE.fullmatch(cod_ibge):
        raise ValueError(f"cod_ibge deve ter 7 dígitos: {cod_ibge!r}")

    parada = Parada(
        municipio=registro["municipio"],
        uf=uf,
        ordem=_inteiro(registro.get("ordem", "")),
        cod_ibge=cod_ibge,
        metricas=_metricas(registro, metricas, decimal),
    )
    return registro["rota_id"], registro["rota_nome"], parada


def _inteiro(texto: str) -> int | None:
    if not texto:
        return None
    try:
        return int(texto)
    except ValueError:
        raise ValueError(f"ordem deve ser inteira: {texto!r}") from None


def _metricas(registro: dict[str, str], colunas: list[str], decimal: str) -> dict[str, float]:
    resultado: dict[str, float] = {}
    for coluna in colunas:
        try:
            valor = numero(registro[coluna], decimal)
        except ValueError:
            raise ValueError(f"métrica {coluna!r} não numérica: {registro[coluna]!r}") from None
        if valor is not None:
            resultado[coluna] = valor
    return resultado


def _ordenar(rota: Rota) -> None:
    # sort estavel: sem ordem mantem a sequencia do arquivo, no fim
    rota.paradas.sort(key=lambda p: (p.ordem is None, p.ordem or 0))
