"""Models endpoint to fetch available models from llama.cpp."""

import httpx
from fastapi import APIRouter, HTTPException

from backend.config import settings
from backend.models import ModelInfo, ModelListResponse
from backend.services.storage import list_servers

router = APIRouter(prefix="/models", tags=["models"])


@router.get("", response_model=ModelListResponse)
async def list_models():
    """Fetch available models from llama.cpp server."""
    try:
        # Use first active admin server if available, else config.yaml default
        server_url = settings.llama.url
        active_servers = await list_servers(active_only=True)
        if active_servers:
            server_url = active_servers[0].url

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{server_url}/v1/models")

            if response.status_code != 200:
                raise HTTPException(
                    status_code=503,
                    detail="Failed to fetch models from LLM server"
                )

            data = response.json()

            # Parse the response from llama.cpp
            models = []
            for model_data in data.get("data", []):
                models.append(ModelInfo(
                    id=model_data.get("id", "unknown"),
                    object=model_data.get("object", "model"),
                    owned_by=model_data.get("owned_by", "llama.cpp")
                ))

            return ModelListResponse(object="list", data=models)

    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail="Cannot connect to LLM server"
        )
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=503,
            detail="Timeout connecting to LLM server"
        )
