import gzip
import io
import json
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from rotamap.geo import ibge


class _Resposta(io.BytesIO):
    def __enter__(self) -> "_Resposta":
        return self


class ApiFalsa:
    """devolve o conteudo configurado e registra as urls pedidas."""

    def __init__(self) -> None:
        self.conteudo: bytes | Exception = b"[]"
        self.pedidas: list[str] = []

    def urlopen(self, pedido: urllib.request.Request, timeout: float) -> _Resposta:
        self.pedidas.append(pedido.full_url)
        if isinstance(self.conteudo, Exception):
            raise self.conteudo
        return _Resposta(self.conteudo)


@pytest.fixture
def api(monkeypatch: pytest.MonkeyPatch) -> ApiFalsa:
    falsa = ApiFalsa()
    monkeypatch.setattr(urllib.request, "urlopen", falsa.urlopen)
    return falsa


def test_baixa_e_grava_no_cache(tmp_path: Path, api: ApiFalsa) -> None:
    api.conteudo = json.dumps([{"municipio-id": 1, "municipio-nome": "A"}]).encode()

    dados = ibge.municipios("SP", tmp_path)

    assert dados == [{"municipio-id": 1, "municipio-nome": "A"}]
    assert "estados/SP/municipios" in api.pedidas[0]
    assert (tmp_path / "municipios_SP.json").exists()


def test_usa_o_cache_sem_rede(tmp_path: Path, api: ApiFalsa) -> None:
    (tmp_path / "distritos_SP.json").write_text("[]", encoding="utf-8")

    assert ibge.distritos("SP", tmp_path) == []
    assert api.pedidas == []


def test_descompacta_gzip(tmp_path: Path, api: ApiFalsa) -> None:
    api.conteudo = gzip.compress(b'{"type": "FeatureCollection", "features": []}')

    caminho = ibge.malha_geojson("SP", tmp_path, "minima")

    assert json.loads(caminho.read_text(encoding="utf-8"))["features"] == []
    assert "qualidade=minima" in api.pedidas[0]


@pytest.mark.parametrize(
    "conteudo",
    [urllib.error.URLError("sem conexão"), TimeoutError(), b"<html>erro</html>"],
)
def test_falha_vira_erro_ibge_sem_sujar_o_cache(
    tmp_path: Path, api: ApiFalsa, conteudo: bytes | Exception
) -> None:
    api.conteudo = conteudo

    with pytest.raises(ibge.ErroIBGE, match="malha local"):
        ibge.municipios("SP", tmp_path)

    assert list(tmp_path.iterdir()) == []


def test_qualidade_invalida(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="qualidade"):
        ibge.malha_geojson("SP", tmp_path, "altissima")


def test_cache_padrao(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ROTAMAP_CACHE", str(tmp_path / "a"))
    assert ibge.cache_padrao() == tmp_path / "a"

    monkeypatch.delenv("ROTAMAP_CACHE")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg"))
    assert ibge.cache_padrao() == tmp_path / "xdg" / "rotamap"
