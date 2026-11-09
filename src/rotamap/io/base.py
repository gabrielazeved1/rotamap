import math
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from rotamap.models import Rota

_LIMITE_PROBLEMAS = 20


@dataclass(frozen=True, slots=True)
class OpcoesEntrada:
    # none deixa cada formato usar o proprio encoding
    encoding: str | None = None
    uf_padrao: str | None = None
    sep: str = ","
    decimal: str = "."


class EntradaInvalida(ValueError):
    def __init__(self, caminho: Path, problemas: list[str]) -> None:
        self.caminho = caminho
        self.problemas = problemas
        linhas = [f"  - {p}" for p in problemas[:_LIMITE_PROBLEMAS]]
        if len(problemas) > _LIMITE_PROBLEMAS:
            linhas.append(f"  ... e mais {len(problemas) - _LIMITE_PROBLEMAS}")
        super().__init__(
            f"{caminho}: {len(problemas)} problema(s) na entrada\n" + "\n".join(linhas)
        )


class Leitor(Protocol):
    def __call__(self, caminho: Path, opcoes: OpcoesEntrada) -> list[Rota]: ...


def numero(texto: str, decimal: str = ".") -> float | None:
    """converte texto em float; vazio vira none."""
    texto = texto.strip()
    if not texto:
        return None
    if decimal == ",":
        # no padrao brasileiro o ponto é separador de milhar
        texto = texto.replace(".", "").replace(",", ".")
    valor = float(texto)
    if not math.isfinite(valor):
        raise ValueError(f"valor não finito: {texto!r}")
    return valor
