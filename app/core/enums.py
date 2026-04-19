
from enum import Enum


class StringEnum(str, Enum):
    pass


class RunStatus(StringEnum):
    QUEUED = "queued"
    RUNNING = "running"
    NEEDS_REVISION = "needs_revision"
    AWAITING_APPROVAL = "awaiting_approval"
    FAILED = "failed"
    COMPLETED = "completed"


class RunStage(StringEnum):
    INTAKE = "intake"
    PLANNER = "planner"
    ARCHITECT = "architect"
    CODER = "coder"
    REVIEWER = "reviewer"
    TESTER = "tester"
    APPROVAL = "approval"
    DONE = "done"


class ArtifactType(StringEnum):
    PLAN = "plan"
    ARCHITECTURE = "architecture"
    CODE_CHANGE = "code_change"
    REVIEW = "review"
    TEST_RESULT = "test_result"
    LOG = "log"


class ProviderStatus(StringEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
