"""Cierra el hallazgo CRITICAL #2 de ``verify-report.md`` (2026-08-26):
el requisito ADDED de ``api-conventions`` "Alcance del borrado suave y
excepción de mantenimiento", escenario "El mantenimiento nunca se expone
por HTTP", solo estaba verificado por inspección estática (``rg``), nunca por
una prueba en tiempo de ejecución.

Importar ``app.main`` no toca la base de datos: la conexión solo ocurre
dentro de ``lifespan`` (``app/main.py``), que un ``TestClient`` sin usar
``with`` jamás dispara. Enumerar ``app.routes`` y recorrer
``app.maintenance``/``scripts`` con ``pkgutil`` es, por lo tanto, seguro sin
BD (design.md, capa "CLI (sin BD)").
"""

import importlib
import pkgutil

from fastapi import APIRouter

from app.main import app

_TOKENS_PROHIBIDOS = ("maintenance", "purge", "seed")


def test_ninguna_ruta_http_registrada_contiene_tokens_de_mantenimiento() -> None:
    rutas = [route.path for route in app.routes if hasattr(route, "path")]

    assert rutas, "la app debe tener rutas registradas para que esta prueba sea significativa"
    for ruta in rutas:
        ruta_normalizada = ruta.lower()
        for token in _TOKENS_PROHIBIDOS:
            assert token not in ruta_normalizada, f"{ruta} expone el token prohibido {token!r}"


def test_ningun_modulo_de_maintenance_ni_scripts_define_un_apirouter() -> None:
    import app.maintenance
    import scripts

    for paquete in (app.maintenance, scripts):
        for info in pkgutil.walk_packages(paquete.__path__, prefix=f"{paquete.__name__}."):
            modulo = importlib.import_module(info.name)
            for nombre, valor in vars(modulo).items():
                assert not isinstance(valor, APIRouter), (
                    f"{info.name}.{nombre} define un APIRouter — el mantenimiento "
                    "nunca debe exponerse por HTTP"
                )
