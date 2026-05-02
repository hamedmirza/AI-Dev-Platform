import React, { FormEvent, useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Activity,
  Archive,
  Boxes,
  Check,
  ChevronRight,
  CircleDot,
  Code2,
  Database,
  FileText,
  GitBranch,
  History,
  LayoutDashboard,
  Loader2,
  Play,
  RefreshCw,
  RotateCcw,
  Save,
  Settings,
  Shield,
  Square,
  X
} from "lucide-react";
import "./styles.css";

type TaskSummary = {
  id: string;
  title: string;
  description: string | null;
  workspace_path: string | null;
  task_type: string | null;
  constraints: string[];
  target_files: string[];
  provider_override: string | null;
  model_override: string | null;
  request_text: string;
  created_at: string;
  created_at_human: string;
};

type RunSummary = {
  id: string;
  task_id: string;
  status: string;
  current_stage: string;
  provider_name: string;
  request_id: string | null;
  retry_count: number;
  error_message: string | null;
  created_at: string;
  updated_at: string;
  created_at_human: string;
  updated_at_human: string;
  task: TaskSummary;
  latest_state?: StateSnapshot | null;
};

type EventItem = {
  id: number;
  event_type: string;
  message: string;
  payload_json: string | null;
  created_at: string;
};

type Artifact = {
  id: number;
  artifact_type: string;
  title: string;
  content: string;
  truncated: boolean;
  created_at: string;
};

type StateSnapshot = {
  id: number;
  stage: string;
  status: string;
  retry_count: number;
  payload_json: string;
  created_at: string;
};

type DiffResponse = {
  has_changes: boolean;
  changed_files: string[];
  diff_text: string;
  branch: string;
};

type WorkspaceFiles = {
  run_id: string;
  files: string[];
};

type WorkspaceFile = {
  run_id: string;
  path: string;
  content: string;
};

type RunHistoryCleanupResponse = {
  deleted_runs: number;
  deleted_tasks: number;
  cleaned_workspaces: number;
  kept_terminal_runs: number;
  message: string;
};

type BackupItem = {
  name: string;
  path: string;
  manifest_path: string;
};

type Health = {
  status: string;
};

type ProviderHealth = {
  provider: string;
  status: string;
  detail: string;
  model: string;
};

type RepositoryHealth = {
  path: string;
  branch: string;
  head_sha: string;
  dirty: boolean;
  remotes: string[];
};

type GithubHealth = {
  configured: boolean;
  detail: string;
};

type ConfigSummary = {
  app_env: string;
  model_provider: string;
  backup_root: string;
  worker_count: number;
  runtime?: Record<string, string | number>;
  repository?: unknown;
  github?: unknown;
};

type AppData = {
  health?: Health;
  provider?: ProviderHealth;
  repository?: RepositoryHealth;
  github?: GithubHealth;
  config?: ConfigSummary;
  runs: RunSummary[];
  backups: BackupItem[];
};

/** Matches `RunStage` in the API (approval, not awaiting_approval). */
const pipelineStageDefs: { id: string; label: string }[] = [
  { id: "intake", label: "Intake" },
  { id: "planner", label: "Planner" },
  { id: "architect", label: "Architect" },
  { id: "ui_designer", label: "UI designer" },
  { id: "coder", label: "Coder" },
  { id: "reviewer", label: "Reviewer" },
  { id: "tester", label: "Tester" },
  { id: "approval", label: "Approval" },
  { id: "done", label: "Done" }
];

function humanizeSnake(s: string): string {
  return s
    .split(/[_\s]+/)
    .filter(Boolean)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase())
    .join(" ");
}

function shouldShowArtifactTypeLabel(title: string, artifactType: string): boolean {
  const ti = title.toLowerCase().trim();
  const typeSlug = artifactType.toLowerCase().replace(/_/g, " ");
  if (ti.endsWith(typeSlug)) return false;
  const parts = artifactType.toLowerCase().split("_").filter((p) => p.length > 2);
  for (const p of parts) {
    if (ti.endsWith(p)) return false;
  }
  return true;
}

function formatTaskSecondaryText(task: TaskSummary): string {
  const desc = (task.description || "").trim();
  if (desc) return desc;
  const rt = (task.request_text || "").trim();
  const stripped = rt.replace(/^Title:\s*[^\n]+\s*\n\s*Description:\s*/i, "").trim();
  if (stripped && stripped !== rt) return stripped;
  return rt || "";
}

function shortRunId(id: string): string {
  return id.length > 12 ? `${id.slice(0, 8)}…` : id;
}

