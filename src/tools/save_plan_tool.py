
import logging
import json
from typing import Dict, Any
from langchain_core.tools import tool
from src.document_store import store_plan_document
from src.models.models import PlanStatus # Import PlanStatus

logger = logging.getLogger(__name__)

@tool
async def save_plan(
    user_id: str,
    thread_id: str,
    plan_json: Dict[str, Any],
    course_plan_id: str,
    departamento_regional: str,
    escola: str,
    docente: str,
    curso: str,
    data_inicio: str,
    data_fim: str,
) -> Dict[str, str]:
    """
    Stores a teaching plan (already in JSON format) in the database and GCS,
    and returns the new plan's ID.
    """
    logger.info(f"Executing save_plan tool for user {user_id} in thread {thread_id}.")
    
    try:
        # 1. Convert the dict to JSON string for storage
        plan_json_str = json.dumps(plan_json, ensure_ascii=False)
        logger.info("Plan JSON ready for storage.")

        # 2. Store the JSON plan
        new_plan_id = await store_plan_document(
            user_id=user_id,
            thread_id=thread_id,
            plan_json_content=plan_json_str,
            course_plan_id=course_plan_id,
            departamento_regional=departamento_regional,
            escola=escola,
            docente=docente,
            curso=curso,
            data_inicio=data_inicio,
            data_fim=data_fim,
            status=PlanStatus.gerado, # Pass default status
        )
        logger.info(f"Successfully stored new plan document. New plan ID: {new_plan_id}")

        # 3. Return the new plan ID
        return {"new_plan_id": new_plan_id}

    except Exception as e:
        logger.error(f"Error during save_plan execution: {e}", exc_info=True)
        return {"error": str(e)}

