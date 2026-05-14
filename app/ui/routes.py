import json
from html import escape
from pathlib import Path
from typing import Optional, cast
from urllib.parse import quote_plus

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.core.exceptions import WorkflowError
from app.core.settings import get_settings
from app.db.models import RunModel
from app.db.session import get_session_factory
from app.providers.health import get_provider_health
from app.schemas.task import TaskCreate
from app.services.artifact_service import list_artifacts
from app.services.backup_service import create_backup, rehearse_restore
from app.services.github_service import get_github_status
from app.services.lmstudio_models_service import fetch_lmstudio_models
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
    get_run_state_snapshots,
    reject_run,
    retry_run,
)
from app.services.settings_service import load_local_settings, save_local_settings
from app.services.task_service import create_task_and_run
from app.ui.render import layout, page, page_with_auto_refresh, react_app_shell, status_badge

router = APIRouter(include_in_schema=False)


def _authorized(request: Request) -> bool:
    return request.cookies.get("operator_token") == get_settings().app_api_token


def _require_authorized(request: Request):
    if not _authorized(request):
        return RedirectResponse("/ui/login", status_code=303)
    return None


def _should_secure_cookie(request: Request) -> bool:
    settings = get_settings()
    return request.url.scheme == "https" or settings.app_env.lower() == "production"


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


