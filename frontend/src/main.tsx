import React, { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Activity,
  Archive,
  Boxes,
  Check,
  ChevronRight,
  CircleDot,
  Code2,
  Copy,
  Database,
  FileText,
  FolderKanban,
  GitBranch,
  HelpCircle,
  History,
  LayoutDashboard,
  MessageSquare,
  Loader2,
  Play,
  RefreshCw,
  RotateCcw,
  Save,
  Send,
  Settings,
  Shield,
  Square,
  X
} from "lucide-react";
import { TaskComposer } from "./components/TaskComposer";
import { api, postForm } from "./http";
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
  login?: string;
  repo_full_name?: string;
  repo_html_url?: string;
  repo_clone_url?: string;
  repo_default_branch?: string;
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
  projects: ProjectSummary[];
  sourceRepos: SavedSourceRepo[];
};

type ProjectSummary = {
  id: string;
  name: string;
  slug: string;
  status: string;
  app_type: string | null;
  source_repo_spec: string | null;
  validation_profile: string;
  readiness_score: number;
  open_questions: number;
  build_items: number;
  active_runs: number;
  created_at: string;
  updated_at: string;
};

type ProjectMessage = {
  id: number;
  project_id: string;
  role: string;
  message_type: string;
  content: string;
  structured_json: string;
  created_at: string;
};

type ProjectQuestion = {
  id: number;
  project_id: string;
  key: string;
  question: string;
  reason: string;
  answer_type: string;
  options: string[];
  status: string;
  answer: string | null;
  created_at: string;
  answered_at: string | null;
};

type ProjectBuildItem = {
  id: number;
  project_id: string;
  parent_id: number | null;
  title: string;
  description: string;
  item_type: string;
  status: string;
  target_files: string[];
  depends_on: string[];
  assigned_role: string;
  run_id: string | null;
  created_at: string;
  updated_at: string;
};

type ProjectDetail = ProjectSummary & {
  initial_requirements: string;
  target_stack: Record<string, string>;
  messages: ProjectMessage[];
  questions: ProjectQuestion[];
  build_items_detail: ProjectBuildItem[];
};

type ProjectCommandResponse = {
  project: ProjectDetail;
  message: string;
  action: string;
  run_id: string | null;
  run_ids: string[];
};

type SavedSourceRepo = {
  id: string;
  label: string;
  source_repo_spec: string;
  kind: string;
  valid: boolean;
  repo_key: string;
  status: string;
  branch: string | null;
  head_sha: string | null;
  remotes: string[];
  dirty: boolean | null;
  created_at: string;
  updated_at: string;
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
  { key: "projects", label: "Projects", href: "/ui/projects", icon: FolderKanban },
  { key: "runs", label: "Runs", href: "/ui#runs", icon: Boxes },
  { key: "repository", label: "Repository", href: "/ui/repository", icon: GitBranch },
  { key: "provider", label: "Provider", href: "/ui/provider", icon: Activity },
  { key: "settings", label: "Settings", href: "/ui/settings", icon: Settings },
  { key: "backups", label: "Backups", href: "/ui/backups", icon: Archive }
];

