import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from rotamap.models import Parada, Rota

VERSAO = 1


def salvar_rotas(rotas: list[Rota], caminho: Path, formato: str = "tidy") -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    dados = {"versao": VERSAO, "formato": formato, "rotas": [asdict(r) for r in rotas]}
    caminho.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")


def carregar_rotas(caminho: Path) -> list[Rota]:
    return [_rota(r) for r in _ler(caminho)["rotas"]]


def ler_formato(caminho: Path) -> str:
    """formato da entrada original, usado para escolher o preset de metricas."""
    formato: str = _ler(caminho).get("formato", "tidy")
    return formato


def _ler(caminho: Path) -> dict[str, Any]:
    dados: dict[str, Any] = json.loads(caminho.read_text(encoding="utf-8"))
    if dados.get("versao") != VERSAO:
        raise ValueError(
            f"{caminho}: versão {dados.get('versao')!r} não suportada, esperado {VERSAO}; "
            "rode a etapa parse de novo"
        )
    return dados


def _rota(dados: dict[str, Any]) -> Rota:
    return Rota(
        id=dados["id"],
        nome=dados["nome"],
        paradas=[Parada(**p) for p in dados["paradas"]],
    )