def _render_runs(runs: list[RunModel], highlighted_run_id: Optional[str] = None) -> str:
    if not runs:
        return '<div class="item"><div class="meta">No runs yet.</div></div>'

    rendered = []
    for run in runs:
        run_title = str(run.task.title) if run.task is not None else "Untitled task"
        is_highlighted = highlighted_run_id == run.id
        border_style = " style=\"border:1px solid #d0a44e;\"" if is_highlighted else ""
        rendered.append(
            f"""
            <div class="item"{border_style}>
              <div class="section-head">
                <h2 style="font-size: 1rem; margin: 0;">
                  <a href="/ui/runs/{escape(run.id)}">{escape(run.id)}</a>
                </h2>
                {status_badge(str(run.status))}
              </div>
              <div class="meta">{escape(run_title)}</div>
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
    models, models_err = fetch_lmstudio_models(settings)
    datalist_options = "".join(
        f'<option value="{escape(str(item.get("id", "")))}"></option>'
        for item in models
        if isinstance(item, dict) and item.get("id")
    )
    models_err_html = (
        f'<p class="meta">LM Studio model list: {escape(models_err)}</p>' if models_err else ""
    )

    def value(key: str, fallback: str) -> str:
        return escape(local_values.get(key, fallback))

    def lm_field(name: str, fallback: str) -> str:
        return (
            f'<input type="text" name="{name}" list="lmstudio-model-ids" '
            f'value="{value(name, fallback)}" placeholder="{name}">'
        )

    return f"""
    <form method="post" action="/ui/settings">
      <datalist id="lmstudio-model-ids">{datalist_options}</datalist>
      {models_err_html}
      <input type="text" name="APP_HOST" value="{value("APP_HOST", settings.app_host)}" placeholder="APP_HOST">
      <input type="text" name="APP_PORT" value="{value("APP_PORT", str(settings.app_port))}" placeholder="APP_PORT">
      <input type="text" name="APP_API_TOKEN" value="{value("APP_API_TOKEN", settings.app_api_token)}" placeholder="APP_API_TOKEN">
      <input type="text" name="WORKER_COUNT" value="{value("WORKER_COUNT", str(settings.worker_count))}" placeholder="WORKER_COUNT">
      <input type="text" name="LMSTUDIO_BASE_URL" value="{value("LMSTUDIO_BASE_URL", settings.lmstudio_base_url)}" placeholder="LMSTUDIO_BASE_URL">
      {lm_field("LMSTUDIO_MODEL", settings.lmstudio_model)}
      {lm_field("LMSTUDIO_MODEL_PLANNER", settings.lmstudio_model_planner or "")}
      {lm_field("LMSTUDIO_MODEL_ARCHITECT", settings.lmstudio_model_architect or "")}
      {lm_field("LMSTUDIO_MODEL_UI_DESIGNER", settings.lmstudio_model_ui_designer or "")}
      {lm_field("LMSTUDIO_MODEL_CODER", settings.lmstudio_model_coder or "")}
      {lm_field("LMSTUDIO_MODEL_REVIEWER", settings.lmstudio_model_reviewer or "")}
      {lm_field("LMSTUDIO_MODEL_TESTER", settings.lmstudio_model_tester or "")}
      {lm_field("LMSTUDIO_MODEL_SUPERVISOR", settings.lmstudio_model_supervisor or "")}
      <input type="text" name="LMSTUDIO_API_KEY" value="{value("LMSTUDIO_API_KEY", settings.lmstudio_api_key)}" placeholder="LMSTUDIO_API_KEY">
      <input type="text" name="PROVIDER_TIMEOUT_SECONDS" value="{value("PROVIDER_TIMEOUT_SECONDS", str(settings.provider_timeout_seconds))}" placeholder="PROVIDER_TIMEOUT_SECONDS">
      <input type="text" name="GIT_CLONE_TIMEOUT_SECONDS" value="{value("GIT_CLONE_TIMEOUT_SECONDS", str(settings.git_clone_timeout_seconds))}" placeholder="GIT_CLONE_TIMEOUT_SECONDS">
      <input type="text" name="SOURCE_REPO_PATH" value="{value("SOURCE_REPO_PATH", str(settings.source_repo_path_resolved or ""))}" placeholder="SOURCE_REPO_PATH">
      <input type="text" name="ALLOWED_GIT_HOSTS" value="{value("ALLOWED_GIT_HOSTS", settings.allowed_git_hosts)}" placeholder="ALLOWED_GIT_HOSTS (comma hosts)">
      <input type="text" name="ALLOWED_SOURCE_REPO_ROOTS" value="{value("ALLOWED_SOURCE_REPO_ROOTS", settings.allowed_source_repo_roots)}" placeholder="ALLOWED_SOURCE_REPO_ROOTS">
      <input type="text" name="WORKSPACE_ROOT" value="{value("WORKSPACE_ROOT", str(settings.workspace_root_path))}" placeholder="WORKSPACE_ROOT">
      <input type="text" name="BACKUP_ROOT" value="{value("BACKUP_ROOT", str(settings.backup_root_path))}" placeholder="BACKUP_ROOT">
      <input type="text" name="GIT_AUTHOR_NAME" value="{value("GIT_AUTHOR_NAME", settings.git_author_name)}" placeholder="GIT_AUTHOR_NAME">
      <input type="text" name="GIT_AUTHOR_EMAIL" value="{value("GIT_AUTHOR_EMAIL", settings.git_author_email)}" placeholder="GIT_AUTHOR_EMAIL">
      <input type="text" name="LOG_LEVEL" value="{value("LOG_LEVEL", settings.log_level)}" placeholder="LOG_LEVEL">
      <input type="text" name="USE_SCOUT_STAGE" value="{value("USE_SCOUT_STAGE", str(settings.use_scout_stage).lower())}" placeholder="USE_SCOUT_STAGE (true/false)">
      <input type="text" name="PLAYBOOK_SUPERVISOR_ENABLED" value="{value("PLAYBOOK_SUPERVISOR_ENABLED", str(settings.playbook_supervisor_enabled).lower())}" placeholder="PLAYBOOK_SUPERVISOR_ENABLED">
      <input type="text" name="PLAYBOOK_REQUIRE_HUMAN_CONFIRM" value="{value("PLAYBOOK_REQUIRE_HUMAN_CONFIRM", str(settings.playbook_require_human_confirm).lower())}" placeholder="PLAYBOOK_REQUIRE_HUMAN_CONFIRM">
      <input type="text" name="PLAYBOOK_SUPERVISOR_SYSTEM_PROMPT_PATH" value="{value("PLAYBOOK_SUPERVISOR_SYSTEM_PROMPT_PATH", settings.playbook_supervisor_system_prompt_path)}" placeholder="PLAYBOOK_SUPERVISOR_SYSTEM_PROMPT_PATH">
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
    selected = selected_path or (files[0] if files else None)
    files_html = "".join(
        f'<a class="nav-link{" active" if item == selected else ""}" '
        f'href="/ui/runs/{escape(run_id)}?file={escape(item)}">{escape(item)}</a>'
        for item in files
    ) or '<div class="item"><div class="meta">No files available in the workspace.</div></div>'

    content = ""
    if selected:
        try:
            content = str(read_run_workspace_file(run_id, selected)["content"])
        except Exception:
            content = ""

    editor = ""
    if selected:
        editor = f"""
        <form method="post" action="/ui/runs/{escape(run_id)}/files/save">
          <input type="hidden" name="path" value="{escape(selected)}">
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
    return HTMLResponse(react_app_shell("Operator Console"))


@router.get("/ui/projects", response_class=HTMLResponse)
def ui_projects(request: Request):
    redirect = _require_authorized(request)
    if redirect:
        return redirect
    return HTMLResponse(react_app_shell("Projects"))


@router.get("/ui/projects/{project_id}", response_class=HTMLResponse)
def ui_project_detail(request: Request, project_id: str):
    redirect = _require_authorized(request)
    if redirect:
        return redirect
    return HTMLResponse(react_app_shell(f"Project {project_id}"))


@router.get("/ui/repository", response_class=HTMLResponse)
def repository_page(request: Request):
    redirect = _require_authorized(request)
    if redirect:
        return redirect
    return HTMLResponse(react_app_shell("Repository"))

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
    return HTMLResponse(react_app_shell("Provider"))

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
    return HTMLResponse(react_app_shell("Settings"))

    settings = get_settings()
    page_success = request.query_params.get("success")
    success_html = (
        f'<section class="panel"><div class="meta" style="color:#2d6a3a;">{escape(page_success)}</div></section>'
        if page_success
        else ""
    )
    body = f"""
    {success_html}
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
    WORKER_COUNT: str = Form("3"),
    LMSTUDIO_BASE_URL: str = Form(...),
    LMSTUDIO_MODEL: str = Form(...),
    LMSTUDIO_MODEL_PLANNER: str = Form(""),
    LMSTUDIO_MODEL_ARCHITECT: str = Form(""),
    LMSTUDIO_MODEL_UI_DESIGNER: str = Form(""),
    LMSTUDIO_MODEL_CODER: str = Form(""),
    LMSTUDIO_MODEL_REVIEWER: str = Form(""),
    LMSTUDIO_MODEL_TESTER: str = Form(""),
    LMSTUDIO_MODEL_SUPERVISOR: str = Form(""),
    LMSTUDIO_API_KEY: str = Form(...),
    PROVIDER_TIMEOUT_SECONDS: str = Form(...),
    GIT_CLONE_TIMEOUT_SECONDS: str = Form("300"),
    SOURCE_REPO_PATH: str = Form(""),
    ALLOWED_GIT_HOSTS: str = Form(""),
    ALLOWED_SOURCE_REPO_ROOTS: str = Form(""),
    WORKSPACE_ROOT: str = Form(...),
    BACKUP_ROOT: str = Form(...),
    GIT_AUTHOR_NAME: str = Form(...),
    GIT_AUTHOR_EMAIL: str = Form(...),
    LOG_LEVEL: str = Form(...),
    USE_SCOUT_STAGE: str = Form("false"),
    PLAYBOOK_SUPERVISOR_ENABLED: str = Form("false"),
    PLAYBOOK_REQUIRE_HUMAN_CONFIRM: str = Form("true"),
    PLAYBOOK_SUPERVISOR_SYSTEM_PROMPT_PATH: str = Form(
        "app/agents/prompts/playbook_supervisor.md",
    ),
    GITHUB_REPO_FULL_NAME: str = Form(default="hamedmirza/AI-Dev-Platform"),
    GITHUB_REPO_DEFAULT_BRANCH: str = Form(default="main"),
):
    redirect = _require_authorized(request)
    if redirect:
        return redirect
    current_token = get_settings().app_api_token
    current_lmstudio_key = get_settings().lmstudio_api_key
    next_token = current_token if APP_API_TOKEN == "__UNCHANGED__" else APP_API_TOKEN
    next_lmstudio_key = (
        current_lmstudio_key if LMSTUDIO_API_KEY == "__UNCHANGED__" else LMSTUDIO_API_KEY
    )

    save_local_settings(
        {
            "APP_HOST": APP_HOST,
            "APP_PORT": APP_PORT,
            "APP_API_TOKEN": next_token,
            "WORKER_COUNT": WORKER_COUNT,
            "LMSTUDIO_BASE_URL": LMSTUDIO_BASE_URL,
            "LMSTUDIO_MODEL": LMSTUDIO_MODEL,
            "LMSTUDIO_MODEL_PLANNER": LMSTUDIO_MODEL_PLANNER,
            "LMSTUDIO_MODEL_ARCHITECT": LMSTUDIO_MODEL_ARCHITECT,
            "LMSTUDIO_MODEL_UI_DESIGNER": LMSTUDIO_MODEL_UI_DESIGNER,
            "LMSTUDIO_MODEL_CODER": LMSTUDIO_MODEL_CODER,
            "LMSTUDIO_MODEL_REVIEWER": LMSTUDIO_MODEL_REVIEWER,
            "LMSTUDIO_MODEL_TESTER": LMSTUDIO_MODEL_TESTER,
            "LMSTUDIO_MODEL_SUPERVISOR": LMSTUDIO_MODEL_SUPERVISOR,
            "LMSTUDIO_API_KEY": next_lmstudio_key,
            "PROVIDER_TIMEOUT_SECONDS": PROVIDER_TIMEOUT_SECONDS,
            "GIT_CLONE_TIMEOUT_SECONDS": GIT_CLONE_TIMEOUT_SECONDS,
            "SOURCE_REPO_PATH": SOURCE_REPO_PATH,
            "ALLOWED_GIT_HOSTS": ALLOWED_GIT_HOSTS,
            "ALLOWED_SOURCE_REPO_ROOTS": ALLOWED_SOURCE_REPO_ROOTS,
            "WORKSPACE_ROOT": WORKSPACE_ROOT,
            "BACKUP_ROOT": BACKUP_ROOT,
            "GIT_AUTHOR_NAME": GIT_AUTHOR_NAME,
            "GIT_AUTHOR_EMAIL": GIT_AUTHOR_EMAIL,
            "LOG_LEVEL": LOG_LEVEL,
            "USE_SCOUT_STAGE": USE_SCOUT_STAGE,
            "PLAYBOOK_SUPERVISOR_ENABLED": PLAYBOOK_SUPERVISOR_ENABLED,
            "PLAYBOOK_REQUIRE_HUMAN_CONFIRM": PLAYBOOK_REQUIRE_HUMAN_CONFIRM,
            "PLAYBOOK_SUPERVISOR_SYSTEM_PROMPT_PATH": PLAYBOOK_SUPERVISOR_SYSTEM_PROMPT_PATH,
            "GITHUB_REPO_FULL_NAME": GITHUB_REPO_FULL_NAME,
            "GITHUB_REPO_DEFAULT_BRANCH": GITHUB_REPO_DEFAULT_BRANCH,
        }
    )
    response = RedirectResponse("/ui/settings?success=Settings+saved.", status_code=303)
    if next_token != request.cookies.get("operator_token"):
        response.set_cookie(
            "operator_token",
            next_token,
            httponly=True,
            samesite="lax",
            secure=_should_secure_cookie(request),
        )
    return response


