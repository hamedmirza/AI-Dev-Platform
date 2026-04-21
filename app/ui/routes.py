import json
from html import escape
from pathlib import Path
from typing import Optional, cast

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select

from app.core.settings import get_settings
from app.db.models import RunModel
from app.db.session import get_session_factory
from app.providers.health import get_provider_health
from app.schemas.task import TaskCreate
from app.services.artifact_service import list_artifacts
from app.services.backup_service import create_backup, rehearse_restore
from app.services.github_service import get_github_status
from app.services.orchestration_service import get_orchestration_service
from app.services.repository_service import (
    get_repository_summary,
    get_run_workspace_diff,
    list_run_workspace_files,
    read_run_workspace_file,
    write_run_workspace_file,
)
from app.services.run_service import (
    abort_run,
    approve_run,
    cleanup_workspace,
    get_run,
    get_run_history,
    reject_run,
    retry_run,
)
from app.services.settings_service import load_local_settings, save_local_settings
from app.services.task_service import create_task_and_run
from app.ui.render import layout, page, page_with_auto_refresh, status_badge

router = APIRouter(include_in_schema=False)


def _authorized(request: Request) -> bool:
    return request.cookies.get("operator_token") == get_settings().app_api_token


def _require_authorized(request: Request):
    if not _authorized(request):
        return RedirectResponse("/ui/login", status_code=303)
    return None


def _nav() -> str:
    return """
      <a href="/ui">Dashboard</a>
      <a href="/ui/repository">Repository</a>
      <a href="/ui/provider">Provider</a>
      <a href="/ui/settings">Settings</a>
      <a href="/ui/backups">Backups</a>
      <a href="/ui/logout">Logout</a>
    """


def _sidebar(active: str) -> str:
    items = [
        ("dashboard", "/ui", "Dashboard"),
        ("repository", "/ui/repository", "Repository"),
        ("provider", "/ui/provider", "Provider"),
        ("settings", "/ui/settings", "Settings"),
        ("backups", "/ui/backups", "Backups"),
    ]
    links = []
    for key, href, label in items:
        active_class = " active" if key == active else ""
        links.append(f'<a class="nav-link{active_class}" href="{href}">{escape(label)}</a>')

    return f"""
    <section class="panel">
      <h3>Console</h3>
      <div class="nav-list">{''.join(links)}</div>
    </section>
    <section class="panel">
      <h3>Operator</h3>
      <div class="meta">
        This console controls local runs, workspace cleanup, and restore rehearsal.
      </div>
      <div class="pill-row" style="margin-top: 12px;">
        <span class="pill">Single operator</span>
        <span class="pill">Local-first</span>
        <span class="pill">Approval gated</span>
      </div>
    </section>
    """


def _item(title: str, value: str) -> str:
    return (
        '<div class="item">'
        f"<h4>{escape(title)}</h4>"
        f'<div class="meta">{escape(value)}</div>'
        "</div>"
    )


def _action_form(action: str, label: str, css_class: str = "") -> str:
    class_attr = f' class="{css_class}"' if css_class else ""
    return (
        f'<form method="post" action="{escape(action)}">'
        f"<button{class_attr} type=\"submit\">{escape(label)}</button>"
        "</form>"
    )


def _render_runs(runs: list[RunModel]) -> str:
    if not runs:
        return '<div class="item"><div class="meta">No runs yet.</div></div>'

    rendered = []
    for run in runs:
        rendered.append(
            f"""
            <div class="item">
              <div class="section-head">
                <h2 style="font-size: 1rem; margin: 0;">
                  <a href="/ui/runs/{escape(run.id)}">{escape(run.id)}</a>
                </h2>
                {status_badge(str(run.status))}
              </div>
              <div class="pill-row">
                <span class="pill">stage: {escape(str(run.current_stage))}</span>
                <span class="pill">provider: {escape(str(run.provider_name))}</span>
              </div>
            </div>
            """
        )
    return "".join(rendered)


