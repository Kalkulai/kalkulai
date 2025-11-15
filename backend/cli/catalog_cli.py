from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from backend.shared.normalize.text import normalize_query
from backend.store import catalog_store
from backend.retriever import index_manager

try:  # pragma: no cover - optional dependency
    import yaml  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    yaml = None

PRODUCT_HEADERS = ["sku", "name", "description", "unit", "volume_l", "price_eur", "active"]
TRUTHY = {"1", "true", "yes", "y", "on"}
FALSY = {"0", "false", "no", "n", "off"}


class CLIError(Exception):
    """Raised when user input is invalid."""


def _resolve_format(path: Path, explicit: Optional[str], allowed: Iterable[str]) -> str:
    if explicit:
        fmt = explicit.lower()
        if fmt not in allowed:
            raise CLIError(f"Unsupported format '{explicit}'. Allowed: {', '.join(sorted(allowed))}")
        return fmt
    suffix = path.suffix.lower()
    if suffix in (".csv", ".tsv") and "csv" in allowed:
        return "csv"
    if suffix == ".json" and "json" in allowed:
        return "json"
    if suffix in (".yaml", ".yml") and "yaml" in allowed:
        return "yaml"
    raise CLIError("Unable to infer format from file extension. Please pass --format.")


def _parse_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return True
    text = str(value).strip().lower()
    if not text:
        return True
    if text in TRUTHY:
        return True
    if text in FALSY:
        return False
    raise CLIError(f"Could not parse boolean value '{value}' for 'active'.")


def _normalize_description(value) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _read_products_from_csv(path: Path) -> List[Dict[str, object]]:
    if not path.exists():
        raise CLIError(f"File not found: {path}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            return []
        missing = [column for column in PRODUCT_HEADERS if column not in reader.fieldnames]
        if missing:
            raise CLIError(f"CSV missing required headers: {', '.join(missing)}")
        products: List[Dict[str, object]] = []
        for line_no, row in enumerate(reader, start=2):
            sku = (row.get("sku") or "").strip()
            name = (row.get("name") or "").strip()
            if not sku or not name:
                raise CLIError(f"Row {line_no}: 'sku' and 'name' are required.")
            product = {
                "sku": sku,
                "name": name,
                "description": _normalize_description(row.get("description")),
                "is_active": _parse_bool(row.get("active")),
            }
            products.append(product)
    return products


def _read_products_from_json(path: Path) -> List[Dict[str, object]]:
    if not path.exists():
        raise CLIError(f"File not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8") or "[]")
    if not isinstance(data, list):
        raise CLIError("JSON payload must be a list of product objects.")
    products: List[Dict[str, object]] = []
    for idx, entry in enumerate(data, start=1):
        if not isinstance(entry, dict):
            raise CLIError(f"Entry {idx} is not a JSON object.")
        sku = (str(entry.get("sku") or "")).strip()
        name = (str(entry.get("name") or "")).strip()
        if not sku or not name:
            raise CLIError(f"Entry {idx}: 'sku' and 'name' are required.")
        product = {
            "sku": sku,
            "name": name,
            "description": _normalize_description(entry.get("description")),
            "is_active": _parse_bool(entry.get("active", entry.get("is_active"))),
        }
        products.append(product)
    return products


def _product_to_row(product: Dict[str, object]) -> Dict[str, object]:
    base = {
        "sku": str(product.get("sku", "")),
        "name": str(product.get("name", "")),
        "description": product.get("description") or "",
        "unit": product.get("unit") or "",
        "volume_l": product.get("volume_l") or "",
        "price_eur": product.get("price_eur") or "",
        "active": bool(product.get("is_active", product.get("active", True))),
    }
    return base


