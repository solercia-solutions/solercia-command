"""Alert engine admin endpoints."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.alerts.evaluator import evaluate_all_organizations
from app.database import get_db
from app.dependencies import require_admin
from app.modules.users.models import User

router = APIRouter(tags=["alerts"])


@router.post("/alerts/evaluate")
async def trigger_evaluation(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> dict:
    """Trigger alert evaluation on demand (admin only). Useful for testing."""
    total = await evaluate_all_organizations(db)
    return {
        "data": {"created": total},
        "message": f"Evaluación completada. {total} notificaciones nuevas creadas.",
    }