def _render_backups() -> str:
    backups = sorted(get_settings().backup_root_path.glob("backup-*"), reverse=True)
    if not backups:
        return '<div class="item"><div class="meta">No backups created yet.</div></div>'

    items = []
    for backup_dir in backups[:12]:
        manifest_path = backup_dir / "manifest.json"
        items.append(
            f"""
            <div class="item">
              <div class="section-head">
                <h2 style="font-size: 1rem; margin: 0;">{escape(backup_dir.name)}</h2>
                <form method="post" action="/ui/backups/restore-rehearsal">
                  <input type="hidden" name="manifest_path" value="{escape(str(manifest_path))}">
                  <button class="secondary" type="submit">Rehearse Restore</button>
                </form>
              </div>
              <div class="meta">{escape(str(manifest_path))}</div>
            </div>
            """
        )
    return "".join(items)


def _settings_form(settings) -> str:
    local_values = load_local_settings()

    def value(key: str, fallback: str) -> str:
        return escape(local_values.get(key, fallback))

    return f"""
    <form method="post" action="/ui/settings">
      <input type="text" name="APP_HOST" value="{value("APP_HOST", settings.app_host)}" placeholder="APP_HOST">
      <input type="text" name="APP_PORT" value="{value("APP_PORT", str(settings.app_port))}" placeholder="APP_PORT">
      <input type="text" name="APP_API_TOKEN" value="{value("APP_API_TOKEN", settings.app_api_token)}" placeholder="APP_API_TOKEN">
      <input type="text" name="LMSTUDIO_BASE_URL" value="{value("LMSTUDIO_BASE_URL", settings.lmstudio_base_url)}" placeholder="LMSTUDIO_BASE_URL">
      <input type="text" name="LMSTUDIO_MODEL" value="{value("LMSTUDIO_MODEL", settings.lmstudio_model)}" placeholder="LMSTUDIO_MODEL">
      <input type="text" name="LMSTUDIO_API_KEY" value="{value("LMSTUDIO_API_KEY", settings.lmstudio_api_key)}" placeholder="LMSTUDIO_API_KEY">
      <input type="text" name="PROVIDER_TIMEOUT_SECONDS" value="{value("PROVIDER_TIMEOUT_SECONDS", str(settings.provider_timeout_seconds))}" placeholder="PROVIDER_TIMEOUT_SECONDS">
      <input type="text" name="SOURCE_REPO_PATH" value="{value("SOURCE_REPO_PATH", str(settings.source_repo_path_resolved or ""))}" placeholder="SOURCE_REPO_PATH">
      <input type="text" name="WORKSPACE_ROOT" value="{value("WORKSPACE_ROOT", str(settings.workspace_root_path))}" placeholder="WORKSPACE_ROOT">
      <input type="text" name="BACKUP_ROOT" value="{value("BACKUP_ROOT", str(settings.backup_root_path))}" placeholder="BACKUP_ROOT">
      <input type="text" name="GIT_AUTHOR_NAME" value="{value("GIT_AUTHOR_NAME", settings.git_author_name)}" placeholder="GIT_AUTHOR_NAME">
      <input type="text" name="GIT_AUTHOR_EMAIL" value="{value("GIT_AUTHOR_EMAIL", settings.git_author_email)}" placeholder="GIT_AUTHOR_EMAIL">
      <input type="text" name="LOG_LEVEL" value="{value("LOG_LEVEL", settings.log_level)}" placeholder="LOG_LEVEL">
      <button type="submit">Save Local Settings</button>
    </form>
    """


def _render_code_change_panel(artifacts) -> str:
    for artifact in artifacts:
        if artifact.artifact_type != "code_change":
            continue
        try:
            payload = json.loads(artifact.content)
        except json.JSONDecodeError:
            return f'<div class="item"><pre>{escape(artifact.content)}</pre></div>'

        files = payload.get("changed_files", [])
        notes = payload.get("implementation_notes", [])
        requires = payload.get("requires_operator_approval", True)
        file_html = "".join(f'<span class="pill">{escape(str(item))}</span>' for item in files)
        notes_html = "".join(
            f'<div class="item"><div class="meta">{escape(str(item))}</div></div>' for item in notes
        )
        return f"""
        <section class="panel">
          <div class="section-head">
            <h2>Code Review Panel</h2>
            {status_badge("approval required" if requires else "approval optional")}
          </div>
          <div class="pill-row">{file_html or '<span class="pill">No changed files listed</span>'}</div>
          <div class="list" style="margin-top: 12px;">
            {notes_html or '<div class="item"><div class="meta">No implementation notes listed.</div></div>'}
          </div>
        </section>
        """
    return ""


