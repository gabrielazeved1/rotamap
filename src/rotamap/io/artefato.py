import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from rotamap.models import Parada, Rota

VERSAO = 1


def salvar_rotas(rotas: list[Rota], caminho: Path) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    dados = {"versao": VERSAO, "rotas": [asdict(r) for r in rotas]}
    caminho.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")


def carregar_rotas(caminho: Path) -> list[Rota]:
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    if dados.get("versao") != VERSAO:
        raise ValueError(
            f"{caminho}: versão {dados.get('versao')!r} não suportada, esperado {VERSAO}; "
            "rode a etapa parse de novo"
        )
    return [_rota(r) for r in dados["rotas"]]


def _rota(dados: dict[str, Any]) -> Rota:
    return Rota(
        id=dados["id"],
        nome=dados["nome"],
        paradas=[Parada(**p) for p in dados["paradas"]],
    )
