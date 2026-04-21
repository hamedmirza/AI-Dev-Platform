from pydantic import BaseModel


class WorkspaceFilesResponse(BaseModel):
    run_id: str
    workspace_path: str
    files: list[str]


class WorkspaceFileResponse(BaseModel):
    run_id: str
    workspace_path: str
    path: str
    content: str


class WorkspaceFileUpdateRequest(BaseModel):
    path: str
    content: str


class WorkspaceFileUpdateResponse(BaseModel):
    run_id: str
    workspace_path: str
    path: str
    content: str
