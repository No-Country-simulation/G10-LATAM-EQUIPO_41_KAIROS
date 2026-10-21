"""Paquete NuevaMente (Kairos).

Versión: 1.N corresponde al Sprint N (1.5 = Sprint 5). Es la única fuente de la versión:
la usan la API (/health, /api/v1/opciones, /docs) y el pie de la interfaz web. Al cambiar
de sprint, se actualiza aquí y en pyproject.toml (un test comprueba que coincidan).
"""

__version__ = "1.5.0"
VERSION_VISIBLE = ".".join(__version__.split(".")[:2])  # la que ve el usuario: "1.5"
