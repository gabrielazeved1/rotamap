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
