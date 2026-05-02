
from enum import Enum


class StringEnum(str, Enum):
    pass


class RunStatus(StringEnum):
    PENDING = "pending"
    RUNNING = "running"
    REVIEW_REQUIRED = "review_required"
    BLOCKED = "blocked"
    AWAITING_APPROVAL = "awaiting_approval"
    CANCELLED = "cancelled"
    FAILED = "failed"
    COMPLETED = "completed"


class RunStage(StringEnum):
    INTAKE = "intake"
    PLANNER = "planner"
    ARCHITECT = "architect"
    UI_DESIGNER = "ui_designer"
    CODER = "coder"
    REVIEWER = "reviewer"
    TESTER = "tester"
    APPROVAL = "approval"
    DONE = "done"


class ArtifactType(StringEnum):
    PLAN = "plan"
    ARCHITECTURE = "architecture"
    UI_DESIGN = "ui_design"
    CODE_CHANGE = "code_change"
    REVIEW = "review"
    TEST_RESULT = "test_result"
    LOG = "log"


class ProviderStatus(StringEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
