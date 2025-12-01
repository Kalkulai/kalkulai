from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path
from typing import Dict, List, Optional

try:  # Preferred
    from sqlmodel import Field, Session, SQLModel, UniqueConstraint, create_engine, select

    _HAS_SQLMODEL = True
except ImportError:  # Fallback to sqlite3
    import sqlite3

    _HAS_SQLMODEL = False

_PRIMARY_DB_URL = os.getenv("DB_URL")
DB_URL = _PRIMARY_DB_URL or os.getenv("KALKULAI_DB_URL") or "sqlite:///backend/var/kalkulai.db"
_engine = None
_engine_url = None


def _ensure_sqlite_dir(url: str) -> str:
    if not url.startswith("sqlite:///"):
        return url
    filename = url.replace("sqlite:///", "", 1)
    if filename == ":memory:":
        return ":memory:"
    Path(filename).parent.mkdir(parents=True, exist_ok=True)
    return filename


_DB_PATH = _ensure_sqlite_dir(DB_URL)
_MEM_ANCHOR = None


if _HAS_SQLMODEL:

    class Product(SQLModel, table=True):
        __tablename__ = "products"
        __table_args__ = (UniqueConstraint("company_id", "sku", name="uq_company_sku"),)

        id: Optional[int] = Field(default=None, primary_key=True)
        company_id: str = Field(index=True)
        sku: str = Field(index=True)
        name: str
        description: Optional[str] = None
        
        # Pricing & Units
        price_eur: Optional[float] = Field(default=None)
        unit: Optional[str] = Field(default=None)  # l, kg, m, m², stk
        volume_l: Optional[float] = Field(default=None)  # Numeric volume/quantity
        
        # Classification
        category: Optional[str] = Field(default=None, index=True)  # paint, primer, tools, etc.
        material_type: Optional[str] = Field(default=None)  # dispersion_paint_white, etc.
        unit_package: Optional[str] = Field(default=None)  # Eimer, Dose, Rolle, etc.
        tags: Optional[str] = Field(default=None)  # Semicolon-separated tags
        
        is_active: bool = Field(default=True, index=True)
        updated_at: datetime = Field(default_factory=datetime.utcnow, index=True)

    class Synonym(SQLModel, table=True):
        __tablename__ = "synonyms"
        __table_args__ = (UniqueConstraint("company_id", "canon", "variant", name="uq_company_synonym"),)

        id: Optional[int] = Field(default=None, primary_key=True)
        company_id: str = Field(index=True)
        canon: str = Field(index=True)
        variant: str
        confidence: float = Field(default=0.9)
        updated_at: datetime = Field(default_factory=datetime.utcnow, index=True)


def _get_engine():
    if not _HAS_SQLMODEL:
        raise RuntimeError("SQLModel is unavailable; use sqlite fallback helpers instead.")
    global _engine, _engine_url
    if _engine is None or _engine_url != DB_URL:
        connect_args = {"check_same_thread": False} if DB_URL.startswith("sqlite") else {}
        _engine = create_engine(DB_URL, echo=False, connect_args=connect_args)
        _engine_url = DB_URL
    return _engine


def _session() -> Session:
    return Session(_get_engine())


def _ensure_sqlite_dir(url: str) -> str:
    if not url.startswith("sqlite:///"):
        return url
    filename = url.replace("sqlite:///", "", 1)
    if filename == ":memory:":
        return ":memory:"
    Path(filename).parent.mkdir(parents=True, exist_ok=True)
    return filename


