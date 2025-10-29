from pathlib import Path
from datetime import datetime
from typing import Dict, Any

from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import HTML


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


def render_pdf_from_template(env: Environment, context: Dict[str, Any], output_dir: Path) -> Path:
    """
    Rendert offer.html mit Jinja und erzeugt PDF in output_dir.
    base_url sollte auf das Projekt zeigen (nicht output_dir),
    damit CSS/Assets aus templates/static aufgelöst werden können.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    html_str = env.get_template("offer.html").render(**context)

    pdf_path = output_dir / f"angebot_{int(datetime.now().timestamp())}.pdf"
    # base_url: Ordner mit Templates (oder Projekt-Root), nicht der Output-Ordner
    base_url = str(output_dir.parent)  # z.B. /app
    HTML(string=html_str, base_url=base_url).write_pdf(str(pdf_path))
    return pdf_path
