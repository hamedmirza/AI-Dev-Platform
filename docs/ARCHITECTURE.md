# Architecture

```text
Client/UI
   ↓
FastAPI API Layer
   ↓
Orchestration Service
   ↓
LangGraph Workflow
   ├─ Planner Agent
   ├─ Architect Agent
   ├─ UI Designer Agent
   ├─ Coder Agent
   ├─ Reviewer Agent
   └─ Tester Agent
   ↓
Tool Wrappers + Provider Adapters
   ├─ Filesystem / Workspace Guard
   ├─ Validation Runners
   └─ LM Studio Provider
   ↓
SQLite Persistence
```
