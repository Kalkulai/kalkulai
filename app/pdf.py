from pathlib import Path
from datetime import datetime
from typing import Dict, Any
from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import HTML

def setup_jinja_env(templates_dir: Path):
    env = Environment(loader=FileSystemLoader(str(templates_dir)), autoescape=select_autoescape(["html"]))
    env.filters['currency'] = lambda v: f"{float(v):.2f}" if isinstance(v,(int,float)) else "0.00"
    return env

def render_pdf_from_template(env, context: Dict[str,Any], output_dir: Path) -> Path:
    html = env.get_template("offer.html").render(**context)
    pdf_path = output_dir / f"angebot_{int(datetime.now().timestamp())}.pdf"
    HTML(string=html, base_url=str(output_dir)).write_pdf(str(pdf_path))
    return pdf_path
