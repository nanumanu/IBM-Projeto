from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.security import require_analyst
from app.seed import reset_and_seed

router = APIRouter(tags=["Admin"], dependencies=[Depends(require_analyst)])


@router.post("/admin/reset-demo", response_model=dict[str, Any], operation_id="reset_demo",
             include_in_schema=True, summary="Apagar tudo e recriar os dados sintéticos")
def reset_demo(db: Session = Depends(get_db)):
    """Recria o cenário da demo com horários relativos a agora. Exige chave de analista."""
    return reset_and_seed(db)
