import os
import logging
import uuid
import asyncio
import json
from collections import Counter
from typing import Optional, Dict, Any
from psycopg import AsyncConnection
from psycopg.rows import dict_row
from azure.storage.blob import BlobServiceClient, BlobClient, ContainerClient, ContentSettings, generate_blob_sas, BlobSasPermissions
from datetime import datetime, timedelta, timezone
from src.models.models import PlanStatus
from src.database import get_db_pool

logger = logging.getLogger(__name__)

# Configurações
STRING_POSTGRES = f"postgresql://{os.getenv('PG_USER')}:{os.getenv('PG_PASSWORD')}@{os.getenv('PG_HOST')}:{os.getenv('PG_PORT')}/{os.getenv('PG_DATABASE')}"
AZURE_MARKDOWN_CONTAINER = os.getenv("AZURE_MARKDOWN_CONTAINER")
AZURE_PLANS_CONTAINER = os.getenv("AZURE_PLANS_CONTAINER")
AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")

# Lazy-initialized Azure Blob Service Client
_blob_service_client: Optional[BlobServiceClient] = None

def _get_blob_service_client() -> BlobServiceClient:
    """Retorna o BlobServiceClient, inicializando apenas uma vez."""
    global _blob_service_client
    if _blob_service_client is None:
        if not AZURE_STORAGE_CONNECTION_STRING:
            raise EnvironmentError("AZURE_STORAGE_CONNECTION_STRING não está configurado.")
        _blob_service_client = BlobServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)
    return _blob_service_client

def _get_container_client(container_name: str) -> ContainerClient:
    """Retorna um ContainerClient para o container especificado."""
    return _get_blob_service_client().get_container_client(container_name)

def _get_blob_client(container_name: str, blob_name: str) -> BlobClient:
    """Retorna um BlobClient para o blob especificado."""
    return _get_blob_service_client().get_blob_client(container_name, blob_name)


