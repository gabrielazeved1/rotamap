import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import pytest

# tres municipios reais com geometrias quadradas inventadas, lado a lado perto de sp
LADO = 0.2
MUNICIPIOS = [
    ("3509502", "Campinas", (0, 0)),
    ("3543402", "Ribeirão Preto", (1, 0)),
    ("3515152", "Euclides da Cunha Paulista", (2, 0)),
]
DISTRITOS = [
    ("Campinas", "3509502"),
    ("Joaquim Egídio", "3509502"),
    ("Ribeirão Preto", "3543402"),
    ("Bonfim Paulista", "3543402"),
]


@pytest.fixture(autouse=True)
def sem_rede(monkeypatch: pytest.MonkeyPatch) -> None:
    def bloqueado(*_: Any, **__: Any) -> None:
        raise AssertionError("teste tentou acessar a rede")

    monkeypatch.setattr(urllib.request, "urlopen", bloqueado)


@pytest.fixture
def rede_fora(monkeypatch: pytest.MonkeyPatch) -> None:
    def sem_conexao(*_: Any, **__: Any) -> None:
        raise urllib.error.URLError("sem conexão")

    monkeypatch.setattr(urllib.request, "urlopen", sem_conexao)


def _quadrado(i: int, j: int) -> dict[str, Any]:
    x, y = -48 + i * LADO, -23 + j * LADO
    anel = [[x, y], [x + LADO, y], [x + LADO, y + LADO], [x, y + LADO], [x, y]]
    return {"type": "Polygon", "coordinates": [anel]}


@pytest.fixture
def cache_sp(tmp_path: Path) -> Path:
    """cache do ibge ja preenchido para sp, sem precisar de rede."""
    cache = tmp_path / "cache"
    cache.mkdir()
    malha = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {"codarea": cod}, "geometry": _quadrado(*xy)}
            for cod, _, xy in MUNICIPIOS
        ],
    }
    municipios = [{"municipio-id": int(cod), "municipio-nome": nome} for cod, nome, _ in MUNICIPIOS]
    distritos = [{"distrito-nome": nome, "municipio-id": int(cod)} for nome, cod in DISTRITOS]
    (cache / "malha_SP_intermediaria.geojson").write_text(json.dumps(malha), encoding="utf-8")
    (cache / "municipios_SP.json").write_text(json.dumps(municipios), encoding="utf-8")
    (cache / "distritos_SP.json").write_text(json.dumps(distritos), encoding="utf-8")
    return cache
