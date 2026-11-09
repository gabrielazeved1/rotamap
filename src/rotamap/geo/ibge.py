import gzip
import json
import logging
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from rotamap import __version__

log = logging.getLogger(__name__)

API = "https://servicodados.ibge.gov.br/api"
QUALIDADES = ("minima", "intermediaria", "maxima")
_GZIP = b"\x1f\x8b"


class ErroIBGE(RuntimeError):
    pass


def cache_padrao() -> Path:
    if pasta := os.environ.get("ROTAMAP_CACHE"):
        return Path(pasta)
    base = os.environ.get("XDG_CACHE_HOME")
    return (Path(base) if base else Path.home() / ".cache") / "rotamap"


def municipios(uf: str, cache: Path) -> list[dict[str, Any]]:
    url = f"{API}/v1/localidades/estados/{uf}/municipios?view=nivelado"
    return _ler_json(_baixar(url, cache / f"municipios_{uf}.json"))


def distritos(uf: str, cache: Path) -> list[dict[str, Any]]:
    url = f"{API}/v1/localidades/estados/{uf}/distritos?view=nivelado"
    return _ler_json(_baixar(url, cache / f"distritos_{uf}.json"))


def malha_geojson(uf: str, cache: Path, qualidade: str = "intermediaria") -> Path:
    if qualidade not in QUALIDADES:
        raise ValueError(f"qualidade {qualidade!r} inválida; use uma de: {', '.join(QUALIDADES)}")
    url = (
        f"{API}/v3/malhas/estados/{uf}?formato=application/vnd.geo%2Bjson"
        f"&intrarregiao=municipio&qualidade={qualidade}"
    )
    return _baixar(url, cache / f"malha_{uf}_{qualidade}.geojson")


def _ler_json(caminho: Path) -> list[dict[str, Any]]:
    dados: list[dict[str, Any]] = json.loads(caminho.read_text(encoding="utf-8"))
    return dados


def _baixar(url: str, destino: Path, timeout: float = 60) -> Path:
    if destino.exists():
        log.debug("usando cache %s", destino)
        return destino

    log.info("baixando %s", url)
    pedido = urllib.request.Request(url, headers={"User-Agent": f"rotamap/{__version__}"})
    try:
        with urllib.request.urlopen(pedido, timeout=timeout) as resposta:
            conteudo: bytes = resposta.read()
        # a api de malhas responde em gzip mesmo sem o cliente pedir
        if conteudo[:2] == _GZIP:
            conteudo = gzip.decompress(conteudo)
        json.loads(conteudo)
    except (urllib.error.URLError, TimeoutError, ValueError) as erro:
        raise ErroIBGE(
            f"não foi possível obter {url} ({erro}); verifique a conexão ou use uma malha local"
        ) from erro

    destino.parent.mkdir(parents=True, exist_ok=True)
    # grava e renomeia para o cache nunca ficar com arquivo pela metade
    temporario = destino.with_name(destino.name + ".tmp")
    temporario.write_bytes(conteudo)
    temporario.replace(destino)
    return destino