def _sqlite_conn():
    global _MEM_ANCHOR
    if _DB_PATH == ":memory:":
        uri = "file:kalkulai_mem?mode=memory&cache=shared"
        if _MEM_ANCHOR is None:
            _MEM_ANCHOR = sqlite3.connect(uri, uri=True)
            _MEM_ANCHOR.row_factory = sqlite3.Row
        conn = sqlite3.connect(uri, uri=True)
    else:
        conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    if _HAS_SQLMODEL:
        SQLModel.metadata.create_all(_get_engine())
        return
    with _sqlite_conn() as conn:
        # Create products table with all fields
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id TEXT NOT NULL,
                sku TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                price_eur REAL,
                unit TEXT,
                volume_l REAL,
                category TEXT,
                material_type TEXT,
                unit_package TEXT,
                tags TEXT,
                is_active INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT NOT NULL,
                UNIQUE(company_id, sku)
            )
            """
        )
        
        # Migrate existing table: Add new columns if they don't exist
        cursor = conn.execute("PRAGMA table_info(products)")
        existing_columns = {row[1] for row in cursor.fetchall()}
        
        new_columns = {
            "price_eur": "REAL",
            "unit": "TEXT",
            "volume_l": "REAL",
            "category": "TEXT",
            "material_type": "TEXT",
            "unit_package": "TEXT",
            "tags": "TEXT",
        }
        
        for col_name, col_type in new_columns.items():
            if col_name not in existing_columns:
                try:
                    conn.execute(f"ALTER TABLE products ADD COLUMN {col_name} {col_type}")
                    print(f"✅ Migration: Added column '{col_name}' to products table")
                except Exception as e:
                    print(f"⚠️  Migration warning: Could not add column '{col_name}': {e}")
        
        conn.execute("CREATE INDEX IF NOT EXISTS idx_products_company ON products(company_id)")
        
        # Only create category index if column exists
        if "category" in existing_columns or "category" in new_columns:
            try:
                conn.execute("CREATE INDEX IF NOT EXISTS idx_products_category ON products(category)")
            except Exception:
                pass  # Column might not exist yet in edge cases
        
        # Create synonyms table
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS synonyms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id TEXT NOT NULL,
                canon TEXT NOT NULL,
                variant TEXT NOT NULL,
                confidence REAL NOT NULL DEFAULT 0.9,
                updated_at TEXT NOT NULL,
                UNIQUE(company_id, canon, variant)
            )
            """
        )
        conn.commit()


def upsert_product(company_id: str, product_dict: Dict[str, object]) -> Dict[str, object]:
    if "sku" not in product_dict or "name" not in product_dict:
        raise ValueError("Product must contain 'sku' and 'name'.")
    sku = str(product_dict["sku"]).strip()
    name = str(product_dict["name"]).strip()
    if not sku or not name:
        raise ValueError("Product 'sku' and 'name' must be non-empty.")
    
    # Extract all fields
    description = product_dict.get("description")
    desc_val = str(description) if description is not None else None
    
    # Pricing & Units
    price_eur = product_dict.get("price_eur")
    price_val = float(price_eur) if price_eur is not None else None
    
    unit = product_dict.get("unit")
    unit_val = str(unit).strip() if unit else None
    
    volume_l = product_dict.get("volume_l")
    volume_val = float(volume_l) if volume_l is not None else None
    
    # Classification
    category = product_dict.get("category")
    category_val = str(category).strip() if category else None
    
    material_type = product_dict.get("material_type")
    material_type_val = str(material_type).strip() if material_type else None
    
    unit_package = product_dict.get("unit_package")
    unit_package_val = str(unit_package).strip() if unit_package else None
    
    tags = product_dict.get("tags")
    tags_val = str(tags).strip() if tags else None
    
    # Active status
    is_active_raw = product_dict.get("is_active")
    if is_active_raw is None and "active" in product_dict:
        is_active_raw = product_dict["active"]
    is_active_specified = is_active_raw is not None
    is_active_val = bool(is_active_raw) if is_active_specified else True
    reactivating = bool(is_active_raw) if is_active_specified else False
    updated = datetime.utcnow().isoformat()

    if _HAS_SQLMODEL:
        with _session() as session:
            stmt = select(Product).where(Product.company_id == company_id, Product.sku == sku)
            product = session.exec(stmt).one_or_none()
            if product is None:
                product = Product(company_id=company_id, sku=sku, name=name)
                session.add(product)
            product.name = name
            product.description = desc_val
            product.price_eur = price_val
            product.unit = unit_val
            product.volume_l = volume_val
            product.category = category_val
            product.material_type = material_type_val
            product.unit_package = unit_package_val
            product.tags = tags_val
            product.is_active = is_active_val
            if reactivating and hasattr(product, "is_deleted"):
                setattr(product, "is_deleted", False)
            product.updated_at = datetime.fromisoformat(updated)
            session.commit()
            session.refresh(product)
            data = product.dict()
            data.pop("id", None)
            return data

    with _sqlite_conn() as conn:
        conn.execute(
            """
            INSERT INTO products(
                company_id, sku, name, description, 
                price_eur, unit, volume_l, 
                category, material_type, unit_package, tags,
                is_active, updated_at
            )
            VALUES (
                :cid, :sku, :name, :desc, 
                :price, :unit, :volume,
                :category, :material_type, :unit_package, :tags,
                :active, :updated
            )
            ON CONFLICT(company_id, sku) DO UPDATE SET
                name = excluded.name,
                description = excluded.description,
                price_eur = excluded.price_eur,
                unit = excluded.unit,
                volume_l = excluded.volume_l,
                category = excluded.category,
                material_type = excluded.material_type,
                unit_package = excluded.unit_package,
                tags = excluded.tags,
                is_active = excluded.is_active,
                updated_at = excluded.updated_at
            """,
            {
                "cid": company_id,
                "sku": sku,
                "name": name,
                "desc": desc_val,
                "price": price_val,
                "unit": unit_val,
                "volume": volume_val,
                "category": category_val,
                "material_type": material_type_val,
                "unit_package": unit_package_val,
                "tags": tags_val,
                "active": 1 if is_active_val else 0,
                "updated": updated,
            },
        )
        conn.commit()
        if reactivating:
            try:
                conn.execute(
                    "UPDATE products SET is_deleted=0 WHERE company_id=? AND sku=?",
                    (company_id, sku),
                )
                conn.commit()
            except Exception:
                pass
        row = conn.execute(
            """
            SELECT company_id, sku, name, description, 
                   price_eur, unit, volume_l,
                   category, material_type, unit_package, tags,
                   is_active, updated_at 
            FROM products 
            WHERE company_id=? AND sku=?
            """,
            (company_id, sku),
        ).fetchone()
        return _normalize_product_row(dict(row))