def _render_diff_panel(run_id: str) -> str:
    diff = get_run_workspace_diff(run_id)
    changed_files = cast(list[str], diff["changed_files"])
    changed_files_html = "".join(
        f'<span class="pill">{escape(str(item))}</span>' for item in changed_files
    )
    diff_body = escape(str(diff["diff_text"])) if diff["diff_text"] else "No local diff detected."
    branch = escape(str(diff.get("branch", ""))) or "unknown"
    return f"""
    <section class="panel">
      <div class="section-head">
        <h2>Workspace Diff</h2>
        {status_badge("changes detected" if diff["has_changes"] else "clean")}
      </div>
      <div class="pill-row">
        <span class="pill">branch: {branch}</span>
        {changed_files_html or '<span class="pill">No changed files</span>'}
      </div>
      <pre style="margin-top: 14px;">{diff_body}</pre>
    </section>
    """


def _render_workspace_editor(run_id: str, selected_path: Optional[str]) -> str:
    workspace = list_run_workspace_files(run_id)
    files = cast(list[str], workspace["files"])
    files_html = "".join(
        f'<a class="nav-link{" active" if item == selected_path else ""}" '
        f'href="/ui/runs/{escape(run_id)}?file={escape(item)}">{escape(item)}</a>'
        for item in files
    ) or '<div class="item"><div class="meta">No files available in the workspace.</div></div>'

    content = ""
    if selected_path:
        try:
            content = str(read_run_workspace_file(run_id, selected_path)["content"])
        except Exception:
            content = ""

    editor = ""
    if selected_path:
        editor = f"""
        <form method="post" action="/ui/runs/{escape(run_id)}/files/save">
          <input type="hidden" name="path" value="{escape(selected_path)}">
          <textarea name="content" style="min-height: 320px;" required>{escape(content)}</textarea>
          <button type="submit">Save File</button>
        </form>
        """
    else:
        editor = '<div class="item"><div class="meta">Select a file to inspect or edit it.</div></div>'

    return f"""
    <section class="panel">
      <div class="section-head">
        <h2>Workspace Files</h2>
      </div>
      <div class="wide-grid">
        <div class="nav-list">{files_html}</div>
        <div>{editor}</div>
      </div>
    </section>
    """


@router.get("/", response_class=HTMLResponse)
def ui_index():
    return RedirectResponse("/ui", status_code=303)


@router.get("/ui", response_class=HTMLResponse)
def ui_root(request: Request):
    redirect = _require_authorized(request)
    if redirect:
        return redirect

    session = get_session_factory()()
    try:
        runs = session.scalars(
            select(RunModel).order_by(RunModel.created_at.desc()).limit(12),
        ).all()
    finally:
        session.close()

    provider = get_provider_health()
    repository = get_repository_summary()
    github = get_github_status()
    backups = sorted(get_settings().backup_root_path.glob("backup-*"), reverse=True)
    github_state = "configured" if bool(github["configured"]) else "missing"
    repo_path = escape(str(repository["path"]))
    repo_head = escape(str(repository["head_sha"]))
    repo_dirty = escape(str(repository["dirty"]))
    repo_branch = escape(str(repository["branch"]))

    body = f"""
    <section class="panel hero">
      <div class="eyebrow">Operator Overview</div>
      <h2>Local operations console for planning, run control, and recovery.</h2>
      <p>
        The platform is now usable as a local-first backend with approval gates, workspace cloning,
        backup rehearsal, and a real run timeline. GitHub remains optional until you wire a token.
      </p>
      <div class="metrics">
        <div class="metric">Provider<strong>{status_badge(provider.status.value)}</strong></div>
        <div class="metric">Repository<strong>{repo_branch}</strong></div>
        <div class="metric">GitHub<strong>{status_badge(github_state)}</strong></div>
        <div class="metric">Backups<strong>{len(backups)}</strong></div>
      </div>
    </section>
    <div class="wide-grid">
      <section class="panel">
        <div class="section-head">
          <h2>New Task</h2>
        </div>
        <form method="post" action="/ui/tasks">
          <input type="text" name="title" placeholder="Run title" required>
          <textarea
            name="request_text"
            placeholder="Describe the software task in detail."
            required
          ></textarea>
          <button type="submit">Start Run</button>
        </form>
      </section>
      <section class="panel">
        <div class="section-head">
          <h2>Repository Snapshot</h2>
          <a href="/ui/repository">Open repository view</a>
        </div>
        <div class="list">
          {_item("Path", repo_path)}
          {_item("Head", repo_head)}
          {_item("Dirty", repo_dirty)}
        </div>
      </section>
    </div>
    <section class="panel">
      <div class="section-head">
        <h2>Recent Runs</h2>
      </div>
      <div class="list">{_render_runs(runs)}</div>
    </section>
    """
    html = layout(
        "Operator Console",
        "Local-first run control for the AI Dev Platform.",
        _nav(),
        body,
        _sidebar("dashboard"),
    )
    return HTMLResponse(page("Operator Console", html))


