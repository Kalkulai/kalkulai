# Admin API

Die Admin-API (unter `/api/admin`) ermöglicht es, Produkte und Synonyme mandantenspezifisch zu pflegen und den Retriever-Index live zu aktualisieren. Authentifizierung erfolgt optional über `ADMIN_API_KEY`: Wenn gesetzt, muss jeder Request den Header `X-Admin-Key` mit diesem Wert senden.

## Beispiele

```bash
export ADMIN_API_KEY=secret
curl -H "X-Admin-Key: secret" -X POST \
  -H "Content-Type: application/json" \
  -d '{"company_id":"demo","sku":"SKU-1","name":"Innenfarbe Weiß"}' \
  http://localhost:8000/api/admin/products
```

Synonyme einpflegen:

```bash
curl -H "X-Admin-Key: secret" -X POST \
  -H "Content-Type: application/json" \
  -d '{"company_id":"demo","canon":"tiefgrund","synonyms":["tief grund","tief-grund"]}' \
  http://localhost:8000/api/admin/synonyms
```

Indexer neu bauen oder inkrementell aktualisieren:

```bash
curl -H "X-Admin-Key: secret" -X POST \
  -H "Content-Type: application/json" \
  -d '{"company_id":"demo"}' \
  http://localhost:8000/api/admin/index/rebuild

curl -H "X-Admin-Key: secret" -X POST \
  -H "Content-Type: application/json" \
  -d '{"company_id":"demo","changed_skus":["SKU-1","SKU-2"]}' \
  http://localhost:8000/api/admin/index/update
```

Stats abrufen:

```bash
curl -H "X-Admin-Key: secret" \
  "http://localhost:8000/api/admin/index/stats?company_id=demo"
```