function currentView() {
  const path = window.location.pathname;
  if ((path === "/ui" || path === "/ui/") && window.location.hash === "#runs") return "runs";
  if (path.includes("/projects")) return "projects";
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

function projectIdFromPath() {
  const match = window.location.pathname.match(/\/ui\/projects\/([^/]+)/);
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
  const [data, setData] = useState<AppData>({ runs: [], backups: [], projects: [], sourceRepos: [] });
  const [project, setProject] = useState<ProjectDetail | null>(null);
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

  const loadGlobal = useCallback(async () => {
    const [health, provider, repository, github, config, runs, backups, projects, sourceRepos] = await Promise.all([
      api<Health>("/api/health"),
      api<ProviderHealth>("/api/health/provider"),
      api<RepositoryHealth>("/api/health/repository"),
      api<GithubHealth>("/api/health/github"),
      api<ConfigSummary>("/api/config"),
      api<RunSummary[]>("/api/runs?limit=24"),
      api<BackupItem[]>("/api/backups"),
      api<ProjectSummary[]>("/api/projects"),
      api<SavedSourceRepo[]>("/api/source-repos")
    ]);
    setData({ health, provider, repository, github, config, runs, backups, projects, sourceRepos });
  }, []);

  const loadRun = useCallback(async (id: string) => {
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
    setSelectedFile((prev) => {
      if (filesData.files.includes(prev)) return prev;
      return filesData.files[0] ?? "";
    });
  }, []);

  const loadProject = useCallback(async (id: string) => {
    const projectData = await api<ProjectDetail>(`/api/projects/${id}`);
    setProject(projectData);
  }, []);

  const clearRunDetail = useCallback(() => {
    setRun(null);
    setEvents([]);
    setArtifacts([]);
    setSnapshots([]);
    setDiff(null);
    setWorkspaceFiles([]);
    setSelectedFile("");
    setFileContent("");
  }, []);

  const clearProjectDetail = useCallback(() => {
    setProject(null);
  }, []);

  const refreshAll = useCallback(
    async (options?: { initial?: boolean }) => {
      const initial = options?.initial ?? false;
      try {
        if (initial) setLoading(true);
        else setError("");
        await loadGlobal();
        const nextView = currentView();
        setView(nextView);
        const id = runIdFromPath();
        const projectId = projectIdFromPath();
        if (id) {
          await loadRun(id);
        } else {
          clearRunDetail();
        }
        if (projectId) {
          await loadProject(projectId);
        } else if (nextView !== "projects") {
          clearProjectDetail();
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to load console data.");
      } finally {
        if (initial) setLoading(false);
      }
    },
    [loadGlobal, loadRun, loadProject, clearRunDetail, clearProjectDetail]
  );

  useEffect(() => {
    void refreshAll({ initial: true });
    const timer = window.setInterval(() => {
      void refreshAll();
    }, 5000);
    const onPopState = () => {
      void refreshAll();
    };
    window.addEventListener("popstate", onPopState);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener("popstate", onPopState);
    };
  }, [refreshAll]);

  useEffect(() => {
    if (!run || !selectedFile) return;
    api<WorkspaceFile>(`/api/runs/${run.id}/workspace/file?path=${encodeURIComponent(selectedFile)}`)
      .then((payload) => setFileContent(payload.content))
      .catch(() => setFileContent(""));
  }, [run?.id, selectedFile]);

  const activeRun = runIdFromPath();

  useEffect(() => {
    if (view !== "runs" || loading) return;
    const section = document.getElementById("runs");
    if (section) section.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [view, loading]);

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
            const active = item.key === view || (item.key === "runs" && (view === "run" || view === "runs"));
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
          <div className="rail-footer-links">
            <a className="rail-link" href="/ui/login">Switch operator</a>
            <a href="/ui/logout">Logout</a>
          </div>
        </div>
      </aside>

      <main className="workspace">
        <header className="topbar">
          <div>
            <p className="eyebrow">Local-first delivery system</p>
            <h1>{titleForView(view, run)}</h1>
          </div>
          <div className="top-actions">
            <button className="icon-button" type="button" title="Refresh console data" onClick={() => void refreshAll()}>
              <RefreshCw size={17} />
            </button>
          </div>
        </header>

        {notice && <Banner tone="ok" message={notice} onClose={() => setNotice("")} />}
        {error && <Banner tone="bad" message={error} onClose={() => setError("")} />}
        {loading ? <LoadingPanel /> : null}

        {!loading && (view === "dashboard" || view === "runs") && (
          <Dashboard
            data={data}
            onNotice={setNotice}
            onError={setError}
            onRefresh={refreshAll}
            onRunCreated={async (runId) => {
              window.history.pushState({}, "", `/ui/runs/${runId}`);
              setView("run");
              await refreshAll();
            }}
          />
        )}
        {!loading && view === "projects" && (
          <ProjectsView
            projects={data.projects}
            sourceRepos={data.sourceRepos}
            project={project}
            onNotice={setNotice}
            onError={setError}
            onRefresh={refreshAll}
            onOpenProject={async (projectId) => {
              window.history.pushState({}, "", `/ui/projects/${projectId}`);
              setView("projects");
              await refreshAll();
            }}
          />
        )}
        {!loading && view === "repository" && <RepositoryView repository={data.repository} />}
        {!loading && view === "provider" && <ProviderView data={data} />}
        {!loading && view === "settings" && <SettingsView config={data.config} onNotice={setNotice} onError={setError} />}
        {!loading && view === "backups" && (
          <BackupsView backups={data.backups} onNotice={setNotice} onError={setError} onRefresh={refreshAll} />
        )}
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
            onRefresh={refreshAll}
          />
        )}
      </main>
    </div>
  );
}