@router.get("/ui/backups", response_class=HTMLResponse)
def backups_page(request: Request):
    redirect = _require_authorized(request)
    if redirect:
        return redirect
    return HTMLResponse(react_app_shell("Backups"))


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
def login_submit(request: Request, token: str = Form(...)):
    response = RedirectResponse("/ui", status_code=303)
    response.set_cookie(
        "operator_token",
        token,
        httponly=True,
        samesite="lax",
        secure=_should_secure_cookie(request),
    )
    return response


@router.get("/ui/logout")
def logout():
    response = RedirectResponse("/ui/login", status_code=303)
    response.delete_cookie("operator_token")
    return response


@router.post("/ui/tasks")
def create_task_ui(
    request: Request,
    title: str = Form(...),
    request_text: str = Form(...),
    workspace_path: str = Form(default=""),
    task_type: str = Form(default=""),
    target_files: str = Form(default=""),
    constraints: str = Form(default=""),
    provider: str = Form(default=""),
    model: str = Form(default=""),
):
    redirect = _require_authorized(request)
    if redirect:
        return redirect

    session = get_session_factory()()
    try:
        task = create_task_and_run(
            session,
            TaskCreate(
                title=title,
                request_text=request_text,
                workspace_path=workspace_path or None,
                task_type=task_type or None,
                target_files=_split_csv(target_files),
                constraints=_split_csv(constraints),
                provider=provider or None,
                model=model or None,
            ),
            provider_name=provider or "ui-submitted",
        )
    except Exception as exc:
        session.close()
        return RedirectResponse(f"/ui?error={quote_plus(str(exc))}", status_code=303)
    finally:
        if session.is_active:
            session.close()

    get_orchestration_service().enqueue_run(task.run_id)
    return RedirectResponse(
        f"/ui?success=Task+created.&created_run_id={quote_plus(task.run_id)}",
        status_code=303,
    )


