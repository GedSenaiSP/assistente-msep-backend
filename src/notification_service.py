import uuid
import logging
import json
from typing import Optional, Dict, Any
from src.agent import get_checkpoint_connection
from src.models.models import NotificationType
from psycopg.rows import dict_row

logger = logging.getLogger(__name__)

async def create_notification(
    user_id: str,
    notification_type: NotificationType,
    message: str,
    plan_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
):
    """
    Cria uma nova notificação para um usuário.
    """
    try:
        async with (await get_checkpoint_connection()).connection() as conn:
            async with conn.cursor() as cur:
                notification_id = uuid.uuid4()
                query = """
                INSERT INTO notifications (id, user_id, plan_id, type, message, metadata)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id;
                """
                await cur.execute(
                    query,
                    (
                        notification_id,
                        user_id,
                        uuid.UUID(plan_id) if plan_id else None,
                        notification_type.value,
                        message,
                        json.dumps(metadata) if metadata else None
                    )
                )
                logger.info(f"Notificação criada: {notification_id} para usuário {user_id}")
                return str(notification_id)
    except Exception as e:
        logger.error(f"Erro ao criar notificação: {e}", exc_info=True)
        raise


async def notify_plan_submitted(plan_id: str, docente_name: str, plan_name: str, escola: str):
    """
    Notifica coordenadores da escola quando um plano é submetido.
    """
    try:
        logger.info(f"🔔 [notify_plan_submitted] Iniciando busca de coordenadores para escola: '{escola}'")
        async with (await get_checkpoint_connection()).connection() as conn:
            async with conn.cursor() as cur:
                # Buscar coordenadores da mesma escola
                query = """
                SELECT user_id FROM users 
                WHERE role = 'coordenador' AND escola = %s;
                """
                await cur.execute(query, (escola,))
                coordenadores = await cur.fetchall()
                
                logger.info(f"🔔 [notify_plan_submitted] Encontrados {len(coordenadores)} coordenadores para escola '{escola}'")
                
                if not coordenadores:
                    logger.warning(f"🔔 [notify_plan_submitted] ATENÇÃO: Nenhum coordenador encontrado para escola '{escola}'")
                
                for coord in coordenadores:
                    logger.info(f"🔔 [notify_plan_submitted] Criando notificação para coordenador: {coord[0]}")
                    message = f"{docente_name} submeteu o plano '{plan_name}' para aprovação."
                    await create_notification(
                        user_id=coord[0],
                        notification_type=NotificationType.plan_submitted,
                        message=message,
                        plan_id=plan_id,
                        metadata={
                            "docente_name": docente_name,
                            "plan_name": plan_name,
                            "escola": escola
                        }
                    )
                    logger.info(f"🔔 [notify_plan_submitted] Coordenador {coord[0]} notificado sobre submissão do plano {plan_id}")
    except Exception as e:
        logger.error(f"🔔 [notify_plan_submitted] Erro ao notificar submissão de plano: {e}", exc_info=True)


async def notify_plan_status_change(plan_id: str, docente_user_id: str, new_status: str, plan_name: str):
    """
    Notifica o docente quando o status do plano muda (retornado ou aprovado).
    """
    try:
        if new_status == "retornado":
            message = f"Seu plano '{plan_name}' foi retornado para correção."
            notification_type = NotificationType.plan_returned
        elif new_status == "aprovado":
            message = f"Seu plano '{plan_name}' foi aprovado!"
            notification_type = NotificationType.plan_approved
        else:
            return  # Não notifica para outros status
        
        await create_notification(
            user_id=docente_user_id,
            notification_type=notification_type,
            message=message,
            plan_id=plan_id,
            metadata={"plan_name": plan_name, "new_status": new_status}
        )
        logger.info(f"Docente {docente_user_id} notificado sobre mudança de status do plano {plan_id} para {new_status}")
    except Exception as e:
        logger.error(f"Erro ao notificar mudança de status: {e}", exc_info=True)


async def create_retroactive_notifications_for_coordinator(
    coordinator_user_id: str,
    school: str,
    plan_limit: int = 50,
    days_limit: int = 30
):
    """
    Cria notificações retroativas para planos submetidos recentemente da escola do coordenador.
    Não agrupa notificações, cria individualmente até o limite.
    """
    logger.info(f"Verificando notificações retroativas para coordenador {coordinator_user_id} na escola {school}")
    try:
        async with (await get_checkpoint_connection()).connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                # Buscar planos submetidos nos últimos X dias desta escola
                # que NÃO tenham notificação de submissão ainda (embora na prática,
                # se o coordenador é novo, ele não tem nenhuma notificação)
                query = f"""
                SELECT p.id, p.user_id, p.summary, p.created_at
                FROM user_plans p
                WHERE p.status = 'submetido'
                  AND p.escola = %s
                  AND p.created_at >= NOW() - INTERVAL '{days_limit} days'
                  AND NOT EXISTS (
                      SELECT 1 FROM notifications n
                      WHERE n.plan_id = p.id
                        AND n.user_id = %s
                        AND n.type = '{NotificationType.plan_submitted}'
                  )
                ORDER BY p.created_at DESC
                LIMIT %s;
                """
                await cur.execute(query, (school, coordinator_user_id, plan_limit))
                pending_plans = await cur.fetchall()
                
                if not pending_plans:
                    logger.info("Nenhum plano pendente encontrado para notificação retroativa.")
                    return
                
                logger.info(f"Encontrados {len(pending_plans)} planos pendentes. Criando notificações...")

                for plan in pending_plans:
                    # Garantir que o summary é um dicionário
                    summary = plan['summary']
                    if isinstance(summary, str):
                        try:
                            summary = json.loads(summary)
                        except:
                            summary = {}
                    
                    plan_name = summary.get('unidade_curricular') or summary.get('nome_uc') or 'Plano de Ensino'
                    docente = summary.get('docente', 'Docente')
                    date_str = plan['created_at'].strftime('%d/%m')
                    
                    message = f"Plano pendente: {docente} submeteu '{plan_name}' em {date_str}."
                    
                    await create_notification(
                        user_id=coordinator_user_id,
                        notification_type=NotificationType.plan_submitted,
                        message=message,
                        plan_id=str(plan['id']),
                        metadata={"is_retroactive": True, "original_date": plan['created_at'].isoformat()}
                    )
                
                logger.info(f"Criadas {len(pending_plans)} notificações retroativas com sucesso.")

    except Exception as e:
        logger.error(f"Erro ao criar notificações retroativas: {e}", exc_info=True)
