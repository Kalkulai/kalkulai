# speech_api.py
"""
Azure Speech Services API - Token-based authentication.

This module provides a secure endpoint to generate short-lived authorization tokens
for Azure Speech Services. The actual Speech API key is kept server-side, and clients
receive only temporary tokens that expire after ~10 minutes.

Environment Variables Required:
    AZURE_SPEECH_KEY: Your Azure Speech Services subscription key
    AZURE_SPEECH_REGION: Azure region (e.g., "westeurope", "eastus")
"""

import os
import logging
from datetime import datetime, timedelta

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger("kalkulai.speech")

router = APIRouter(prefix="/api/speech", tags=["speech"])

# --- Configuration from environment ---
AZURE_SPEECH_KEY = os.getenv("AZURE_SPEECH_KEY", "").strip()
AZURE_SPEECH_REGION = os.getenv("AZURE_SPEECH_REGION", "westeurope").strip()

# Token cache to avoid hitting Azure too frequently
_token_cache: dict = {"token": None, "expires_at": None}
TOKEN_REFRESH_MARGIN = timedelta(minutes=2)  # Refresh 2 min before expiry


class SpeechTokenResponse(BaseModel):
    """Response model for speech token endpoint."""
    token: str
    region: str
    expires_in_seconds: int


class SpeechConfigResponse(BaseModel):
    """Response model for speech config (without token, just region info)."""
    region: str
    enabled: bool


async def _fetch_azure_token() -> tuple[str, datetime]:
    """
    Fetch a new authorization token from Azure Speech Services.
    
    Azure tokens are valid for 10 minutes.
    See: https://learn.microsoft.com/en-us/azure/ai-services/speech-service/rest-speech-to-text
    """
    if not AZURE_SPEECH_KEY:
        raise HTTPException(
            status_code=503,
            detail="Azure Speech key nicht konfiguriert. Bitte AZURE_SPEECH_KEY in .env setzen."
        )
    
    token_url = f"https://{AZURE_SPEECH_REGION}.api.cognitive.microsoft.com/sts/v1.0/issueToken"
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                token_url,
                headers={
                    "Ocp-Apim-Subscription-Key": AZURE_SPEECH_KEY,
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                timeout=10.0,
            )
            response.raise_for_status()
            token = response.text
            # Azure tokens are valid for 10 minutes
            expires_at = datetime.utcnow() + timedelta(minutes=10)
            return token, expires_at
    except httpx.HTTPStatusError as e:
        logger.error(f"Azure Speech API error: {e.response.status_code} - {e.response.text}")
        raise HTTPException(
            status_code=502,
            detail=f"Azure Speech API Fehler: {e.response.status_code}"
        )
    except httpx.RequestError as e:
        logger.error(f"Azure Speech connection error: {e}")
        raise HTTPException(
            status_code=502,
            detail="Verbindung zu Azure Speech Services fehlgeschlagen."
        )


@router.get("/config", response_model=SpeechConfigResponse)
async def get_speech_config():
    """
    Get speech service configuration (without exposing sensitive data).
    
    Frontend can use this to check if voice input is available before showing UI.
    """
    return SpeechConfigResponse(
        region=AZURE_SPEECH_REGION,
        enabled=bool(AZURE_SPEECH_KEY),
    )


@router.get("/token", response_model=SpeechTokenResponse)
async def get_speech_token():
    """
    Get a short-lived authorization token for Azure Speech Services.
    
    The token can be used directly by the frontend with the Azure Speech SDK.
    Tokens are valid for approximately 10 minutes.
    
    This endpoint caches tokens and refreshes them automatically before expiry.
    """
    global _token_cache
    
    if not AZURE_SPEECH_KEY:
        raise HTTPException(
            status_code=503,
            detail="Spracherkennung nicht konfiguriert. Bitte Administrator kontaktieren."
        )
    
    now = datetime.utcnow()
    
    # Check if we have a valid cached token
    if (
        _token_cache["token"] 
        and _token_cache["expires_at"] 
        and _token_cache["expires_at"] > now + TOKEN_REFRESH_MARGIN
    ):
        remaining = (_token_cache["expires_at"] - now).total_seconds()
        return SpeechTokenResponse(
            token=_token_cache["token"],
            region=AZURE_SPEECH_REGION,
            expires_in_seconds=int(remaining),
        )
    
    # Fetch new token
    token, expires_at = await _fetch_azure_token()
    
    # Cache it
    _token_cache["token"] = token
    _token_cache["expires_at"] = expires_at
    
    remaining = (expires_at - now).total_seconds()
    logger.info(f"New Azure Speech token issued, expires in {int(remaining)}s")
    
    return SpeechTokenResponse(
        token=token,
        region=AZURE_SPEECH_REGION,
        expires_in_seconds=int(remaining),
    )

