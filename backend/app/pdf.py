from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape

# Optional import for weasyprint (requires system dependencies)
try:
    from weasyprint import HTML
    WEASYPRINT_AVAILABLE = True
except ImportError:
    WEASYPRINT_AVAILABLE = False
    HTML = None  # type: ignore


OFFER_TEMPLATE_DEFINITIONS: List[Dict[str, Any]] = [
    {
        "id": "classic",
        "file": "offer.html",
        "label": "Klassik",
        "tagline": "Zeitlos & seriös",
        "description": "Klares Tabellenlayout mit dezenter Typografie – ideal für konservative Kunden.",
        "accent": "#111827",
        "background": "#f5f5f4",
        "is_default": True,
    },
    {
        "id": "modern",
        "file": "offer_modern.html",
        "label": "Modern",
        "tagline": "Frisch & reduziert",
        "description": "Große Headline, viel Weißraum und zarte Karten – perfekt für digitale Präsentationen.",
        "accent": "#0ea5e9",
        "background": "#ecfeff",
    },
    {
        "id": "premium",
        "file": "offer_premium.html",
        "label": "Premium",
        "tagline": "Fein & elegant",
        "description": "Dunkler Seitenrand, Serifentypografie und goldene Akzente für hochwertige Projekte.",
        "accent": "#b45309",
        "background": "#fffbeb",
    },
    {
        "id": "custom",
        "file": "offer_custom.html",
        "label": "Eigenes Layout",
        "tagline": "Individuell & markenscharf",
        "description": "Nutze deinen eigenen Aufbau, Farben und Textbausteine für maximale Wiedererkennbarkeit.",
        "accent": "#4f46e5",
        "background": "#eef2ff",
    },
]

OFFER_TEMPLATE_INDEX: Dict[str, Dict[str, Any]] = {tpl["id"]: tpl for tpl in OFFER_TEMPLATE_DEFINITIONS}
DEFAULT_OFFER_TEMPLATE_ID = next((tpl["id"] for tpl in OFFER_TEMPLATE_DEFINITIONS if tpl.get("is_default")), "classic")


def setup_jinja_env(templates_dir: Path):
    env = Environment(
        loader=FileSystemLoader(str(templates_dir)),
        autoescape=select_autoescape(["html"]),
    )
    env.filters["currency"] = (
        lambda v: f"{float(v):.2f}" if isinstance(v, (int, float)) or str(v).replace(".", "", 1).isdigit() else "0.00"
    )

    # optional: date_format-Filter, falls du dieses Modul solo benutzen möchtest
    from datetime import datetime

    def _date_format(value: str, fmt: str = "%d.%m.%Y") -> str:
        for f in ("%Y-%m-%d", "%d.%m.%Y", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(value, f).strftime(fmt)
            except ValueError:
                continue
        return value

    env.filters["date_format"] = _date_format

    return env


def list_offer_templates() -> List[Dict[str, Any]]:
    """Return lightweight metadata for all offer templates."""
    return [
        {
            "id": tpl["id"],
            "label": tpl["label"],
            "tagline": tpl["tagline"],
            "description": tpl["description"],
            "accent": tpl["accent"],
            "background": tpl.get("background", "#ffffff"),
            "is_default": bool(tpl.get("is_default", False)),
        }
        for tpl in OFFER_TEMPLATE_DEFINITIONS
    ]


def resolve_offer_template(template_id: str | None) -> Dict[str, Any]:
    """Return template definition, falling back to the default template."""
    if not template_id:
        return OFFER_TEMPLATE_INDEX[DEFAULT_OFFER_TEMPLATE_ID]
    template = OFFER_TEMPLATE_INDEX.get(str(template_id).strip().lower())
    if template:
        return template
    return OFFER_TEMPLATE_INDEX[DEFAULT_OFFER_TEMPLATE_ID]


def render_pdf_from_template(env: Environment, template_file: str, context: Dict[str, Any], output_dir: Path) -> Path:
    """
    Rendert eine HTML-Vorlage mit Jinja und erzeugt ein PDF im output_dir.
    base_url sollte auf das Projekt zeigen (nicht output_dir),
    damit CSS/Assets aus templates/static aufgelöst werden können.
    """
    if not WEASYPRINT_AVAILABLE or HTML is None:
        raise RuntimeError(
            "weasyprint is not available. Install it with: pip install weasyprint\n"
            "Note: weasyprint requires system dependencies (cairo, pango, etc.)"
        )
    
    output_dir.mkdir(parents=True, exist_ok=True)
    html_str = env.get_template(template_file).render(**context)

    pdf_path = output_dir / f"angebot_{int(datetime.now().timestamp())}.pdf"
    # base_url: Ordner mit Templates (oder Projekt-Root), nicht der Output-Ordner
    base_url = str(output_dir.parent)  # z.B. /app
    HTML(string=html_str, base_url=base_url).write_pdf(str(pdf_path))
    return pdf_path