const nav = [
  { key: "dashboard", label: "Dashboard", href: "/ui", icon: LayoutDashboard },
  { key: "runs", label: "Runs", href: "/ui#runs", icon: Boxes },
  { key: "repository", label: "Repository", href: "/ui/repository", icon: GitBranch },
  { key: "provider", label: "Provider", href: "/ui/provider", icon: Activity },
  { key: "settings", label: "Settings", href: "/ui/settings", icon: Settings },
  { key: "backups", label: "Backups", href: "/ui/backups", icon: Archive }
];

function api<T>(path: string, init?: RequestInit): Promise<T> {
  return fetch(path, {
    credentials: "same-origin",
    headers: {
      "content-type": "application/json",
      ...(init?.headers || {})
    },
    ...init
  }).then(async (response) => {
    if (!response.ok) {
      const detail = await response.text();
      throw new Error(detail || `${response.status} ${response.statusText}`);
    }
    return response.json() as Promise<T>;
  });
}

function postForm(path: string, fields: Record<string, string>): Promise<Response> {
  const form = new FormData();
  Object.entries(fields).forEach(([key, value]) => form.append(key, value));
  return fetch(path, {
    method: "POST",
    credentials: "same-origin",
    body: form,
    redirect: "manual"
  });
}

function currentView() {
  const path = window.location.pathname;
  if (path.includes("/runs/")) return "run";
  if (path.endsWith("/repository")) return "repository";
  if (path.endsWith("/provider")) return "provider";
  if (path.endsWith("/settings")) return "settings";
  if (path.endsWith("/backups")) return "backups";
  return "dashboard";
}

function runIdFromPath() {
  const match = window.location.pathname.match(/\/ui\/runs\/([^/]+)/);
  return match ? decodeURIComponent(match[1]) : null;
}

function statusTone(value: string) {
  const lower = value.toLowerCase();
  if (["failed", "cancelled", "blocked", "unavailable", "invalid"].some((item) => lower.includes(item))) return "bad";
  if (["await", "review", "pending", "queued", "degraded"].some((item) => lower.includes(item))) return "warn";
  return "ok";
}