@router.get("/ui/repository", response_class=HTMLResponse)
def repository_page(request: Request):
    redirect = _require_authorized(request)
    if redirect:
        return redirect

    repository = get_repository_summary()
    remotes = cast(list[str], repository["remotes"])
    remote_html = "".join(
        _item("Remote", str(remote)) for remote in remotes
    ) or '<div class="item"><div class="meta">No git remotes configured.</div></div>'
    repo_path = str(repository["path"])
    repo_branch = str(repository["branch"])
    repo_head = str(repository["head_sha"])
    repo_dirty = str(repository["dirty"])

    body = f"""
    <section class="panel hero">
      <div class="eyebrow">Repository</div>
      <h2>Current managed local repository state.</h2>
      <p>
        This view shows the actual repository path, branch, head SHA, dirty state, and configured
        remotes for the source clone the operator console is using.
      </p>
    </section>
    <div class="wide-grid">
      <section class="panel">
        <div class="list">
          {_item("Path", repo_path)}
          {_item("Branch", repo_branch)}
          {_item("Head SHA", repo_head)}
          {_item("Dirty", repo_dirty)}
        </div>
      </section>
      <section class="panel">
        <div class="section-head">
          <h2>Git Remotes</h2>
        </div>
        <div class="list">{remote_html}</div>
      </section>
    </div>
    """
    html = layout(
        "Repository",
        "Managed local checkout details.",
        _nav(),
        body,
        _sidebar("repository"),
    )
    return HTMLResponse(page("Repository", html))


@router.get("/ui/provider", response_class=HTMLResponse)
def provider_page(request: Request):
    redirect = _require_authorized(request)
    if redirect:
        return redirect

    settings = get_settings()
    provider = get_provider_health()
    github = get_github_status()
    github_state = "configured" if bool(github["configured"]) else "missing"

    body = f"""
    <section class="panel hero">
      <div class="eyebrow">Provider</div>
      <h2>Model routing and remote integration readiness.</h2>
      <p>
        This screen shows the active provider health, the configured model endpoint, and whether
        GitHub API access is currently enabled on this machine.
      </p>
    </section>
    <div class="wide-grid">
      <section class="panel">
        <div class="section-head">
          <h2>LM Studio</h2>
        </div>
        <div class="list">
          <div class="item"><h4>Status</h4><div>{status_badge(provider.status.value)}</div></div>
          {_item("Base URL", settings.lmstudio_base_url)}
          {_item("Model", settings.lmstudio_model)}
          {_item("Timeout", f"{settings.provider_timeout_seconds} seconds")}
          {_item("Detail", provider.detail)}
        </div>
      </section>
      <section class="panel">
        <div class="section-head">
          <h2>GitHub API</h2>
        </div>
        <div class="list">
          <div class="item"><h4>Configured</h4><div>{status_badge(github_state)}</div></div>
          {_item("Detail", str(github["detail"]))}
        </div>
      </section>
    </div>
    """
    html = layout(
        "Provider",
        "Remote model and integration health.",
        _nav(),
        body,
        _sidebar("provider"),
    )
    return HTMLResponse(page("Provider", html))


