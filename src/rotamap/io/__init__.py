from pathlib import Path

from rotamap.io.artefato import carregar_rotas, salvar_rotas
from rotamap.io.base import EntradaInvalida, Leitor, OpcoesEntrada
from rotamap.io.erp_914 import ler_erp_914
from rotamap.io.tidy import ler_tidy
from rotamap.models import Rota

__all__ = [
    "LEITORES",
    "EntradaInvalida",
    "OpcoesEntrada",
    "carregar_rotas",
    "ler_entrada",
    "salvar_rotas",
]

LEITORES: dict[str, Leitor] = {
    "tidy": ler_tidy,
    "erp_914": ler_erp_914,
}


def ler_entrada(
    caminho: Path, formato: str = "tidy", opcoes: OpcoesEntrada | None = None
) -> list[Rota]:
    try:
        leitor = LEITORES[formato]
    except KeyError:
        formatos = ", ".join(LEITORES)
        raise ValueError(f"formato desconhecido {formato!r}; use um de: {formatos}") from None
    return leitor(caminho, opcoes or OpcoesEntrada())
