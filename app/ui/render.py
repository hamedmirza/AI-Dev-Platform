from html import escape


def page(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{escape(title)}</title>
    <style>
      :root {{
        --bg: #f3ede3;
        --panel: rgba(255, 251, 244, 0.92);
        --panel-strong: #fffdf8;
        --ink: #1d1913;
        --muted: #665d4f;
        --line: #d8ccb6;
        --accent: #0f766e;
        --accent-strong: #115e59;
        --accent-soft: rgba(15, 118, 110, 0.10);
        --warn: #92400e;
        --danger: #991b1b;
        --shadow: 0 16px 42px rgba(65, 42, 16, 0.09);
      }}
      * {{ box-sizing: border-box; }}
      body {{
        margin: 0;
        font-family: "Iowan Old Style", Georgia, "Times New Roman", serif;
        background:
          radial-gradient(circle at top right, rgba(15,118,110,0.14), transparent 24%),
          radial-gradient(circle at top left, rgba(146,64,14,0.07), transparent 20%),
          linear-gradient(180deg, #fbf7f0 0%, var(--bg) 100%);
        color: var(--ink);
      }}
      a {{ color: var(--accent-strong); text-decoration: none; }}
      a:hover {{ text-decoration: underline; }}
      .shell {{
        max-width: 1280px;
        margin: 0 auto;
        padding: 24px 20px 54px;
      }}
      .masthead {{
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        gap: 16px;
        margin-bottom: 24px;
      }}
      .title {{
        font-size: 2.1rem;
        line-height: 1;
        margin: 0 0 6px;
      }}
      .subtitle {{
        margin: 0;
        color: var(--muted);
        font-size: 0.98rem;
      }}
      .layout {{
        display: grid;
        grid-template-columns: 240px 1fr;
        gap: 20px;
      }}
      .sidebar {{
        display: grid;
        gap: 18px;
        align-self: start;
        position: sticky;
        top: 20px;
      }}
      .sidebar .panel {{
        padding: 16px;
      }}
      .nav-list {{
        display: grid;
        gap: 8px;
      }}
      .nav-link {{
        display: block;
        padding: 11px 13px;
        border-radius: 14px;
        border: 1px solid var(--line);
        background: rgba(255,255,255,0.62);
        color: var(--ink);
      }}
      .nav-link.active {{
        border-color: rgba(15,118,110,0.26);
        background: var(--accent-soft);
        color: var(--accent-strong);
        font-weight: 700;
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
        border: 1px solid var(--line);
        border-radius: 18px;
        padding: 18px;
        box-shadow: var(--shadow);
      }}
      .panel h2, .panel h3 {{
        margin: 0 0 12px;
        font-size: 1.08rem;
      }}
      .panel h3 {{
        font-size: 0.95rem;
        color: var(--muted);
        text-transform: uppercase;
        letter-spacing: 0.04em;
      }}
      .metrics {{
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
        gap: 12px;
      }}
      .metric {{
        border: 1px solid var(--line);
        border-radius: 14px;
        padding: 14px;
        background: rgba(255,255,255,0.65);
      }}
      .metric strong {{
        display: block;
        font-size: 1.45rem;
        margin-top: 4px;
      }}
      .status {{
        display: inline-block;
        padding: 4px 10px;
        border-radius: 999px;
        font-size: 0.82rem;
        border: 1px solid var(--line);
        background: #fff;
      }}
      .status.ok {{ color: var(--accent-strong); border-color: rgba(15,118,110,0.3); }}
      .status.warn {{ color: var(--warn); border-color: rgba(146,64,14,0.25); }}
      .status.bad {{ color: var(--danger); border-color: rgba(153,27,27,0.25); }}
      form {{ display: grid; gap: 10px; }}
      input, textarea, button {{
        font: inherit;
      }}
      input, textarea {{
        width: 100%;
        border: 1px solid var(--line);
        border-radius: 12px;
        padding: 10px 12px;
        background: var(--panel-strong);
      }}
      textarea {{ min-height: 140px; resize: vertical; }}
      button {{
        border: 0;
        border-radius: 999px;
        padding: 10px 16px;
        background: var(--accent);
        color: white;
        cursor: pointer;
      }}
      button.secondary {{
        background: #8a7862;
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
        border: 1px solid var(--line);
        border-radius: 14px;
        padding: 14px;
        background: rgba(255,255,255,0.6);
      }}
      .item h4 {{
        margin: 0 0 6px;
        font-size: 1rem;
      }}
      .hero {{
        display: grid;
        gap: 12px;
      }}
      .hero .eyebrow {{
        color: var(--muted);
        text-transform: uppercase;
        letter-spacing: 0.08em;
        font-size: 0.78rem;
      }}
      .hero h2 {{
        margin: 0;
        font-size: 2rem;
        line-height: 1.02;
      }}
      .hero p {{
        margin: 0;
        color: var(--muted);
        max-width: 64ch;
      }}
      .meta {{
        color: var(--muted);
        font-size: 0.9rem;
      }}
      .pill-row {{
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
      }}
      .pill {{
        padding: 7px 10px;
        border-radius: 999px;
        border: 1px solid var(--line);
        background: rgba(255,255,255,0.62);
        color: var(--muted);
        font-size: 0.84rem;
      }}
      pre {{
        margin: 0;
        white-space: pre-wrap;
        word-break: break-word;
        font-family: "SFMono-Regular", Menlo, monospace;
        font-size: 0.86rem;
        line-height: 1.45;
      }}
      .nav {{
        display: flex;
        gap: 12px;
        align-items: center;
      }}
      .nav a {{
        padding: 8px 12px;
        border-radius: 999px;
        border: 1px solid var(--line);
        background: rgba(255,255,255,0.62);
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
      @media (max-width: 920px) {{
        .layout, .grid, .wide-grid {{ grid-template-columns: 1fr; }}
        .sidebar {{
          position: static;
        }}
      }}
    </style>
  </head>
  <body>
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
      </div>
      <div class="nav">{nav_html}</div>
    </header>
    <div class="layout">
      <aside class="sidebar">{side_html}</aside>
      <section class="stack">{body_html}</section>
    </div>
    """