function titleForView(view: string, run: RunSummary | null) {
  if (view === "run") return run ? run.task.title : "Run detail";
  if (view === "runs") return "Runs";
  if (view === "projects") return "Projects";
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

function ProjectsView({
  projects,
  sourceRepos,
  project,
  onNotice,
  onError,
  onRefresh,
  onOpenProject
}: {
  projects: ProjectSummary[];
  sourceRepos: SavedSourceRepo[];
  project: ProjectDetail | null;
  onNotice: (message: string) => void;
  onError: (message: string) => void;
  onRefresh: () => Promise<void>;
  onOpenProject: (projectId: string) => Promise<void>;
}) {
  const [projectSourceRepo, setProjectSourceRepo] = useState("");
  const [projectSourceMode, setProjectSourceMode] = useState<"default" | "saved" | "custom">("default");
  const [loadRepoSpec, setLoadRepoSpec] = useState("");
  const [loadRepoLabel, setLoadRepoLabel] = useState("");

  const saveSourceRepo = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const spec = loadRepoSpec.trim();
    if (!spec) return;
    try {
      const saved = await api<SavedSourceRepo>("/api/source-repos", {
        method: "POST",
        body: JSON.stringify({
          source_repo: spec,
          label: loadRepoLabel.trim() || null
        })
      });
      setProjectSourceMode("saved");
      setProjectSourceRepo(saved.source_repo_spec);
      setLoadRepoSpec("");
      setLoadRepoLabel("");
      onNotice(`Repo saved: ${saved.label}`);
      await onRefresh();
    } catch (err) {
      onError(err instanceof Error ? err.message : "Repo save failed.");
    }
  };

  const createProject = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      const created = await api<ProjectDetail>("/api/projects", {
        method: "POST",
        body: JSON.stringify({
          name: String(form.get("name") || ""),
          initial_requirements: String(form.get("initial_requirements") || ""),
          source_repo: projectSourceRepo.trim() || null,
          app_type: String(form.get("app_type") || "") || null,
          validation_profile: String(form.get("validation_profile") || "python")
        })
      });
      onNotice("Project created. Intake questions are ready.");
      await onOpenProject(created.id);
    } catch (err) {
      onError(err instanceof Error ? err.message : "Project creation failed.");
    }
  };

  return (
    <div className="project-workbench">
      <aside className="project-sidebar">
        <section className="panel">
          <div className="panel-head">
            <div>
              <p className="eyebrow">Load repo</p>
              <h2>Saved sources</h2>
            </div>
            <GitBranch size={20} />
          </div>
          <form className="form-grid compact-form repo-load-form" onSubmit={saveSourceRepo}>
            <input
              value={loadRepoLabel}
              onChange={(event) => setLoadRepoLabel(event.target.value)}
              placeholder="Repo label, optional"
            />
            <input
              value={loadRepoSpec}
              onChange={(event) => setLoadRepoSpec(event.target.value)}
              placeholder="Local path or remote URL"
              required
            />
            <button type="submit"><Save size={16} /> Save Repo</button>
          </form>
          {sourceRepos.length > 0 ? (
            <div className="saved-repo-list">
              {sourceRepos.map((repo) => (
                <button
                  className={projectSourceRepo === repo.source_repo_spec ? "saved-repo-item active" : "saved-repo-item"}
                  type="button"
                  key={repo.id}
                  onClick={() => {
                    setProjectSourceMode("saved");
                    setProjectSourceRepo(repo.source_repo_spec);
                  }}
                >
                  <strong>{repo.label}</strong>
                  <span>{repo.valid === false ? "invalid" : repo.kind}{repo.branch ? ` · ${repo.branch}` : ""}{repo.dirty ? " · dirty" : ""}</span>
                </button>
              ))}
            </div>
          ) : (
            <div className="empty compact-empty">No saved repos.</div>
          )}
        </section>
        <section className="panel">
          <div className="panel-head">
            <div>
              <p className="eyebrow">Projects</p>
              <h2>App workspaces</h2>
            </div>
            <FolderKanban size={20} />
          </div>
          <form className="form-grid compact-form" onSubmit={createProject}>
            <input name="name" placeholder="Project name" required />
            <input name="app_type" placeholder="App type, e.g. SaaS, internal tool" />
            <select
              value={
                projectSourceMode === "custom"
                  ? "__custom__"
                  : projectSourceMode === "saved"
                    ? projectSourceRepo
                    : ""
              }
              onChange={(event) => {
                const value = event.target.value;
                if (value === "__custom__") {
                  setProjectSourceMode("custom");
                  setProjectSourceRepo("");
                  return;
                }
                if (!value) {
                  setProjectSourceMode("default");
                  setProjectSourceRepo("");
                  return;
                }
                setProjectSourceMode("saved");
                setProjectSourceRepo(value);
              }}
            >
              <option value="">Default configured repo</option>
              {sourceRepos.map((repo) => (
                <option value={repo.source_repo_spec} key={repo.id}>{repo.label}</option>
              ))}
              <option value="__custom__">Custom path or URL</option>
            </select>
            {projectSourceMode === "custom" ? (
              <input
                value={projectSourceRepo}
                onChange={(event) => setProjectSourceRepo(event.target.value)}
                placeholder="Source repo path or URL"
              />
            ) : null}
            <select name="validation_profile" defaultValue="full-stack">
              <option value="python">Python</option>
              <option value="frontend">Frontend</option>
              <option value="full-stack">Full-stack</option>
              <option value="new-app">New app</option>
            </select>
            <textarea
              name="initial_requirements"
              placeholder="Describe the app you want. The assistant will ask questions before building."
              required
            />
            <button type="submit"><MessageSquare size={16} /> Create Project Chat</button>
          </form>
        </section>
        <section className="panel project-list-panel">
          <div className="list">
            {projects.length === 0 && <div className="empty">No projects yet.</div>}
            {projects.map((item) => (
              <a
                className={project?.id === item.id ? "project-list-item active" : "project-list-item"}
                href={`/ui/projects/${item.id}`}
                key={item.id}
              >
                <strong>{item.name}</strong>
                <span>{item.readiness_score}% ready · {item.open_questions} questions</span>
                <StatusPill value={item.status} />
              </a>
            ))}
          </div>
        </section>
      </aside>
      {project ? (
        <ProjectDetailView
          project={project}
          onNotice={onNotice}
          onError={onError}
          onRefresh={onRefresh}
        />
      ) : (
        <section className="panel project-empty-state">
          <FolderKanban size={28} />
          <h2>Select or create a project</h2>
          <p className="muted">
            Each project gets its own chat, intake questions, build plan, agent queue, and
            validation profile.
          </p>
        </section>
      )}
    </div>
  );
}