@router.get("/ui/settings", response_class=HTMLResponse)
def settings_page(request: Request):
    redirect = _require_authorized(request)
    if redirect:
        return redirect

    settings = get_settings()
    body = f"""
    <section class="panel hero">
      <div class="eyebrow">Settings</div>
      <h2>Edit local runtime overrides for this repo.</h2>
      <p>
        These values are written into a local <code>.env</code> file in the repo root and used by the
        current server process after the settings cache is refreshed.
      </p>
    </section>
    <section class="panel">
      <div class="section-head"><h2>Editable Local Settings</h2></div>
      {_settings_form(settings)}
    </section>
    """
    html = layout(
        "Settings",
        "Local configuration overrides.",
        _nav(),
        body,
        _sidebar("settings"),
    )
    return HTMLResponse(page("Settings", html))


@router.post("/ui/settings")
def settings_submit(
    request: Request,
    APP_HOST: str = Form(...),
    APP_PORT: str = Form(...),
    APP_API_TOKEN: str = Form(...),
    LMSTUDIO_BASE_URL: str = Form(...),
    LMSTUDIO_MODEL: str = Form(...),
    LMSTUDIO_API_KEY: str = Form(...),
    PROVIDER_TIMEOUT_SECONDS: str = Form(...),
    SOURCE_REPO_PATH: str = Form(""),
    WORKSPACE_ROOT: str = Form(...),
    BACKUP_ROOT: str = Form(...),
    GIT_AUTHOR_NAME: str = Form(...),
    GIT_AUTHOR_EMAIL: str = Form(...),
    LOG_LEVEL: str = Form(...),
):
    redirect = _require_authorized(request)
    if redirect:
        return redirect

    save_local_settings(
        {
            "APP_HOST": APP_HOST,
            "APP_PORT": APP_PORT,
            "APP_API_TOKEN": APP_API_TOKEN,
            "LMSTUDIO_BASE_URL": LMSTUDIO_BASE_URL,
            "LMSTUDIO_MODEL": LMSTUDIO_MODEL,
            "LMSTUDIO_API_KEY": LMSTUDIO_API_KEY,
            "PROVIDER_TIMEOUT_SECONDS": PROVIDER_TIMEOUT_SECONDS,
            "SOURCE_REPO_PATH": SOURCE_REPO_PATH,
            "WORKSPACE_ROOT": WORKSPACE_ROOT,
            "BACKUP_ROOT": BACKUP_ROOT,
            "GIT_AUTHOR_NAME": GIT_AUTHOR_NAME,
            "GIT_AUTHOR_EMAIL": GIT_AUTHOR_EMAIL,
            "LOG_LEVEL": LOG_LEVEL,
        }
    )
    response = RedirectResponse("/ui/settings", status_code=303)
    if APP_API_TOKEN != request.cookies.get("operator_token"):
        response.set_cookie("operator_token", APP_API_TOKEN, httponly=True, samesite="lax")
    return response


@router.get("/ui/backups", response_class=HTMLResponse)
def backups_page(request: Request):
    redirect = _require_authorized(request)
    if redirect:
        return redirect

    body = f"""
    <section class="panel hero">
      <div class="eyebrow">Backups</div>
      <h2>Create and rehearse local recovery sets.</h2>
      <p>
        Backups include the SQLite database and manifest metadata. Restore rehearsal copies the DB
        into a non-live location so recovery can be tested without touching the active database.
      </p>
    </section>
    <section class="panel">
      <div class="section-head">
        <h2>Backup Controls</h2>
        <form method="post" action="/ui/backups/run">
          <button type="submit">Create Backup</button>
        </form>
      </div>
      <div class="list">{_render_backups()}</div>
    </section>
    """
    html = layout(
        "Backups",
        "Local backup and restore rehearsal tools.",
        _nav(),
        body,
        _sidebar("backups"),
    )
    return HTMLResponse(page("Backups", html))


