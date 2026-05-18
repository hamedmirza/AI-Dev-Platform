import React, { FormEvent, useEffect, useRef, useState } from "react";
import { Play } from "lucide-react";

import { api } from "../http";

type TaskTemplate = {
  id: string;
  label: string;
  taskType: string;
  title: string;
  requestText: string;
  constraints: string;
  targetFiles: string;
};

const taskTemplates: TaskTemplate[] = [
  {
    id: "feature",
    label: "Feature implementation (default)",
    taskType: "feature",
    title: "Implement feature slice",
    requestText: "Implement the requested feature end-to-end with tests and keep validation green.",
    constraints: "small PR, preserve existing behavior, no secrets",
    targetFiles: ""
  },
  {
    id: "bugfix",
    label: "Bug fix",
    taskType: "bugfix",
    title: "Fix reported bug",
    requestText: "Reproduce the bug, implement a fix with minimal blast radius, and add regression coverage.",
    constraints: "no regressions, root-cause explained",
    targetFiles: ""
  },
  {
    id: "deployment",
    label: "Deployment process + observation",
    taskType: "deployment",
    title: "Harden deployment process and observe rollout",
    requestText: "Use app agents to improve deployment flow (build, release, rollback checks), execute verification, and document observations from runtime/health metrics.",
    constraints: "safe rollout, rollback plan, measurable verification",
    targetFiles: "docs/DEPLOYMENT_SCALING.md,.github/workflows/ci.yml,.github/workflows/docker.yml"
  }
];

function splitCsv(value: string) {
  return value.split(",").map((item) => item.trim()).filter(Boolean);
}

export function TaskComposer({
  onNotice,
  onError,
  onRunCreated
}: {
  onNotice: (message: string) => void;
  onError: (message: string) => void;
  onRunCreated: (runId: string) => Promise<void>;
}) {
  const formRef = useRef<HTMLFormElement | null>(null);
  const [templateId, setTemplateId] = useState<string>(taskTemplates[0].id);
  const [showAdvanced, setShowAdvanced] = useState<boolean>(false);

  const applyTemplate = (nextTemplateId: string) => {
    const form = formRef.current;
    if (!form) return;
    const selected = taskTemplates.find((item) => item.id === nextTemplateId) || taskTemplates[0];
    const setValue = (name: string, value: string) => {
      const field = form.elements.namedItem(name) as HTMLInputElement | HTMLTextAreaElement | null;
      if (field) field.value = value;
    };
    setValue("title", selected.title);
    setValue("task_type", selected.taskType);
    setValue("request_text", selected.requestText);
    setValue("constraints", selected.constraints);
    setValue("target_files", selected.targetFiles);
  };

  useEffect(() => {
    applyTemplate(taskTemplates[0].id);
  }, []);

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
          validation_profile: String(form.get("validation_profile") || "auto"),
          stage_models
        })
      });
      onNotice(`Task created: ${created.run_id}`);
      await onRunCreated(created.run_id);
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
      <p className="muted">Fields marked with * are required. Start with a preset, then tweak.</p>
      <form className="form-grid" onSubmit={submit} ref={formRef}>
        <div>
          <label className="field-label" htmlFor="task_preset">Task preset</label>
          <select
            id="task_preset"
            name="task_preset"
            value={templateId}
            onChange={(event) => {
              const next = event.target.value;
              setTemplateId(next);
              applyTemplate(next);
            }}
          >
            {taskTemplates.map((item) => (
              <option value={item.id} key={item.id}>{item.label}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="field-label" htmlFor="title">Run title *</label>
          <input id="title" name="title" placeholder="Run title" required />
        </div>
        <div className="two-col">
          <div>
            <label className="field-label" htmlFor="task_type">Task type</label>
            <select id="task_type" name="task_type" defaultValue="feature">
              <option value="">(auto)</option>
              <option value="feature">feature</option>
              <option value="bugfix">bugfix</option>
              <option value="deployment">deployment</option>
              <option value="refactor">refactor</option>
              <option value="docs">docs</option>
            </select>
          </div>
          <div>
            <label className="field-label" htmlFor="source_repo">Source repo</label>
            <input id="source_repo" name="source_repo" placeholder="Path/URL. Remote requires ALLOWED_GIT_HOSTS." />
          </div>
        </div>
        <label className="muted" style={{ display: "flex", gap: "8px", alignItems: "center" }}>
          <input type="checkbox" name="use_scout" defaultChecked /> Use read-only scout preamble for planner
        </label>
        <div>
          <label className="field-label" htmlFor="request_text">Task description *</label>
          <textarea id="request_text" name="request_text" placeholder="Describe the implementation task." required />
        </div>
        <div className="two-col">
          <button className="ghost compact" type="button" onClick={() => setShowAdvanced((v) => !v)}>
            {showAdvanced ? "Hide advanced options" : "Show advanced options"}
          </button>
        </div>
        {showAdvanced ? (
          <>
            <div>
              <label className="field-label" htmlFor="workspace_path">Workspace path</label>
              <input id="workspace_path" name="workspace_path" placeholder="Optional workspace path override" />
            </div>
            <div className="two-col">
              <div>
                <label className="field-label" htmlFor="provider">Provider</label>
                <select id="provider" name="provider" defaultValue="">
                  <option value="">(default)</option>
                  <option value="lmstudio">lmstudio</option>
                </select>
              </div>
              <div>
                <label className="field-label" htmlFor="model">Model override</label>
                <input id="model" name="model" placeholder="Optional model id override" />
              </div>
            </div>
            <div>
              <label className="field-label" htmlFor="stage_models_json">Per-stage models JSON</label>
              <textarea id="stage_models_json" name="stage_models_json" placeholder='Optional JSON, e.g. {"coder":"model-id"}' rows={2} />
            </div>
            <div>
              <label className="field-label" htmlFor="target_files">Target files</label>
              <input id="target_files" name="target_files" placeholder="Comma-separated paths (optional)" />
            </div>
            <div>
              <label className="field-label" htmlFor="validation_profile">Validation profile</label>
              <select id="validation_profile" name="validation_profile" defaultValue="auto">
                <option value="auto">Auto detect</option>
                <option value="python">Python</option>
                <option value="react-vite">React/Vite</option>
                <option value="full-stack">Full-stack</option>
              </select>
            </div>
            <div>
              <label className="field-label" htmlFor="constraints">Constraints</label>
              <input id="constraints" name="constraints" placeholder="Comma-separated constraints (optional)" />
            </div>
          </>
        ) : null}
        <button type="submit"><Play size={16} /> Start Run</button>
      </form>
    </section>
  );
}