def _run_action_redirect(run_id: str, error: Optional[str] = None) -> RedirectResponse:
    location = f"/ui/runs/{run_id}"
    if error:
        location += f"?error={quote_plus(error)}"
    return RedirectResponse(location, status_code=303)


@router.post("/ui/runs/{run_id}/approve")
def approve_ui(request: Request, run_id: str, note: str = Form(default="")):
    redirect = _require_authorized(request)
    if redirect:
        return redirect
    session = get_session_factory()()
    try:
        approve_run(session, run_id, note or None)
    except WorkflowError as exc:
        return _run_action_redirect(run_id, str(exc))
    finally:
        session.close()
    return _run_action_redirect(run_id)


@router.get("/ui/runs/{run_id}/approve")
def approve_ui_get(run_id: str):
    return _run_action_redirect(run_id, "Use the approve button to submit this action.")


@router.post("/ui/runs/{run_id}/reject")
def reject_ui(request: Request, run_id: str, note: str = Form(default="")):
    redirect = _require_authorized(request)
    if redirect:
        return redirect
    session = get_session_factory()()
    try:
        reject_run(session, run_id, note or None)
    except WorkflowError as exc:
        return _run_action_redirect(run_id, str(exc))
    finally:
        session.close()
    return _run_action_redirect(run_id)


