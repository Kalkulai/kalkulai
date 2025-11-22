from backend.app.error_messages import (
    chat_unknown_products_message,
    offer_unknown_products_message,
)


def test_chat_unknown_products_single():
    msg = chat_unknown_products_message(["Premiumfarbe weiß 10L"])
    assert "Hinweis zur Produktprüfung" in msg
    assert "- Premiumfarbe weiß 10L" in msg
    assert "Bitte wähle passende Alternativen" in msg


def test_chat_unknown_products_multiple():
    msg = chat_unknown_products_message(["Produkt A", "Produkt B"])
    assert msg.count("- ") == 2
    assert "Produkt A" in msg and "Produkt B" in msg


def test_offer_unknown_products_single():
    msg = offer_unknown_products_message(["Tiefgrund 10 L"])
    assert "Angebot kann noch nicht erstellt werden" in msg
    assert "- Tiefgrund 10 L" in msg
    assert "Sobald alle Materialien vorhanden sind" in msg or "Bitte passe die Materialliste an" in msg


def test_offer_unknown_products_multiple():
    msg = offer_unknown_products_message(["Produkt X", "Produkt Y", "Produkt Z"])
    assert msg.count("- ") == 3
    assert "Produkt X" in msg and "Produkt Y" in msg and "Produkt Z" in msg