def list_products(
    company_id: str,
    include_deleted: bool = False,
    filter_skus: Optional[List[str]] = None,
) -> List[Dict[str, object]]:
    if _HAS_SQLMODEL:
        with _session() as session:
            stmt = select(Product).where(Product.company_id == company_id)
            if not include_deleted:
                stmt = stmt.where(Product.is_active.is_(True))
            if filter_skus:
                stmt = stmt.where(Product.sku.in_(filter_skus))
            return [prod.dict(exclude={"id"}) for prod in session.exec(stmt).all()]
    with _sqlite_conn() as conn:
        query = (
            """SELECT company_id, sku, name, description, 
                      price_eur, unit, volume_l,
                      category, material_type, unit_package, tags,
                      is_active, updated_at 
               FROM products WHERE company_id=?"""
        )
        params = [company_id]
        if not include_deleted:
            query += " AND is_active=1"
        if filter_skus:
            placeholders = ",".join(["?"] * len(filter_skus))
            query += f" AND sku IN ({placeholders})"
            params.extend(filter_skus)
        rows = conn.execute(query, tuple(params)).fetchall()
        return [_normalize_product_row(dict(r)) for r in rows]


def get_active_products(company_id: str) -> List[Dict[str, object]]:
    if _HAS_SQLMODEL:
        with _session() as session:
            stmt = select(Product).where(Product.company_id == company_id, Product.is_active.is_(True))
            return [prod.dict(exclude={"id"}) for prod in session.exec(stmt).all()]
    with _sqlite_conn() as conn:
        rows = conn.execute(
            """SELECT company_id, sku, name, description, 
                      price_eur, unit, volume_l,
                      category, material_type, unit_package, tags,
                      is_active, updated_at 
               FROM products 
               WHERE company_id=? AND is_active=1""",
            (company_id,),
        ).fetchall()
        return [_normalize_product_row(dict(r)) for r in rows]


