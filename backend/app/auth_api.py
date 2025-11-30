"""
Authentication API endpoints for Kalkulai.
"""
from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, Body, HTTPException, Header, Depends
from pydantic import BaseModel, EmailStr

from . import auth

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str
    password: str


class RegisterRequest(BaseModel):
    email: str
    password: str
    name: str = ""


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class ChangeEmailRequest(BaseModel):
    new_email: str
    password: str  # Require current password for email change


class UpdateProfileRequest(BaseModel):
    name: Optional[str] = None


class AuthResponse(BaseModel):
    token: str
    user: dict


def get_current_user(authorization: Optional[str] = Header(None)) -> dict:
    """Dependency to get current authenticated user."""
    if not authorization:
        raise HTTPException(status_code=401, detail="Nicht authentifiziert")
    
    # Extract token from "Bearer <token>"
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Ungültiges Token-Format")
    
    token = parts[1]
    payload = auth.verify_jwt(token)
    
    if not payload:
        raise HTTPException(status_code=401, detail="Token ungültig oder abgelaufen")
    
    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Ungültiges Token")
    
    user = auth.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="Benutzer nicht gefunden")
    
    return user


@router.post("/login")
def login(request: LoginRequest):
    """Login with email and password."""
    user = auth.authenticate_user(request.email, request.password)
    
    if not user:
        raise HTTPException(
            status_code=401,
            detail="E-Mail oder Passwort falsch"
        )
    
    token = auth.create_jwt({"user_id": user["id"], "email": user["email"]})
    
    return {
        "token": token,
        "user": {
            "id": user["id"],
            "email": user["email"],
            "name": user["name"],
        }
    }


@router.post("/register")
def register(request: RegisterRequest):
    """Register a new user."""
    if len(request.password) < 6:
        raise HTTPException(
            status_code=400,
            detail="Passwort muss mindestens 6 Zeichen lang sein"
        )
    
    try:
        user = auth.create_user(
            email=request.email,
            password=request.password,
            name=request.name
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    token = auth.create_jwt({"user_id": user["id"], "email": user["email"]})
    
    return {
        "token": token,
        "user": {
            "id": user["id"],
            "email": user["email"],
            "name": user["name"],
        }
    }


@router.get("/me")
def get_me(current_user: dict = Depends(get_current_user)):
    """Get current user profile."""
    return {
        "user": {
            "id": current_user["id"],
            "email": current_user["email"],
            "name": current_user["name"],
            "created_at": current_user["created_at"],
        }
    }


@router.post("/change-password")
def change_password(
    request: ChangePasswordRequest,
    current_user: dict = Depends(get_current_user)
):
    """Change user password."""
    if len(request.new_password) < 6:
        raise HTTPException(
            status_code=400,
            detail="Neues Passwort muss mindestens 6 Zeichen lang sein"
        )
    
    # Verify current password
    if not auth.verify_current_password(current_user["id"], request.current_password):
        raise HTTPException(
            status_code=400,
            detail="Aktuelles Passwort ist falsch"
        )
    
    # Update password
    success = auth.update_user_password(current_user["id"], request.new_password)
    
    if not success:
        raise HTTPException(status_code=500, detail="Fehler beim Aktualisieren")
    
    return {"success": True, "message": "Passwort erfolgreich geändert"}


@router.post("/change-email")
def change_email(
    request: ChangeEmailRequest,
    current_user: dict = Depends(get_current_user)
):
    """Change user email."""
    # Verify password
    if not auth.verify_current_password(current_user["id"], request.password):
        raise HTTPException(
            status_code=400,
            detail="Passwort ist falsch"
        )
    
    try:
        success = auth.update_user_email(current_user["id"], request.new_email)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    if not success:
        raise HTTPException(status_code=500, detail="Fehler beim Aktualisieren")
    
    # Generate new token with updated email
    token = auth.create_jwt({
        "user_id": current_user["id"],
        "email": request.new_email.lower()
    })
    
    return {
        "success": True,
        "message": "E-Mail erfolgreich geändert",
        "token": token,
        "user": {
            "id": current_user["id"],
            "email": request.new_email.lower(),
            "name": current_user["name"],
        }
    }


@router.put("/profile")
def update_profile(
    request: UpdateProfileRequest,
    current_user: dict = Depends(get_current_user)
):
    """Update user profile (name)."""
    if request.name is not None:
        auth.update_user_name(current_user["id"], request.name)
    
    # Get updated user
    user = auth.get_user_by_id(current_user["id"])
    
    return {
        "success": True,
        "user": {
            "id": user["id"],
            "email": user["email"],
            "name": user["name"],
        }
    }


@router.post("/logout")
def logout(current_user: dict = Depends(get_current_user)):
    """Logout (client should discard token)."""
    # In a stateless JWT setup, we just return success
    # Client is responsible for discarding the token
    return {"success": True, "message": "Erfolgreich abgemeldet"}


@router.post("/verify")
def verify_token(current_user: dict = Depends(get_current_user)):
    """Verify if token is still valid."""
    return {
        "valid": True,
        "user": {
            "id": current_user["id"],
            "email": current_user["email"],
            "name": current_user["name"],
        }
    }


class OfferLayoutRequest(BaseModel):
    layout: Dict[str, Any]


@router.get("/layout/offer")
def get_offer_layout(current_user: dict = Depends(get_current_user)):
    """Return stored offer layout configuration for the current user."""
    layout = auth.get_user_layout(current_user["id"], kind="offer") or {}
    return {"layout": layout}


@router.put("/layout/offer")
def save_offer_layout(
    request: OfferLayoutRequest,
    current_user: dict = Depends(get_current_user),
):
    """Persist offer layout configuration for the current user."""
    # keep the payload flexible; basic size guard to avoid abuse
    if len(json.dumps(request.layout, ensure_ascii=False)) > 50_000:
        raise HTTPException(status_code=400, detail="Layout ist zu groß")
    auth.save_user_layout(current_user["id"], request.layout, kind="offer")
    return {"success": True}