@router.get("/ui/runs/{run_id}/reject")
def reject_ui_get(run_id: str):
    return _run_action_redirect(run_id, "Use the reject button to submit this action.")


@router.get("/runs/{run_id}/approve")
def approve_alias_get(run_id: str):
    return _run_action_redirect(run_id, "Use /ui/runs/{id} actions from the run detail page.")


@router.get("/runs/{run_id}/reject")
def reject_alias_get(run_id: str):
    return _run_action_redirect(run_id, "Use /ui/runs/{id} actions from the run detail page.")


@router.post("/ui/runs/{run_id}/retry")
def retry_ui(request: Request, run_id: str, note: str = Form(default="")):
    redirect = _require_authorized(request)
    if redirect:
        return redirect
    session = get_session_factory()()
    try:
        retry_run(session, run_id, note or None)
    except WorkflowError as exc:
        return _run_action_redirect(run_id, str(exc))
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
    except WorkflowError as exc:
        return _run_action_redirect(run_id, str(exc))
    finally:
        session.close()
    return _run_action_redirect(run_id)


@router.post("/ui/runs/{run_id}/cleanup")
def cleanup_ui(request: Request, run_id: str):
    redirect = _require_authorized(request)
    if redirect:
        return redirect
    try:
        cleanup_workspace(run_id)
    except Exception as exc:
        return _run_action_redirect(run_id, str(exc))
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
    try:
        write_run_workspace_file(run_id, path, content)
    except Exception as exc:
        return _run_action_redirect(run_id, str(exc))
    return RedirectResponse(f"/ui/runs/{run_id}?file={path}", status_code=303)


