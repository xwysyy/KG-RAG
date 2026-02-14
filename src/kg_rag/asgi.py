"""ASGI entrypoint for running the FastAPI backend."""

from __future__ import annotations

import uvicorn

from kg_rag.api.app import create_app
from kg_rag.config import settings

app = create_app()


def main() -> None:
    uvicorn.run(
        "kg_rag.asgi:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=False,
    )
