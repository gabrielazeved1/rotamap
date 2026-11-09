"""gera um csv tidy sintetico com municipios reais e rotas e metricas inventadas."""

import csv
import logging
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import numpy as np
import numpy.typing as npt

log = logging.getLogger(__name__)

COLUNAS = [
    "rota_id",
    "rota_nome",
    "municipio",
    "uf",
    "ordem",
    "clientes",
    "atendidos",
    "entregas",
    "valor_total",
    "peso_kg",
    "lucro_pct",
]
LINHA_BALCAO = "Retirada no balcão"

Linha = dict[str, str | int | float]


@dataclass(frozen=True, slots=True)
class OpcoesExemplo:
    rotas: int = 40
    seed: int = 42
    cobertura: float = 0.7  # fracao dos municipios atendida por alguma rota
    max_municipios: int = 18
    # nomes fora do padrao para mostrar o matching
    sujeira: bool = True


def gerar_exemplo(malha: gpd.GeoDataFrame, opcoes: OpcoesExemplo | None = None) -> list[Linha]:
    """linhas no formato tidy; malha precisa das colunas nome, uf e geometry."""
    opcoes = opcoes or OpcoesExemplo()
    rng = np.random.default_rng(opcoes.seed)
    projetada = malha.to_crs("EPSG:5880").reset_index(drop=True)
    centros = np.column_stack(
        [projetada.representative_point().x, projetada.representative_point().y]
    )
    if opcoes.rotas > len(projetada):
        log.warning(
            "a malha tem só %d município(s); gerando %d rota(s) em vez de %d",
            len(projetada),
            len(projetada),
            opcoes.rotas,
        )
    sementes = _sementes(centros, min(opcoes.rotas, len(projetada)), rng)
    grupos = _grupos(centros, sementes, opcoes, rng)

    linhas: list[Linha] = []
    # ids de oeste para leste, como numeracao de rotas costuma ser
    for numero, semente in enumerate(sorted(grupos, key=lambda s: centros[s][0]), start=1):
        rota_id = str(100 + numero)
        rota_nome = f"Região de {projetada.loc[semente, 'nome']}"
        for ordem, indice in enumerate(_percurso(centros, grupos[semente]), start=1):
            linha: Linha = {
                "rota_id": rota_id,
                "rota_nome": rota_nome,
                "municipio": str(projetada.loc[indice, "nome"]),
                "uf": str(projetada.loc[indice, "uf"]),
                "ordem": ordem,
            }
            linhas.append(linha | _metricas(rng))
    if opcoes.sujeira:
        _sujar(linhas, rng)
    log.info("%d rotas e %d linhas sintéticas", len(grupos), len(linhas))
    return linhas


def salvar_csv(linhas: list[Linha], caminho: Path) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("w", encoding="utf-8", newline="") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=COLUNAS)
        escritor.writeheader()
        escritor.writerows(linhas)


def _sementes(centros: npt.NDArray[np.float64], k: int, rng: np.random.Generator) -> list[int]:
    # amostragem do ponto mais distante: espalha as rotas pelo estado todo
    escolhidas = [int(rng.integers(len(centros)))]
    distancia = np.hypot(*(centros - centros[escolhidas[0]]).T)
    while len(escolhidas) < k:
        proxima = int(np.argmax(distancia))
        escolhidas.append(proxima)
        distancia = np.minimum(distancia, np.hypot(*(centros - centros[proxima]).T))
    return escolhidas


def _grupos(
    centros: npt.NDArray[np.float64],
    sementes: list[int],
    opcoes: OpcoesExemplo,
    rng: np.random.Generator,
) -> dict[int, list[int]]:
    atendidos = rng.random(len(centros)) < opcoes.cobertura
    atendidos[sementes] = True
    distancias = np.hypot(*(centros[:, None, :] - centros[sementes][None, :, :]).transpose(2, 0, 1))
    mais_perto = np.argmin(distancias, axis=1)

    grupos: dict[int, list[int]] = {}
    for j, semente in enumerate(sementes):
        membros = [int(i) for i in np.flatnonzero(atendidos & (mais_perto == j))]
        membros.sort(key=lambda i: distancias[i, j])
        tamanho = int(rng.integers(3, opcoes.max_municipios + 1))
        grupos[semente] = membros[:tamanho]
    return grupos


def _percurso(centros: npt.NDArray[np.float64], membros: list[int]) -> list[int]:
    # vizinho mais proximo a partir da sede da rota: ordem de visita plausivel
    restantes = list(membros[1:])
    percurso = membros[:1]
    while restantes:
        atual = centros[percurso[-1]]
        proximo = min(restantes, key=lambda i: float(np.hypot(*(centros[i] - atual))))
        percurso.append(proximo)
        restantes.remove(proximo)
    return percurso


def _metricas(rng: np.random.Generator) -> Linha:
    clientes = max(1, round(rng.lognormal(np.log(15), 0.9)))
    atendidos = max(1, int(rng.binomial(clientes, rng.uniform(0.3, 0.9))))
    entregas = atendidos * int(rng.integers(1, 4))
    valor = round(entregas * rng.lognormal(np.log(2500), 0.5), 2)
    return {
        "clientes": clientes,
        "atendidos": atendidos,
        "entregas": entregas,
        "valor_total": valor,
        "peso_kg": round(valor / rng.uniform(8, 14), 1),
        "lucro_pct": round(float(np.clip(rng.normal(16, 3), 5, 30)), 2),
    }


def _sujar(linhas: list[Linha], rng: np.random.Generator) -> None:
    # como sai de um erp: maiusculas sem acento, regiao colada no nome e linha que nao é cidade
    for linha in linhas:
        if rng.random() < 0.15:
            linha["municipio"] = _sem_acento(str(linha["municipio"])).upper()
    primeira = linhas[0]
    centro = primeira | {"municipio": f"{_sem_acento(str(primeira['municipio'])).upper()} CENTRO"}
    balcao = primeira | {"municipio": LINHA_BALCAO} | _metricas(rng)
    fim_da_rota = max(
        i for i, linha in enumerate(linhas) if linha["rota_id"] == primeira["rota_id"]
    )
    ultima_ordem = int(linhas[fim_da_rota]["ordem"])
    centro["ordem"], balcao["ordem"] = ultima_ordem + 1, ultima_ordem + 2
    linhas[fim_da_rota + 1 : fim_da_rota + 1] = [centro | _metricas(rng), balcao]


def _sem_acento(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
