
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> None:
    from app.db.session import get_session_factory, init_db
    from app.schemas.task import TaskCreate
    from app.services.task_service import create_task_and_run

    init_db()
    session = get_session_factory()()
    try:
        create_task_and_run(
            session,
            TaskCreate(
                title="Demo run",
                request_text="Create a demo run for the local operator console.",
            ),
            provider_name="seed-script",
        )
    finally:
        session.close()


if __name__ == "__main__":
    main()