async def init_document_table():
    """Cria a tabela 'processed_documents' se ela não existir.
    O conteúdo Markdown será SEMPRE armazenado no Azure Blob Storage."""
    async with (await get_db_pool()).connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS processed_documents (
                    id UUID PRIMARY KEY,
                    user_id VARCHAR(255) NOT NULL,
                    thread_id VARCHAR(255) NOT NULL,
                    original_pdf_filename VARCHAR(512),
                    blob_path VARCHAR(1024) NOT NULL, -- Caminho para o blob no Azure
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
            """)
            await cur.execute("CREATE INDEX IF NOT EXISTS idx_processed_documents_user_id ON processed_documents (user_id);")
            await cur.execute("CREATE INDEX IF NOT EXISTS idx_processed_documents_thread_id ON processed_documents (thread_id);")
            logger.info("Tabela 'processed_documents' (Azure Blob) verificada/criada com sucesso.")

async def _upload_to_azure(container_name: str, content: str, blob_name: str) -> None:
    """Upload de conteúdo de texto para Azure Blob Storage."""
    if not container_name:
        raise ValueError("Nome do container Azure não configurado.")
    try:
        blob_client = _get_blob_client(container_name, blob_name)
        settings = ContentSettings(content_type="text/markdown")
        await asyncio.to_thread(blob_client.upload_blob, content, overwrite=True, content_settings=settings)
        logger.info(f"Conteúdo enviado para Azure Blob: {container_name}/{blob_name}")
    except Exception as e:
        logger.error(f"Erro ao enviar para Azure Blob ({container_name}/{blob_name}): {e}", exc_info=True)
        raise

async def _upload_bytes_to_azure(container_name: str, data: bytes, blob_name: str, content_type: str = "application/octet-stream") -> None:
    """Upload de conteúdo binário (DOCX, PPTX, PDF) para Azure Blob Storage."""
    if not container_name:
        raise ValueError("Nome do container Azure não configurado.")
    try:
        blob_client = _get_blob_client(container_name, blob_name)
        settings = ContentSettings(content_type=content_type)
        await asyncio.to_thread(blob_client.upload_blob, data, overwrite=True, content_settings=settings)
        logger.info(f"Arquivo binário enviado para Azure Blob: {container_name}/{blob_name}")
    except Exception as e:
        logger.error(f"Erro ao enviar binário para Azure Blob ({container_name}/{blob_name}): {e}", exc_info=True)
        raise

async def _download_from_azure(container_name: str, blob_name: str) -> Optional[str]:
    """Download de conteúdo de texto do Azure Blob Storage."""
    if not container_name:
        raise ValueError("Nome do container Azure não configurado.")
    try:
        blob_client = _get_blob_client(container_name, blob_name)
        
        exists = await asyncio.to_thread(blob_client.exists)
        if not exists:
            logger.warning(f"Blob Azure não encontrado: {container_name}/{blob_name}")
            return None
        
        downloader = await asyncio.to_thread(blob_client.download_blob)
        content_bytes = await asyncio.to_thread(downloader.readall)
        logger.info(f"Conteúdo baixado de Azure Blob: {container_name}/{blob_name}")
        return content_bytes.decode('utf-8')
    except Exception as e:
        logger.error(f"Erro ao baixar de Azure Blob ({container_name}/{blob_name}): {e}", exc_info=True)
        raise

async def _download_bytes_from_azure(container_name: str, blob_name: str) -> Optional[bytes]:
    """Download de conteúdo binário do Azure Blob Storage."""
    if not container_name:
        raise ValueError("Nome do container Azure não configurado.")
    try:
        blob_client = _get_blob_client(container_name, blob_name)
        
        exists = await asyncio.to_thread(blob_client.exists)
        if not exists:
            logger.warning(f"Blob Azure não encontrado: {container_name}/{blob_name}")
            return None
        
        downloader = await asyncio.to_thread(blob_client.download_blob)
        content_bytes = await asyncio.to_thread(downloader.readall)
        logger.info(f"Arquivo binário baixado de Azure Blob: {container_name}/{blob_name}")
        return content_bytes
    except Exception as e:
        logger.error(f"Erro ao baixar binário de Azure Blob ({container_name}/{blob_name}): {e}", exc_info=True)
        raise

def _generate_sas_url(container_name: str, blob_name: str, expiry_minutes: int = 60) -> str:
    """Gera uma URL com SAS token para acesso temporário a um blob."""
    service_client = _get_blob_service_client()
    account_name = service_client.account_name
    # Extrair account key da connection string
    conn_str_parts = {p.split("=", 1)[0]: p.split("=", 1)[1] for p in AZURE_STORAGE_CONNECTION_STRING.split(";") if "=" in p}
    account_key = conn_str_parts.get("AccountKey", "")
    
    sas_token = generate_blob_sas(
        account_name=account_name,
        container_name=container_name,
        blob_name=blob_name,
        account_key=account_key,
        permission=BlobSasPermissions(read=True),
        expiry=datetime.now(timezone.utc) + timedelta(minutes=expiry_minutes)
    )
    
    return f"https://{account_name}.blob.core.windows.net/{container_name}/{blob_name}?{sas_token}"


async def store_markdown_document(
    user_id: str,
    thread_id: str,
    markdown_content: str,
    original_pdf_filename: Optional[str] = None
) -> str:
    """
    Armazena o conteúdo Markdown SEMPRE no Azure Blob Storage e os metadados no DB.
    Retorna o ID do documento armazenado (para o registro no DB).
    """
    doc_id = uuid.uuid4()
    
    if not AZURE_MARKDOWN_CONTAINER:
        logger.error("Azure Container não configurado. Não é possível armazenar o Markdown.")
        raise ValueError("Azure Container não configurado para armazenar arquivo.")

    blob_name = f"processed_markdowns/{user_id}/{doc_id}.json"
    
    await _upload_to_azure(AZURE_MARKDOWN_CONTAINER, markdown_content, blob_name)
    logger.info(f"Markdown (ID: {doc_id}) armazenado no Azure em {blob_name}.")

    async with (await get_db_pool()).connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO processed_documents 
                (id, user_id, thread_id, original_pdf_filename, blob_path)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (doc_id, user_id, thread_id, original_pdf_filename, blob_name)
            )
    logger.info(f"Metadados do Markdown (ID: {doc_id}, Blob: {blob_name}) salvos no DB.")
    return str(doc_id)

async def store_plan_document(
    user_id: str,
    thread_id: str,
    plan_json_content: str,
    course_plan_id: str,
    departamento_regional: str,
    escola: str,
    docente: str,
    curso: str,
    data_inicio: str,
    data_fim: str,
    status: PlanStatus = PlanStatus.gerado,
) -> str:
    """
    Armazena o plano de curso (JSON) no Azure Blob, extrai um resumo, e armazena os metadados e o resumo no DB.
    Retorna o ID do plano armazenado.
    """
    plan_id = uuid.uuid4()

    if not AZURE_PLANS_CONTAINER:
        logger.error("Azure Container não configurado. Não é possível armazenar o plano.")
        raise ValueError("Azure Container não configurado para armazenar arquivo.")

    # 1. Salva o JSON completo no Azure Blob
    blob_name = f"user_plans/{user_id}/{plan_id}.json"
    await _upload_to_azure(AZURE_PLANS_CONTAINER, plan_json_content, blob_name)
    logger.info(f"Plano (ID: {plan_id}) armazenado no Azure em {blob_name}.")

    # 2. Extrai os metadados para o resumo de forma inteligente
    summary_data = {}
    try:
        full_plan_data = json.loads(plan_json_content)

        # Detecta o tipo de plano e extrai os dados do local correto
        if "plano_de_ensino" in full_plan_data: # Plano gerado por IA
            plan_data = full_plan_data.get("plano_de_ensino", {})
            cabecalho = plan_data.get("informacoes_curso", {})
            summary_data = {
                "nome_uc": cabecalho.get("unidade_curricular"),
                "turma": cabecalho.get("turma"),
                "escola": cabecalho.get("unidade"),
            }
            situacoes = plan_data.get("situacoes_aprendizagem", [])
            tipos_sa = []
            for sa in situacoes:
                estrategia = sa.get("estrategia_aprendizagem", {})
                tipo = estrategia.get("tipo")
                if tipo:
                    tipos_sa.append(tipo)
            summary_data["contagem_sa_por_tipo"] = dict(Counter(tipos_sa))

        elif "informacoes_gerais" in full_plan_data: # Plano manual
            cabecalho = full_plan_data.get("informacoes_gerais", {})
            summary_data = {
                "nome_uc": cabecalho.get("unidade_curricular"),
                "turma": cabecalho.get("turma"),
                "escola": cabecalho.get("escola"),
            }
            situacoes = full_plan_data.get("situacoes_aprendizagem", [])
            tipos_sa = [sa.get("estrategia") for sa in situacoes if sa.get("estrategia")]
            summary_data["contagem_sa_por_tipo"] = dict(Counter(tipos_sa))

    except (json.JSONDecodeError, AttributeError) as e:
        logger.error(f"Falha ao extrair resumo do JSON do plano para o ID {plan_id}. Resumo ficará vazio. Erro: {e}")

    # 3. Salva os metadados e o resumo no banco de dados
    async with (await get_db_pool()).connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO user_plans 
                (id, user_id, thread_id, course_plan_id, blob_path, summary, departamento_regional, escola, docente, curso, data_inicio, data_fim, status, arquivado)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (plan_id, user_id, thread_id, course_plan_id, blob_name, json.dumps(summary_data), departamento_regional, escola, docente, curso, data_inicio, data_fim, status.value, False)
            )
    logger.info(f"Metadados e resumo do plano (ID: {plan_id}) salvos no DB.")
    return str(plan_id)

async def get_markdown_document(stored_doc_id: str) -> Optional[str]:
    """Recupera o conteúdo Markdown do Azure Blob usando o ID do registro no DB."""
    try:
        doc_uuid = uuid.UUID(stored_doc_id)
    except ValueError:
        logger.error(f"ID de documento inválido fornecido para recuperação: {stored_doc_id}")
        return None

    async with (await get_db_pool()).connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT blob_path FROM processed_documents WHERE id = %s",
                (doc_uuid,)
            )
            record = await cur.fetchone()

    if not record:
        logger.warning(f"Nenhum documento encontrado com ID: {stored_doc_id}")
        return None

    blob_name = record['blob_path']
    if not blob_name:
        logger.error(f"Registro do DB para ID: {stored_doc_id} não tem blob_name (deveria ter).")
        return None
        
    logger.info(f"Markdown (ID: {stored_doc_id}) será recuperado do Azure Blob path: {blob_name}.")
    return await _download_from_azure(AZURE_MARKDOWN_CONTAINER, blob_name)

async def setup_document_storage():
    await init_document_table()
    if not AZURE_MARKDOWN_CONTAINER:
        logger.critical("AZURE_MARKDOWN_CONTAINER NÃO ESTÁ DEFINIDO. O ARMAZENAMENTO DE MARKDOWN NÃO FUNCIONARÁ.")
        raise EnvironmentError("AZURE_MARKDOWN_CONTAINER não está configurado.")
    else:
        logger.info(f"Armazenamento de planos de curso configurado para usar o container: {AZURE_MARKDOWN_CONTAINER}")
    
    if not AZURE_PLANS_CONTAINER:
        logger.critical("AZURE_PLANS_CONTAINER NÃO ESTÁ DEFINIDO. O ARMAZENAMENTO DE PLANOS NÃO FUNCIONARÁ.")
        raise EnvironmentError("AZURE_PLANS_CONTAINER não está configurado.")
    else:
        logger.info(f"Armazenamento de planos de ensino configurado para usar o container: {AZURE_PLANS_CONTAINER}")
        
async def get_plan_document(plan_id: str) -> Optional[str]:
    """Recupera o conteúdo JSON de um plano específico do Azure Blob usando o seu ID."""
    try:
        plan_uuid = uuid.UUID(plan_id)
    except ValueError:
        logger.error(f"ID de plano inválido fornecido para recuperação: {plan_id}")
        return None

    async with (await get_db_pool()).connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT blob_path FROM user_plans WHERE id = %s",
                (plan_uuid,)
            )
            record = await cur.fetchone()

    if not record:
        logger.warning(f"Nenhum plano encontrado com ID: {plan_id}")
        return None

    blob_name = record['blob_path']
    if not blob_name:
        logger.error(f"Registro do DB para o plano ID: {plan_id} não possui um caminho de blob (blob_path).")
        return None
        
    logger.info(f"Plano (ID: {plan_id}) será recuperado do Azure Blob path: {blob_name}.")
    
    return await _download_from_azure(AZURE_PLANS_CONTAINER, blob_name)

async def get_plan_document_with_metadata(plan_id: str) -> Optional[Dict[str, Any]]:
    """
    Recupera o conteúdo JSON de um plano do Azure Blob e seus metadados do banco de dados.
    """
    try:
        plan_uuid = uuid.UUID(plan_id)
    except ValueError:
        logger.error(f"ID de plano inválido fornecido para recuperação: {plan_id}")
        return None

    async with (await get_db_pool()).connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT blob_path, departamento_regional FROM user_plans WHERE id = %s",
                (plan_uuid,)
            )
            record = await cur.fetchone()

    if not record:
        logger.warning(f"Nenhum plano encontrado com ID: {plan_id}")
        return None

    blob_name = record['blob_path']
    departamento_regional = record['departamento_regional']
    
    if not blob_name:
        logger.error(f"Registro do DB para o plano ID: {plan_id} não possui um caminho de blob (blob_path).")
        return None

    plan_content = await _download_from_azure(AZURE_PLANS_CONTAINER, blob_name)
    if plan_content is None:
        return None

    return {
        "plan_content": plan_content,
        "departamento_regional": departamento_regional
    }
