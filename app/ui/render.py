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
        --bg: #f4f6f8;
        --bg-soft: #e8eef2;
        --panel: rgba(255, 255, 255, 0.92);
        --panel-strong: #ffffff;
        --ink: #0f172a;
        --ink-soft: #1e293b;
        --muted: #4b5563;
        --line: #d7dee8;
        --line-strong: #c5d0dc;
        --accent: #0f4c81;
        --accent-strong: #0b3c69;
        --accent-soft: rgba(15, 76, 129, 0.1);
        --accent-glow: rgba(15, 76, 129, 0.18);
        --warn: #9a5e11;
        --danger: #b42318;
        --ok: #067647;
        --radius: 16px;
        --shadow: 0 20px 46px rgba(15, 23, 42, 0.08);
        --shadow-soft: 0 10px 26px rgba(15, 23, 42, 0.05);
      }}
      * {{ box-sizing: border-box; }}
      body {{
        margin: 0;
        font-family: "Avenir Next", "Segoe UI", "Helvetica Neue", sans-serif;
        background:
          radial-gradient(circle at 0% 0%, rgba(15, 76, 129, 0.09), transparent 28%),
          radial-gradient(circle at 100% 0%, rgba(6, 118, 71, 0.08), transparent 24%),
          linear-gradient(180deg, #f9fbfc 0%, var(--bg) 42%, var(--bg-soft) 100%);
        color: var(--ink);
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
        padding: 28px 22px 56px;
      }}
      .masthead {{
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 22px;
        margin-bottom: 26px;
        padding: 18px 22px;
        border: 1px solid var(--line);
        border-radius: calc(var(--radius) + 2px);
        background: linear-gradient(
          115deg,
          rgba(255, 255, 255, 0.88),
          rgba(255, 255, 255, 0.74)
        );
        box-shadow: var(--shadow-soft);
        backdrop-filter: blur(8px);
      }}
      .title {{
        font-size: 2rem;
        line-height: 1.05;
        margin: 0 0 4px;
        letter-spacing: -0.02em;
      }}
      .subtitle {{
        margin: 0;
        color: var(--muted);
        font-size: 0.93rem;
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
        padding: 10px 12px;
        border-radius: 12px;
        border: 1px solid var(--line);
        background: rgba(255, 255, 255, 0.7);
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
        border-radius: var(--radius);
        padding: 18px 18px 16px;
        box-shadow: var(--shadow);
        backdrop-filter: blur(8px);
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
        border: 1px solid var(--line);
        border-radius: 12px;
        padding: 12px;
        background: rgba(255, 255, 255, 0.74);
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
        padding: 4px 10px 5px;
        border-radius: 999px;
        font-size: 0.77rem;
        font-weight: 700;
        letter-spacing: 0.01em;
        border: 1px solid var(--line-strong);
        background: #fff;
      }}
      .status.ok {{
        color: var(--ok);
        border-color: rgba(6, 118, 71, 0.3);
        background: rgba(6, 118, 71, 0.06);
      }}
      .status.warn {{
        color: var(--warn);
        border-color: rgba(154, 94, 17, 0.32);
        background: rgba(154, 94, 17, 0.07);
      }}
      .status.bad {{
        color: var(--danger);
        border-color: rgba(180, 35, 24, 0.3);
        background: rgba(180, 35, 24, 0.06);
      }}
      form {{ display: grid; gap: 10px; }}
      input, textarea, button {{
        font: inherit;
      }}
      input, textarea {{
        width: 100%;
        border: 1px solid var(--line);
        border-radius: 10px;
        padding: 10px 11px;
        background: var(--panel-strong);
        color: var(--ink-soft);
      }}
      input:focus, textarea:focus {{
        outline: none;
        border-color: var(--accent-glow);
        box-shadow: 0 0 0 3px rgba(15, 76, 129, 0.12);
      }}
      textarea {{ min-height: 140px; resize: vertical; }}
      button {{
        border: 0;
        border-radius: 999px;
        padding: 10px 15px;
        font-weight: 700;
        letter-spacing: 0.01em;
        background: var(--accent);
        color: white;
        cursor: pointer;
        transition: transform 120ms ease, box-shadow 120ms ease, background 120ms ease;
      }}
      button:hover {{
        transform: translateY(-1px);
        box-shadow: 0 8px 18px rgba(15, 76, 129, 0.24);
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
        border: 1px solid var(--line);
        border-radius: 12px;
        padding: 13px;
        background: rgba(255, 255, 255, 0.78);
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
        border: 1px solid var(--line);
        background: rgba(255, 255, 255, 0.76);
        color: #475569;
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
