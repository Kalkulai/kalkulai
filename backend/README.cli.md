# Catalog CLI

This lightweight CLI lets you manage company catalogs directly against the
local store and retriever index without hitting the REST API.

## Setup

```
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Set `KALKULAI_DB_URL` to choose the database (defaults to the on-disk SQLite
file shipped with the repo):

```
export KALKULAI_DB_URL=sqlite:///backend/var/kalkulai.db
```

## Usage

```
# Import CSV and rebuild index
python -m backend.cli.catalog_cli import-products --company-id acme --path ./acme_catalog.csv

# Export JSON
python -m backend.cli.catalog_cli export-products --company-id acme --path ./out.json --format json

# Synonyms
python -m backend.cli.catalog_cli import-synonyms --company-id acme --path ./syn.yaml --clear-existing
python -m backend.cli.catalog_cli export-synonyms --company-id acme --path ./syn.out.yaml

# Index ops
python -m backend.cli.catalog_cli rebuild-index --company-id acme
python -m backend.cli.catalog_cli update-index --company-id acme --skus sku123,sku456
python -m backend.cli.catalog_cli stats --company-id acme
```
