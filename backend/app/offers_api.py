"""
Offers API - Speichern und Verwalten von Angeboten
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Body, HTTPException, Header, Depends
from pydantic import BaseModel

from app.auth_api import get_current_user

# Database path
DB_PATH = Path(__file__).parent.parent / "var" / "kalkulai.db"

router = APIRouter(prefix="/api/offers", tags=["offers"])


# --- Models ---

class OfferPosition(BaseModel):
    nr: int
    name: str
    menge: float
    einheit: str
    epreis: float
    gesamtpreis: Optional[float] = None


class CreateOfferRequest(BaseModel):
    title: str
    kunde: Optional[str] = None
    positions: List[OfferPosition]
    notes: Optional[str] = None


class UpdateOfferRequest(BaseModel):
    title: Optional[str] = None
    kunde: Optional[str] = None
    positions: Optional[List[OfferPosition]] = None
    notes: Optional[str] = None
    status: Optional[str] = None


# --- Database ---

def _get_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_offers_table() -> None:
    """Initialize offers table."""
    conn = _get_db()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS offers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                kunde TEXT,
                positions TEXT NOT NULL,
                notes TEXT,
                status TEXT DEFAULT 'draft',
                netto_summe REAL DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_offers_user ON offers(user_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_offers_status ON offers(status)")
        conn.commit()
    finally:
        conn.close()


def _calculate_netto(positions: List[Dict]) -> float:
    """Calculate netto sum from positions."""
    total = 0.0
    for p in positions:
        menge = float(p.get("menge", 0) or 0)
        epreis = float(p.get("epreis", 0) or 0)
        total += menge * epreis
    return round(total, 2)


def _offer_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    """Convert database row to dict."""
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "title": row["title"],
        "kunde": row["kunde"],
        "positions": json.loads(row["positions"]) if row["positions"] else [],
        "notes": row["notes"],
        "status": row["status"],
        "netto_summe": row["netto_summe"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


# --- API Endpoints ---

@router.get("")
def list_offers(
    status: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    """List all offers for current user."""
    conn = _get_db()
    try:
        if status:
            cursor = conn.execute(
                "SELECT * FROM offers WHERE user_id = ? AND status = ? ORDER BY updated_at DESC",
                (current_user["id"], status)
            )
        else:
            cursor = conn.execute(
                "SELECT * FROM offers WHERE user_id = ? ORDER BY updated_at DESC",
                (current_user["id"],)
            )
        rows = cursor.fetchall()
        return {"offers": [_offer_to_dict(row) for row in rows]}
    finally:
        conn.close()


@router.post("")
def create_offer(
    request: CreateOfferRequest,
    current_user: dict = Depends(get_current_user)
):
    """Create a new offer."""
    positions_list = [p.model_dump() for p in request.positions]
    
    # Calculate gesamtpreis for each position
    for p in positions_list:
        p["gesamtpreis"] = round((p.get("menge", 0) or 0) * (p.get("epreis", 0) or 0), 2)
    
    netto = _calculate_netto(positions_list)
    
    conn = _get_db()
    try:
        cursor = conn.execute(
            """INSERT INTO offers (user_id, title, kunde, positions, notes, netto_summe)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                current_user["id"],
                request.title,
                request.kunde,
                json.dumps(positions_list, ensure_ascii=False),
                request.notes,
                netto
            )
        )
        conn.commit()
        offer_id = cursor.lastrowid
        
        # Fetch and return the created offer
        cursor = conn.execute("SELECT * FROM offers WHERE id = ?", (offer_id,))
        row = cursor.fetchone()
        return {"offer": _offer_to_dict(row)}
    finally:
        conn.close()


@router.get("/{offer_id}")
def get_offer(
    offer_id: int,
    current_user: dict = Depends(get_current_user)
):
    """Get a specific offer."""
    conn = _get_db()
    try:
        cursor = conn.execute(
            "SELECT * FROM offers WHERE id = ? AND user_id = ?",
            (offer_id, current_user["id"])
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Angebot nicht gefunden")
        return {"offer": _offer_to_dict(row)}
    finally:
        conn.close()


@router.put("/{offer_id}")
def update_offer(
    offer_id: int,
    request: UpdateOfferRequest,
    current_user: dict = Depends(get_current_user)
):
    """Update an offer."""
    conn = _get_db()
    try:
        # Check if offer exists and belongs to user
        cursor = conn.execute(
            "SELECT * FROM offers WHERE id = ? AND user_id = ?",
            (offer_id, current_user["id"])
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Angebot nicht gefunden")
        
        # Build update query dynamically
        updates = []
        values = []
        
        if request.title is not None:
            updates.append("title = ?")
            values.append(request.title)
        
        if request.kunde is not None:
            updates.append("kunde = ?")
            values.append(request.kunde)
        
        if request.positions is not None:
            positions_list = [p.model_dump() for p in request.positions]
            for p in positions_list:
                p["gesamtpreis"] = round((p.get("menge", 0) or 0) * (p.get("epreis", 0) or 0), 2)
            updates.append("positions = ?")
            values.append(json.dumps(positions_list, ensure_ascii=False))
            updates.append("netto_summe = ?")
            values.append(_calculate_netto(positions_list))
        
        if request.notes is not None:
            updates.append("notes = ?")
            values.append(request.notes)
        
        if request.status is not None:
            updates.append("status = ?")
            values.append(request.status)
        
        if updates:
            updates.append("updated_at = CURRENT_TIMESTAMP")
            values.append(offer_id)
            values.append(current_user["id"])
            
            conn.execute(
                f"UPDATE offers SET {', '.join(updates)} WHERE id = ? AND user_id = ?",
                values
            )
            conn.commit()
        
        # Fetch and return updated offer
        cursor = conn.execute("SELECT * FROM offers WHERE id = ?", (offer_id,))
        row = cursor.fetchone()
        return {"offer": _offer_to_dict(row)}
    finally:
        conn.close()


@router.delete("/{offer_id}")
def delete_offer(
    offer_id: int,
    current_user: dict = Depends(get_current_user)
):
    """Delete an offer."""
    conn = _get_db()
    try:
        cursor = conn.execute(
            "SELECT id FROM offers WHERE id = ? AND user_id = ?",
            (offer_id, current_user["id"])
        )
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Angebot nicht gefunden")
        
        conn.execute("DELETE FROM offers WHERE id = ?", (offer_id,))
        conn.commit()
        return {"success": True, "message": "Angebot gelöscht"}
    finally:
        conn.close()


@router.post("/{offer_id}/duplicate")
def duplicate_offer(
    offer_id: int,
    current_user: dict = Depends(get_current_user)
):
    """Duplicate an offer."""
    conn = _get_db()
    try:
        cursor = conn.execute(
            "SELECT * FROM offers WHERE id = ? AND user_id = ?",
            (offer_id, current_user["id"])
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Angebot nicht gefunden")
        
        # Create copy with new title
        new_title = f"{row['title']} (Kopie)"
        cursor = conn.execute(
            """INSERT INTO offers (user_id, title, kunde, positions, notes, netto_summe, status)
               VALUES (?, ?, ?, ?, ?, ?, 'draft')""",
            (
                current_user["id"],
                new_title,
                row["kunde"],
                row["positions"],
                row["notes"],
                row["netto_summe"]
            )
        )
        conn.commit()
        
        # Fetch and return new offer
        cursor = conn.execute("SELECT * FROM offers WHERE id = ?", (cursor.lastrowid,))
        new_row = cursor.fetchone()
        return {"offer": _offer_to_dict(new_row)}
    finally:
        conn.close()