@router.get("/ui/runs/{run_id}", response_class=HTMLResponse)
def run_detail(request: Request, run_id: str):
    redirect = _require_authorized(request)
    if redirect:
        return redirect
    return HTMLResponse(react_app_shell(f"Run {run_id}"))

    session = get_session_factory()()
    try:
        run = get_run(session, run_id)
        if run is None:
            return HTMLResponse(page("Run Not Found", "<p>Run not found.</p>"), status_code=404)
        history = get_run_history(session, run_id)
        artifacts = list_artifacts(session, run_id)
        snapshots = get_run_state_snapshots(session, run_id)
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
    snapshots_html = (
        "".join(
            (
                '<div class="item">'
                f"<h4>{escape(item.stage)} / {escape(item.status)}</h4>"
                f'<div class="meta">retry_count={escape(str(item.retry_count))}</div>'
                f"<pre>{escape(item.payload_json)}</pre>"
                "</div>"
            )
            for item in snapshots[-6:]
        )
        or '<div class="item"><div class="meta">No state snapshots recorded yet.</div></div>'
    )
    code_change_panel = _render_code_change_panel(artifacts)
    diff_panel = _render_diff_panel(run_id)
    workspace_editor = _render_workspace_editor(run_id, selected_file)
    auto_refresh = run.status in {"pending", "running"}

    page_error = request.query_params.get("error")
    error_html = (
        f'<section class="panel"><div class="meta" style="color:#9f3a2d;">{escape(page_error)}</div></section>'
        if page_error
        else ""
    )
    body = f"""
    {error_html}
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
        <span class="pill">request: {escape(str(run.request_id or "-"))}</span>
        <span class="pill">retries: {escape(str(run.retry_count))}</span>
      </div>
    </section>
    <section class="panel">
      <div class="section-head">
        <h2>Task Metadata</h2>
      </div>
      <div class="list">
        {_item("Title", str(run.task.title))}
        {_item("Description", str(run.task.description or run.task.request_text))}
        {_item("Workspace", str(run.task.workspace_path or "-"))}
        {_item("Task Type", str(run.task.task_type or "-"))}
        {_item("Constraints", ", ".join(run.task.constraints) or "-")}
        {_item("Target Files", ", ".join(run.task.target_files) or "-")}
        {_item("Provider Override", str(run.task.provider_override or "-"))}
        {_item("Model Override", str(run.task.model_override or "-"))}
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
        <div class="section-head"><h2>State Snapshots</h2></div>
        <div class="list">{snapshots_html}</div>
      </section>
    </div>
    <div class="wide-grid">
      <section class="panel">
        <div class="section-head"><h2>Artifacts</h2></div>
        <div class="list">{artifact_html}</div>
      </section>
      <section class="panel">
        <div class="section-head"><h2>Task Prompt</h2></div>
        <pre>{escape(run.task.request_text)}</pre>
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


def _split_csv(raw_value: str) -> list[str]:
    return [item.strip() for item in raw_value.split(",") if item.strip()]


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
