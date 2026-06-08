"""
M-03: Defesa em Profundidade — RBAC no Backend
Replica no backend as regras de autorização do proxy:
  - Vertical: rotas admin-only exigem role administrativa
  - Horizontal: acesso a dados de outro usuário exige role administrativa
"""
import logging
from fastapi import HTTPException
from psycopg.rows import dict_row
from .jwt_validator import AuthenticatedUser

logger = logging.getLogger(__name__)

ADMIN_ROLES = {"administracao_nacional", "administracao_regional", "coordenador"}


async def get_user_role_from_db(user_id: str) -> str | None:
    """Busca a role do usuário no banco de dados usando o pool existente."""
    from ..agent import get_checkpoint_connection

    try:
        async with (await get_checkpoint_connection()).connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute("SELECT role FROM users WHERE user_id = %s;", (user_id,))
                record = await cur.fetchone()
                return record["role"] if record else None
    except Exception as e:
        logger.error(f"Erro ao buscar role do usuário {user_id}: {e}", exc_info=True)
        return None


async def require_admin(auth: AuthenticatedUser) -> None:
    """Dependency: bloqueia se o usuário não possui role administrativa (Regra Vertical)."""
    role = await get_user_role_from_db(auth.user_id)
    if role not in ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Acesso restrito à Administração.")


async def require_self_or_admin(auth: AuthenticatedUser, target_user_id: str) -> None:
    """Helper: permite acesso se for o próprio usuário ou admin (Regra Horizontal)."""
    if auth.user_id == target_user_id:
        return
    role = await get_user_role_from_db(auth.user_id)
    if role not in ADMIN_ROLES:
        raise HTTPException(
            status_code=403,
            detail="Acesso negado: você não pode manipular dados de outras contas.",
        )
