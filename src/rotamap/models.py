import re
from dataclasses import dataclass, field

UFS = frozenset(
    {
        "AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MG", "MS", "MT", "PA",
        "PB", "PE", "PI", "PR", "RJ", "RN", "RO", "RR", "RS", "SC", "SE", "SP", "TO",
    }
)  # fmt: skip


@dataclass(slots=True)
class Parada:
    municipio: str
    uf: str
    ordem: int | None = None
    cod_ibge: str | None = None
    metricas: dict[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class Rota:
    id: str
    nome: str
    paradas: list[Parada] = field(default_factory=list)


def chave_rota(rota_id: str) -> tuple[tuple[int, int | str], ...]:
    """ordena ids como numeros quando possivel: 2 vem antes de 10."""
    partes = re.split(r"(\d+)", rota_id)
    return tuple((0, int(p)) if p.isdigit() else (1, p) for p in partes if p)
