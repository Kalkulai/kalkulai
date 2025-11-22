"""Unified, friendly error messages for catalog validation.

Each helper returns plain-text German output following the
freundlich & hilfsbereit tone (Variante B) so chat and offer flows
share the same wording.
"""

from __future__ import annotations

from typing import Iterable


def _bullet_list(items: Iterable[str]) -> str:
    return "\n".join(f"- {item}" for item in items)


def chat_unknown_products_message(unknown_products: list[str]) -> str:
    """Friendly chat reply when products are missing in the catalog."""
    cleaned = [p.strip() for p in unknown_products if p.strip()]
    if not cleaned:
        return (
            "Hinweis zur Produktprüfung\n\n"
            "- Einige angegebene Produkte fehlen aktuell im Katalog.\n"
            "Bitte nenne Produkte aus der vorhandenen Liste oder melde dich kurz beim Büro, damit die Daten ergänzt werden."
        )
    bullets = _bullet_list(cleaned)
    return (
        "Hinweis zur Produktprüfung\n\n"
        "Diese Produkte konnten wir nicht im Katalog finden:\n"
        f"{bullets}\n\n"
        "Bitte wähle passende Alternativen aus unserem Bestand oder gib dem Büro Bescheid, damit die Datenbank kurzfristig erweitert wird."
    )


def offer_unknown_products_message(unknown_products: list[str]) -> str:
    """Text for offer-generation errors when products are missing."""
    cleaned = [p.strip() for p in unknown_products if p.strip()]
    if not cleaned:
        return (
            "Angebot kann noch nicht erstellt werden\n\n"
            "- Es fehlen noch Produkte im Katalog.\n"
            "Sobald alle Materialien vorhanden sind, geht es direkt weiter."
        )
    bullets = _bullet_list(cleaned)
    return (
        "Angebot kann noch nicht erstellt werden\n\n"
        "Diese Produkte sind aktuell nicht im Katalog hinterlegt:\n"
        f"{bullets}\n\n"
        "Bitte passe die Materialliste an oder lass sie vom Innendienst ergänzen. Anschließend erstellen wir das Angebot sofort."
    )