@router.get("/ui/login", response_class=HTMLResponse)
def login_page():
    body = f"""
    <header class="masthead">
      <div>
        <h1 class="title">Operator Login</h1>
        <p class="subtitle">Enter the local operator token configured for this service.</p>
      </div>
      <div class="nav">{_nav()}</div>
    </header>
    <section class="panel hero" style="max-width: 720px; margin: 40px auto 0;">
      <div class="eyebrow">Access</div>
      <h2>Use the local operator token to unlock the console.</h2>
      <p>
        The UI is intentionally local-first. It trusts a single operator token and uses a session
        cookie after login.
      </p>
      <form method="post" action="/ui/login">
        <input type="password" name="token" placeholder="Operator token" required>
        <button type="submit">Enter Console</button>
      </form>
    </section>
    """
    return HTMLResponse(page("Operator Login", body))


@router.post("/ui/login")
def login_submit(token: str = Form(...)):
    response = RedirectResponse("/ui", status_code=303)
    response.set_cookie("operator_token", token, httponly=True, samesite="lax")
    return response


@router.get("/ui/logout")
def logout():
    response = RedirectResponse("/ui/login", status_code=303)
    response.delete_cookie("operator_token")
    return response


@router.post("/ui/tasks")
def create_task_ui(request: Request, title: str = Form(...), request_text: str = Form(...)):
    redirect = _require_authorized(request)
    if redirect:
        return redirect

    session = get_session_factory()()
    try:
        task = create_task_and_run(
            session,
            TaskCreate(title=title, request_text=request_text),
            provider_name="ui-submitted",
        )
    finally:
        session.close()

    get_orchestration_service().enqueue_run(task.run_id)
    return RedirectResponse(f"/ui/runs/{task.run_id}", status_code=303)


def _run_action_redirect(run_id: str) -> RedirectResponse:
    return RedirectResponse(f"/ui/runs/{run_id}", status_code=303)


@router.post("/ui/runs/{run_id}/approve")
def approve_ui(request: Request, run_id: str, note: str = Form(default="")):
    redirect = _require_authorized(request)
    if redirect:
        return redirect
    session = get_session_factory()()
    try:
        approve_run(session, run_id, note or None)
    finally:
        session.close()
    return _run_action_redirect(run_id)


@router.post("/ui/runs/{run_id}/reject")
def reject_ui(request: Request, run_id: str, note: str = Form(default="")):
    redirect = _require_authorized(request)
    if redirect:
        return redirect
    session = get_session_factory()()
    try:
        reject_run(session, run_id, note or None)
    finally:
        session.close()
    return _run_action_redirect(run_id)


@router.post("/ui/runs/{run_id}/retry")
def retry_ui(request: Request, run_id: str, note: str = Form(default="")):
    redirect = _require_authorized(request)
    if redirect:
        return redirect
    session = get_session_factory()()
    try:
        retry_run(session, run_id, note or None)
    finally:
        session.close()
    get_orchestration_service().enqueue_run(run_id)
    return _run_action_redirect(run_id)


@router.post("/ui/runs/{run_id}/abort")
def abort_ui(request: Request, run_id: str, note: str = Form(default="")):
    redirect = _require_authorized(request)
    if redirect:
        return redirect
    session = get_session_factory()()
    try:
        abort_run(session, run_id, note or None)
    finally:
        session.close()
    return _run_action_redirect(run_id)


@router.post("/ui/runs/{run_id}/cleanup")
def cleanup_ui(request: Request, run_id: str):
    redirect = _require_authorized(request)
    if redirect:
        return redirect
    cleanup_workspace(run_id)
    return _run_action_redirect(run_id)


@router.post("/ui/runs/{run_id}/files/save")
def save_workspace_file_ui(
    request: Request,
    run_id: str,
    path: str = Form(...),
    content: str = Form(...),
):
    redirect = _require_authorized(request)
    if redirect:
        return redirect
    write_run_workspace_file(run_id, path, content)
    return RedirectResponse(f"/ui/runs/{run_id}?file={path}", status_code=303)