function App() {
  const [view, setView] = useState(currentView());
  const [data, setData] = useState<AppData>({ runs: [], backups: [] });
  const [run, setRun] = useState<RunSummary | null>(null);
  const [events, setEvents] = useState<EventItem[]>([]);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [snapshots, setSnapshots] = useState<StateSnapshot[]>([]);
  const [diff, setDiff] = useState<DiffResponse | null>(null);
  const [workspaceFiles, setWorkspaceFiles] = useState<string[]>([]);
  const [selectedFile, setSelectedFile] = useState("");
  const [fileContent, setFileContent] = useState("");
  const [notice, setNotice] = useState(new URLSearchParams(window.location.search).get("success") || "");
  const [error, setError] = useState(new URLSearchParams(window.location.search).get("error") || "");
  const [loading, setLoading] = useState(true);

  const loadGlobal = async () => {
    const [health, provider, repository, github, config, runs, backups] = await Promise.all([
      api<Health>("/api/health"),
      api<ProviderHealth>("/api/health/provider"),
      api<RepositoryHealth>("/api/health/repository"),
      api<GithubHealth>("/api/health/github"),
      api<ConfigSummary>("/api/config"),
      api<RunSummary[]>("/api/runs?limit=24"),
      api<BackupItem[]>("/api/backups")
    ]);
    setData({ health, provider, repository, github, config, runs, backups });
  };

  const loadRun = async (id: string) => {
    const [runData, historyData, artifactData, snapshotData, diffData, filesData] = await Promise.all([
      api<RunSummary>(`/api/runs/${id}`),
      api<EventItem[]>(`/api/runs/${id}/history`),
      api<Artifact[]>(`/api/runs/${id}/artifacts`),
      api<StateSnapshot[]>(`/api/runs/${id}/state-snapshots`),
      api<DiffResponse>(`/api/runs/${id}/diff`),
      api<WorkspaceFiles>(`/api/runs/${id}/workspace/files`)
    ]);
    setRun(runData);
    setEvents(historyData);
    setArtifacts(artifactData);
    setSnapshots(snapshotData);
    setDiff(diffData);
    setWorkspaceFiles(filesData.files);
    if (filesData.files.length && !selectedFile) {
      setSelectedFile(filesData.files[0]);
    }
  };

  useEffect(() => {
    const refresh = async () => {
      try {
        setError("");
        await loadGlobal();
        const nextView = currentView();
        setView(nextView);
        const id = runIdFromPath();
        if (id) {
          await loadRun(id);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to load console data.");
      } finally {
        setLoading(false);
      }
    };
    void refresh();
    const timer = window.setInterval(refresh, 5000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!run || !selectedFile) return;
    api<WorkspaceFile>(`/api/runs/${run.id}/workspace/file?path=${encodeURIComponent(selectedFile)}`)
      .then((payload) => setFileContent(payload.content))
      .catch(() => setFileContent(""));
  }, [run?.id, selectedFile]);

  const activeRun = runIdFromPath();

  return (
    <div className="app-shell">
      <aside className="rail">
        <a className="brand" href="/ui" onClick={() => setView("dashboard")}>
          <span className="brand-mark"><Code2 size={18} /></span>
          <span>
            <strong>AI Dev</strong>
            <small>Operator Console</small>
          </span>
        </a>
        <nav>
          {nav.map((item) => {
            const Icon = item.icon;
            const active = item.key === view || (item.key === "runs" && view === "run");
            return (
              <a className={active ? "active" : ""} href={item.href} key={item.key}>
                <Icon size={18} />
                <span>{item.label}</span>
              </a>
            );
          })}
        </nav>
        <div className="rail-footer">
          <StatusPill value={data.provider?.status || "loading"} />
          <a href="/ui/logout">Logout</a>
        </div>
      </aside>

      <main className="workspace">
        <header className="topbar">
          <div>
            <p className="eyebrow">Local-first delivery system</p>
            <h1>{titleForView(view, run)}</h1>
          </div>
          <div className="top-actions">
            <button className="icon-button" type="button" title="Refresh" onClick={() => window.location.reload()}>
              <RefreshCw size={17} />
            </button>
          </div>
        </header>

        {notice && <Banner tone="ok" message={notice} onClose={() => setNotice("")} />}
        {error && <Banner tone="bad" message={error} onClose={() => setError("")} />}
        {loading ? <LoadingPanel /> : null}

        {!loading && view === "dashboard" && (
          <Dashboard data={data} onNotice={setNotice} onError={setError} />
        )}
        {!loading && view === "repository" && <RepositoryView repository={data.repository} />}
        {!loading && view === "provider" && <ProviderView data={data} />}
        {!loading && view === "settings" && <SettingsView config={data.config} onNotice={setNotice} onError={setError} />}
        {!loading && view === "backups" && <BackupsView backups={data.backups} onNotice={setNotice} onError={setError} />}
        {!loading && view === "run" && activeRun && run && (
          <RunView
            run={run}
            events={events}
            artifacts={artifacts}
            snapshots={snapshots}
            diff={diff}
            workspaceFiles={workspaceFiles}
            selectedFile={selectedFile}
            fileContent={fileContent}
            onSelectFile={setSelectedFile}
            onFileContent={setFileContent}
            onNotice={setNotice}
            onError={setError}
          />
        )}
      </main>
    </div>
  );
}

function titleForView(view: string, run: RunSummary | null) {
  if (view === "run") return run ? run.task.title : "Run detail";
  if (view === "repository") return "Repository";
  if (view === "provider") return "Provider";
  if (view === "settings") return "Settings";
  if (view === "backups") return "Backups";
  return "Operator Console";
}

function StatusPill({ value }: { value: string }) {
  return <span className={`status ${statusTone(value)}`}>{value}</span>;
}

function Banner({ tone, message, onClose }: { tone: "ok" | "bad"; message: string; onClose: () => void }) {
  return (
    <section className={`banner ${tone}`}>
      <span>{message}</span>
      <button className="icon-button" type="button" onClick={onClose}><X size={16} /></button>
    </section>
  );
}

function LoadingPanel() {
  return (
    <section className="panel center">
      <Loader2 className="spin" size={22} />
      <span>Loading console state</span>
    </section>
  );
}

function Dashboard({ data, onNotice, onError }: { data: AppData; onNotice: (message: string) => void; onError: (message: string) => void }) {
  const lanes = useMemo(() => groupRuns(data.runs), [data.runs]);
  const activeCount = lanes.Active.length + lanes.Review.length;
  const issueCount = lanes.Blocked.length;
  const clearTerminalHistory = async () => {
    try {
      const result = await api<RunHistoryCleanupResponse>(
        "/api/runs/clear-terminal-history?keep_latest=4&cleanup_workspaces=true",
        { method: "POST", body: "{}" }
      );
      onNotice(result.message);
      window.location.reload();
    } catch (err) {
      onError(err instanceof Error ? err.message : "Run history cleanup failed.");
    }
  };
  return (
    <div className="stack">
      <section className="health-grid">
        <Metric icon={<Database />} label="API" value={data.health?.status || "unknown"} />
        <Metric icon={<Activity />} label="Provider" value={data.provider?.status || "unknown"} />
        <Metric icon={<GitBranch />} label="Branch" value={data.repository?.branch || "unknown"} />
        <Metric icon={<Shield />} label="GitHub" value={data.github?.configured ? "configured" : "missing"} />
      </section>
      <section className="dashboard-grid">
        <TaskComposer onNotice={onNotice} onError={onError} />
        <section className="panel">
          <div className="panel-head">
            <div>
              <p className="eyebrow">Repository</p>
              <h2>{data.repository?.branch || "No branch detected"}</h2>
            </div>
            <GitBranch size={20} />
          </div>
          <InfoRows rows={[
            ["Path", data.repository?.path || "-"],
            ["Head", data.repository?.head_sha || "-"],
            ["Dirty", String(data.repository?.dirty ?? "-")]
          ]} />
        </section>
      </section>
      <section className="panel" id="runs">
        <div className="panel-head">
          <div>
            <p className="eyebrow">Run board</p>
            <h2>Agent task kanban</h2>
          </div>
          <div className="panel-actions">
            <span className="status ok">{activeCount} active</span>
            <span className={`status ${issueCount ? "bad" : "ok"}`}>{issueCount} issues</span>
            <button className="ghost compact" type="button" onClick={clearTerminalHistory}>
              <Archive size={16} /> Clear terminal history
            </button>
          </div>
        </div>
        <div className="kanban">
          {Object.entries(lanes).map(([lane, runs]) => (
            <div className="lane" key={lane}>
              <div className="lane-title">
                <span>{lane}</span>
                <strong>{runs.length}</strong>
              </div>
              {runs.length === 0 && <div className="lane-empty">No runs</div>}
              {runs.map((item) => <RunCard run={item} key={item.id} />)}
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

function groupRuns(runs: RunSummary[]) {
  const groups: Record<string, RunSummary[]> = {
    Active: [],
    Review: [],
    Blocked: [],
    Complete: []
  };
  runs.forEach((run) => {
    if (["pending", "queued", "running"].includes(run.status)) groups.Active.push(run);
    else if (["awaiting_approval", "review_required"].includes(run.status)) groups.Review.push(run);
    else if (["blocked", "failed", "cancelled"].includes(run.status)) groups.Blocked.push(run);
    else groups.Complete.push(run);
  });
  return groups;
}

function Metric({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <section className="metric-card">
      <div className="metric-icon">{icon}</div>
      <span>{label}</span>
      <strong>{value}</strong>
    </section>
  );
}

function TaskComposer({ onNotice, onError }: { onNotice: (message: string) => void; onError: (message: string) => void }) {
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      const stageModelsRaw = String(form.get("stage_models_json") || "").trim();
      let stage_models: Record<string, string> | null = null;
      if (stageModelsRaw) {
        try {
          const parsed = JSON.parse(stageModelsRaw) as Record<string, string>;
          stage_models = typeof parsed === "object" && parsed !== null ? parsed : null;
        } catch {
          throw new Error("stage_models_json must be valid JSON object, e.g. {\"coder\":\"my-model-id\"}");
        }
      }
      const created = await api<{ run_id: string }>("/api/tasks", {
        method: "POST",
        body: JSON.stringify({
          title: String(form.get("title") || ""),
          request_text: String(form.get("request_text") || ""),
          workspace_path: String(form.get("workspace_path") || "") || null,
          task_type: String(form.get("task_type") || "") || null,
          target_files: splitCsv(String(form.get("target_files") || "")),
          constraints: splitCsv(String(form.get("constraints") || "")),
          provider: String(form.get("provider") || "") || null,
          model: String(form.get("model") || "") || null,
          source_repo: String(form.get("source_repo") || "") || null,
          use_scout: form.get("use_scout") === "on",
          stage_models
        })
      });
      onNotice(`Task created: ${created.run_id}`);
      window.history.replaceState({}, "", `/ui/runs/${created.run_id}`);
      window.location.assign(`/ui/runs/${created.run_id}`);
    } catch (err) {
      onError(err instanceof Error ? err.message : "Task creation failed.");
    }
  };

  return (
    <section className="panel">
      <div className="panel-head">
        <div>
          <p className="eyebrow">New task</p>
          <h2>Start an agent run</h2>
        </div>
        <Play size={20} />
      </div>
      <form className="form-grid" onSubmit={submit}>
        <input name="title" placeholder="Run title" required />
        <input name="workspace_path" placeholder="Workspace path (optional)" />
        <div className="two-col">
          <input name="task_type" placeholder="Task type" />
          <input name="provider" placeholder="Provider" />
        </div>
        <input name="model" placeholder="Model override" />
        <input name="source_repo" placeholder="Source repo path or URL (optional; requires ALLOWED_GIT_HOSTS for remotes)" />
        <label className="muted" style={{ display: "flex", gap: "8px", alignItems: "center" }}>
          <input type="checkbox" name="use_scout" /> Use read-only scout preamble for planner
        </label>
        <textarea name="stage_models_json" placeholder='Optional per-stage models JSON, e.g. {"coder":"model-id"}' rows={2} />
        <input name="target_files" placeholder="Target files, comma-separated" />
        <input name="constraints" placeholder="Constraints, comma-separated" />
        <textarea name="request_text" placeholder="Describe the implementation task." required />
        <button type="submit"><Play size={16} /> Start Run</button>
      </form>
    </section>
  );
}

function splitCsv(value: string) {
  return value.split(",").map((item) => item.trim()).filter(Boolean);
}

function RunCard({ run }: { run: RunSummary }) {
  return (
    <a className="run-card" href={`/ui/runs/${run.id}`}>
      <div className="run-card-top">
        <StatusPill value={run.status} />
        <ChevronRight size={16} />
      </div>
      <strong>{run.task.title}</strong>
      <span className="muted" title={run.id}>Run {shortRunId(run.id)}</span>
      <div className="chip-row">
        <span>{humanizeSnake(run.current_stage)}</span>
        <span>{run.provider_name}</span>
        <span>retries {run.retry_count}</span>
        <span>{run.created_at_human}</span>
      </div>
      {run.error_message ? <p className="run-error">{run.error_message}</p> : null}
    </a>
  );
}

function RepositoryView({ repository }: { repository?: RepositoryHealth }) {
  return (
    <section className="panel">
      <div className="panel-head">
        <div>
          <p className="eyebrow">Managed checkout</p>
          <h2>{repository?.branch || "Repository"}</h2>
        </div>
        <GitBranch size={22} />
      </div>
      <InfoRows rows={[
        ["Path", repository?.path || "-"],
        ["Branch", repository?.branch || "-"],
        ["Head SHA", repository?.head_sha || "-"],
        ["Dirty", String(repository?.dirty ?? "-")],
        ["Remotes", repository?.remotes?.join(", ") || "No remotes configured"]
      ]} />
    </section>
  );
}

function ProviderView({ data }: { data: AppData }) {
  return (
    <div className="dashboard-grid">
      <section className="panel">
        <div className="panel-head">
          <div>
            <p className="eyebrow">LM Studio</p>
            <h2>{data.provider?.model || "Provider"}</h2>
          </div>
          <StatusPill value={data.provider?.status || "unknown"} />
        </div>
        <InfoRows rows={[
          ["Provider", data.provider?.provider || "-"],
          ["Detail", data.provider?.detail || "-"],
          ["Base URL", String(data.config?.runtime?.lmstudio_base_url || "-")],
          ["Timeout", `${String(data.config?.runtime?.provider_timeout_seconds || "-")} seconds`]
        ]} />
      </section>
      <section className="panel">
        <div className="panel-head">
          <div>
            <p className="eyebrow">GitHub</p>
            <h2>{data.github?.configured ? "Configured" : "Missing"}</h2>
          </div>
          <Shield size={22} />
        </div>
        <p className="muted">{data.github?.detail || "No GitHub status available."}</p>
      </section>
    </div>
  );
}

function SettingsView({ config, onNotice, onError }: { config?: ConfigSummary; onNotice: (message: string) => void; onError: (message: string) => void }) {
  const runtime = config?.runtime || {};
  const [modelIds, setModelIds] = useState<string[]>([]);
  const [modelsError, setModelsError] = useState<string | null>(null);

  const refreshModels = async () => {
    try {
      const payload = await api<{ models: { id: string }[]; error: string | null }>("/api/config/lmstudio/models");
      setModelsError(payload.error);
      setModelIds((payload.models || []).map((m) => m.id).filter(Boolean));
    } catch (err) {
      setModelsError(err instanceof Error ? err.message : "Failed to load models");
      setModelIds([]);
    }
  };

  useEffect(() => {
    void refreshModels();
  }, [String(runtime.lmstudio_base_url), String(runtime.lmstudio_api_key)]);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const fields = Object.fromEntries(Array.from(form.entries()).map(([key, value]) => [key, String(value)]));
    fields.APP_API_TOKEN = "__UNCHANGED__";
    try {
      await postForm("/ui/settings", fields);
      onNotice("Settings saved.");
    } catch (err) {
      onError(err instanceof Error ? err.message : "Settings save failed.");
    }
  };

  return (
    <section className="panel">
      <div className="panel-head">
        <div>
          <p className="eyebrow">Runtime settings</p>
          <h2>Local configuration</h2>
        </div>
        <Settings size={22} />
      </div>
      <form className="settings-grid" onSubmit={submit}>
        <datalist id="lmstudio-model-ids">
          {modelIds.map((id) => (
            <option value={id} key={id} />
          ))}
        </datalist>
        {modelsError ? <p className="muted">Model list: {modelsError}</p> : null}
        <div className="two-col">
          <button className="ghost compact" type="button" onClick={() => void refreshModels()}>
            <RefreshCw size={16} /> Refresh LM Studio models
          </button>
        </div>
        <input name="APP_HOST" defaultValue={String(runtime.app_host || "0.0.0.0")} placeholder="APP_HOST" />
        <input name="APP_PORT" defaultValue={String(runtime.app_port || "8400")} placeholder="APP_PORT" />
        <input name="APP_API_TOKEN" type="hidden" value="__UNCHANGED__" readOnly />
        <input name="WORKER_COUNT" defaultValue={String(config?.worker_count ?? 1)} placeholder="WORKER_COUNT" />
        <input name="LMSTUDIO_BASE_URL" defaultValue={String(runtime.lmstudio_base_url || "")} placeholder="LMSTUDIO_BASE_URL" />
        <input name="LMSTUDIO_MODEL" list="lmstudio-model-ids" defaultValue={String(runtime.lmstudio_model || "")} placeholder="LMSTUDIO_MODEL" />
        <input name="LMSTUDIO_MODEL_PLANNER" list="lmstudio-model-ids" defaultValue={String(runtime.lmstudio_model_planner || "")} placeholder="LMSTUDIO_MODEL_PLANNER" />
        <input name="LMSTUDIO_MODEL_ARCHITECT" list="lmstudio-model-ids" defaultValue={String(runtime.lmstudio_model_architect || "")} placeholder="LMSTUDIO_MODEL_ARCHITECT" />
        <input name="LMSTUDIO_MODEL_UI_DESIGNER" list="lmstudio-model-ids" defaultValue={String(runtime.lmstudio_model_ui_designer || "")} placeholder="LMSTUDIO_MODEL_UI_DESIGNER" />
        <input name="LMSTUDIO_MODEL_CODER" list="lmstudio-model-ids" defaultValue={String(runtime.lmstudio_model_coder || "")} placeholder="LMSTUDIO_MODEL_CODER" />
        <input name="LMSTUDIO_MODEL_REVIEWER" list="lmstudio-model-ids" defaultValue={String(runtime.lmstudio_model_reviewer || "")} placeholder="LMSTUDIO_MODEL_REVIEWER" />
        <input name="LMSTUDIO_MODEL_TESTER" list="lmstudio-model-ids" defaultValue={String(runtime.lmstudio_model_tester || "")} placeholder="LMSTUDIO_MODEL_TESTER" />
        <input name="LMSTUDIO_MODEL_SUPERVISOR" list="lmstudio-model-ids" defaultValue={String(runtime.lmstudio_model_supervisor || "")} placeholder="LMSTUDIO_MODEL_SUPERVISOR" />
        <input name="LMSTUDIO_API_KEY" defaultValue={String(runtime.lmstudio_api_key || "")} placeholder="LMSTUDIO_API_KEY" />
        <input name="PROVIDER_TIMEOUT_SECONDS" defaultValue={String(runtime.provider_timeout_seconds || "60")} placeholder="PROVIDER_TIMEOUT_SECONDS" />
        <input name="GIT_CLONE_TIMEOUT_SECONDS" defaultValue={String(runtime.git_clone_timeout_seconds || "300")} placeholder="GIT_CLONE_TIMEOUT_SECONDS" />
        <input name="SOURCE_REPO_PATH" defaultValue={String(runtime.source_repo_path || "")} placeholder="SOURCE_REPO_PATH" />
        <input name="ALLOWED_GIT_HOSTS" defaultValue={String(runtime.allowed_git_hosts || "")} placeholder="ALLOWED_GIT_HOSTS" />
        <input name="ALLOWED_SOURCE_REPO_ROOTS" defaultValue={String(runtime.allowed_source_repo_roots || "")} placeholder="ALLOWED_SOURCE_REPO_ROOTS" />
        <input name="WORKSPACE_ROOT" defaultValue={String(runtime.workspace_root || "")} placeholder="WORKSPACE_ROOT" />
        <input name="BACKUP_ROOT" defaultValue={String(runtime.backup_root || "")} placeholder="BACKUP_ROOT" />
        <input name="GIT_AUTHOR_NAME" defaultValue={String(runtime.git_author_name || "")} placeholder="GIT_AUTHOR_NAME" />
        <input name="GIT_AUTHOR_EMAIL" defaultValue={String(runtime.git_author_email || "")} placeholder="GIT_AUTHOR_EMAIL" />
        <input name="LOG_LEVEL" defaultValue={String(runtime.log_level || "INFO")} placeholder="LOG_LEVEL" />
        <input name="USE_SCOUT_STAGE" defaultValue={String(runtime.use_scout_stage ?? "false")} placeholder="USE_SCOUT_STAGE" />
        <input name="PLAYBOOK_SUPERVISOR_ENABLED" defaultValue={String(runtime.playbook_supervisor_enabled ?? "false")} placeholder="PLAYBOOK_SUPERVISOR_ENABLED" />
        <input name="PLAYBOOK_REQUIRE_HUMAN_CONFIRM" defaultValue={String(runtime.playbook_require_human_confirm ?? "true")} placeholder="PLAYBOOK_REQUIRE_HUMAN_CONFIRM" />
        <input name="PLAYBOOK_SUPERVISOR_SYSTEM_PROMPT_PATH" defaultValue={String(runtime.playbook_supervisor_system_prompt_path || "app/agents/prompts/playbook_supervisor.md")} placeholder="PLAYBOOK_SUPERVISOR_SYSTEM_PROMPT_PATH" />
        <button type="submit"><Save size={16} /> Save Settings</button>
      </form>
    </section>
  );
}

function BackupsView({ backups, onNotice, onError }: { backups: BackupItem[]; onNotice: (message: string) => void; onError: (message: string) => void }) {
  const createBackup = async () => {
    try {
      await api("/api/backups/run", { method: "POST", body: "{}" });
      onNotice("Backup created.");
      window.location.reload();
    } catch (err) {
      onError(err instanceof Error ? err.message : "Backup failed.");
    }
  };
  const rehearse = async (manifestPath: string) => {
    try {
      const params = new URLSearchParams({ manifest_path: manifestPath });
      await fetch(`/api/backups/restore-rehearsal?${params.toString()}`, {
        method: "POST",
        credentials: "same-origin"
      });
      onNotice("Restore rehearsal completed.");
    } catch (err) {
      onError(err instanceof Error ? err.message : "Restore rehearsal failed.");
    }
  };
  return (
    <section className="panel">
      <div className="panel-head">
        <div>
          <p className="eyebrow">Recovery</p>
          <h2>Backups</h2>
        </div>
        <button type="button" onClick={createBackup}><Archive size={16} /> Create Backup</button>
      </div>
      <div className="list">
        {backups.length === 0 && <div className="empty">No backups created yet.</div>}
        {backups.map((backup) => (
          <div className="list-row" key={backup.path}>
            <div>
              <strong>{backup.name}</strong>
              <span>{backup.manifest_path}</span>
            </div>
            <button className="ghost" type="button" onClick={() => rehearse(backup.manifest_path)}>
              <RotateCcw size={16} /> Rehearse
            </button>
          </div>
        ))}
      </div>
    </section>
  );
}

function RunView(props: {
  run: RunSummary;
  events: EventItem[];
  artifacts: Artifact[];
  snapshots: StateSnapshot[];
  diff: DiffResponse | null;
  workspaceFiles: string[];
  selectedFile: string;
  fileContent: string;
  onSelectFile: (path: string) => void;
  onFileContent: (content: string) => void;
  onNotice: (message: string) => void;
  onError: (message: string) => void;
}) {
  const { run, events, artifacts, snapshots, diff, workspaceFiles, selectedFile, fileContent, onSelectFile, onFileContent, onNotice, onError } = props;

  useEffect(() => {
    const prev = document.title;
    document.title = `${run.task.title} · ${shortRunId(run.id)}`;
    return () => {
      document.title = prev;
    };
  }, [run.id, run.task.title]);

  const act = async (action: string) => {
    try {
      const path = action === "cleanup" ? `/api/runs/${run.id}/cleanup-workspace` : `/api/runs/${run.id}/${action}`;
      await api(path, { method: "POST", body: action === "cleanup" ? "{}" : JSON.stringify({ note: `Operator ${action}` }) });
      onNotice(`${action} requested.`);
      window.location.reload();
    } catch (err) {
      onError(err instanceof Error ? err.message : `${action} failed.`);
    }
  };
  const saveFile = async () => {
    if (!selectedFile) return;
    try {
      await api(`/api/runs/${run.id}/workspace/file`, {
        method: "POST",
        body: JSON.stringify({ path: selectedFile, content: fileContent })
      });
      onNotice("File saved.");
    } catch (err) {
      onError(err instanceof Error ? err.message : "File save failed.");
    }
  };
  return (
    <div className="stack">
      <section className="panel">
        <div className="run-hero">
          <div>
            <p className="eyebrow">Run detail</p>
            <h2>{run.task.title}</h2>
            <p className="muted">
              <span title={run.id}>Run ID {run.id}</span>
            </p>
            <p className="muted">{formatTaskSecondaryText(run.task)}</p>
          </div>
          <StatusPill value={run.status} />
        </div>
        <div className="chip-row run-time-row">
          <span>Task created: {run.task.created_at_human}</span>
          <span>Run created: {run.created_at_human}</span>
          <span>Updated: {run.updated_at_human}</span>
          <span>Retries: {run.retry_count}</span>
        </div>
        {run.error_message ? (
          <div className="error-panel">
            <strong>Current issue</strong>
            <span>{run.error_message}</span>
          </div>
        ) : null}
        <div className="pipeline">
          {pipelineStageDefs.map(({ id, label }) => {
            const active = id === run.current_stage;
            return (
              <div className={active ? "stage active" : "stage"} key={id}>
                <CircleDot size={15} />
                <span>{label}</span>
              </div>
            );
          })}
        </div>
        <div className="action-row">
          {run.status === "awaiting_approval" ? (
            <>
              <button type="button" onClick={() => act("approve")}><Check size={16} /> Approve</button>
              <button className="warn" type="button" onClick={() => act("reject")}><X size={16} /> Reject</button>
            </>
          ) : null}
          <button className="ghost" type="button" onClick={() => act("retry")}><RefreshCw size={16} /> Retry</button>
          <button className="danger" type="button" onClick={() => act("abort")}><Square size={16} /> Abort</button>
          <button className="ghost" type="button" onClick={() => act("cleanup")}><Archive size={16} /> Cleanup</button>
        </div>
      </section>

      <section className="detail-grid">
        <PanelList title="Timeline" icon={<History />} items={events.map((item) => [item.event_type, item.message])} />
        <PanelList title="State Snapshots" icon={<Activity />} items={snapshots.slice(-8).reverse().map((item) => [`${item.stage} / ${item.status}`, `retry_count=${item.retry_count}`])} />
      </section>

      <section className="detail-grid">
        <section className="panel">
          <div className="panel-head"><h2>Artifacts</h2><FileText size={20} /></div>
          <div className="list">
            {artifacts.length === 0 && <div className="empty">No artifacts recorded yet.</div>}
            {artifacts.map((artifact) => (
              <details className="artifact" key={artifact.id}>
                <summary>
                  {artifact.title}
                  {shouldShowArtifactTypeLabel(artifact.title, artifact.artifact_type) ? (
                    <span className="muted"> {humanizeSnake(artifact.artifact_type)}</span>
                  ) : null}
                </summary>
                <pre>{artifact.content}</pre>
              </details>
            ))}
          </div>
        </section>
        <section className="panel">
          <div className="panel-head">
            <h2>Workspace Diff</h2>
            <StatusPill value={diff?.has_changes ? "changes detected" : "clean"} />
          </div>
          <div className="chip-row">{diff?.changed_files.map((file) => <span key={file}>{file}</span>)}</div>
          <pre>{diff?.diff_text || "No local diff detected."}</pre>
        </section>
      </section>

      <section className="panel">
        <div className="panel-head"><h2>Workspace Files</h2><Code2 size={20} /></div>
        <div className="file-editor">
          <div className="file-list">
            {workspaceFiles.length === 0 && <div className="empty">No files available.</div>}
            {workspaceFiles.map((file) => (
              <button className={file === selectedFile ? "selected" : ""} type="button" onClick={() => onSelectFile(file)} key={file}>
                {file}
              </button>
            ))}
          </div>
          <div className="editor-pane">
            <textarea value={fileContent} onChange={(event) => onFileContent(event.target.value)} />
            <button type="button" onClick={saveFile}><Save size={16} /> Save File</button>
          </div>
        </div>
      </section>
    </div>
  );
}

function PanelList({ title, icon, items }: { title: string; icon: React.ReactNode; items: string[][] }) {
  return (
    <section className="panel">
      <div className="panel-head"><h2>{title}</h2>{icon}</div>
      <div className="list">
        {items.length === 0 && <div className="empty">No records yet.</div>}
        {items.map(([titleValue, detail], index) => (
          <div className="list-row" key={`${titleValue}-${index}`}>
            <div>
              <strong>{titleValue}</strong>
              <span>{detail}</span>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function InfoRows({ rows }: { rows: string[][] }) {
  return (
    <div className="info-rows">
      {rows.map(([label, value]) => (
        <div key={label}>
          <span>{label}</span>
          <strong>{value}</strong>
        </div>
      ))}
    </div>
  );
}

createRoot(document.getElementById("root") as HTMLElement).render(<App />);