def delete_product(company_id: str, sku: str) -> bool:
    timestamp = datetime.utcnow()
    if _HAS_SQLMODEL:
        with _session() as session:
            stmt = select(Product).where(Product.company_id == company_id, Product.sku == sku)
            product = session.exec(stmt).one_or_none()
            if product is None:
                return False
            product.is_active = False
            product.updated_at = timestamp
            session.add(product)
            session.commit()
            return True
    with _sqlite_conn() as conn:
        cur = conn.execute(
            "UPDATE products SET is_active=0, updated_at=? WHERE company_id=? AND sku=?",
            (timestamp.isoformat(), company_id, sku),
        )
        conn.commit()
        return cur.rowcount > 0


def list_synonyms(company_id: str) -> Dict[str, List[str]]:
    if _HAS_SQLMODEL:
        with _session() as session:
            stmt = select(Synonym).where(Synonym.company_id == company_id)
            mapping: Dict[str, List[str]] = {}
            for syn in session.exec(stmt).all():
                mapping.setdefault(syn.canon, []).append(syn.variant)
            return mapping
    with _sqlite_conn() as conn:
        rows = conn.execute(
            "SELECT canon, variant FROM synonyms WHERE company_id=? ORDER BY canon",
            (company_id,),
        ).fetchall()
        mapping: Dict[str, List[str]] = {}
        for row in rows:
            mapping.setdefault(row["canon"], []).append(row["variant"])
        return mapping


def add_synonym(company_id: str, canon: str, variant: str, confidence: float = 0.9) -> Dict[str, object]:
    canon_norm = canon.strip()
    variant_norm = variant.strip()
    if not canon_norm or not variant_norm:
        raise ValueError("Canon and variant must be non-empty.")

    timestamp = datetime.utcnow()
    if _HAS_SQLMODEL:
        with _session() as session:
            stmt = select(Synonym).where(
                Synonym.company_id == company_id,
                Synonym.canon == canon_norm,
                Synonym.variant == variant_norm,
            )
            synonym = session.exec(stmt).one_or_none()
            if synonym is None:
                synonym = Synonym(
                    company_id=company_id,
                    canon=canon_norm,
                    variant=variant_norm,
                    confidence=confidence,
                )
                session.add(synonym)
            else:
                synonym.confidence = confidence
                synonym.updated_at = timestamp
                session.add(synonym)
            session.commit()
            session.refresh(synonym)
            data = synonym.dict()
            data.pop("id", None)
            return data

    with _sqlite_conn() as conn:
        conn.execute(
            """
            INSERT INTO synonyms(company_id, canon, variant, confidence, updated_at)
            VALUES (:cid, :canon, :variant, :conf, :updated)
            ON CONFLICT(company_id, canon, variant) DO UPDATE SET
                confidence = excluded.confidence,
                updated_at = excluded.updated_at
            """,
            {
                "cid": company_id,
                "canon": canon_norm,
                "variant": variant_norm,
                "conf": confidence,
                "updated": timestamp.isoformat(),
            },
        )
        conn.commit()
        row = conn.execute(
            "SELECT company_id, canon, variant, confidence, updated_at FROM synonyms WHERE company_id=? AND canon=? AND variant=?",
            (company_id, canon_norm, variant_norm),
        ).fetchone()
        return dict(row)


def clear_synonyms(company_id: str) -> int:
    if _HAS_SQLMODEL:
        with _session() as session:
            stmt = select(Synonym).where(Synonym.company_id == company_id)
            synonyms = session.exec(stmt).all()
            count = len(synonyms)
            for synonym in synonyms:
                session.delete(synonym)
            session.commit()
            return count
    with _sqlite_conn() as conn:
        cur = conn.execute("DELETE FROM synonyms WHERE company_id=?", (company_id,))
        conn.commit()
        return cur.rowcount or 0


def insert_synonym(company_id: str, canon: str, variant: str, confidence: float = 0.9) -> Dict[str, object]:
    """Compatibility alias for add_synonym."""

    return add_synonym(company_id, canon, variant, confidence)


def _normalize_product_row(data: Dict[str, object]) -> Dict[str, object]:
    if "is_active" in data:
        data["is_active"] = bool(data["is_active"])
    return data