def _write_products_csv(path: Path, products: List[Dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=PRODUCT_HEADERS)
        writer.writeheader()
        for product in products:
            row = _product_to_row(product)
            row["active"] = "true" if row["active"] else "false"
            writer.writerow(row)


def _write_products_json(path: Path, products: List[Dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = []
    for product in products:
        row = _product_to_row(product)
        payload.append(
            {
                "sku": row["sku"],
                "name": row["name"],
                "description": row["description"],
                "unit": row["unit"],
                "volume_l": row["volume_l"],
                "price_eur": row["price_eur"],
                "active": row["active"],
            }
        )
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _read_yaml_mapping(path: Path) -> Dict[str, List[str]]:
    if yaml is None:
        raise CLIError("PyYAML is required for YAML operations. Please install pyyaml.")
    if not path.exists():
        raise CLIError(f"File not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise CLIError("Synonym YAML must define a mapping of canon -> [variants].")
    normalized: Dict[str, List[str]] = {}
    for canon, variants in data.items():
        canon_norm = normalize_query(str(canon))
        if not canon_norm:
            continue
        entries: List[str] = []
        if isinstance(variants, list):
            raw_iter = variants
        else:
            raw_iter = [variants]
        for variant in raw_iter:
            variant_norm = normalize_query(str(variant))
            if variant_norm:
                entries.append(variant_norm)
        if entries:
            normalized[canon_norm] = sorted(set(entries))
    return normalized


def _write_yaml_mapping(path: Path, mapping: Dict[str, List[str]]) -> None:
    if yaml is None:
        raise CLIError("PyYAML is required for YAML operations. Please install pyyaml.")
    path.parent.mkdir(parents=True, exist_ok=True)
    cleaned = {canon: sorted(set(variants)) for canon, variants in mapping.items() if variants}
    path.write_text(yaml.safe_dump(cleaned, sort_keys=True), encoding="utf-8")


def _parse_skus(value: str) -> List[str]:
    if not value:
        raise CLIError("--skus requires a comma-separated list of SKU values.")
    entries = [sku.strip() for sku in value.split(",") if sku.strip()]
    if not entries:
        raise CLIError("--skus requires at least one SKU.")
    return entries


def cmd_import_products(args: argparse.Namespace) -> None:
    company_id = args.company_id
    path = Path(args.path)
    fmt = _resolve_format(path, args.format, {"csv", "json"})
    if fmt == "csv":
        products = _read_products_from_csv(path)
    else:
        products = _read_products_from_json(path)
    existing = {
        prod["sku"]
        for prod in catalog_store.list_products(company_id, include_deleted=True)
    }
    inserted = 0
    updated = 0
    for product in products:
        if product["sku"] in existing:
            updated += 1
        else:
            inserted += 1
            existing.add(product["sku"])
        catalog_store.upsert_product(
            company_id,
            {
                "sku": product["sku"],
                "name": product["name"],
                "description": product["description"],
                "is_active": product["is_active"],
            },
        )
    if args.rebuild_index:
        index_manager.rebuild_index(company_id)
        stats = index_manager.index_stats(company_id)
        print(
            f"Imported {len(products)} products (inserted={inserted} updated={updated}); "
            f"rebuild docs={stats['docs']}."
        )
    else:
        print(f"Imported {len(products)} products (inserted={inserted} updated={updated}).")


def cmd_export_products(args: argparse.Namespace) -> None:
    company_id = args.company_id
    path = Path(args.path)
    fmt = _resolve_format(path, args.format, {"csv", "json"})
    products = catalog_store.get_active_products(company_id)
    products_sorted = sorted(products, key=lambda item: item.get("sku", ""))
    if fmt == "csv":
        _write_products_csv(path, products_sorted)
    else:
        _write_products_json(path, products_sorted)
    print(f"Exported {len(products_sorted)} products to {path}.")


def cmd_import_synonyms(args: argparse.Namespace) -> None:
    company_id = args.company_id
    path = Path(args.path)
    mapping = _read_yaml_mapping(path)
    if args.clear_existing:
        catalog_store.clear_synonyms(company_id)
    inserted = 0
    for canon, variants in mapping.items():
        for variant in variants:
            catalog_store.insert_synonym(company_id, canon, variant)
            inserted += 1
    print(f"Imported {inserted} synonyms for {company_id}.")


def cmd_export_synonyms(args: argparse.Namespace) -> None:
    company_id = args.company_id
    path = Path(args.path)
    mapping = catalog_store.list_synonyms(company_id)
    normalized: Dict[str, List[str]] = {}
    for canon, variants in mapping.items():
        canon_norm = normalize_query(canon)
        if not canon_norm:
            continue
        entries: List[str] = []
        for variant in variants:
            variant_norm = normalize_query(variant)
            if variant_norm:
                entries.append(variant_norm)
        unique = sorted(set(entries))
        if unique:
            normalized[canon_norm] = unique
    _write_yaml_mapping(path, normalized)
    print(f"Exported {len(normalized)} synonym groups to {path}.")


def cmd_rebuild_index(args: argparse.Namespace) -> None:
    company_id = args.company_id
    index_manager.rebuild_index(company_id)
    stats = index_manager.index_stats(company_id)
    print(f"Rebuilt index for {company_id}: docs={stats['docs']} backend={stats['backend']}.")


def cmd_update_index(args: argparse.Namespace) -> None:
    company_id = args.company_id
    skus = _parse_skus(args.skus)
    stats = index_manager.update_index(company_id, skus)
    print(
        f"Updated index for {company_id}: skus={len(skus)} docs={stats['docs']} backend={stats['backend']}."
    )


def cmd_stats(args: argparse.Namespace) -> None:
    company_id = args.company_id
    active = len(catalog_store.get_active_products(company_id))
    total = len(catalog_store.list_products(company_id, include_deleted=True))
    synonyms = sum(len(values) for values in catalog_store.list_synonyms(company_id).values())
    stats = index_manager.index_stats(company_id)
    print(
        f"Company {company_id} stats:\n"
        f"- products: active={active} total={total}\n"
        f"- synonyms: {synonyms}\n"
        f"- index: docs={stats['docs']} backend={stats['backend']} built_at={stats['built_at']}"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage catalog data via the local store/index.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    import_products = subparsers.add_parser("import-products", help="Import products from CSV/JSON.")
    import_products.add_argument("--company-id", required=True)
    import_products.add_argument("--path", required=True)
    import_products.add_argument("--format", choices=("csv", "json"), default=None)
    import_products.add_argument(
        "--rebuild-index",
        dest="rebuild_index",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    import_products.set_defaults(func=cmd_import_products)

    export_products = subparsers.add_parser("export-products", help="Export active products.")
    export_products.add_argument("--company-id", required=True)
    export_products.add_argument("--path", required=True)
    export_products.add_argument("--format", choices=("csv", "json"), default=None)
    export_products.set_defaults(func=cmd_export_products)

    import_synonyms = subparsers.add_parser("import-synonyms", help="Import synonyms from YAML.")
    import_synonyms.add_argument("--company-id", required=True)
    import_synonyms.add_argument("--path", required=True)
    import_synonyms.add_argument(
        "--clear-existing",
        dest="clear_existing",
        action=argparse.BooleanOptionalAction,
        default=False,
    )
    import_synonyms.set_defaults(func=cmd_import_synonyms)

    export_synonyms = subparsers.add_parser("export-synonyms", help="Export synonyms to YAML.")
    export_synonyms.add_argument("--company-id", required=True)
    export_synonyms.add_argument("--path", required=True)
    export_synonyms.set_defaults(func=cmd_export_synonyms)

    rebuild = subparsers.add_parser("rebuild-index", help="Rebuild the retriever index.")
    rebuild.add_argument("--company-id", required=True)
    rebuild.set_defaults(func=cmd_rebuild_index)

    update = subparsers.add_parser("update-index", help="Update specific SKUs in the index.")
    update.add_argument("--company-id", required=True)
    update.add_argument("--skus", required=True, help="Comma-separated list of SKUs.")
    update.set_defaults(func=cmd_update_index)

    stats = subparsers.add_parser("stats", help="Show store and index stats.")
    stats.add_argument("--company-id", required=True)
    stats.set_defaults(func=cmd_stats)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    catalog_store.init_db()
    try:
        args.func(args)
    except CLIError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except FileNotFoundError as exc:  # pragma: no cover - defensive
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
