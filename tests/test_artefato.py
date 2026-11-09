import json
from pathlib import Path

import pytest

from rotamap.io import carregar_rotas, salvar_rotas
from rotamap.models import Parada, Rota


def test_ida_e_volta(tmp_path: Path) -> None:
    rotas = [
        Rota(
            id="10",
            nome="Noroeste",
            paradas=[
                Parada("Araçatuba", "SP", ordem=1, cod_ibge="3502804", metricas={"valor": 1.5}),
                Parada("Birigui", "SP"),
            ],
        )
    ]
    caminho = tmp_path / "sub" / "rotas.json"

    salvar_rotas(rotas, caminho)

    assert carregar_rotas(caminho) == rotas
    assert "Araçatuba" in caminho.read_text(encoding="utf-8")


def test_versao_incompativel(tmp_path: Path) -> None:
    caminho = tmp_path / "rotas.json"
    caminho.write_text(json.dumps({"versao": 99, "rotas": []}), encoding="utf-8")

    with pytest.raises(ValueError, match="parse de novo"):
        carregar_rotas(caminho)