@router.get("/ui/runs/{run_id}", response_class=HTMLResponse)
def run_detail(request: Request, run_id: str):
    redirect = _require_authorized(request)
    if redirect:
        return redirect

    session = get_session_factory()()
    try:
        run = get_run(session, run_id)
        if run is None:
            return HTMLResponse(page("Run Not Found", "<p>Run not found.</p>"), status_code=404)
        history = get_run_history(session, run_id)
        artifacts = list_artifacts(session, run_id)
    finally:
        session.close()

    selected_file = request.query_params.get("file")
    history_html = (
        "".join(
            (
                '<div class="item">'
                f"<h4>{escape(item.event_type)}</h4>"
                f'<div class="meta">{escape(item.message)}</div>'
                "</div>"
            )
            for item in history
        )
        or '<div class="item"><div class="meta">No history recorded yet.</div></div>'
    )
    artifact_html = (
        "".join(
            f"""
            <div class="item">
              <h4>{escape(item.title)}</h4>
              <div class="pill-row" style="margin-bottom: 10px;">
                <span class="pill">{escape(item.artifact_type)}</span>
                <span class="pill">truncated: {escape(str(item.truncated))}</span>
              </div>
              <pre>{escape(item.content)}</pre>
            </div>
            """
            for item in artifacts
        )
        or '<div class="item"><div class="meta">No artifacts recorded yet.</div></div>'
    )
    code_change_panel = _render_code_change_panel(artifacts)
    diff_panel = _render_diff_panel(run_id)
    workspace_editor = _render_workspace_editor(run_id, selected_file)
    auto_refresh = run.status in {"pending", "running"}

    body = f"""
    <section class="panel hero">
      <div class="eyebrow">Run Detail</div>
      <h2>Run {escape(run.id)}</h2>
      <p>
        Status, operator actions, and artifact review for the current run.
        Approval here only affects local run state until GitHub is configured.
      </p>
      <div class="pill-row">
        {status_badge(str(run.status))}
        <span class="pill">stage: {escape(str(run.current_stage))}</span>
        <span class="pill">provider: {escape(str(run.provider_name))}</span>
      </div>
    </section>
    <section class="panel">
      <div class="section-head">
        <h2>Actions</h2>
      </div>
      <div class="actions">
        {_action_form(f"/ui/runs/{run_id}/approve", "Approve")}
        {_action_form(f"/ui/runs/{run_id}/reject", "Reject", "warn")}
        {_action_form(f"/ui/runs/{run_id}/retry", "Retry", "secondary")}
        {_action_form(f"/ui/runs/{run_id}/abort", "Abort", "danger")}
        {_action_form(f"/ui/runs/{run_id}/cleanup", "Cleanup Workspace", "secondary")}
      </div>
      <p class="meta" style="margin-top: 12px;">
        {escape(run.error_message or "No current error message.")}
      </p>
    </section>
    <div class="wide-grid">
      <section class="panel">
        <div class="section-head"><h2>Timeline</h2></div>
        <div class="list">{history_html}</div>
      </section>
      <section class="panel">
        <div class="section-head"><h2>Artifacts</h2></div>
        <div class="list">{artifact_html}</div>
      </section>
    </div>
    {code_change_panel}
    {diff_panel}
    {workspace_editor}
    """
    html = layout(
        f"Run {run.id}",
        "Detailed local run view.",
        _nav(),
        body,
        _sidebar("dashboard"),
    )
    if auto_refresh:
        return HTMLResponse(page_with_auto_refresh(f"Run {run.id}", html, interval_seconds=3))
    return HTMLResponse(page(f"Run {run.id}", html))


@router.post("/ui/backups/run")
def backup_ui(request: Request):
    redirect = _require_authorized(request)
    if redirect:
        return redirect
    create_backup()
    return RedirectResponse("/ui/backups", status_code=303)


@router.post("/ui/backups/restore-rehearsal")
def restore_rehearsal_ui(request: Request, manifest_path: str = Form(...)):
    redirect = _require_authorized(request)
    if redirect:
        return redirect

    rehearsal = rehearse_restore(manifest_path=Path(manifest_path))
    body = f"""
    <section class="panel hero">
      <div class="eyebrow">Restore Rehearsal</div>
      <h2>Backup restore rehearsal completed.</h2>
      <p>
        The backup set was copied into a non-live rehearsal directory. You can inspect the restored
        SQLite file there without touching the active database.
      </p>
      <pre>{escape(json.dumps(rehearsal.model_dump(), indent=2))}</pre>
    </section>
    """
    html = layout(
        "Restore Rehearsal",
        "Non-destructive backup validation.",
        _nav(),
        body,
        _sidebar("backups"),
    )
    return HTMLResponse(page("Restore Rehearsal", html))
