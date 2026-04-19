
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ArtifactModel
from app.schemas.artifact import ArtifactResponse


def list_artifacts(session: Session, run_id: str) -> list[ArtifactResponse]:
    artifacts = session.scalars(
        select(ArtifactModel).where(ArtifactModel.run_id == run_id).order_by(ArtifactModel.id.asc())
    ).all()
    return [
        ArtifactResponse(
            id=item.id,
            artifact_type=item.artifact_type,
            title=item.title,
            content=item.content,
            truncated=item.truncated,
            created_at=item.created_at,
        )
        for item in artifacts
    ]
