from __future__ import annotations

import os
from typing import Dict, List, Optional

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, Field

from backend.shared.normalize.text import normalize_query
from backend.store import catalog_store
from backend.retriever import index_manager

ADMIN_API_KEY = os.getenv("ADMIN_API_KEY")


class ProductIn(BaseModel):
    company_id: str = Field(..., min_length=1)
    sku: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    description: Optional[str] = None
    active: bool = True


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    active: Optional[bool] = None


class ProductOut(BaseModel):
    company_id: str
    sku: str
    name: str
    description: Optional[str]
    active: bool
    updated_at: Optional[str]


class SynonymIn(BaseModel):
    company_id: str
    canon: str
    synonyms: List[str] = Field(default_factory=list)


class IndexUpdateIn(BaseModel):
    company_id: str
    changed_skus: List[str] = Field(default_factory=list)


router = APIRouter(prefix="/api/admin")


def require_admin(x_admin_key: Optional[str] = Header(None, alias="X-Admin-Key")):
    if ADMIN_API_KEY and x_admin_key != ADMIN_API_KEY:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")


def _product_to_out(data: Dict[str, object]) -> ProductOut:
    return ProductOut(
        company_id=str(data.get("company_id")),
        sku=str(data.get("sku")),
        name=str(data.get("name")),
        description=data.get("description"),
        active=bool(data.get("is_active") if "is_active" in data else data.get("active", True)),
        updated_at=str(data.get("updated_at")) if data.get("updated_at") is not None else None,
    )


@router.get("/products", response_model=List[ProductOut])
def list_active_products(
    company_id: str = Query(...),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    include_deleted: bool = Query(False),
    _: None = Depends(require_admin),
):
    if include_deleted:
        products = catalog_store.list_products(company_id, include_deleted=True)
    else:
        products = catalog_store.get_active_products(company_id)
    paged = products[offset : offset + limit]
    return [_product_to_out(prod) for prod in paged]


@router.post("/products", response_model=ProductOut)
def create_or_update_product(product: ProductIn, _: None = Depends(require_admin)):
    payload = {
        "sku": product.sku,
        "name": product.name,
        "description": product.description,
        "is_active": product.active,
    }
    data = catalog_store.upsert_product(product.company_id, payload)
    return _product_to_out(data)


@router.put("/products/{sku}", response_model=ProductOut)
def update_product(
    sku: str,
    update: ProductUpdate,
    company_id: str = Query(...),
    _: None = Depends(require_admin),
):
    products = catalog_store.list_products(company_id, include_deleted=True)
    current = next((prod for prod in products if prod["sku"] == sku), None)
    if current is None:
        raise HTTPException(status_code=404, detail="Product not found")
    payload = {
        "sku": sku,
        "name": update.name or current.get("name"),
        "description": update.description if update.description is not None else current.get("description"),
        "is_active": current.get("is_active") if update.active is None else update.active,
    }
    data = catalog_store.upsert_product(company_id, payload)
    return _product_to_out(data)


@router.delete("/products/{sku}", response_model=Dict[str, bool])
def delete_product_route(sku: str, company_id: str = Query(...), _: None = Depends(require_admin)):
    deleted = catalog_store.delete_product(company_id, sku)
    return {"deleted": deleted}


@router.post("/synonyms", response_model=Dict[str, List[str]])
def add_synonyms(payload: SynonymIn, _: None = Depends(require_admin)):
    canon = normalize_query(payload.canon)
    for variant in payload.synonyms:
        norm_variant = normalize_query(variant)
        if norm_variant:
            catalog_store.add_synonym(payload.company_id, canon, norm_variant)
    return list_synonyms(company_id=payload.company_id)


@router.get("/synonyms", response_model=Dict[str, List[str]])
def list_synonyms(company_id: str = Query(...), _: None = Depends(require_admin)):
    mapping = catalog_store.list_synonyms(company_id)
    normalized: Dict[str, List[str]] = {}
    for canon, variants in mapping.items():
        canon_norm = normalize_query(canon)
        variant_norms = sorted({normalize_query(v) for v in variants if normalize_query(v)})
        if variant_norms:
            normalized[canon_norm] = variant_norms
    return normalized


@router.post("/index/rebuild", response_model=Dict[str, object])
def rebuild_index(payload: Dict[str, str] = Body(...), _: None = Depends(require_admin)):
    company_id = payload.get("company_id")
    if not company_id:
        raise HTTPException(status_code=400, detail="company_id required")
    index_manager.rebuild_index(company_id)
    return index_manager.get_index_stats(company_id)


@router.post("/index/update", response_model=Dict[str, object])
def update_index(payload: IndexUpdateIn, _: None = Depends(require_admin)):
    index_manager.update_index_incremental(payload.company_id, payload.changed_skus)
    return index_manager.get_index_stats(payload.company_id)


@router.get("/index/stats", response_model=Dict[str, object])
def get_stats(company_id: str = Query(...), _: None = Depends(require_admin)):
    return index_manager.get_index_stats(company_id)
