import json
from html import escape
from pathlib import Path


def page(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{escape(title)}</title>
    <style>
      @import url("https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=Inter:wght@400;500;600;700&display=swap");
      :root {{
        --bg-base: #f5f7ff;
        --bg-alt: #eaf2ff;
        --ink: #142037;
        --ink-soft: #243451;
        --muted: #617089;
        --line: #d7deef;
        --line-strong: #c2cbe1;
        --panel: rgba(255, 255, 255, 0.87);
        --panel-strong: rgba(255, 255, 255, 0.98);
        --radius: 14px;
        --accent: #0358d8;
        --accent-strong: #003ea6;
        --accent-soft: rgba(3, 88, 216, 0.14);
        --accent-glow: rgba(3, 88, 216, 0.3);
        --ok: #0d855f;
        --warn: #a86d00;
        --danger: #c1323f;
        --shadow: 0 20px 46px rgba(17, 34, 68, 0.12);
        --shadow-soft: 0 8px 18px rgba(17, 34, 68, 0.09);
      }}
      * {{ box-sizing: border-box; }}
      body {{
        margin: 0;
        font-family: "Inter", "Segoe UI", sans-serif;
        background:
          radial-gradient(85rem 42rem at -10% -20%, rgba(3, 88, 216, 0.2), transparent 48%),
          radial-gradient(70rem 40rem at 108% -5%, rgba(15, 133, 95, 0.2), transparent 46%),
          linear-gradient(180deg, #f8faff 0%, var(--bg-base) 52%, var(--bg-alt) 100%);
        color: var(--ink);
        min-height: 100vh;
      }}
      body::before {{
        content: "";
        position: fixed;
        inset: 0;
        pointer-events: none;
        background-image: repeating-linear-gradient(
          135deg,
          rgba(20, 32, 55, 0.03) 0,
          rgba(20, 32, 55, 0.03) 1px,
          transparent 1px,
          transparent 12px
        );
        opacity: 0.52;
        z-index: 0;
      }}
      .global-ribbon {{
        position: fixed;
        top: 12px;
        right: 12px;
        z-index: 20;
        padding: 8px 12px;
        border-radius: 999px;
        border: 1px solid var(--accent-glow);
        background: rgba(255, 255, 255, 0.95);
        color: var(--accent-strong);
        font-size: 0.76rem;
        font-weight: 800;
        letter-spacing: 0.04em;
        text-transform: uppercase;
        box-shadow: 0 8px 22px rgba(3, 62, 166, 0.2);
      }}
      a {{
        color: var(--accent-strong);
        text-decoration: none;
        font-weight: 600;
      }}
      a:hover {{ text-decoration: underline; }}
      .shell {{
        max-width: 1320px;
        margin: 0 auto;
        padding: 30px 24px 56px;
        position: relative;
        z-index: 1;
      }}
      .masthead {{
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 22px;
        margin-bottom: 26px;
        padding: 18px 22px 19px;
        border: 1px solid rgba(3, 88, 216, 0.16);
        border-radius: calc(var(--radius) + 6px);
        background:
          linear-gradient(120deg, rgba(255, 255, 255, 0.95), rgba(237, 246, 255, 0.85));
        box-shadow: var(--shadow-soft);
        backdrop-filter: blur(10px);
        animation: rise-in 360ms ease both, glow-in 480ms ease both;
      }}
      .title {{
        font-family: "Space Grotesk", "Inter", sans-serif;
        font-size: 2.05rem;
        line-height: 1.05;
        margin: 0 0 4px;
        letter-spacing: -0.02em;
      }}
      .subtitle {{
        margin: 0;
        color: var(--muted);
        font-size: 0.93rem;
      }}
      .build-tag {{
        display: inline-flex;
        align-items: center;
        gap: 8px;
        margin-top: 10px;
        padding: 6px 10px;
        border-radius: 999px;
        border: 1px solid rgba(3, 88, 216, 0.24);
        background: var(--accent-soft);
        color: var(--accent-strong);
        font-size: 0.74rem;
        font-weight: 700;
        letter-spacing: 0.04em;
        text-transform: uppercase;
      }}
      .layout {{
        display: grid;
        grid-template-columns: 268px 1fr;
        gap: 22px;
      }}
      .sidebar {{
        display: grid;
        gap: 16px;
        align-self: start;
        position: sticky;
        top: 16px;
      }}
      .sidebar .panel {{
        padding: 16px 15px;
      }}
      .nav-list {{
        display: grid;
        gap: 8px;
      }}
      .nav-link {{
        display: block;
        padding: 10px 12px 11px;
        border-radius: 12px;
        border: 1px solid var(--line);
        background: rgba(255, 255, 255, 0.73);
        color: var(--ink-soft);
        transition: all 140ms ease;
      }}
      .nav-link:hover {{
        transform: translateY(-1px);
        border-color: var(--line-strong);
        text-decoration: none;
      }}
      .nav-link.active {{
        border-color: var(--accent-glow);
        background: var(--accent-soft);
        color: var(--accent-strong);
        font-weight: 700;
        box-shadow: inset 0 0 0 1px rgba(3, 88, 216, 0.18);
      }}
      .grid {{
        display: grid;
        grid-template-columns: 320px 1fr;
        gap: 18px;
      }}
      .wide-grid {{
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 18px;
      }}
      .stack {{
        display: grid;
        gap: 18px;
      }}
      .panel {{
        background: var(--panel);
        border: 1px solid rgba(3, 88, 216, 0.12);
        border-radius: var(--radius);
        padding: 18px 18px 16px;
        box-shadow: var(--shadow);
        backdrop-filter: blur(8px);
        animation: rise-in 440ms ease both;
      }}
      .panel h2, .panel h3 {{
        margin: 0 0 11px;
        font-size: 1.08rem;
      }}
      .panel h3 {{
        font-size: 0.82rem;
        color: var(--muted);
        text-transform: uppercase;
        letter-spacing: 0.08em;
      }}
      .metrics {{
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
        gap: 11px;
      }}
      .metric {{
        border: 1px solid rgba(3, 88, 216, 0.14);
        border-radius: 12px;
        padding: 12px;
        background: rgba(255, 255, 255, 0.86);
        color: var(--muted);
        font-size: 0.84rem;
      }}
      .metric strong {{
        display: block;
        font-size: 1.38rem;
        margin-top: 6px;
        color: var(--ink-soft);
      }}
      .status {{
        display: inline-block;
        padding: 4px 10px 6px;
        border-radius: 999px;
        font-size: 0.77rem;
        font-weight: 700;
        letter-spacing: 0.01em;
        border: 1px solid var(--line-strong);
        background: #fff;
      }}
      .status.ok {{
        color: var(--ok);
        border-color: rgba(13, 133, 95, 0.33);
        background: rgba(13, 133, 95, 0.08);
      }}
      .status.warn {{
        color: var(--warn);
        border-color: rgba(168, 109, 0, 0.3);
        background: rgba(168, 109, 0, 0.08);
      }}
      .status.bad {{
        color: var(--danger);
        border-color: rgba(193, 50, 63, 0.31);
        background: rgba(193, 50, 63, 0.08);
      }}
      form {{ display: grid; gap: 10px; }}
      input, textarea, button {{
        font: inherit;
      }}
      input, textarea {{
        width: 100%;
        border: 1px solid var(--line-strong);
        border-radius: 10px;
        padding: 10px 11px;
        background: var(--panel-strong);
        color: var(--ink-soft);
      }}
      input:focus, textarea:focus {{
        outline: none;
        border-color: var(--accent-glow);
        box-shadow: 0 0 0 3px rgba(3, 88, 216, 0.2);
      }}
      textarea {{ min-height: 140px; resize: vertical; }}
      button {{
        border: 0;
        border-radius: 999px;
        padding: 10px 16px;
        font-weight: 700;
        letter-spacing: 0.01em;
        background: var(--accent);
        color: white;
        cursor: pointer;
        transition: transform 120ms ease, box-shadow 120ms ease, background 120ms ease;
      }}
      button:hover {{
        transform: translateY(-1px);
        box-shadow: 0 8px 20px rgba(3, 88, 216, 0.3);
        background: var(--accent-strong);
      }}
      button.secondary {{
        background: #4b5563;
      }}
      button.warn {{
        background: var(--warn);
      }}
      button.danger {{
        background: var(--danger);
      }}
      .row {{
        display: flex;
        flex-wrap: wrap;
        gap: 10px;
        align-items: center;
      }}
      .list {{
        display: grid;
        gap: 12px;
      }}
      .item {{
        border: 1px solid rgba(3, 88, 216, 0.12);
        border-radius: 12px;
        padding: 13px;
        background: rgba(255, 255, 255, 0.85);
      }}
      .item h4 {{
        margin: 0 0 6px;
        font-size: 0.95rem;
        color: var(--ink-soft);
      }}
      .hero {{
        display: grid;
        gap: 12px;
      }}
      .hero .eyebrow {{
        color: var(--muted);
        text-transform: uppercase;
        letter-spacing: 0.08em;
        font-size: 0.72rem;
        font-weight: 700;
      }}
      .hero h2 {{
        margin: 0;
        font-size: 1.72rem;
        line-height: 1.08;
        letter-spacing: -0.015em;
      }}
      .hero p {{
        margin: 0;
        color: var(--muted);
        max-width: 64ch;
        line-height: 1.45;
      }}
      .meta {{
        color: var(--muted);
        font-size: 0.86rem;
        line-height: 1.38;
      }}
      .pill-row {{
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
      }}
      .pill {{
        padding: 6px 10px 7px;
        border-radius: 999px;
        border: 1px solid rgba(3, 88, 216, 0.13);
        background: rgba(255, 255, 255, 0.9);
        color: #4c5f7f;
        font-size: 0.77rem;
        font-weight: 600;
      }}
      pre {{
        margin: 0;
        white-space: pre-wrap;
        word-break: break-word;
        font-family: "SF Mono", Menlo, Consolas, monospace;
        font-size: 0.82rem;
        line-height: 1.45;
        padding: 10px;
        border-radius: 10px;
        background: rgba(245, 248, 252, 0.8);
        border: 1px solid var(--line);
      }}
      .nav {{
        display: flex;
        gap: 10px;
        flex-wrap: wrap;
        align-items: center;
      }}
      .nav a {{
        padding: 7px 11px;
        border-radius: 999px;
        border: 1px solid var(--line);
        background: rgba(255, 255, 255, 0.74);
        color: var(--ink-soft);
        font-size: 0.85rem;
        transition: all 120ms ease;
      }}
      .nav a:hover {{
        transform: translateY(-1px);
        text-decoration: none;
        border-color: var(--line-strong);
      }}
      .section-head {{
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 12px;
        margin-bottom: 12px;
      }}
      .section-head h2 {{
        margin-bottom: 0;
      }}
      .actions {{
        display: flex;
        flex-wrap: wrap;
        gap: 10px;
      }}
      @keyframes rise-in {{
        from {{
          opacity: 0;
          transform: translateY(9px);
        }}
        to {{
          opacity: 1;
          transform: translateY(0);
        }}
      }}
      @keyframes glow-in {{
        from {{
          box-shadow: 0 0 0 rgba(3, 88, 216, 0);
        }}
        to {{
          box-shadow: 0 10px 34px rgba(3, 88, 216, 0.11);
        }}
      }}
      @media (max-width: 920px) {{
        .layout, .grid, .wide-grid {{ grid-template-columns: 1fr; }}
        .masthead {{
          align-items: flex-start;
          flex-direction: column;
        }}
        .sidebar {{
          position: static;
        }}
      }}
    </style>
  </head>
  <body>
    <div class="global-ribbon">UI Redesign Active</div>
    <main class="shell">
      {body}
    </main>
  </body>
</html>"""


def page_with_auto_refresh(title: str, body: str, interval_seconds: int) -> str:
    refresh = max(interval_seconds, 2)
    return page(
        title,
        f'<script>setTimeout(function(){{window.location.reload();}}, {refresh * 1000});</script>{body}',
    )


def react_app_shell(title: str = "AI Dev Platform") -> str:
    def asset_url(path: str) -> str:
        normalized = path.removeprefix("assets/")
        return f"/ui/assets/{escape(normalized)}"

    manifest_path = Path(__file__).resolve().parent / "static" / ".vite" / "manifest.json"
    app_script = ""
    app_styles = ""
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            entry = manifest.get("index.html", {})
            script = entry.get("file")
            if script:
                app_script = f'<script type="module" src="{asset_url(script)}"></script>'
            app_styles = "".join(
                f'<link rel="stylesheet" href="{asset_url(item)}">'
                for item in entry.get("css", [])
            )
        except (OSError, json.JSONDecodeError):
            app_script = ""

    fallback = """
      <div class="shell">
        <section class="panel hero">
          <div class="eyebrow">Frontend build missing</div>
          <h2>React console assets have not been built yet.</h2>
          <p>Run <code>npm --prefix frontend run build</code> and restart the FastAPI server.</p>
        </section>
      </div>
    """

    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{escape(title)}</title>
    {app_styles}
  </head>
  <body>
    <div id="root">{fallback if not app_script else ""}</div>
    {app_script}
  </body>
</html>"""


def status_badge(value: str) -> str:
    lowered = value.lower()
    css = "ok"
    if any(token in lowered for token in ("fail", "cancel", "unavailable", "invalid")):
        css = "bad"
    elif any(
        token in lowered for token in ("warn", "degraded", "await", "review", "block", "pending")
    ):
        css = "warn"
    return f'<span class="status {css}">{escape(value)}</span>'


def layout(
    title: str,
    subtitle: str,
    nav_html: str,
    body_html: str,
    side_html: str,
) -> str:
    return f"""
    <header class="masthead">
      <div>
        <h1 class="title">{escape(title)}</h1>
        <p class="subtitle">{escape(subtitle)}</p>
        <div class="build-tag">UI Redesign Live · 2026-04-29</div>
      </div>
      <div class="nav">{nav_html}</div>
    </header>
    <div class="layout">
      <aside class="sidebar">{side_html}</aside>
      <section class="stack">{body_html}</section>
    </div>
    """