function ProjectDetailView({
  project,
  onNotice,
  onError,
  onRefresh
}: {
  project: ProjectDetail;
  onNotice: (message: string) => void;
  onError: (message: string) => void;
  onRefresh: () => Promise<void>;
}) {
  const [draft, setDraft] = useState("");
  const sendMessage = async (message: string) => {
    const trimmed = message.trim();
    if (!trimmed) return;
    try {
      const result = await api<ProjectCommandResponse>(`/api/projects/${project.id}/messages`, {
        method: "POST",
        body: JSON.stringify({ content: trimmed })
      });
      setDraft("");
      if (result.run_ids.length > 1) onNotice(`${result.run_ids.length} parallel agent runs started.`);
      else if (result.run_id) onNotice(`Agent run started: ${result.run_id}`);
      else onNotice("Project chat updated.");
      await onRefresh();
    } catch (err) {
      onError(err instanceof Error ? err.message : "Project command failed.");
    }
  };
  const answerQuestion = async (question: ProjectQuestion, answer: string) => {
    if (!answer.trim()) return;
    try {
      await api<ProjectDetail>(`/api/projects/${project.id}/questions/${question.id}/answer`, {
        method: "POST",
        body: JSON.stringify({ answer })
      });
      onNotice("Question answered.");
      await onRefresh();
    } catch (err) {
      onError(err instanceof Error ? err.message : "Answer failed.");
    }
  };
  const approvePlan = async () => {
    try {
      await api<ProjectDetail>(`/api/projects/${project.id}/plan/approve`, {
        method: "POST",
        body: "{}"
      });
      onNotice("Build plan approved.");
      await onRefresh();
    } catch (err) {
      onError(err instanceof Error ? err.message : "Plan approval failed.");
    }
  };
  const startBuild = async () => {
    try {
      const result = await api<ProjectCommandResponse>(`/api/projects/${project.id}/start-build`, {
        method: "POST",
        body: "{}"
      });
      if (result.run_ids.length > 1) onNotice(`${result.run_ids.length} parallel agent runs started.`);
      else if (result.run_id) onNotice(`Agent run started: ${result.run_id}`);
      else {
        const lastMessage = result.project.messages[result.project.messages.length - 1];
        onNotice(lastMessage?.content || "Start command processed.");
      }
      await onRefresh();
    } catch (err) {
      onError(err instanceof Error ? err.message : "Start build failed.");
    }
  };
  const openQuestions = project.questions.filter((item) => item.status === "open");
  return (
    <div className="project-main">
      <section className="panel project-hero-panel">
        <div className="project-title-row">
          <div>
            <p className="eyebrow">Project workspace</p>
            <h2>{project.name}</h2>
            <p className="muted">{project.initial_requirements}</p>
          </div>
          <div className="project-score">
            <strong>{project.readiness_score}%</strong>
            <span>requirements ready</span>
          </div>
        </div>
        <div className="chip-row">
          <span>{humanizeSnake(project.status)}</span>
          <span>{project.validation_profile}</span>
          <span>{project.source_repo_spec || "default repo"}</span>
        </div>
        <div className="action-row">
          <button className="ghost" type="button" onClick={() => void sendMessage("create plan")}>
            <FileText size={16} /> Create Plan
          </button>
          <button type="button" onClick={approvePlan}>
            <Check size={16} /> Approve Plan
          </button>
          <button type="button" onClick={startBuild}>
            <Play size={16} /> Start Agents
          </button>
          <button className="ghost" type="button" onClick={() => void sendMessage("status")}>
            <Activity size={16} /> Status
          </button>
          <button className="warn" type="button" onClick={() => void sendMessage("pause")}>
            <Square size={16} /> Pause
          </button>
        </div>
      </section>

      <section className="project-grid">
        <section className="panel chat-panel">
          <div className="panel-head">
            <div>
              <p className="eyebrow">Interactive chat</p>
              <h2>Requirements and commands</h2>
            </div>
            <MessageSquare size={20} />
          </div>
          <div className="chat-stream">
            {project.messages.map((message) => (
              <div className={`chat-bubble ${message.role}`} key={message.id}>
                <span>{message.role} · {humanizeSnake(message.message_type)}</span>
                <p>{message.content}</p>
              </div>
            ))}
          </div>
          <form
            className="chat-compose"
            onSubmit={(event) => {
              event.preventDefault();
              void sendMessage(draft);
            }}
          >
            <textarea
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              placeholder="Answer a question or type a command: create plan, approve plan, start build, pause, status"
            />
            <button type="submit"><Send size={16} /> Send</button>
          </form>
        </section>

        <section className="panel question-panel">
          <div className="panel-head">
            <div>
              <p className="eyebrow">Open questions</p>
              <h2>{openQuestions.length} needed before build</h2>
            </div>
            <HelpCircle size={20} />
          </div>
          <div className="list">
            {project.questions.map((question) => (
              <QuestionCard
                question={question}
                onAnswer={(answer) => answerQuestion(question, answer)}
                key={question.id}
              />
            ))}
          </div>
        </section>
      </section>

      <section className="panel">
        <div className="panel-head">
          <div>
            <p className="eyebrow">Build plan</p>
            <h2>Scoped agent work</h2>
          </div>
          <Boxes size={20} />
        </div>
        <div className="build-items">
          {project.build_items_detail.length === 0 && (
            <div className="empty">No build items yet. Answer questions, then create a plan.</div>
          )}
          {project.build_items_detail.map((item) => (
            <div className="build-item" key={item.id}>
              <div>
                <strong>{item.title}</strong>
                <p className="muted">{item.description}</p>
                <div className="chip-row">
                  <span>{item.assigned_role}</span>
                  <span>{item.status}</span>
                  {item.depends_on.length > 0 ? <span>waits for {item.depends_on.length}</span> : <span>parallel-ready</span>}
                  {item.target_files.map((file) => <span key={file}>{file}</span>)}
                </div>
              </div>
              {item.run_id ? (
                <a className="button ghost compact" href={`/ui/runs/${item.run_id}`}>
                  Open run
                </a>
              ) : (
                <StatusPill value={item.status} />
              )}
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

function QuestionCard({
  question,
  onAnswer
}: {
  question: ProjectQuestion;
  onAnswer: (answer: string) => Promise<void>;
}) {
  const [answer, setAnswer] = useState(question.answer || "");
  const answered = question.status === "answered";
  return (
    <div className={answered ? "question-card answered" : "question-card"}>
      <div className="question-card-head">
        <StatusPill value={question.status} />
        <span>{question.key}</span>
      </div>
      <strong>{question.question}</strong>
      <p className="muted">{question.reason}</p>
      {question.options.length > 0 && (
        <div className="chip-row">
          {question.options.map((option) => (
            <button
              className="ghost compact"
              type="button"
              onClick={() => setAnswer(option)}
              key={option}
            >
              {option}
            </button>
          ))}
        </div>
      )}
      <div className="question-answer-row">
        <input
          value={answer}
          onChange={(event) => setAnswer(event.target.value)}
          placeholder="Answer"
          disabled={answered}
        />
        <button
          className="compact"
          type="button"
          onClick={() => void onAnswer(answer)}
          disabled={answered}
        >
          Save
        </button>
      </div>
    </div>
  );
}

function Dashboard({
  data,
  onNotice,
  onError,
  onRefresh,
  onRunCreated
}: {
  data: AppData;
  onNotice: (message: string) => void;
  onError: (message: string) => void;
  onRefresh: () => Promise<void>;
  onRunCreated: (runId: string) => Promise<void>;
}) {
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
      await onRefresh();
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
        <Metric
          icon={<Shield />}
          label="GitHub"
          value={
            data.github?.configured
              ? "configured"
              : data.github?.repo_full_name
                ? "repo set / token missing"
                : "token missing"
          }
        />
      </section>
      <section className="dashboard-grid">
        <TaskComposer onNotice={onNotice} onError={onError} onRunCreated={onRunCreated} />
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
  const isDirty = repository?.dirty === true;
  const [copiedKey, setCopiedKey] = useState<string | null>(null);
  const [copyNotice, setCopyNotice] = useState<string | null>(null);
  const fixOptions = [
    {
      key: "commit",
      label: "1) Keep your work (recommended)",
      command: "git add -A && git commit -m \"WIP: save local changes\""
    },
    {
      key: "stash",
      label: "2) Stash changes temporarily",
      command: "git stash push -u -m \"temp-cleanup\" && git stash list"
    },
    {
      key: "discard",
      label: "3) Drop local changes (destructive)",
      command: "git restore --staged . && git restore . && git clean -fd"
    }
  ];

  const copyCommand = async (key: string, command: string) => {
    const fallbackCopyPrompt = () => {
      window.prompt("Clipboard is unavailable here. Copy this command manually:", command);
      setCopyNotice("Clipboard API unavailable. Prompt shown for manual copy.");
    };

    try {
      if (!navigator.clipboard || !window.isSecureContext) {
        fallbackCopyPrompt();
        return;
      }
      await navigator.clipboard.writeText(command);
      setCopiedKey(key);
      setCopyNotice(null);
      window.setTimeout(() => {
        setCopiedKey((current) => (current === key ? null : current));
      }, 1400);
    } catch {
      fallbackCopyPrompt();
    }
  };

  return (
    <section className="panel">
      <div className="panel-head">
        <div>
          <p className="eyebrow">Managed checkout</p>
          <h2>{repository?.branch || "Repository"}</h2>
        </div>
        <GitBranch size={22} />
      </div>
      <details className="repo-details" open>
        <summary>Repository details</summary>
        <InfoRows rows={[
          ["Path", repository?.path || "-"],
          ["Branch", repository?.branch || "-"],
          ["Head SHA", repository?.head_sha || "-"],
          ["Dirty", String(repository?.dirty ?? "-")],
          ["Remotes", repository?.remotes?.join(", ") || "No remotes configured"]
        ]} />
      </details>
      {isDirty ? (
        <details className="repo-details repo-dirty-details">
          <summary>Dirty working tree: fix options</summary>
          <p className="muted">The checkout has uncommitted changes. Pick one approach:</p>
          {copyNotice ? <p className="muted repo-copy-notice">{copyNotice}</p> : null}
          <div className="repo-fix-options">
            {fixOptions.map((option) => (
              <div key={option.key}>
                <div className="repo-fix-option-head">
                  <strong>{option.label}</strong>
                  <button type="button" className="ghost compact" onClick={() => void copyCommand(option.key, option.command)}>
                    {copiedKey === option.key ? <Check size={14} /> : <Copy size={14} />}
                    {copiedKey === option.key ? "Copied" : "Copy command"}
                  </button>
                </div>
                <pre>{option.command}</pre>
              </div>
            ))}
          </div>
        </details>
      ) : null}
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
        {data.github?.repo_full_name ? (
          <InfoRows
            rows={[
              ["Canonical repo", data.github.repo_full_name],
              ["Default branch", String(data.github.repo_default_branch || "-")],
              ["Web", data.github.repo_html_url || "-"],
              ["Clone (HTTPS)", data.github.repo_clone_url || "-"],
              ["API user", data.github.login ? String(data.github.login) : "-"]
            ]}
          />
        ) : (
          <p className="muted">Set GITHUB_REPO_FULL_NAME under Settings to show canonical repo links.</p>
        )}
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
  }, [String(runtime.lmstudio_base_url), String(runtime.lmstudio_api_key_configured ?? "")]);

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
        <p className="muted">
          LM Studio API key is {runtime.lmstudio_api_key_configured ? "configured" : "not configured"}.
        </p>
        <div className="two-col">
          <button className="ghost compact" type="button" onClick={() => void refreshModels()}>
            <RefreshCw size={16} /> Refresh LM Studio models
          </button>
        </div>
        <input name="APP_HOST" defaultValue={String(runtime.app_host || "0.0.0.0")} placeholder="APP_HOST" />
        <input name="APP_PORT" defaultValue={String(runtime.app_port || "8400")} placeholder="APP_PORT" />
        <input name="APP_API_TOKEN" type="hidden" value="__UNCHANGED__" readOnly />
        <input name="WORKER_COUNT" defaultValue={String(config?.worker_count ?? 3)} placeholder="WORKER_COUNT" />
        <input name="LMSTUDIO_BASE_URL" defaultValue={String(runtime.lmstudio_base_url || "")} placeholder="LMSTUDIO_BASE_URL" />
        <input name="LMSTUDIO_MODEL" list="lmstudio-model-ids" defaultValue={String(runtime.lmstudio_model || "")} placeholder="LMSTUDIO_MODEL" />
        <input name="LMSTUDIO_MODEL_PLANNER" list="lmstudio-model-ids" defaultValue={String(runtime.lmstudio_model_planner || "")} placeholder="LMSTUDIO_MODEL_PLANNER" />
        <input name="LMSTUDIO_MODEL_ARCHITECT" list="lmstudio-model-ids" defaultValue={String(runtime.lmstudio_model_architect || "")} placeholder="LMSTUDIO_MODEL_ARCHITECT" />
        <input name="LMSTUDIO_MODEL_UI_DESIGNER" list="lmstudio-model-ids" defaultValue={String(runtime.lmstudio_model_ui_designer || "")} placeholder="LMSTUDIO_MODEL_UI_DESIGNER" />
        <input name="LMSTUDIO_MODEL_CODER" list="lmstudio-model-ids" defaultValue={String(runtime.lmstudio_model_coder || "")} placeholder="LMSTUDIO_MODEL_CODER" />
        <input name="LMSTUDIO_MODEL_REVIEWER" list="lmstudio-model-ids" defaultValue={String(runtime.lmstudio_model_reviewer || "")} placeholder="LMSTUDIO_MODEL_REVIEWER" />
        <input name="LMSTUDIO_MODEL_TESTER" list="lmstudio-model-ids" defaultValue={String(runtime.lmstudio_model_tester || "")} placeholder="LMSTUDIO_MODEL_TESTER" />
        <input name="LMSTUDIO_MODEL_SUPERVISOR" list="lmstudio-model-ids" defaultValue={String(runtime.lmstudio_model_supervisor || "")} placeholder="LMSTUDIO_MODEL_SUPERVISOR" />
        <input
          name="LMSTUDIO_API_KEY"
          type="password"
          defaultValue="__UNCHANGED__"
          placeholder="LMSTUDIO_API_KEY (leave as __UNCHANGED__ to keep current)"
        />
        <input name="PROVIDER_TIMEOUT_SECONDS" defaultValue={String(runtime.provider_timeout_seconds || "60")} placeholder="PROVIDER_TIMEOUT_SECONDS" />
        <input name="GIT_CLONE_TIMEOUT_SECONDS" defaultValue={String(runtime.git_clone_timeout_seconds || "300")} placeholder="GIT_CLONE_TIMEOUT_SECONDS" />
        <input name="SOURCE_REPO_PATH" defaultValue={String(runtime.source_repo_path || "")} placeholder="SOURCE_REPO_PATH" />
        <p className="muted">Canonical GitHub repo for this platform (owner/repo, used in Provider view and health).</p>
        <input
          name="GITHUB_REPO_FULL_NAME"
          defaultValue={String(runtime.github_repo_full_name || "")}
          placeholder="GITHUB_REPO_FULL_NAME (e.g. hamedmirza/AI-Dev-Platform)"
        />
        <input
          name="GITHUB_REPO_DEFAULT_BRANCH"
          defaultValue={String(runtime.github_repo_default_branch || "main")}
          placeholder="GITHUB_REPO_DEFAULT_BRANCH"
        />
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

function BackupsView({
  backups,
  onNotice,
  onError,
  onRefresh
}: {
  backups: BackupItem[];
  onNotice: (message: string) => void;
  onError: (message: string) => void;
  onRefresh: () => Promise<void>;
}) {
  const createBackup = async () => {
    try {
      await api("/api/backups/run", { method: "POST", body: "{}" });
      onNotice("Backup created.");
      await onRefresh();
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
  onRefresh: () => Promise<void>;
}) {
  const { run, events, artifacts, snapshots, diff, workspaceFiles, selectedFile, fileContent, onSelectFile, onFileContent, onNotice, onError, onRefresh } =
    props;

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
      await onRefresh();
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
      await onRefresh();
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
