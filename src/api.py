from io import BytesIO
import logging
import platform
import asyncio
import sys

# Correção para psycopg no Windows - precisa de SelectorEventLoop
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, File, HTTPException, Request, BackgroundTasks, Form, UploadFile
from fastapi.responses import FileResponse, StreamingResponse, RedirectResponse
import os
from dotenv import load_dotenv
from psycopg import AsyncConnection  # Adiciona esta importação
from psycopg.rows import dict_row # Adiciona dict_row
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from .agent import run_agent, get_checkpoint_connection, setup_tables, setup_checkpointer, initialize_agent, save_manual_plan_with_checkpoint
from src.database import init_db_pool, close_db_pool
from .document_store import setup_document_storage, store_markdown_document, store_plan_document, get_plan_document, get_plan_document_with_metadata, get_markdown_document
from .pdf_processor import convert_pdf_to_markdown, convert_pdf_bytes_to_text
from .docx_exporter import generate_docx
import json # Para carregar strings JSON
import uuid # Para gerar IDs
from docling.document_converter import DocumentConverter, DocumentStream
from .models.models import (
    RequestBody,
    GetThreadsRequest, GetThreadsResponse,
    ChatHistoryRequest, MessageInfo, ChatHistoryResponse,
    ThreadInfo, GetThreadsWithTitlesRequest, GetThreadsWithTitlesResponse,
    ModelConfigRequest,
    FullPlanDetailsResponse,
    PlanGenerationBodyWithStoredId, PlanGenerationResponse,
    SituacaoAprendizagemInput,
    GetPlansRequest, GetPlansResponse, GetPlanResponse, GetSinglePlanRequest, RenameThreadRequest, PlanSummary, UpdatePlanStatusRequest,
    SetDepartmentRequest, GetUserConfigResponse, ExportPlanByIdRequest,
    CreateUserRequest, AllUsersResponse, UserResponse, UserRoleResponse, MetricsResponse, MetricItem, DailyPlanCount,
    ManualPlanRequest, ArchivePlanRequest, PlanStatus, UserRole, TogglePublicRequest,
    NotificationResponse, NotificationListResponse, MarkAsReadRequest, NotificationType,
    PlanStatusHistoryEntry, PlanStatusHistoryResponse
)
from .models.job_models import JobStatus, JobCreateResponse, JobStatusResponse
from .models.didactic_resource_models import (
    GenerateResourceRequest, DidacticResourceResponse, 
    DidacticResourceListResponse, DidacticResourceJobResponse,
    ResourceStatus
)
from .models.slide_models import (
    GenerateSlidesRequest, SlideResourceResponse,
    SlideResourceListResponse, SlideResourceJobResponse,
    SlideResourceStatus
)
from .models.exercise_models import GenerateExercisesRequest
from .agents.exercises_agent import generate_exercises
from src.utils.utils import convert_markdown_to_json, convert_plan_json_to_markdown
from src.notification_service import notify_plan_submitted, notify_plan_status_change

from src.docling_converter import setup_optimized_converter

# Importa a middleware CORS <<<<<<----- ADICIONADO
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi import Depends

# Configuração específica para Windows
if platform.system() == 'Windows':
    from asyncio import WindowsSelectorEventLoopPolicy
    asyncio.set_event_loop_policy(WindowsSelectorEventLoopPolicy())

# Configuração do logging com cores
import colorlog

# Handler para arquivo (sem cores)
# file_handler = logging.FileHandler("logs/msep.log", encoding='utf-8')
# file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))

# Handler para console (com cores)
console_handler = colorlog.StreamHandler()
console_handler.setFormatter(colorlog.ColoredFormatter(
    '%(log_color)s%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    log_colors={
        'DEBUG': 'cyan',
        'INFO': 'green',
        'WARNING': 'yellow',
        'ERROR': 'red',
        'CRITICAL': 'bold_red',
    }
))

logging.basicConfig(
    level=logging.DEBUG,
    # handlers=[file_handler, console_handler]
    handlers=[console_handler]
)
logger = logging.getLogger(__name__)

# Carrega variáveis do .env
load_dotenv()

app = FastAPI(title="Assistente Virtual MSEP API", description="API assíncrona do Assistente Virtual da MSEP com Gemini e PostgreSQL, usando Langgraph e Langchain", version="1.0")

# --- CONFIGURAÇÃO DO CORS --- <<<<<<----- ADICIONADO
# Lista de origens permitidas. "*" permite qualquer origem.
# Para produção, é MAIS SEGURO listar explicitamente as origens do seu frontend:
origins = [
    os.getenv("CORS_ALLOWED_ORIGIN", "https://assistentemsep.senai.br"),
    "http://localhost:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  # Permite as origens definidas acima
    allow_credentials=False, # Permite cookies/credenciais (se necessário) -> CUIDADO: Se True, origins não pode ser ["*"]! Mude para False se usar ["*"] ou liste origens específicas. Vamos usar False com ["*"].
    allow_methods=["*"],    # Permite todos os métodos (GET, POST, etc.)
    allow_headers=["*"],    # Permite todos os cabeçalhos
)

API_SECRET_TOKEN = os.getenv("API_SECRET_TOKEN")
if not API_SECRET_TOKEN:
    raise ValueError("API_SECRET_TOKEN não está configurado no ambiente.")

security = HTTPBearer()

async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    if credentials.scheme != "Bearer" or credentials.credentials != API_SECRET_TOKEN:
        raise HTTPException(
            status_code=401,
            detail="Token inválido ou não fornecido.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return credentials.credentials

# --- FIM DA CONFIGURAÇÃO DO CORS ---

doc_converter: DocumentConverter = None

from .rag_service import init_rag # Importa serviço de RAG

@app.on_event("startup")
async def startup_event():
    global doc_converter
    
    # Configuração crítica para evitar erros de symlink ao baixar modelos do Hugging Face via docling.
    # Desabilita avisos de symlink e tenta forçar o não uso de symlinks no cache.
    os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
    os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "0"
    
    logger.info("Inicializando o backend...")
    await init_db_pool() # Inicializa o pool de conexões
    doc_converter = setup_optimized_converter()
    await setup_checkpointer()
    await setup_tables()
    await setup_document_storage()
    await initialize_agent()
    await init_rag() # Inicializa o índice vetorial MSEP
    logger.info("Eventos de startup concluídos.")

@app.on_event("shutdown")
async def shutdown_event():
    await close_db_pool() # Fecha o pool de conexões
    logger.info("Eventos de shutdown concluídos.")

@app.post("/chat", response_model=JobCreateResponse, dependencies=[Depends(verify_token)])
async def process_message(body: RequestBody, background_tasks: BackgroundTasks):
    """
    Inicia o processamento assíncrono de uma mensagem de chat.
    Retorna imediatamente com um job_id para consulta posterior.
    """
    job_id = str(uuid.uuid4())
    logger.info(f"Endpoint /chat chamado. Job {job_id} criado para user: {body.userId}")

    # Payload para armazenar no banco
    request_payload = {
        "type": "chat",
        "message": body.message,
        "user_id": body.userId,
        "thread_id": body.threadId,
    }

    # Salvar job no banco de dados
    try:
        async with (await get_checkpoint_connection()).connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    INSERT INTO generation_jobs (job_id, user_id, thread_id, status, progress, current_step, request_payload)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (job_id, body.userId, body.threadId, JobStatus.pending.value, 0, "Iniciando...", json.dumps(request_payload))
                )
    except Exception as e:
        logger.error(f"Erro ao criar job de chat {job_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro ao iniciar processamento da mensagem.")

    # Adicionar tarefa em background
    background_tasks.add_task(process_chat_message, job_id, request_payload)

    return JobCreateResponse(
        job_id=job_id,
        status=JobStatus.pending,
        message="Processamento iniciado. Use GET /chat/status/{job_id} para acompanhar."
    )


async def process_chat_message(job_id: str, request_payload: dict):
    """
    Função de background que processa a mensagem de chat.
    """
    logger.info(f"Processamento do job de chat {job_id} iniciado.")
    
    async def update_job_status(status: str, progress: int, current_step: str = None, result: dict = None, error: str = None):
        try:
            async with (await get_checkpoint_connection()).connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        UPDATE generation_jobs 
                        SET status = %s, progress = %s, current_step = %s, result = %s, error = %s, updated_at = CURRENT_TIMESTAMP
                        WHERE job_id = %s
                        """,
                        (status, progress, current_step, json.dumps(result) if result else None, error, job_id)
                    )
        except Exception as e:
            logger.error(f"Erro ao atualizar status do job de chat {job_id}: {e}")
    
    try:
        await update_job_status(JobStatus.processing.value, 30, "Processando mensagem...")
        
        result = await run_agent(
            input_command_or_message=request_payload["message"],
            user_id=request_payload["user_id"],
            thread_id=request_payload["thread_id"],
        )
        
        await update_job_status(JobStatus.processing.value, 90, "Finalizando...")
        
        response_data = {
            "message": result["response"], 
            "title": result["title"],
            "user_id": request_payload["user_id"], 
            "thread_id": request_payload["thread_id"]
        }
        
        await update_job_status(JobStatus.completed.value, 100, "Concluído", result=response_data)
        logger.info(f"Job de chat {job_id} concluído com sucesso.")
        
    except Exception as e:
        logger.error(f"Erro no processamento do job de chat {job_id}: {e}", exc_info=True)
        await update_job_status(JobStatus.failed.value, 0, "Falhou", error=str(e))


@app.post("/chat/upload", response_model=JobCreateResponse, dependencies=[Depends(verify_token)])
async def chat_with_upload(
    message: str = Form(""),
    userId: str = Form(...),
    threadId: str = Form(...),
    files: List[UploadFile] = File(...),
    background_tasks: BackgroundTasks = None
):
    """
    Inicia o processamento assíncrono de uma mensagem com arquivos.
    Retorna imediatamente com um job_id para consulta posterior.
    O processamento do Docling acontece em background.
    """
    job_id = str(uuid.uuid4())
    logger.info(f"Endpoint /chat/upload chamado. Job {job_id} criado para user: {userId}")

    # Ler os bytes dos arquivos RAPIDAMENTE (apenas leitura, sem processamento)
    files_data = []
    for file in files:
        try:
            content = await file.read()
            files_data.append({
                "filename": file.filename,
                "content": content  # bytes
            })
        except Exception as e:
            logger.error(f"Erro ao ler o arquivo {file.filename}: {e}", exc_info=True)
            files_data.append({
                "filename": file.filename,
                "content": None,
                "error": str(e)
            })

    # Payload para armazenar no banco (sem o conteúdo dos arquivos, é muito grande)
    request_payload = {
        "type": "chat_upload",
        "message": message,
        "user_id": userId,
        "thread_id": threadId,
    }

    # Salvar job no banco de dados
    try:
        async with (await get_checkpoint_connection()).connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    INSERT INTO generation_jobs (job_id, user_id, thread_id, status, progress, current_step, request_payload)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (job_id, userId, threadId, JobStatus.pending.value, 0, "Iniciando processamento dos arquivos...", json.dumps(request_payload))
                )
    except Exception as e:
        logger.error(f"Erro ao criar job de chat/upload {job_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro ao iniciar processamento.")

    # Adicionar tarefa em background - passando os bytes dos arquivos
    background_tasks.add_task(process_chat_upload, job_id, request_payload, files_data)

    return JobCreateResponse(
        job_id=job_id,
        status=JobStatus.pending,
        message="Processamento iniciado. Use GET /chat/status/{job_id} para acompanhar."
    )


async def process_chat_upload(job_id: str, request_payload: dict, files_data: list):
    """
    Função de background que processa mensagem com upload de arquivos.
    O processamento do Docling acontece aqui, em background.
    """
    logger.info(f"Processamento do job de chat/upload {job_id} iniciado.")
    
    async def update_job_status(status: str, progress: int, current_step: str = None, result: dict = None, error: str = None):
        try:
            async with (await get_checkpoint_connection()).connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        UPDATE generation_jobs 
                        SET status = %s, progress = %s, current_step = %s, result = %s, error = %s, updated_at = CURRENT_TIMESTAMP
                        WHERE job_id = %s
                        """,
                        (status, progress, current_step, json.dumps(result) if result else None, error, job_id)
                    )
        except Exception as e:
            logger.error(f"Erro ao atualizar status do job de chat/upload {job_id}: {e}")
    
    try:
        await update_job_status(JobStatus.processing.value, 10, "Processando arquivos com Docling...")
        
        # Processar arquivos com Docling AQUI, em background
        file_contents = []
        total_files = len(files_data)
        for idx, file_info in enumerate(files_data):
            filename = file_info["filename"]
            content = file_info.get("content")
            
            if content is None:
                file_contents.append(f"--- Erro ao ler o arquivo {filename} ---")
                continue
                
            try:
                progress = 10 + int((idx / total_files) * 40)  # 10-50%
                await update_job_status(JobStatus.processing.value, progress, f"Processando {filename}...")
                
                bytes_io_object = BytesIO(content)
                stream = DocumentStream(stream=bytes_io_object, source=filename, name=filename)
                # Executa a conversão síncrona em uma thread separada para não bloquear o event loop
                result = await asyncio.to_thread(doc_converter.convert, stream)
                text_content = result.document.export_to_text()
                file_contents.append(f"--- Conteúdo do arquivo {filename} ---\n{text_content}")
                logger.info(f"Arquivo {filename} processado com sucesso no job {job_id}")
            except Exception as e:
                logger.error(f"Erro ao processar o arquivo {filename} com docling no job {job_id}: {e}", exc_info=True)
                file_contents.append(f"--- Erro ao processar o arquivo {filename} ---")

        document_content = "\n\n".join(file_contents)
        
        await update_job_status(JobStatus.processing.value, 60, "Analisando documento com IA...")
        
        input_para_agente = f"CMD_ANALYZE_DOCUMENT:{request_payload['message']}"
        initial_payload = {
            "document_content": document_content
        }

        result = await run_agent(
            input_command_or_message=input_para_agente,
            user_id=request_payload["user_id"],
            thread_id=request_payload["thread_id"],
            initial_payload=initial_payload
        )
        
        await update_job_status(JobStatus.processing.value, 90, "Finalizando...")
        
        response_data = {
            "message": result["response"],
            "title": result["title"],
            "user_id": request_payload["user_id"],
            "thread_id": request_payload["thread_id"]
        }
        
        await update_job_status(JobStatus.completed.value, 100, "Concluído", result=response_data)
        logger.info(f"Job de chat/upload {job_id} concluído com sucesso.")
        
    except Exception as e:
        logger.error(f"Erro no processamento do job de chat/upload {job_id}: {e}", exc_info=True)
        await update_job_status(JobStatus.failed.value, 0, "Falhou", error=str(e))


@app.get("/chat/status/{job_id}", response_model=JobStatusResponse, dependencies=[Depends(verify_token)])
async def get_chat_status(job_id: str):
    """
    Retorna o status atual de um job de chat (chat ou chat/upload).
    """
    logger.info(f"Consultando status do job de chat: {job_id}")
    
    try:
        async with (await get_checkpoint_connection()).connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    "SELECT job_id, status, progress, current_step, result, error FROM generation_jobs WHERE job_id = %s",
                    (job_id,)
                )
                record = await cur.fetchone()
        
        if not record:
            raise HTTPException(status_code=404, detail=f"Job {job_id} não encontrado.")
        
        return JobStatusResponse(
            job_id=str(record['job_id']),
            status=JobStatus(record['status']),
            progress=record['progress'],
            current_step=record['current_step'],
            result=record['result'],
            error=record['error']
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao consultar status do job de chat {job_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro ao consultar status do job.")


@app.get("/health", response_model=dict)
async def health_check():
    try:
        logger.info("Health check solicitado")
        return {"status": "servidor rodando"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@app.post("/get_threads", response_model=GetThreadsResponse, dependencies=[Depends(verify_token)])
async def get_threads(body: GetThreadsRequest):
    try:
        logger.info(f"Endpoint get_threads solicitado para user_id: {body.userId}")
        async with (await get_checkpoint_connection()).connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                query = """
                SELECT DISTINCT thread_id 
                FROM checkpoints 
                WHERE (metadata->>'user_id') = %s
                """
                await cur.execute(query, (body.userId,))
                thread_ids = [row['thread_id'] async for row in cur]
        
        return GetThreadsResponse(
            userId=body.userId,
            all_threads=thread_ids
        )
    except Exception as e:
        logger.error(f"Erro ao recuperar threads: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/chat_history", response_model=ChatHistoryResponse, dependencies=[Depends(verify_token)])
async def get_chat_history(body: ChatHistoryRequest):
    try:
        logger.info(f"Endpoint chat_history solicitado para thread_id: {body.threadId}")
        conn = await get_checkpoint_connection() # Agora retorna o POOL
        # AsyncPostgresSaver(conn=pool) deve funcionar conforme documentação recente de LangGraph/LangChain
        checkpointer = AsyncPostgresSaver(conn=conn)
        
        config = {"configurable": {"thread_id": body.threadId}}
        checkpoint_tuple = await checkpointer.aget_tuple(config)
        
        if not checkpoint_tuple or 'messages' not in checkpoint_tuple.checkpoint['channel_values']:
            return ChatHistoryResponse(threadId=body.threadId, messages=[],title=None)
        
        messages = checkpoint_tuple.checkpoint['channel_values']['messages']
        title = checkpoint_tuple.checkpoint['channel_values'].get('title')
        
        # Recuperar timestamps históricos para as mensagens
        message_timestamps = {} # Map index -> timestamp
        
        # Itera sobre todos os checkpoints para encontrar quando cada mensagem apareceu pela primeira vez
        async for hist_tuple in checkpointer.alist(config):
            chk = hist_tuple.checkpoint
            ts = chk.get('ts')
            if not ts: continue
            
            hist_msgs = chk.get('channel_values', {}).get('messages', [])
            if not isinstance(hist_msgs, list): continue
            
            # Para cada mensagem neste checkpoint, registramos o timestamp se for o mais antigo visto para esse índice
            for i in range(len(hist_msgs)):
                if i not in message_timestamps or ts < message_timestamps[i]:
                    message_timestamps[i] = ts

        extracted_messages = [
            MessageInfo(
                type=type(msg).__name__,
                content=msg if isinstance(msg, str) else msg.content,
                additional_info={
                    "id": getattr(msg, 'id', None),
                    **({"tool_calls": msg.tool_calls} if hasattr(msg, 'tool_calls') else {}),
                    **({"tool_call_id": msg.tool_call_id} if hasattr(msg, 'tool_call_id') else {})
                },
                timestamp=message_timestamps.get(idx)
            ) for idx, msg in enumerate(messages)
        ]
        
        # Não fechamos a conexão pois é o pool global
        return ChatHistoryResponse(
            threadId=body.threadId,
            messages=extracted_messages,
            title=title
        )
    except Exception as e:
        logger.error(f"Erro ao recuperar histórico de chat: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/get_threads_with_titles", response_model=GetThreadsWithTitlesResponse, dependencies=[Depends(verify_token)])
async def get_threads_with_titles(body: GetThreadsWithTitlesRequest):
    try:
        logger.info(f"Endpoint get_threads_with_titles solicitado para user_id: {body.userId}")
        async with (await get_checkpoint_connection()).connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                # Define the pattern for the LIKE clause separately
                thread_id_exclude_pattern = "op_extract_full_plan_details%"
                
                query = """
                SELECT thread_id, (checkpoint->'channel_values'->>'title') AS title
                FROM (
                    SELECT 
                        thread_id, 
                        checkpoint,
                        ROW_NUMBER() OVER (PARTITION BY thread_id ORDER BY (metadata->>'step')::int DESC) AS rn
                    FROM checkpoints
                    WHERE (metadata->>'user_id') = %s
                ) t
                WHERE rn = 1
                AND thread_id NOT LIKE %s;
                """
                await cur.execute(query, (body.userId,thread_id_exclude_pattern))
                threads = [
                    ThreadInfo(thread_id=row['thread_id'], title=row['title'])
                    async for row in cur
                ]
        
        return GetThreadsWithTitlesResponse(
            userId=body.userId,
            threads=threads
        )
    except Exception as e:
        logger.error(f"Erro ao recuperar threads com títulos: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/delete_thread/{thread_id}", dependencies=[Depends(verify_token)])
async def delete_thread(thread_id: str, user_id: str = Form(...)):
    try:
        logger.info(f"Endpoint delete_thread solicitado para thread_id: {thread_id} e user_id: {user_id}")
        async with (await get_checkpoint_connection()).connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                # Verifica se o thread_id pertence ao user_id
                query_check = """
                SELECT EXISTS (
                    SELECT 1 FROM checkpoints 
                    WHERE thread_id = %s AND (metadata->>'user_id') = %s
                ) as exists_flag
                """
                await cur.execute(query_check, (thread_id, user_id))
                result = await cur.fetchone()
                if not result['exists_flag']:
                    raise HTTPException(status_code=404, detail="Thread not found for this user")

                # Exclui o thread
                query_delete = """
                DELETE FROM checkpoints 
                WHERE thread_id = %s AND (metadata->>'user_id') = %s
                """
                await cur.execute(query_delete, (thread_id, user_id))
                await conn.commit()

        return {"message": "Thread deleted successfully", "thread_id": thread_id}
    except Exception as e:
        logger.error(f"Erro ao excluir thread: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    
@app.post("/configure_model", dependencies=[Depends(verify_token)])
async def configure_model(config: ModelConfigRequest):
    try:
        logger.info(f"Endpoint configure_model solicitado para user_id: {config.user_id}, temperature={config.temperature}, top_p={config.top_p}")
        
        # Atualiza o banco de dados
        async with (await get_checkpoint_connection()).connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                query = """
                INSERT INTO user_configs (user_id, temperature, top_p)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE
                SET temperature = EXCLUDED.temperature,
                    top_p = EXCLUDED.top_p,
                    updated_at = CURRENT_TIMESTAMP
                """
                await cur.execute(query, (config.user_id, config.temperature, config.top_p))

        return {
            "message": "Model configuration updated successfully for user",
            "user_id": config.user_id,
            "temperature": config.temperature,
            "top_p": config.top_p
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Erro ao configurar modelo para user_id {config.user_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    
@app.post("/pdf/extract_full_details", response_model=JobCreateResponse, dependencies=[Depends(verify_token)])
async def pdf_extract_full_plan_details(
    file: UploadFile = File(..., description="Arquivo PDF do plano de curso completo."),
    user_id: str = Form(..., description="ID do usuário."),
    thread_id: str = Form(..., description="ID da conversa/sessão original para associar o documento."),
    original_pdf_filename: Optional[str] = Form(None, description="Nome original do arquivo PDF (opcional)."),
    background_tasks: BackgroundTasks = None
):
    """
    Inicia a extração assíncrona de detalhes de um plano de curso em PDF.
    Retorna imediatamente com um job_id para consulta posterior.
    """
    operation_description = "extract_full_plan_details"
    effective_filename = original_pdf_filename or file.filename or "unknown.pdf"
    job_id = str(uuid.uuid4())
    
    logger.info(f"Endpoint /{operation_description} chamado. Job {job_id} criado para user: {user_id}, thread_orig: {thread_id}, file: {effective_filename}")
    
    if not file.content_type == "application/pdf":
        raise HTTPException(status_code=400, detail="Tipo de arquivo inválido. Apenas PDF é aceito.")

    # Verificar se já existe documento com mesmo filename para este usuário
    async with (await get_checkpoint_connection()).connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT id FROM processed_documents WHERE user_id = %s AND original_pdf_filename = %s",
                (user_id, effective_filename)
            )
            existing = await cur.fetchone()
            if existing:
                raise HTTPException(
                    status_code=409, 
                    detail=f"Plano de curso '{effective_filename}' já foi processado. Use a opção 'Usar plano já processado' para reutilizá-lo."
                )

    try:
        # Ler os bytes do arquivo ANTES de retornar (UploadFile não pode ser lido em background)
        file_bytes = await file.read()
        if not file_bytes:
            raise HTTPException(status_code=400, detail=f"Arquivo PDF '{effective_filename}' está vazio.")
        
        # Payload para guardar no banco e usar no processamento
        request_payload = {
            "user_id": user_id,
            "thread_id": thread_id,
            "effective_filename": effective_filename,
        }

        # Salvar job no banco de dados
        async with (await get_checkpoint_connection()).connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    INSERT INTO generation_jobs (job_id, user_id, thread_id, status, progress, current_step, request_payload)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (job_id, user_id, thread_id, JobStatus.pending.value, 0, "Iniciando extração...", json.dumps(request_payload))
                )
        
        # Adicionar tarefa em background
        background_tasks.add_task(process_pdf_extraction, job_id, request_payload, file_bytes)

        return JobCreateResponse(
            job_id=job_id,
            status=JobStatus.pending,
            message="Extração de PDF iniciada. Use GET /pdf/extract_status/{job_id} para acompanhar o progresso."
        )

    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Erro ao criar job de extração de PDF {job_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro ao iniciar extração do PDF.")


async def process_pdf_extraction(job_id: str, request_payload: dict, file_bytes: bytes):
    """
    Função de background que processa a extração de detalhes do PDF.
    Atualiza o status no banco de dados conforme progride.
    """
    logger.info(f"Processamento do job de extração de PDF {job_id} iniciado.")
    operation_description = "extract_full_plan_details"
    effective_filename = request_payload["effective_filename"]
    user_id = request_payload["user_id"]
    thread_id = request_payload["thread_id"]
    
    async def update_job_status(status: str, progress: int, current_step: str = None, result: dict = None, error: str = None):
        try:
            async with (await get_checkpoint_connection()).connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        UPDATE generation_jobs 
                        SET status = %s, progress = %s, current_step = %s, result = %s, error = %s, updated_at = CURRENT_TIMESTAMP
                        WHERE job_id = %s
                        """,
                        (status, progress, current_step, json.dumps(result) if result else None, error, job_id)
                    )
        except Exception as e:
            logger.error(f"Erro ao atualizar status do job de extração PDF {job_id}: {e}")
    
    try:
        await update_job_status(JobStatus.processing.value, 10, "Convertendo PDF para texto...")
        
        # Converter PDF para texto
        try:
            markdown_content = convert_pdf_bytes_to_text(file_bytes, effective_filename)
        except ValueError as ve:
            raise Exception(str(ve))
        
        await update_job_status(JobStatus.processing.value, 30, "Extraindo informações do plano de curso...")
        
        # Cria um thread_id único para a operação do agente LangGraph
        agent_operation_thread_id = f"op_{operation_description}_{uuid.uuid4().hex[:12]}"

        agent_initial_payload = {
            "user_id": user_id,
            "thread_id": agent_operation_thread_id,
            "pdf_markdown_content": markdown_content,
            "messages": []
        }
        
        await update_job_status(JobStatus.processing.value, 40, "Analisando documento com IA...")
        
        # Chamar o agente
        agent_result_dict = await run_agent(
            input_command_or_message=f"CMD_EXTRACT_FULL_PLAN_DETAILS:{effective_filename}",
            user_id=user_id,
            thread_id=agent_operation_thread_id,
            initial_payload=agent_initial_payload
        )
        
        await update_job_status(JobStatus.processing.value, 80, "Processando resultado...")
        
        full_details_json_str = agent_result_dict.get("response")
        if not full_details_json_str:
            raise Exception("Agente não retornou os detalhes completos do plano extraído.")
        
        logger.debug(f"Tentando fazer parse do JSON retornado pela ferramenta: {full_details_json_str[:500]}...")
        
        try:
            extracted_details = json.loads(full_details_json_str)
        except json.JSONDecodeError as json_err:
            logger.error(f"Resposta da ferramenta {operation_description} não é JSON válido: {json_err}")
            raise Exception(f"Resposta inválida da ferramenta de extração: {json_err}")
        
        await update_job_status(JobStatus.processing.value, 90, "Armazenando documento...")
        
        # Armazena o documento
        stored_doc_id = await store_markdown_document(
            user_id=user_id,
            thread_id=thread_id,
            markdown_content=full_details_json_str,
            original_pdf_filename=effective_filename
        )
        logger.info(f"Markdown para '{effective_filename}' ({operation_description}) armazenado com ID: {stored_doc_id}")
        
        # Preparar resultado final
        result = {
            "stored_markdown_id": stored_doc_id,
            "user_id": user_id,
            "thread_id": thread_id,
            "original_pdf_filename": effective_filename,
            "nomeCurso": extracted_details.get("nomeCurso"),
            "unidadesCurriculares": extracted_details.get("unidadesCurriculares", [])
        }
        
        await update_job_status(JobStatus.completed.value, 100, "Concluído", result=result)
        logger.info(f"Job de extração de PDF {job_id} concluído com sucesso.")
        
    except Exception as e:
        logger.error(f"Erro no processamento do job de extração de PDF {job_id}: {e}", exc_info=True)
        await update_job_status(JobStatus.failed.value, 0, "Falhou", error=str(e))


@app.get("/pdf/extract_status/{job_id}", response_model=JobStatusResponse, dependencies=[Depends(verify_token)])
async def get_pdf_extraction_status(job_id: str):
    """
    Retorna o status atual de um job de extração de PDF.
    """
    logger.info(f"Consultando status do job de extração PDF: {job_id}")
    
    try:
        async with (await get_checkpoint_connection()).connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    "SELECT job_id, status, progress, current_step, result, error FROM generation_jobs WHERE job_id = %s",
                    (job_id,)
                )
                record = await cur.fetchone()
        
        if not record:
            raise HTTPException(status_code=404, detail=f"Job {job_id} não encontrado.")
        
        return JobStatusResponse(
            job_id=str(record['job_id']),
            status=JobStatus(record['status']),
            progress=record['progress'],
            current_step=record['current_step'],
            result=record['result'],
            error=record['error']
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao consultar status do job de extração PDF {job_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro ao consultar status do job.")


# ============================================================================
# ENDPOINTS PARA REUTILIZAÇÃO DE DOCUMENTOS PROCESSADOS
# ============================================================================

@app.get("/processed_documents", dependencies=[Depends(verify_token)])
async def list_processed_documents(user_id: str):
    """
    Lista planos de curso já processados para o usuário.
    Retorna apenas o mais recente de cada original_pdf_filename.
    """
    logger.info(f"Endpoint /processed_documents chamado para user_id: {user_id}")
    
    try:
        async with (await get_checkpoint_connection()).connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                # DISTINCT ON retorna apenas o registro mais recente para cada filename
                await cur.execute(
                    """
                    SELECT DISTINCT ON (original_pdf_filename) 
                        id, original_pdf_filename, created_at
                    FROM processed_documents 
                    WHERE user_id = %s AND original_pdf_filename IS NOT NULL
                    ORDER BY original_pdf_filename, created_at DESC
                    """,
                    (user_id,)
                )
                records = await cur.fetchall()
        
        return {
            "documents": [
                {
                    "id": str(record["id"]),
                    "original_pdf_filename": record["original_pdf_filename"],
                    "created_at": record["created_at"].isoformat() if record["created_at"] else None
                }
                for record in records
            ]
        }
    except Exception as e:
        logger.error(f"Erro ao listar documentos processados para user {user_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro ao listar documentos processados.")


@app.get("/processed_documents/{doc_id}", dependencies=[Depends(verify_token)])
async def get_processed_document(doc_id: str):
    """
    Retorna o conteúdo JSON completo de um documento processado.
    Usado para carregar plano de curso já processado anteriormente.
    """
    logger.info(f"Endpoint /processed_documents/{doc_id} chamado")
    
    try:
        # Buscar o conteúdo do GCS usando a função existente
        content = await get_markdown_document(doc_id)
        
        if not content:
            raise HTTPException(status_code=404, detail=f"Documento {doc_id} não encontrado.")
        
        # Parse do JSON armazenado
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            raise HTTPException(status_code=500, detail="Erro ao decodificar conteúdo do documento.")
        
        # Retorna no formato esperado pelo frontend (FullPlanDetailsResponse)
        return {
            "stored_markdown_id": doc_id,
            "nomeCurso": data.get("nomeCurso"),
            "unidadesCurriculares": data.get("unidadesCurriculares", [])
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao recuperar documento processado {doc_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro ao recuperar documento processado.")


@app.post("/teaching_plan/generate", response_model=JobCreateResponse, dependencies=[Depends(verify_token)])
async def generate_teaching_plan(
    body: PlanGenerationBodyWithStoredId,
    background_tasks: BackgroundTasks
):
    """
    Inicia a geração assíncrona de um plano de ensino.
    Retorna imediatamente com um job_id para consulta posterior.
    """
    operation_description = "generate_teaching_plan"
    job_id = str(uuid.uuid4())
    logger.info(f"Endpoint /{operation_description} chamado. Job {job_id} criado para stored_id: {body.stored_markdown_id} por user: {body.user_id}")

    # Converter Pydantic models para dicts para armazenar no banco
    horarios_list_of_dicts = [h.model_dump() for h in body.horarios] if body.horarios else []
    situacoes_aprendizagem_list_of_dicts = []
    if body.situacoes_aprendizagem:
        for sa_input_model in body.situacoes_aprendizagem:
            situacoes_aprendizagem_list_of_dicts.append(sa_input_model.model_dump())

    # Payload completo da requisição para guardar no banco
    request_payload = {
        "stored_markdown_id": body.stored_markdown_id,
        "user_id": body.user_id,
        "thread_id": body.thread_id,
        "docente": body.docente,
        "escola": body.escola,
        "departamento_regional": body.departamento_regional,
        "curso": body.curso,
        "turma": body.turma,
        "modalidade": body.modalidade,
        "uc": body.uc,
        "data_inicio": body.data_inicio,
        "data_fim": body.data_fim,
        "situacoes_aprendizagem": situacoes_aprendizagem_list_of_dicts,
        "horarios": horarios_list_of_dicts,
    }

    # Salvar job no banco de dados
    try:
        async with (await get_checkpoint_connection()).connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    INSERT INTO generation_jobs (job_id, user_id, thread_id, status, progress, current_step, request_payload)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (job_id, body.user_id, body.thread_id, JobStatus.pending.value, 0, "Iniciando...", json.dumps(request_payload))
                )
    except Exception as e:
        logger.error(f"Erro ao criar job {job_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro ao iniciar geração do plano.")

    # Adicionar tarefa em background
    background_tasks.add_task(process_plan_generation, job_id, request_payload)

    return JobCreateResponse(
        job_id=job_id,
        status=JobStatus.pending,
        message="Geração de plano iniciada. Use GET /teaching_plan/status/{job_id} para acompanhar o progresso."
    )


async def process_plan_generation(job_id: str, request_payload: dict):
    """
    Função de background que processa a geração do plano.
    Atualiza o status no banco de dados conforme progride.
    """
    logger.info(f"Processamento do job {job_id} iniciado.")
    
    async def update_job_status(status: str, progress: int, current_step: str = None, result: dict = None, error: str = None):
        try:
            async with (await get_checkpoint_connection()).connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        UPDATE generation_jobs 
                        SET status = %s, progress = %s, current_step = %s, result = %s, error = %s, updated_at = CURRENT_TIMESTAMP
                        WHERE job_id = %s
                        """,
                        (status, progress, current_step, json.dumps(result) if result else None, error, job_id)
                    )
        except Exception as e:
            logger.error(f"Erro ao atualizar status do job {job_id}: {e}")
    
    try:
        await update_job_status(JobStatus.processing.value, 10, "Preparando dados...")
        
        # Preparar payload para o agente
        agent_initial_payload = {
            "user_id": request_payload["user_id"],
            "thread_id": request_payload["thread_id"],
            "stored_markdown_id": request_payload["stored_markdown_id"],
            "plan_docente": request_payload["docente"],
            "plan_unidade_operacional": request_payload["escola"],
            "plan_departamento_regional": request_payload["departamento_regional"],
            "plan_nome_curso": request_payload["curso"],
            "plan_turma": request_payload["turma"],
            "plan_modalidade": request_payload.get("modalidade", "Presencial"),
            "plan_nome_uc": request_payload["uc"],
            "plan_data_inicio": request_payload["data_inicio"],
            "plan_data_fim": request_payload["data_fim"],
            "plan_situacoes_aprendizagem": request_payload["situacoes_aprendizagem"],
            "plan_horarios": request_payload["horarios"],
            "messages": [],
        }
        
        await update_job_status(JobStatus.processing.value, 20, "Executando agente de geração...")
        
        # Chamar o agente
        agent_result_dict = await run_agent(
            input_command_or_message=f"CMD_GENERATE_TEACHING_PLAN:doc_id={request_payload['stored_markdown_id']}",
            user_id=request_payload["user_id"],
            thread_id=request_payload["thread_id"],
            initial_payload=agent_initial_payload
        )
        
        await update_job_status(JobStatus.processing.value, 80, "Processando resultado...")
        
        plan_markdown_json_str = agent_result_dict.get("response")
        if not plan_markdown_json_str:
            raise Exception("Agente não retornou resposta.")
            
        plan_data = json.loads(plan_markdown_json_str)
        
        if "error" in plan_data:
            raise Exception(plan_data.get('details', plan_data.get('error', 'Erro desconhecido')))
        
        # Extrair e salvar tokens da geração do plano
        input_tokens = plan_data.get("input_tokens", 0)
        output_tokens = plan_data.get("output_tokens", 0)
        if input_tokens > 0 or output_tokens > 0:
            try:
                from src.utils.token_tracker import TokenUsage, upsert_thread_tokens
                tokens = TokenUsage(input_tokens=input_tokens, output_tokens=output_tokens)
                async with (await get_checkpoint_connection()).connection() as conn:
                    await upsert_thread_tokens(
                        conn,
                        request_payload["thread_id"],
                        request_payload["user_id"],
                        tokens
                    )
                logger.info(f"Tokens salvos para geração de plano: {input_tokens} entrada, {output_tokens} saída")
            except Exception as e_tokens:
                logger.error(f"Erro ao salvar tokens da geração de plano: {e_tokens}", exc_info=True)
                # Não propaga o erro - tracking de tokens não deve quebrar o fluxo principal
        
        # Compatibilidade: suporta tanto plan_json (novo) quanto plan_markdown (legado)
        if "plan_json" in plan_data:
            # Novo formato: converter JSON estruturado para Markdown
            plan_json = plan_data["plan_json"]
            plan_markdown = convert_plan_json_to_markdown(plan_json)
            logger.info("Convertido plan_json para Markdown para compatibilidade com frontend.")
        else:
            # Formato legado: usar plan_markdown diretamente
            plan_markdown = plan_data.get("plan_markdown", "")
        
        plan_markdown_with_warning = plan_markdown + "\n\n⚠️ Este Plano de Ensino foi gerado por IA e deve ser avaliado por um docente."
        
        result = {
            "userId": request_payload["user_id"],
            "threadId": request_payload["thread_id"],
            "plan_markdown": plan_markdown_with_warning
        }
        
        await update_job_status(JobStatus.completed.value, 100, "Concluído", result=result)
        logger.info(f"Job {job_id} concluído com sucesso.")
        
    except Exception as e:
        logger.error(f"Erro no processamento do job {job_id}: {e}", exc_info=True)
        await update_job_status(JobStatus.failed.value, 0, "Falhou", error=str(e))


@app.get("/teaching_plan/status/{job_id}", response_model=JobStatusResponse, dependencies=[Depends(verify_token)])
async def get_plan_generation_status(job_id: str):
    """
    Retorna o status atual de um job de geração de plano.
    """
    logger.info(f"Consultando status do job: {job_id}")
    
    try:
        async with (await get_checkpoint_connection()).connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    "SELECT job_id, status, progress, current_step, result, error FROM generation_jobs WHERE job_id = %s",
                    (job_id,)
                )
                record = await cur.fetchone()
        
        if not record:
            raise HTTPException(status_code=404, detail=f"Job {job_id} não encontrado.")
        
        return JobStatusResponse(
            job_id=str(record['job_id']),
            status=JobStatus(record['status']),
            progress=record['progress'],
            current_step=record['current_step'],
            result=record['result'],
            error=record['error']
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao consultar status do job {job_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro ao consultar status do job.")

@app.get("/plans", response_model=GetPlansResponse, dependencies=[Depends(verify_token)])
async def get_plans_unified(user_id: str):
    """
    Recupera uma lista de resumos de planos de ensino com base na role do usuário.
    - Docente: vê apenas seus próprios planos.
    - Coordenador: vê todos os planos de sua escola.
    - Administrador Regional: vê todos os planos de seu departamento.
    - Administrador Nacional: vê todos os planos do sistema.
    """
    logger.info(f"Endpoint /plans (unificado) solicitado por user_id: {user_id}")
    try:
        async with (await get_checkpoint_connection()).connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur: # Usando dict_row
                role, user_school, user_department = await _get_user_info(user_id, conn)

                # Base query with LEFT JOIN to thread_tokens for token metrics
                query_base = """
                    SELECT up.id, up.thread_id, up.summary, up.departamento_regional, up.escola, up.docente, 
                           up.curso, up.data_inicio, up.data_fim, up.status, up.arquivado, up.publico,
                           tt.input_tokens, tt.output_tokens
                    FROM user_plans up
                    LEFT JOIN thread_tokens tt ON up.thread_id = tt.thread_id
                """
                params = ()

                if role == UserRole.docente.value:
                    query = f"{query_base} WHERE up.user_id = %s ORDER BY up.created_at DESC"
                    params = (user_id,)
                elif role == UserRole.coordenador.value:
                    if not user_school:
                        raise HTTPException(status_code=400, detail="Coordenador não está associado a uma escola.")
                    query = f"{query_base} WHERE up.escola = %s ORDER BY up.created_at DESC"
                    params = (user_school,)
                elif role == UserRole.administracao_regional.value:
                    if not user_department:
                        raise HTTPException(status_code=400, detail="Administrador regional não está associado a um departamento.")
                    query = f"{query_base} WHERE up.departamento_regional = %s ORDER BY up.created_at DESC"
                    params = (user_department,)
                elif role == UserRole.administracao_nacional.value:
                    query = f"{query_base} ORDER BY up.created_at DESC"
                    params = ()
                else:
                    # Se a role for desconhecida ou não tiver permissão, retorna uma lista vazia por segurança.
                    logger.warning(f"Usuário {user_id} com role '{role}' desconhecida tentou acessar /plans.")
                    return GetPlansResponse(user_id=user_id, plans=[])

                await cur.execute(query, params)
                records = await cur.fetchall()
        
        summaries = []
        for record in records:
            # record é um dict agora
            plan_id = record['id']
            summary_data = record['summary']
            departamento_regional = record['departamento_regional']
            escola = record['escola']
            docente = record['docente']
            curso = record['curso']
            data_inicio = record['data_inicio']
            data_fim = record['data_fim']
            status = record['status']
            arquivado = record['arquivado']
            publico = record.get('publico', False)
            input_tokens = record.get('input_tokens')
            output_tokens = record.get('output_tokens')
            
            if summary_data is None:
                summary_data = {}
            
            summaries.append(PlanSummary(
                plan_id=str(plan_id),
                nome_uc=summary_data.get("nome_uc"),
                turma=summary_data.get("turma"),
                escola=escola or summary_data.get("escola"),
                departamento_regional=departamento_regional or summary_data.get("departamento_regional"),
                docente=docente or summary_data.get("docente"),
                curso=curso or summary_data.get("curso"),
                data_inicio=str(data_inicio) if data_inicio else None,
                data_fim=str(data_fim) if data_fim else None,
                contagem_sa_por_tipo=summary_data.get("contagem_sa_por_tipo"),
                status=PlanStatus(status),
                arquivado=arquivado,
                publico=publico,
                input_tokens=input_tokens,
                output_tokens=output_tokens
            ))
            
        return GetPlansResponse(user_id=user_id, plans=summaries)

    except HTTPException as he:
        raise he
    except Exception as e:
        # No caso de um erro, é importante logar a role para facilitar a depuração.
        user_role_for_log = locals().get('role', 'desconhecida')
        logger.error(f"Erro ao recuperar planos para o usuário {user_id} com role {user_role_for_log}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno ao buscar os planos.")


@app.get("/plans/public", response_model=GetPlansResponse, dependencies=[Depends(verify_token)])
async def get_public_plans():
    """
    Recupera uma lista de todos os planos públicos aprovados.
    Planos públicos são visíveis para todos os usuários do sistema.
    """
    logger.info("Endpoint /plans/public solicitado")
    try:
        async with (await get_checkpoint_connection()).connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                query = """
                SELECT id, summary, departamento_regional, escola, docente, curso, data_inicio, data_fim, status, arquivado, publico 
                FROM user_plans 
                WHERE publico = TRUE AND status = 'aprovado'
                ORDER BY created_at DESC
                """
                await cur.execute(query)
                records = await cur.fetchall()
        
        summaries = []
        for record in records:
            plan_id = record['id']
            summary_data = record['summary']
            departamento_regional = record['departamento_regional']
            escola = record['escola']
            docente = record['docente']
            curso = record['curso']
            data_inicio = record['data_inicio']
            data_fim = record['data_fim']
            status = record['status']
            arquivado = record['arquivado']
            publico = record.get('publico', False)
            
            if summary_data is None:
                summary_data = {}
            
            summaries.append(PlanSummary(
                plan_id=str(plan_id),
                nome_uc=summary_data.get("nome_uc"),
                turma=summary_data.get("turma"),
                escola=escola or summary_data.get("escola"),
                departamento_regional=departamento_regional or summary_data.get("departamento_regional"),
                docente=docente or summary_data.get("docente"),
                curso=curso or summary_data.get("curso"),
                data_inicio=str(data_inicio) if data_inicio else None,
                data_fim=str(data_fim) if data_fim else None,
                contagem_sa_por_tipo=summary_data.get("contagem_sa_por_tipo"),
                status=PlanStatus(status),
                arquivado=arquivado,
                publico=publico
            ))
            
        return GetPlansResponse(user_id="public", plans=summaries)

    except Exception as e:
        logger.error(f"Erro ao recuperar planos públicos: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno ao buscar os planos públicos.")


@app.put("/plan/toggle_public", dependencies=[Depends(verify_token)])
async def toggle_plan_public(body: TogglePublicRequest):
    """
    Alterna a visibilidade pública de um plano.
    Apenas planos com status 'aprovado' podem ser tornados públicos.
    """
    plan_id = body.plan_id
    logger.info(f"Endpoint /plan/toggle_public solicitado para plan_id: {plan_id}")
    
    try:
        plan_uuid = uuid.UUID(plan_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="O ID do plano fornecido é inválido.")
    
    try:
        async with (await get_checkpoint_connection()).connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                # Verifica se o plano existe e qual o seu status atual
                await cur.execute(
                    "SELECT status, publico FROM user_plans WHERE id = %s",
                    (plan_uuid,)
                )
                record = await cur.fetchone()
                
                if not record:
                    raise HTTPException(status_code=404, detail=f"Plano com ID {plan_id} não encontrado.")
                
                current_status = record['status']
                current_publico = record.get('publico', False)
                
                # Apenas planos aprovados podem ser tornados públicos
                if current_status != PlanStatus.aprovado.value:
                    raise HTTPException(
                        status_code=400, 
                        detail="Apenas planos com status 'aprovado' podem ser tornados públicos."
                    )
                
                # Alterna o valor
                new_publico = not current_publico
                
                # Atualiza no banco
                await cur.execute(
                    "UPDATE user_plans SET publico = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
                    (new_publico, plan_uuid)
                )
        
        logger.info(f"Plano {plan_id} - visibilidade pública alterada para: {new_publico}")
        return {"plan_id": plan_id, "publico": new_publico, "message": f"Plano {'tornado público' if new_publico else 'tornado privado'} com sucesso."}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao alternar visibilidade do plano {plan_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno ao atualizar visibilidade do plano.")

async def _get_user_info(user_id: str, conn: AsyncConnection) -> tuple:
    """Helper para obter a role, escola e departamento do usuário."""
    # Como conn é passado, assumimos que quem chama decide a row_factory,
    # mas aqui precisamos garantir o acesso correto.
    # Vamos criar um cursor novo com dict_row para garantir.
    async with conn.cursor(row_factory=dict_row) as cur:
        query = "SELECT role, escola, departamento_regional FROM users WHERE user_id = %s;"
        await cur.execute(query, (user_id,))
        user_info = await cur.fetchone()
        if not user_info:
            raise HTTPException(status_code=404, detail="Usuário não encontrado.")
        return user_info['role'], user_info['escola'], user_info['departamento_regional']


    
@app.post("/get_single_plan", response_model=GetPlanResponse, dependencies=[Depends(verify_token)])
async def get_single_plan(body: GetSinglePlanRequest):
    """
    Recupera os detalhes e o conteúdo de um plano de ensino específico pelo seu ID.
    """
    plan_id = body.plan_id
    logger.info(f"Endpoint /get_single_plan solicitado para o ID: {plan_id}.")
    
    try:
        # Primeiro, busca os metadados do plano no banco de dados
        async with (await get_checkpoint_connection()).connection() as conn: # Reutilizando a função de conexão
            async with conn.cursor(row_factory=dict_row) as cur:
                query = """
                SELECT id, user_id, thread_id, course_plan_id, created_at, blob_path 
                FROM user_plans WHERE id = %s
                """
                await cur.execute(query, (uuid.UUID(plan_id),))
                record = await cur.fetchone()

        if not record:
            logger.warning(f"Plano com ID: {plan_id} não encontrado no banco de dados.")
            raise HTTPException(status_code=404, detail=f"Plano com ID {plan_id} não encontrado.")

        # Desempacota os metadados via chaves
        db_id = record['id']
        user_id = record['user_id']
        thread_id = record['thread_id']
        course_plan_id = record['course_plan_id']
        created_at = record['created_at']
        blob_path = record['blob_path']
        
        # Agora, busca o conteúdo do plano no GCS
        plan_content_str = await get_plan_document(plan_id)

        if plan_content_str is None:
            # Isso seria estranho se o registro do DB existe, mas pode acontecer
            logger.error(f"Registro do plano {plan_id} encontrado no DB, mas o conteúdo não foi encontrado no GCS em {blob_path}.")
            raise HTTPException(status_code=404, detail=f"Conteúdo do plano com ID {plan_id} não encontrado no armazenamento.")

        # Converte a string JSON do GCS em um objeto Python (dicionário)
        plan_content_json = json.loads(plan_content_str)

        # Monta a resposta final usando o modelo Pydantic
        return GetPlanResponse(
            plan_id=str(db_id),
            user_id=user_id,
            thread_id=thread_id,
            course_plan_id=course_plan_id,
            created_at=str(created_at),
            plan_content=plan_content_json
        )

    except ValueError: # Caso o plan_id não seja um UUID válido
        raise HTTPException(status_code=400, detail="O ID do plano fornecido é inválido.")
    except HTTPException as he:
        # Re-levanta a exceção para que o FastAPI a manipule
        raise he
    except Exception as e:
        logger.error(f"Erro inesperado ao buscar o plano {plan_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno ao buscar o plano de ensino.")
    
@app.post("/thread/rename", status_code=200, dependencies=[Depends(verify_token)])
async def rename_thread(body: RenameThreadRequest):
    """
    Renomeia o título de uma conversa específica.
    """
    logger.info(f"Endpoint /thread/rename solicitado para thread_id: {body.thread_id} por user: {body.user_id}")
    try:
        async with (await get_checkpoint_connection()).connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                # Atualiza o campo 'title' no JSON do checkpoint mais recente,
                # identificado pelo maior valor de 'step' na metadata.
                update_title_query = """
                UPDATE checkpoints
                SET checkpoint = jsonb_set(
                    checkpoint,
                    '{channel_values,title}',
                    %s::jsonb,
                    true
                )
                WHERE thread_id = %s
                  AND (metadata->>'user_id') = %s
                  AND (metadata->>'step')::int = (
                    SELECT MAX((metadata->>'step')::int)
                    FROM checkpoints
                    WHERE thread_id = %s AND (metadata->>'user_id') = %s
                  );
                """
                # O novo título precisa ser formatado como uma string JSON ("new_title")
                await cur.execute(
                    update_title_query,
                    (json.dumps(body.new_title), body.thread_id, body.user_id, body.thread_id, body.user_id)
                )
        
        return {"message": "Título da conversa atualizado com sucesso."}

    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Erro inesperado ao renomear a conversa {body.thread_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno ao renomear a conversa.")

@app.post("/user/set_department", status_code=200, dependencies=[Depends(verify_token)])
async def set_user_department(body: SetDepartmentRequest):
    """
    Define ou atualiza o departamento regional de um usuário.
    """
    logger.info(f"Endpoint /user/set_department solicitado para user: {body.user_id}")
    try:
        async with (await get_checkpoint_connection()).connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                # Usa INSERT ON CONFLICT (UPSERT) para criar ou atualizar o registro
                upsert_query = """
                INSERT INTO user_configs (user_id, departamento_regional)
                VALUES (%s, %s)
                ON CONFLICT (user_id) DO UPDATE
                SET departamento_regional = EXCLUDED.departamento_regional,
                    updated_at = CURRENT_TIMESTAMP;
                """
                await cur.execute(upsert_query, (body.user_id, body.departamento_regional))
        
        return {"message": "Departamento regional do usuário atualizado com sucesso."}

    except Exception as e:
        logger.error(f"Erro inesperado ao definir o departamento para o usuário {body.user_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno ao atualizar o departamento do usuário.")

@app.get("/user/config/{user_id}", response_model=GetUserConfigResponse, dependencies=[Depends(verify_token)])
async def get_user_config(user_id: str):
    """
    Recupera o departamento regional de um usuário.
    """
    logger.info(f"Endpoint /user/config solicitado para user: {user_id}")
    try:
        async with (await get_checkpoint_connection()).connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                query = """
                SELECT departamento_regional
                FROM user_configs
                WHERE user_id = %s;
                """
                await cur.execute(query, (user_id,))
                record = await cur.fetchone()
                
        department = record['departamento_regional'] if record and record['departamento_regional'] else None
        return GetUserConfigResponse(user_id=user_id, departamento_regional=department)
    
    except Exception as e:
        logger.error(f"Erro inesperado ao buscar a configuração para o usuário {user_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno ao buscar a configuração do usuário.")

@app.post("/export/docx", dependencies=[Depends(verify_token)])
async def export_plan_as_docx(body: ExportPlanByIdRequest):
    """
    Busca um plano de ensino pelo ID, gera um arquivo DOCX e o retorna para download.
    """
    logger.info(f"Endpoint /export/docx solicitado para o plan_id: {body.plan_id}")
    try:
        # 1. Buscar o conteúdo do plano e os metadados (incluindo o departamento)
        plan_data = await get_plan_document_with_metadata(body.plan_id)
        if not plan_data:
            raise HTTPException(status_code=404, detail=f"Plano com ID {body.plan_id} não encontrado.")

        plan_content_str = plan_data.get("plan_content")
        departamento_regional = plan_data.get("departamento_regional")

        # 2. Converter a string JSON em um dicionário Python
        plan_content_json = json.loads(plan_content_str)

        # 3. Gerar o documento DOCX em memória, passando o departamento regional
        docx_file = generate_docx(plan_content_json, departamento_regional)

        # 4. Definir o nome do arquivo para download
        filename = f"plano_de_ensino_{body.plan_id}.docx"

        # 5. Retornar o arquivo como uma resposta de streaming
        return StreamingResponse(
            docx_file,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )

    except HTTPException as he:
        raise he # Re-lança exceções HTTP para o FastAPI tratar

    except Exception as e:
        logger.error(f"Erro inesperado ao exportar o plano {body.plan_id} para DOCX: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno ao gerar o arquivo DOCX.")

@app.post("/user", status_code=201, dependencies=[Depends(verify_token)])
async def create_or_update_user(body: CreateUserRequest):
    """
    Cria um novo usuário ou atualiza um existente.
    O email só é atualizado se o valor atual for NULL ou 'seu_novo_email@dominio.com'.
    """
    logger.info(f"Endpoint /user chamado para user_id: {body.user_id}")
    try:
        async with (await get_checkpoint_connection()).connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                query = """
                INSERT INTO users (user_id, full_name, email, role, departamento_regional, escola)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE
                SET full_name = EXCLUDED.full_name,
                    email = CASE 
                        WHEN users.email IS NULL OR users.email = 'seu_novo_email@dominio.com' 
                        THEN EXCLUDED.email 
                        ELSE users.email 
                    END,
                    role = EXCLUDED.role,
                    departamento_regional = EXCLUDED.departamento_regional,
                    escola = EXCLUDED.escola,
                    updated_at = CURRENT_TIMESTAMP;
                """
                await cur.execute(query, (body.user_id, body.full_name, body.email, body.role.value, body.departamento_regional, body.escola))

        # Notificações Retroativas (se for coordenador)
        if body.role == UserRole.coordenador and body.escola:
            try:
                from src.notification_service import create_retroactive_notifications_for_coordinator
                await create_retroactive_notifications_for_coordinator(
                    coordinator_user_id=body.user_id,
                    school=body.escola
                )
                logger.info(f"Notificações retroativas processadas para coordenador {body.user_id}")
            except Exception as e:
                # Não falha o request, apenas loga o erro
                logger.error(f"Erro ao processar notificações retroativas: {e}", exc_info=True)

        return {"message": "Usuário criado/atualizado com sucesso."}
    except Exception as e:
        logger.error(f"Erro ao criar/atualizar usuário: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno ao processar o usuário.")

@app.get("/users", response_model=AllUsersResponse, dependencies=[Depends(verify_token)])
async def get_all_users():
    """
    Recupera todos os usuários cadastrados.
    """
    logger.info("Endpoint /users solicitado")
    try:
        async with (await get_checkpoint_connection()).connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                query = "SELECT user_id, full_name, email, role, departamento_regional, escola FROM users;"
                await cur.execute(query)
                records = await cur.fetchall()
        
        # Corrigido para acessar via chaves do dict
        users = [
            UserResponse(
                user_id=rec['user_id'], 
                full_name=rec['full_name'], 
                email=rec['email'], 
                role=rec['role'], 
                departamento_regional=rec['departamento_regional'], 
                escola=rec['escola']
            ) for rec in records
        ]
        return AllUsersResponse(users=users)
    except Exception as e:
        logger.error(f"Erro ao recuperar usuários: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno ao buscar usuários.")

@app.get("/user/{user_id}", response_model=UserResponse, dependencies=[Depends(verify_token)])
async def get_user(user_id: str):
    """
    Recupera um usuário específico pelo seu ID.
    """
    logger.info(f"Endpoint /user/{user_id} solicitado")
    try:
        async with (await get_checkpoint_connection()).connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                query = "SELECT user_id, full_name, email, role, departamento_regional, escola FROM users WHERE user_id = %s;"
                await cur.execute(query, (user_id,))
                record = await cur.fetchone()
        
        if not record:
            raise HTTPException(status_code=404, detail="Usuário não encontrado.")
        
        return UserResponse(
            user_id=record['user_id'], 
            full_name=record['full_name'], 
            email=record['email'], 
            role=record['role'], 
            departamento_regional=record['departamento_regional'], 
            escola=record['escola']
        )
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Erro ao recuperar usuário {user_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno ao buscar o usuário.")

@app.get("/metrics", response_model=MetricsResponse, dependencies=[Depends(verify_token)])
async def get_metrics(user_id: str):
    """
    Fornece um conjunto de métricas sobre o uso da plataforma.
    Acesso restrito a usuários com a role 'administracao_nacional'.
    """
    logger.info(f"Endpoint /metrics solicitado por user: {user_id}")
    try:
        async with (await get_checkpoint_connection()).connection() as conn:
            role, _, _ = await _get_user_info(user_id, conn)

            if role != UserRole.administracao_nacional.value:
                raise HTTPException(status_code=403, detail="Acesso negado. Permissão insuficiente.")

            async with conn.cursor(row_factory=dict_row) as cur:
                # 1. Total de usuários
                await cur.execute("SELECT COUNT(*) as total FROM users;")
                total_users = (await cur.fetchone())['total']

                # 2. Total de planos
                await cur.execute("SELECT COUNT(*) as total FROM user_plans;")
                total_plans = (await cur.fetchone())['total']

                # 3. Contagem por departamento
                await cur.execute("SELECT departamento_regional, COUNT(user_id) as count FROM users WHERE departamento_regional IS NOT NULL GROUP BY departamento_regional;")
                users_by_dept_raw = await cur.fetchall()
                await cur.execute("SELECT departamento_regional, COUNT(id) as count FROM user_plans WHERE departamento_regional IS NOT NULL GROUP BY departamento_regional;")
                plans_by_dept_raw = await cur.fetchall()

                # 4. Contagem por escola
                await cur.execute("SELECT escola, departamento_regional, COUNT(user_id) as count FROM users WHERE escola IS NOT NULL AND departamento_regional IS NOT NULL GROUP BY escola, departamento_regional;")
                users_by_school_raw = await cur.fetchall()
                await cur.execute("SELECT escola, departamento_regional, COUNT(id) as count FROM user_plans WHERE escola IS NOT NULL AND departamento_regional IS NOT NULL GROUP BY escola, departamento_regional;")
                plans_by_school_raw = await cur.fetchall()

                # 5. Contagem por docente
                await cur.execute("SELECT full_name, escola, departamento_regional, COUNT(user_id) as count FROM users WHERE role = 'docente' GROUP BY full_name, escola, departamento_regional;")
                users_by_docente_raw = await cur.fetchall()
                await cur.execute("SELECT docente, escola, departamento_regional, COUNT(id) as count FROM user_plans WHERE docente IS NOT NULL GROUP BY docente, escola, departamento_regional;")
                plans_by_docente_raw = await cur.fetchall()

                # 6. Contagem de tipos de situação de aprendizagem
                await cur.execute("SELECT summary FROM user_plans WHERE summary IS NOT NULL;")
                all_summaries_raw = await cur.fetchall()

                # 7. Contagem de planos por dia
                await cur.execute("SELECT TO_CHAR(created_at AT TIME ZONE 'America/Sao_Paulo', 'YYYY-MM-DD') as creation_day, COUNT(*) as plan_count FROM user_plans GROUP BY creation_day ORDER BY creation_day;")
                plans_per_day_raw = await cur.fetchall()

                # 8. Agregação de tokens para PLANOS (threads em user_plans OU que começam com op_extract_)
                await cur.execute("""
                    SELECT 
                        COALESCE(SUM(tt.input_tokens), 0) as total_input,
                        COALESCE(SUM(tt.output_tokens), 0) as total_output,
                        COUNT(DISTINCT tt.thread_id) as count
                    FROM thread_tokens tt
                    WHERE tt.thread_id IN (SELECT thread_id FROM user_plans)
                       OR tt.thread_id LIKE 'op_extract_%';
                """)
                plan_token_stats = await cur.fetchone()
                plan_total_input = plan_token_stats['total_input'] if plan_token_stats else 0
                plan_total_output = plan_token_stats['total_output'] if plan_token_stats else 0
                plan_count = plan_token_stats['count'] if plan_token_stats else 0
                avg_input_per_plan = plan_total_input / plan_count if plan_count > 0 else 0
                avg_output_per_plan = plan_total_output / plan_count if plan_count > 0 else 0

                # 9. Agregação de tokens para CONVERSAS (excluindo planos e extrações)
                await cur.execute("""
                    SELECT 
                        COALESCE(SUM(input_tokens), 0) as total_input,
                        COALESCE(SUM(output_tokens), 0) as total_output,
                        COUNT(*) as count
                    FROM thread_tokens tt
                    WHERE tt.thread_id NOT IN (SELECT thread_id FROM user_plans)
                      AND tt.thread_id NOT LIKE 'op_extract_%';
                """)
                conv_token_stats = await cur.fetchone()
                conv_total_input = conv_token_stats['total_input'] if conv_token_stats else 0
                conv_total_output = conv_token_stats['total_output'] if conv_token_stats else 0
                conv_count = conv_token_stats['count'] if conv_token_stats else 0
                avg_input_per_conv = conv_total_input / conv_count if conv_count > 0 else 0
                avg_output_per_conv = conv_total_output / conv_count if conv_count > 0 else 0

        # Processamento e junção dos dados em Python
        contagem_geral_sa = {}
        for summary_dict in all_summaries_raw:
            summary_data = summary_dict['summary']
            if summary_data and "contagem_sa_por_tipo" in summary_data:
                for sa_type, count in summary_data["contagem_sa_por_tipo"].items():
                    contagem_geral_sa[sa_type] = contagem_geral_sa.get(sa_type, 0) + count

        plans_per_day = [DailyPlanCount(date=row['creation_day'], count=row['plan_count']) for row in plans_per_day_raw]

        metrics_by_dept = {}
        for row in users_by_dept_raw:
            name = row['departamento_regional']
            count = row['count']
            metrics_by_dept[name] = {"name": name, "user_count": count, "plan_count": 0}
        for row in plans_by_dept_raw:
            name = row['departamento_regional']
            count = row['count']
            if name in metrics_by_dept:
                metrics_by_dept[name]["plan_count"] = count
            else:
                metrics_by_dept[name] = {"name": name, "user_count": 0, "plan_count": count}

        metrics_by_school = {}
        for row in users_by_school_raw:
            escola = row['escola']
            departamento_regional = row['departamento_regional']
            count = row['count']
            key = (escola, departamento_regional)
            metrics_by_school[key] = {"name": escola, "departamento_regional": departamento_regional, "user_count": count, "plan_count": 0}
        for row in plans_by_school_raw:
            escola = row['escola']
            departamento_regional = row['departamento_regional']
            count = row['count']
            key = (escola, departamento_regional)
            if key in metrics_by_school:
                metrics_by_school[key]["plan_count"] = count
            else:
                metrics_by_school[key] = {"name": escola, "departamento_regional": departamento_regional, "user_count": 0, "plan_count": count}

        metrics_by_docente = {}
        for row in users_by_docente_raw:
            full_name = row['full_name']
            escola = row['escola']
            departamento_regional = row['departamento_regional']
            count = row['count']
            key = (full_name, escola, departamento_regional)
            metrics_by_docente[key] = {"name": full_name, "escola": escola, "departamento_regional": departamento_regional, "user_count": count, "plan_count": 0}
        for row in plans_by_docente_raw:
            docente = row['docente']
            escola = row['escola']
            departamento_regional = row['departamento_regional']
            count = row['count']
            key = (docente, escola, departamento_regional)
            if key in metrics_by_docente:
                metrics_by_docente[key]["plan_count"] = count
            else:
                metrics_by_docente[key] = {"name": docente, "escola": escola, "departamento_regional": departamento_regional, "user_count": 0, "plan_count": count}

        ranking_by_department = sorted([MetricItem(**data) for data in metrics_by_dept.values()], key=lambda x: x.user_count + x.plan_count, reverse=True)
        ranking_by_school = sorted([MetricItem(**data) for data in metrics_by_school.values()], key=lambda x: x.user_count + x.plan_count, reverse=True)
        ranking_by_docente = sorted([MetricItem(**data) for data in metrics_by_docente.values()], key=lambda x: x.user_count + x.plan_count, reverse=True)

        return MetricsResponse(
            total_users=total_users,
            total_plans=total_plans,
            plans_per_day=plans_per_day,
            ranking_by_department=ranking_by_department,
            ranking_by_school=ranking_by_school,
            ranking_by_docente=ranking_by_docente,
            contagem_geral_sa_por_tipo=contagem_geral_sa,
            # Plan tokens
            total_input_tokens=plan_total_input,
            total_output_tokens=plan_total_output,
            avg_input_tokens_per_plan=avg_input_per_plan,
            avg_output_tokens_per_plan=avg_output_per_plan,
            # Conversation tokens
            total_input_tokens_conversations=conv_total_input,
            total_output_tokens_conversations=conv_total_output,
            avg_input_tokens_per_conversation=avg_input_per_conv,
            avg_output_tokens_per_conversation=avg_output_per_conv
        )

    except Exception as e:
        logger.error(f"Erro ao gerar métricas: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno ao gerar métricas.")

@app.get("/metrics/by_school", response_model=MetricsResponse, dependencies=[Depends(verify_token)])
async def get_metrics_by_school(user_id: str):
    """
    Fornece um conjunto de métricas sobre o uso da plataforma para a escola do usuário.
    Acesso restrito a usuários com a role 'coordenador'.
    """
    logger.info(f"Endpoint /metrics/by_school solicitado por user: {user_id}")
    try:
        async with (await get_checkpoint_connection()).connection() as conn:
            role, user_school, _ = await _get_user_info(user_id, conn)

            if role != UserRole.coordenador.value:
                raise HTTPException(status_code=403, detail="Acesso negado. Apenas coordenadores podem acessar este endpoint.")
            
            if not user_school:
                raise HTTPException(status_code=400, detail="Usuário não está associado a uma escola.")

            async with conn.cursor(row_factory=dict_row) as cur:
                # 1. Total de usuários na escola
                await cur.execute("SELECT COUNT(*) as count FROM users WHERE escola = %s;", (user_school,))
                total_users = (await cur.fetchone())['count']

                # 2. Total de planos na escola
                await cur.execute("SELECT COUNT(*) as count FROM user_plans WHERE escola = %s;", (user_school,))
                total_plans = (await cur.fetchone())['count']

                # 3. Contagem por departamento (apenas o da escola)
                await cur.execute("SELECT departamento_regional, COUNT(user_id) as count FROM users WHERE escola = %s AND departamento_regional IS NOT NULL GROUP BY departamento_regional;", (user_school,))
                users_by_dept_raw = await cur.fetchall()
                await cur.execute("SELECT departamento_regional, COUNT(id) as count FROM user_plans WHERE escola = %s AND departamento_regional IS NOT NULL GROUP BY departamento_regional;", (user_school,))
                plans_by_dept_raw = await cur.fetchall()

                # 4. Contagem por escola (apenas a escola atual)
                await cur.execute("SELECT escola, departamento_regional, COUNT(user_id) as count FROM users WHERE escola = %s AND departamento_regional IS NOT NULL GROUP BY escola, departamento_regional;", (user_school,))
                users_by_school_raw = await cur.fetchall()
                await cur.execute("SELECT escola, departamento_regional, COUNT(id) as count FROM user_plans WHERE escola = %s AND departamento_regional IS NOT NULL GROUP BY escola, departamento_regional;", (user_school,))
                plans_by_school_raw = await cur.fetchall()

                # 5. Contagem por docente na escola
                await cur.execute("SELECT full_name, escola, departamento_regional, COUNT(user_id) as count FROM users WHERE role = 'docente' AND escola = %s GROUP BY full_name, escola, departamento_regional;", (user_school,))
                users_by_docente_raw = await cur.fetchall()
                await cur.execute("SELECT docente, escola, departamento_regional, COUNT(id) as count FROM user_plans WHERE docente IS NOT NULL AND escola = %s GROUP BY docente, escola, departamento_regional;", (user_school,))
                plans_by_docente_raw = await cur.fetchall()

                # 6. Contagem de tipos de situação de aprendizagem na escola
                await cur.execute("SELECT summary FROM user_plans WHERE escola = %s AND summary IS NOT NULL;", (user_school,))
                all_summaries_raw = await cur.fetchall()

                # 7. Contagem de planos por dia na escola
                await cur.execute("SELECT TO_CHAR(created_at AT TIME ZONE 'America/Sao_Paulo', 'YYYY-MM-DD') as creation_day, COUNT(*) as plan_count FROM user_plans WHERE escola = %s GROUP BY creation_day ORDER BY creation_day;", (user_school,))
                plans_per_day_raw = await cur.fetchall()

                # 8. Agregação de tokens para PLANOS da escola (threads em user_plans OU que começam com op_extract_)
                await cur.execute("""
                    SELECT 
                        COALESCE(SUM(tt.input_tokens), 0) as total_input,
                        COALESCE(SUM(tt.output_tokens), 0) as total_output,
                        COUNT(DISTINCT tt.thread_id) as count
                    FROM thread_tokens tt
                    WHERE (tt.thread_id IN (SELECT thread_id FROM user_plans WHERE escola = %s)
                       OR tt.thread_id LIKE 'op_extract_%%');
                """, (user_school,))
                plan_token_stats = await cur.fetchone()
                plan_total_input = plan_token_stats['total_input'] if plan_token_stats else 0
                plan_total_output = plan_token_stats['total_output'] if plan_token_stats else 0
                plan_count = plan_token_stats['count'] if plan_token_stats else 0
                avg_input_per_plan = plan_total_input / plan_count if plan_count > 0 else 0
                avg_output_per_plan = plan_total_output / plan_count if plan_count > 0 else 0

                # 9. Agregação de tokens para CONVERSAS da escola (excluindo planos e extrações)
                await cur.execute("""
                    SELECT 
                        COALESCE(SUM(tt.input_tokens), 0) as total_input,
                        COALESCE(SUM(tt.output_tokens), 0) as total_output,
                        COUNT(tt.thread_id) as count
                    FROM thread_tokens tt
                    JOIN users u ON tt.user_id = u.user_id
                    WHERE u.escola = %s
                      AND tt.thread_id NOT IN (SELECT thread_id FROM user_plans)
                      AND tt.thread_id NOT LIKE 'op_extract_%%';
                """, (user_school,))
                conv_token_stats = await cur.fetchone()
                conv_total_input = conv_token_stats['total_input'] if conv_token_stats else 0
                conv_total_output = conv_token_stats['total_output'] if conv_token_stats else 0
                conv_count = conv_token_stats['count'] if conv_token_stats else 0
                avg_input_per_conv = conv_total_input / conv_count if conv_count > 0 else 0
                avg_output_per_conv = conv_total_output / conv_count if conv_count > 0 else 0

        # Processamento e junção dos dados em Python
        contagem_geral_sa = {}
        for summary_dict in all_summaries_raw:
            summary_data = summary_dict['summary']
            if summary_data and "contagem_sa_por_tipo" in summary_data:
                for sa_type, count in summary_data["contagem_sa_por_tipo"].items():
                    contagem_geral_sa[sa_type] = contagem_geral_sa.get(sa_type, 0) + count

        plans_per_day = [DailyPlanCount(date=row['creation_day'], count=row['plan_count']) for row in plans_per_day_raw]

        metrics_by_dept = {}
        for row in users_by_dept_raw:
            name = row['departamento_regional']
            count = row['count']
            metrics_by_dept[name] = {"name": name, "user_count": count, "plan_count": 0}
        for row in plans_by_dept_raw:
            name = row['departamento_regional']
            count = row['count']
            if name in metrics_by_dept:
                metrics_by_dept[name]["plan_count"] = count
            else:
                metrics_by_dept[name] = {"name": name, "user_count": 0, "plan_count": count}

        metrics_by_school = {}
        for row in users_by_school_raw:
            escola = row['escola']
            departamento_regional = row['departamento_regional']
            count = row['count']
            key = (escola, departamento_regional)
            metrics_by_school[key] = {"name": escola, "departamento_regional": departamento_regional, "user_count": count, "plan_count": 0}
        for row in plans_by_school_raw:
            escola = row['escola']
            departamento_regional = row['departamento_regional']
            count = row['count']
            key = (escola, departamento_regional)
            if key in metrics_by_school:
                metrics_by_school[key]["plan_count"] = count
            else:
                metrics_by_school[key] = {"name": escola, "departamento_regional": departamento_regional, "user_count": 0, "plan_count": count}

        metrics_by_docente = {}
        for row in users_by_docente_raw:
            full_name = row['full_name']
            escola = row['escola']
            departamento_regional = row['departamento_regional']
            count = row['count']
            key = (full_name, escola, departamento_regional)
            metrics_by_docente[key] = {"name": full_name, "escola": escola, "departamento_regional": departamento_regional, "user_count": count, "plan_count": 0}
        for row in plans_by_docente_raw:
            docente = row['docente']
            escola = row['escola']
            departamento_regional = row['departamento_regional']
            count = row['count']
            key = (docente, escola, departamento_regional)
            if key in metrics_by_docente:
                metrics_by_docente[key]["plan_count"] = count
            else:
                metrics_by_docente[key] = {"name": docente, "escola": escola, "departamento_regional": departamento_regional, "user_count": 0, "plan_count": count}

        ranking_by_department = sorted([MetricItem(**data) for data in metrics_by_dept.values()], key=lambda x: x.user_count + x.plan_count, reverse=True)
        ranking_by_school = sorted([MetricItem(**data) for data in metrics_by_school.values()], key=lambda x: x.user_count + x.plan_count, reverse=True)
        ranking_by_docente = sorted([MetricItem(**data) for data in metrics_by_docente.values()], key=lambda x: x.user_count + x.plan_count, reverse=True)

        return MetricsResponse(
            total_users=total_users,
            total_plans=total_plans,
            plans_per_day=plans_per_day,
            ranking_by_department=ranking_by_department,
            ranking_by_school=ranking_by_school,
            ranking_by_docente=ranking_by_docente,
            contagem_geral_sa_por_tipo=contagem_geral_sa,
            # Plan tokens
            total_input_tokens=plan_total_input,
            total_output_tokens=plan_total_output,
            avg_input_tokens_per_plan=avg_input_per_plan,
            avg_output_tokens_per_plan=avg_output_per_plan,
            # Conversation tokens
            total_input_tokens_conversations=conv_total_input,
            total_output_tokens_conversations=conv_total_output,
            avg_input_tokens_per_conversation=avg_input_per_conv,
            avg_output_tokens_per_conversation=avg_output_per_conv
        )

    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Erro ao gerar métricas para a escola do usuário {user_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erro interno ao gerar métricas para a escola.")

@app.get("/metrics/by_department", response_model=MetricsResponse, dependencies=[Depends(verify_token)])
async def get_metrics_by_department(user_id: str):
    """
    Fornece um conjunto de métricas sobre o uso da plataforma para o departamento regional do usuário.
    Acesso restrito a usuários com a role 'administracao_regional'.
    """
    logger.info(f"Endpoint /metrics/by_department solicitado por user: {user_id}")
    try:
        async with (await get_checkpoint_connection()).connection() as conn:
            role, _, user_department = await _get_user_info(user_id, conn)

            if role != UserRole.administracao_regional.value:
                raise HTTPException(status_code=403, detail="Acesso negado. Apenas administradores regionais podem acessar este endpoint.")

            if not user_department:
                raise HTTPException(status_code=400, detail="Usuário não está associado a um departamento regional.")

            async with conn.cursor(row_factory=dict_row) as cur:
                # 1. Total de usuários no departamento
                await cur.execute("SELECT COUNT(*) as count FROM users WHERE departamento_regional = %s;", (user_department,))
                total_users = (await cur.fetchone())['count']

                # 2. Total de planos no departamento
                await cur.execute("SELECT COUNT(*) as count FROM user_plans WHERE departamento_regional = %s;", (user_department,))
                total_plans = (await cur.fetchone())['count']

                # 3. Contagem por departamento (apenas o atual)
                await cur.execute("SELECT departamento_regional, COUNT(user_id) as count FROM users WHERE departamento_regional = %s GROUP BY departamento_regional;", (user_department,))
                users_by_dept_raw = await cur.fetchall()
                await cur.execute("SELECT departamento_regional, COUNT(id) as count FROM user_plans WHERE departamento_regional = %s GROUP BY departamento_regional;", (user_department,))
                plans_by_dept_raw = await cur.fetchall()

                # 4. Contagem por escola no departamento
                await cur.execute("SELECT escola, departamento_regional, COUNT(user_id) as count FROM users WHERE departamento_regional = %s AND escola IS NOT NULL GROUP BY escola, departamento_regional;", (user_department,))
                users_by_school_raw = await cur.fetchall()
                await cur.execute("SELECT escola, departamento_regional, COUNT(id) as count FROM user_plans WHERE departamento_regional = %s AND escola IS NOT NULL GROUP BY escola, departamento_regional;", (user_department,))
                plans_by_school_raw = await cur.fetchall()

                # 5. Contagem por docente no departamento
                await cur.execute("SELECT full_name, escola, departamento_regional, COUNT(user_id) as count FROM users WHERE role = 'docente' AND departamento_regional = %s GROUP BY full_name, escola, departamento_regional;", (user_department,))
                users_by_docente_raw = await cur.fetchall()
                await cur.execute("SELECT docente, escola, departamento_regional, COUNT(id) as count FROM user_plans WHERE docente IS NOT NULL AND departamento_regional = %s GROUP BY docente, escola, departamento_regional;", (user_department,))
                plans_by_docente_raw = await cur.fetchall()

                # 6. Contagem de tipos de situação de aprendizagem no departamento
                await cur.execute("SELECT summary FROM user_plans WHERE departamento_regional = %s AND summary IS NOT NULL;", (user_department,))
                all_summaries_raw = await cur.fetchall()

                # 7. Contagem de planos por dia no departamento
                await cur.execute("SELECT TO_CHAR(created_at AT TIME ZONE 'America/Sao_Paulo', 'YYYY-MM-DD') as creation_day, COUNT(*) as plan_count FROM user_plans WHERE departamento_regional = %s GROUP BY creation_day ORDER BY creation_day;", (user_department,))
                plans_per_day_raw = await cur.fetchall()

                # 8. Agregação de tokens para PLANOS do departamento (threads em user_plans OU que começam com op_extract_)
                await cur.execute("""
                    SELECT 
                        COALESCE(SUM(tt.input_tokens), 0) as total_input,
                        COALESCE(SUM(tt.output_tokens), 0) as total_output,
                        COUNT(DISTINCT tt.thread_id) as count
                    FROM thread_tokens tt
                    WHERE (tt.thread_id IN (SELECT thread_id FROM user_plans WHERE departamento_regional = %s)
                       OR tt.thread_id LIKE 'op_extract_%%');
                """, (user_department,))
                plan_token_stats = await cur.fetchone()
                plan_total_input = plan_token_stats['total_input'] if plan_token_stats else 0
                plan_total_output = plan_token_stats['total_output'] if plan_token_stats else 0
                plan_count = plan_token_stats['count'] if plan_token_stats else 0
                avg_input_per_plan = plan_total_input / plan_count if plan_count > 0 else 0
                avg_output_per_plan = plan_total_output / plan_count if plan_count > 0 else 0

                # 9. Agregação de tokens para CONVERSAS do departamento (excluindo planos e extrações)
                await cur.execute("""
                    SELECT 
                        COALESCE(SUM(tt.input_tokens), 0) as total_input,
                        COALESCE(SUM(tt.output_tokens), 0) as total_output,
                        COUNT(tt.thread_id) as count
                    FROM thread_tokens tt
                    JOIN users u ON tt.user_id = u.user_id
                    WHERE u.departamento_regional = %s
                      AND tt.thread_id NOT IN (SELECT thread_id FROM user_plans)
                      AND tt.thread_id NOT LIKE 'op_extract_%%';
                """, (user_department,))
                conv_token_stats = await cur.fetchone()
                conv_total_input = conv_token_stats['total_input'] if conv_token_stats else 0
                conv_total_output = conv_token_stats['total_output'] if conv_token_stats else 0
                conv_count = conv_token_stats['count'] if conv_token_stats else 0
                avg_input_per_conv = conv_total_input / conv_count if conv_count > 0 else 0
                avg_output_per_conv = conv_total_output / conv_count if conv_count > 0 else 0

        # Processamento e junção dos dados em Python
        contagem_geral_sa = {}
        for summary_dict in all_summaries_raw:
            summary_data = summary_dict['summary']
            if summary_data and "contagem_sa_por_tipo" in summary_data:
                for sa_type, count in summary_data["contagem_sa_por_tipo"].items():
                    contagem_geral_sa[sa_type] = contagem_geral_sa.get(sa_type, 0) + count

        plans_per_day = [DailyPlanCount(date=row['creation_day'], count=row['plan_count']) for row in plans_per_day_raw]

        metrics_by_dept = {}
        for row in users_by_dept_raw:
            name = row['departamento_regional']
            count = row['count']
            metrics_by_dept[name] = {"name": name, "user_count": count, "plan_count": 0}
        for row in plans_by_dept_raw:
            name = row['departamento_regional']
            count = row['count']
            if name in metrics_by_dept:
                metrics_by_dept[name]["plan_count"] = count
            else:
                metrics_by_dept[name] = {"name": name, "user_count": 0, "plan_count": count}

        metrics_by_school = {}
        for row in users_by_school_raw:
            escola = row['escola']
            departamento_regional = row['departamento_regional']
            count = row['count']
            key = (escola, departamento_regional)
            metrics_by_school[key] = {"name": escola, "departamento_regional": departamento_regional, "user_count": count, "plan_count": 0}
        for row in plans_by_school_raw:
            escola = row['escola']
            departamento_regional = row['departamento_regional']
            count = row['count']
            key = (escola, departamento_regional)
            if key in metrics_by_school:
                metrics_by_school[key]["plan_count"] = count
            else:
                metrics_by_school[key] = {"name": escola, "departamento_regional": departamento_regional, "user_count": 0, "plan_count": count}

        metrics_by_docente = {}
        for row in users_by_docente_raw:
            full_name = row['full_name']
            escola = row['escola']
            departamento_regional = row['departamento_regional']
            count = row['count']
            key = (full_name, escola, departamento_regional)
            metrics_by_docente[key] = {"name": full_name, "escola": escola, "departamento_regional": departamento_regional, "user_count": count, "plan_count": 0}
        for row in plans_by_docente_raw:
            docente = row['docente']
            escola = row['escola']
            departamento_regional = row['departamento_regional']
            count = row['count']
            key = (docente, escola, departamento_regional)
            if key in metrics_by_docente:
                metrics_by_docente[key]["plan_count"] = count
            else:
                metrics_by_docente[key] = {"name": docente, "escola": escola, "departamento_regional": departamento_regional, "user_count": 0, "plan_count": count}

        ranking_by_department = sorted([MetricItem(**data) for data in metrics_by_dept.values()], key=lambda x: x.user_count + x.plan_count, reverse=True)
        ranking_by_school = sorted([MetricItem(**data) for data in metrics_by_school.values()], key=lambda x: x.user_count + x.plan_count, reverse=True)
        ranking_by_docente = sorted([MetricItem(**data) for data in metrics_by_docente.values()], key=lambda x: x.user_count + x.plan_count, reverse=True)

        return MetricsResponse(
            total_users=total_users,
            total_plans=total_plans,
            plans_per_day=plans_per_day,
            ranking_by_department=ranking_by_department,
            ranking_by_school=ranking_by_school,
            ranking_by_docente=ranking_by_docente,
            contagem_geral_sa_por_tipo=contagem_geral_sa,
            # Plan tokens
            total_input_tokens=plan_total_input,
            total_output_tokens=plan_total_output,
            avg_input_tokens_per_plan=avg_input_per_plan,
            avg_output_tokens_per_plan=avg_output_per_plan,
            # Conversation tokens
            total_input_tokens_conversations=conv_total_input,
            total_output_tokens_conversations=conv_total_output,
            avg_input_tokens_per_conversation=avg_input_per_conv,
            avg_output_tokens_per_conversation=avg_output_per_conv
        )

    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Erro ao gerar métricas para o departamento do usuário {user_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno ao gerar métricas para o departamento.")


def transform_manual_to_standard_format(body: ManualPlanRequest) -> dict:
    """
    Transforma o plano manual para o formato padrão esperado pelo frontend (mesmo do plano IA).
    Isso garante compatibilidade com a visualização, exportação e fluxo de aprovação.
    """
    situacoes_transformadas = []
    
    for sa in body.situacoes_aprendizagem:
        # Transformar critérios
        criterios_dicotomicos = []
        criterios_graduais = []
        
        for criterio in sa.criterios:
            capacidade_nome = criterio.capacidade or criterio.criterio  # Usa capacidade se disponível, senão usa o critério
            if criterio.tipo == "dicotomico":
                criterios_dicotomicos.append({
                    "capacidade": capacidade_nome,
                    "criterios": [criterio.criterio]
                })
            else:  # gradual
                criterios_graduais.append({
                    "capacidade": capacidade_nome,
                    "criterio": criterio.criterio,
                    "niveis": {
                        "nivel_1": criterio.nivel1 or "",
                        "nivel_2": criterio.nivel2 or "",
                        "nivel_3": criterio.nivel3 or "",
                        "nivel_4": criterio.nivel4 or ""
                    }
                })
        
        # Transformar plano de aula
        plano_aula_transformado = []
        for aula in sa.plano_aula:
            horas_aulas_data = f"{aula.data} ({aula.hora_inicio} - {aula.hora_fim})" if aula.data else f"{aula.hora_inicio} - {aula.hora_fim}"
            plano_aula_transformado.append({
                "horas_aulas_data": horas_aulas_data,
                "capacidades": ", ".join(aula.capacidades) if aula.capacidades else "",
                "conhecimentos": ", ".join(aula.conhecimentos) if aula.conhecimentos else "",
                "estrategias": aula.estrategias,
                "recursos_ambientes": aula.recursos,
                "criterios_avaliacao": ", ".join(aula.criterios_avaliacao) if aula.criterios_avaliacao else "",
                "instrumento_avaliacao": aula.instrumento,
                "referencias": aula.referencias
            })
        
        # Transformar conhecimentos para estrutura hierárquica
        conhecimentos_transformados = [{"topico": k, "subtopicos": []} for k in sa.conhecimentos]
        
        situacoes_transformadas.append({
            "titulo": sa.tema,
            "capacidades": {
                "basicas": sa.capacidades_tecnicas,
                "socioemocionais": sa.capacidades_socioemocionais
            },
            "conhecimentos": conhecimentos_transformados,
            "estrategia_aprendizagem": {
                "tipo": sa.estrategia,
                "aulas_previstas": str(len(sa.plano_aula)),
                "carga_horaria": "",
                "detalhes": {
                    "titulo_sa": sa.tema,
                    "contextualizacao": "",
                    "desafio": sa.desafio,  # Mantém o HTML
                    "resultados_esperados": ""
                }
            },
            "criterios_avaliacao": {
                "dicotomicos": criterios_dicotomicos,
                "graduais": criterios_graduais
            },
            "plano_de_aula": plano_aula_transformado,
            "perguntas_mediadoras": []
        })
    
    return {
        "plano_de_ensino": {
            "informacoes_curso": {
                "curso": body.informacoes_gerais.curso,
                "turma": body.informacoes_gerais.turma,
                "unidade_curricular": body.informacoes_gerais.unidade_curricular,
                "modulo": "",
                "carga_horaria_total": "",
                "objetivo": "",
                "modalidade": body.informacoes_gerais.modalidade or "Presencial",
                "professor": body.informacoes_gerais.professor,
                "unidade": body.informacoes_gerais.escola,
                "departamento_regional": body.informacoes_gerais.departamento_regional
            },
            "situacoes_aprendizagem": situacoes_transformadas
        }
    }


@app.post("/plan/manual", status_code=201, dependencies=[Depends(verify_token)])
async def create_manual_plan(body: ManualPlanRequest):
    """
    Recebe um plano de ensino completo em JSON (estrutura aninhada), criado manualmente pelo frontend,
    e armazena no Google Cloud Storage e banco de dados.
    Também cria um checkpoint do LangGraph para que o botão 'Editar com IA' funcione.
    """
    logger.info(f"Endpoint /plan/manual chamado por user: {body.user_id}")
    try:
        # Extrair metadados do conteúdo do plano para a tabela de resumo
        plan_content = body.plan_content
        plano_ensino = plan_content.get("plano_de_ensino", {})
        info_curso = plano_ensino.get("informacoes_curso", {})
        
        # Obter campos com fallback seguro
        departamento = info_curso.get("departamento_regional")
        escola = info_curso.get("unidade") or info_curso.get("escola")
        docente = info_curso.get("professor") or info_curso.get("docente")
        curso = info_curso.get("curso")
        data_inicio = info_curso.get("data_inicio", "")
        data_fim = info_curso.get("data_fim", "")
        turma = info_curso.get("turma", "")
        
        # ALWAYS generate a new thread_id for manual saves.
        # This ensures the original plan's conversation is preserved
        # and the new manually-saved plan gets its own conversation for "Edit with AI".
        effective_thread_id = str(uuid.uuid4())
        logger.info(f"Gerado novo thread_id para plano manual: {effective_thread_id} (thread_id original do body: {body.thread_id})")
        
        # Serializar para JSON
        plan_json_content = json.dumps(plan_content, indent=2, ensure_ascii=False)

        # Save plan AND create LangGraph checkpoint (no LLM consumption)
        result = await save_manual_plan_with_checkpoint(
            user_id=body.user_id,
            thread_id=effective_thread_id,
            plan_json=plan_content,
            plan_json_content=plan_json_content,
            course_plan_id=body.course_plan_id or "manual",
            departamento_regional=departamento,
            escola=escola,
            docente=docente,
            curso=curso,
            turma=turma,
            data_inicio=data_inicio,
            data_fim=data_fim
        )

        return {
            "message": "Plano manual armazenado com sucesso!",
            "plan_id": result["plan_id"],
            "thread_id": result["thread_id"]
        }

    except Exception as e:
        logger.error(f"Erro ao armazenar plano manual: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno ao armazenar o plano manual.")

@app.get("/user/{user_id}/role", response_model=UserRoleResponse, dependencies=[Depends(verify_token)])
async def get_user_role(user_id: str):
    """
    Recupera a role de um usuário específico.
    """
    logger.info(f"Endpoint /user/{user_id}/role solicitado")
    try:
        async with (await get_checkpoint_connection()).connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                query = "SELECT role FROM users WHERE user_id = %s;"
                await cur.execute(query, (user_id,))
                record = await cur.fetchone()
        
        if not record:
            raise HTTPException(status_code=404, detail="Usuário não encontrado.")
        
        return UserRoleResponse(role=record['role'])
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Erro ao recuperar role do usuário {user_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno ao buscar a role do usuário.")

@app.post("/plan/update_status", status_code=200, dependencies=[Depends(verify_token)])
async def update_plan_status(body: UpdatePlanStatusRequest):
    """
    Atualiza o estado de um plano de ensino, salva no histórico com comentário e notifica quando apropriado.
    """
    logger.info(f"Endpoint /plan/update_status chamado para plan_id: {body.plan_id}")
    try:
        async with (await get_checkpoint_connection()).connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                # Buscar informações do plano antes de atualizar
                plan_query = """
                SELECT user_id, summary, status
                FROM user_plans
                WHERE id = %s;
                """
                await cur.execute(plan_query, (uuid.UUID(body.plan_id),))
                plan_info = await cur.fetchone()
                
                if not plan_info:
                    raise HTTPException(status_code=404, detail="Plano não encontrado.")
                
                previous_status = plan_info['status']
                
                # Extrair nome do plano do summary
                plan_name = "Plano de Ensino"
                docente_name = "Docente"
                escola = None
                if plan_info['summary'] and isinstance(plan_info['summary'], dict):
                    plan_name = plan_info['summary'].get('nome_uc', plan_name)
                    docente_name = plan_info['summary'].get('docente', docente_name)
                    escola = plan_info['summary'].get('escola')
                
                # Buscar nome do usuário que está fazendo a alteração
                await cur.execute("SELECT full_name FROM users WHERE user_id = %s;", (body.user_id,))
                user_record = await cur.fetchone()
                changed_by_name = user_record['full_name'] if user_record else None
                
                # Atualizar status do plano
                update_query = """
                UPDATE user_plans
                SET status = %s, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s;
                """
                await cur.execute(update_query, (body.new_state.value, uuid.UUID(body.plan_id)))
                
                # Salvar entrada no histórico
                history_query = """
                INSERT INTO plan_status_history 
                (plan_id, previous_status, new_status, comment, changed_by_user_id, changed_by_name)
                VALUES (%s, %s, %s, %s, %s, %s);
                """
                await cur.execute(history_query, (
                    uuid.UUID(body.plan_id),
                    previous_status,
                    body.new_state.value,
                    body.comment,
                    body.user_id,
                    changed_by_name
                ))
                logger.info(f"Histórico de status salvo para plano {body.plan_id}: {previous_status} -> {body.new_state.value}")
        
        # Notificar coordenadores quando um plano é submetido
        logger.info(f"🔔 DEBUG: body.new_state = {body.new_state}, escola = {escola}")
        if body.new_state == PlanStatus.submetido and escola:
            logger.info(f"🔔 Tentando notificar coordenadores sobre submissão do plano {body.plan_id}")
            await notify_plan_submitted(
                plan_id=body.plan_id,
                docente_name=docente_name,
                plan_name=plan_name,
                escola=escola
            )
            logger.info(f"🔔 Notificação de submissão enviada com sucesso")
        
        # Notificar docente sobre mudança de status (retornado ou aprovado)
        logger.info(f"🔔 DEBUG: Verificando se deve notificar docente. Status: {body.new_state}")
        if body.new_state in [PlanStatus.retornado, PlanStatus.aprovado]:
            logger.info(f"🔔 Tentando notificar docente {plan_info['user_id']} sobre mudança de status para {body.new_state.value}")
            await notify_plan_status_change(
                plan_id=body.plan_id,
                docente_user_id=plan_info['user_id'],
                new_status=body.new_state.value,
                plan_name=plan_name
            )
            logger.info(f"🔔 Notificação de mudança de status enviada com sucesso")
        
        return {"message": "Status do plano atualizado com sucesso."}

    except HTTPException:
        raise
    except ValueError:
        raise HTTPException(status_code=400, detail="O ID do plano fornecido é inválido.")
    except Exception as e:
        logger.error(f"Erro inesperado ao atualizar o status do plano {body.plan_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno ao atualizar o status do plano.")

@app.get("/plan/{plan_id}/history", response_model=PlanStatusHistoryResponse, dependencies=[Depends(verify_token)])
async def get_plan_status_history(plan_id: str):
    """
    Retorna o histórico completo de mudanças de status de um plano, com comentários e data/hora.
    """
    logger.info(f"Endpoint /plan/{plan_id}/history chamado")
    try:
        async with (await get_checkpoint_connection()).connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                # Verificar se o plano existe
                await cur.execute("SELECT id FROM user_plans WHERE id = %s;", (uuid.UUID(plan_id),))
                plan_exists = await cur.fetchone()
                
                if not plan_exists:
                    raise HTTPException(status_code=404, detail="Plano não encontrado.")
                
                # Buscar histórico ordenado por data (mais recente primeiro)
                history_query = """
                SELECT id, previous_status, new_status, comment, changed_by_user_id, changed_by_name, created_at
                FROM plan_status_history
                WHERE plan_id = %s
                ORDER BY created_at DESC;
                """
                await cur.execute(history_query, (uuid.UUID(plan_id),))
                records = await cur.fetchall()
        
        history = [
            PlanStatusHistoryEntry(
                id=str(r['id']),
                previous_status=r['previous_status'],
                new_status=r['new_status'],
                comment=r['comment'],
                changed_by_user_id=r['changed_by_user_id'],
                changed_by_name=r['changed_by_name'],
                created_at=r['created_at'].isoformat() if r['created_at'] else None
            )
            for r in records
        ]
        
        return PlanStatusHistoryResponse(plan_id=plan_id, history=history)
        
    except HTTPException:
        raise
    except ValueError:
        raise HTTPException(status_code=400, detail="O ID do plano fornecido é inválido.")
    except Exception as e:
        logger.error(f"Erro ao buscar histórico do plano {plan_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno ao buscar histórico do plano.")

@app.post("/plan/archive", status_code=200, dependencies=[Depends(verify_token)])
async def archive_plan(body: ArchivePlanRequest):
    """
    Arquiva ou desarquiva um plano de ensino.
    """
    logger.info(f"Endpoint /plan/archive chamado para plan_id: {body.plan_id}")
    try:
        async with (await get_checkpoint_connection()).connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                query = """
                UPDATE user_plans
                SET arquivado = %s
                WHERE id = %s;
                """
                await cur.execute(query, (body.archived, uuid.UUID(body.plan_id)))
        
        return {"message": "Plano arquivado/desarquivado com sucesso."}

    except ValueError: # Captura erro se o plan_id não for um UUID válido
        raise HTTPException(status_code=400, detail="O ID do plano fornecido é inválido.")
    except Exception as e:
        logger.error(f"Erro inesperado ao arquivar o plano {body.plan_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno ao arquivar o plano.")


# ============================================================================
# ENDPOINTS DE NOTIFICAÇÕES
# ============================================================================

@app.get("/notifications", response_model=NotificationListResponse, dependencies=[Depends(verify_token)])
async def get_notifications(user_id: str, limit: int = 50, offset: int = 0, unread_only: bool = False):
    """
    Retorna as notificações de um usuário.
    """
    logger.info(f"Endpoint /notifications chamado por user_id: {user_id}")
    try:
        async with (await get_checkpoint_connection()).connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                # Buscar notificações
                where_clause = "WHERE user_id = %s"
                params = [user_id]
                
                if unread_only:
                    where_clause += " AND is_read = FALSE"
                
                query = f"""
                SELECT id, user_id, plan_id, type, message, is_read, created_at, read_at, metadata
                FROM notifications
                {where_clause}
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s;
                """
                params.extend([limit, offset])
                await cur.execute(query, params)
                records = await cur.fetchall()
                
                # Contar não lidas
                count_query = "SELECT COUNT(*) as count FROM notifications WHERE user_id = %s AND is_read = FALSE;"
                await cur.execute(count_query, (user_id,))
                unread_count = (await cur.fetchone())['count']
        
        notifications = [
            NotificationResponse(
                id=str(r['id']),
                user_id=r['user_id'],
                plan_id=str(r['plan_id']) if r['plan_id'] else None,
                type=r['type'],
                message=r['message'],
                is_read=r['is_read'],
                created_at=r['created_at'].isoformat() if r['created_at'] else None,
                read_at=r['read_at'].isoformat() if r['read_at'] else None,
                metadata=r['metadata']
            )
            for r in records
        ]
        
        return NotificationListResponse(
            notifications=notifications,
            unread_count=unread_count
        )
    except Exception as e:
        logger.error(f"Erro ao buscar notificações: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno ao buscar notificações.")


@app.post("/notifications/mark-read", dependencies=[Depends(verify_token)])
async def mark_notifications_as_read(body: MarkAsReadRequest, user_id: str):
    """
    Marca notificações como lidas.
    """
    logger.info(f"Endpoint /notifications/mark-read chamado por user_id: {user_id}")
    try:
        async with (await get_checkpoint_connection()).connection() as conn:
            async with conn.cursor() as cur:
                # Validar que as notificações pertencem ao usuário
                notification_uuids = [uuid.UUID(nid) for nid in body.notification_ids]
                
                query = """
                UPDATE notifications
                SET is_read = TRUE, read_at = CURRENT_TIMESTAMP
                WHERE id = ANY(%s) AND user_id = %s;
                """
                await cur.execute(query, (notification_uuids, user_id))
        
        return {"message": "Notificações marcadas como lidas."}
    except Exception as e:
        logger.error(f"Erro ao marcar notificações como lidas: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno.")


# ============================================================================
# ENDPOINTS DE RECURSOS DIDÁTICOS
# ============================================================================

@app.post("/didactic-resource/generate", response_model=DidacticResourceJobResponse, dependencies=[Depends(verify_token)])
async def generate_didactic_resource(
    body: GenerateResourceRequest,
    background_tasks: BackgroundTasks
):
    """
    Inicia a geração assíncrona de um recurso didático para uma SA.
    Retorna imediatamente com um job_id para consulta posterior.
    """
    logger.info(f"Endpoint /didactic-resource/generate chamado para plan_id: {body.plan_id}, sa_index: {body.sa_index}")
    
    try:
        # Buscar dados do plano
        plan_data = await get_plan_data_for_resource(body.plan_id)
        if not plan_data:
            raise HTTPException(status_code=404, detail="Plano não encontrado.")
        
        # Criar registro do recurso
        resource_id = uuid.uuid4()
        job_id = uuid.uuid4()
        
        async with (await get_checkpoint_connection()).connection() as conn:
            async with conn.cursor() as cur:
                # Inserir recurso com status pending
                await cur.execute("""
                    INSERT INTO didactic_resources (id, plan_id, sa_index, title, blob_path, num_chapters, status, user_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    resource_id,
                    uuid.UUID(body.plan_id),
                    body.sa_index,
                    "Gerando...",  # Título temporário
                    "",  # GCS blob será preenchido depois
                    body.num_chapters,
                    ResourceStatus.pending.value,
                    body.user_id
                ))
                
                # Criar job de geração
                await cur.execute("""
                    INSERT INTO generation_jobs (job_id, user_id, thread_id, status, progress, current_step, request_payload)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (
                    job_id,
                    body.user_id,
                    str(resource_id),  # Usar resource_id como thread_id
                    JobStatus.pending.value,
                    0,
                    "Iniciando geração...",
                    json.dumps({"resource_id": str(resource_id), "plan_id": body.plan_id, "sa_index": body.sa_index, "num_chapters": body.num_chapters})
                ))
        
        # Iniciar processamento em background
        background_tasks.add_task(
            process_didactic_resource_generation,
            str(job_id),
            str(resource_id),
            body.plan_id,
            body.sa_index,
            body.num_chapters,
            body.user_id,
            plan_data
        )
        
        return DidacticResourceJobResponse(
            job_id=str(job_id),
            resource_id=str(resource_id),
            status=ResourceStatus.pending,
            message="Geração de recurso didático iniciada."
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao iniciar geração de recurso didático: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno ao iniciar geração.")


async def get_plan_data_for_resource(plan_id: str) -> Optional[dict]:
    """Busca dados do plano necessários para gerar o recurso."""
    try:
        from .document_store import get_plan_document_with_metadata
        
        plan_data = await get_plan_document_with_metadata(plan_id)
        return plan_data
    except Exception as e:
        logger.error(f"Erro ao buscar dados do plano {plan_id}: {e}")
        return None


async def process_didactic_resource_generation(
    job_id: str,
    resource_id: str,
    plan_id: str,
    sa_index: int,
    num_chapters: int,
    user_id: str,
    plan_data: dict
):
    """Função de background que processa a geração do recurso didático."""
    from .agents.didactic_resource_agent import run_didactic_resource_agent
    from .document_store import _upload_bytes_to_azure, AZURE_PLANS_CONTAINER
    
    logger.info(f"Iniciando geração de recurso didático {resource_id}")
    
    async def update_status(status: str, progress: int, current_step: str = None, error: str = None):
        async with (await get_checkpoint_connection()).connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    UPDATE generation_jobs
                    SET status = %s, progress = %s, current_step = %s, error = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE job_id = %s
                """, (status, progress, current_step, error, uuid.UUID(job_id)))
    
    async def update_resource(title: str = None, blob_path: str = None, status: str = None, error: str = None):
        async with (await get_checkpoint_connection()).connection() as conn:
            async with conn.cursor() as cur:
                updates = []
                params = []
                if title:
                    updates.append("title = %s")
                    params.append(title)
                if blob_path:
                    updates.append("blob_path = %s")
                    params.append(blob_path)
                if status:
                    updates.append("status = %s")
                    params.append(status)
                if error:
                    updates.append("error = %s")
                    params.append(error)
                updates.append("updated_at = CURRENT_TIMESTAMP")
                
                params.append(uuid.UUID(resource_id))
                
                await cur.execute(f"""
                    UPDATE didactic_resources SET {', '.join(updates)} WHERE id = %s
                """, tuple(params))
    
    try:
        await update_status(JobStatus.processing.value, 5, "Extraindo dados da SA...")
        await update_resource(status=ResourceStatus.processing.value)
        
        # Extrair dados da SA do plano
        plan_content = plan_data.get("plan_content", {})
        # Se plan_content for string JSON, fazer parse
        if isinstance(plan_content, str):
            plan_content = json.loads(plan_content)
        plano_ensino = plan_content.get("plano_de_ensino", {})
        situacoes = plano_ensino.get("situacoes_aprendizagem", [])
        info_curso = plano_ensino.get("informacoes_curso", {})
        
        if sa_index >= 0:
            # SA específica
            if sa_index >= len(situacoes):
                raise ValueError(f"SA index {sa_index} não encontrada no plano.")
            sa = situacoes[sa_index]
            sas_to_process = [sa]
        else:
            # Todas as SAs
            sas_to_process = situacoes
        
        # Processar cada SA
        all_docx_bytes = []
        all_titles = []
        
        for idx, sa in enumerate(sas_to_process):
            sa_tema = sa.get("tema_gerador", sa.get("desafio", "Situação de Aprendizagem"))
            
            # Extrair capacidades
            capacidades = sa.get("capacidades", {})
            cap_tecnicas = capacidades.get("tecnicas", [])
            cap_socio = capacidades.get("socioemocionais", [])
            
            estrategia = sa.get("estrategia_aprendizagem", {}).get("tipo", "Situação-Problema")
            
            curso_nome = info_curso.get("curso", "Curso Técnico")
            uc_nome = info_curso.get("unidade_curricular", "Unidade Curricular")
            
            await update_status(JobStatus.processing.value, 10 + (idx * 80 // len(sas_to_process)), f"Gerando recurso para SA {idx + 1}...")
            
            # Chamar o agente
            def on_progress(progress, step):
                # Atualização síncrona simplificada
                logger.info(f"Progresso SA {idx + 1}: {progress}% - {step}")
            
            result = await run_didactic_resource_agent(
                sa_tema=sa_tema,
                sa_capacidades_tecnicas=cap_tecnicas,
                sa_capacidades_socioemocionais=cap_socio,
                sa_estrategia=estrategia,
                curso_nome=curso_nome,
                uc_nome=uc_nome,
                num_chapters=num_chapters,
                on_progress=on_progress
            )
            
            if result.get("status") == "failed":
                raise Exception(result.get("error", "Erro desconhecido na geração"))
            
            all_docx_bytes.append(result.get("docx_bytes"))
            all_titles.append(result.get("title", f"Recurso SA {idx + 1}"))
        
        # Usar o primeiro título ou combinar
        final_title = all_titles[0] if len(all_titles) == 1 else f"Recursos Didáticos - {len(all_titles)} SAs"
        final_docx = all_docx_bytes[0]  # Para múltiplas SAs, poderia combinar
        
        await update_status(JobStatus.processing.value, 90, "Salvando no armazenamento...")
        
        # Salvar no Azure Blob Storage
        blob_name = f"didactic-resources/{user_id}/{resource_id}.docx"
        
        await _upload_bytes_to_azure(AZURE_PLANS_CONTAINER, final_docx, blob_name, content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
        
        logger.info(f"Recurso didático salvo em Azure Blob: {blob_name}")
        
        # Atualizar registros
        await update_resource(title=final_title, blob_path=blob_name, status=ResourceStatus.completed.value)
        
        await update_status(JobStatus.completed.value, 100, "Concluído", error=None)
        
        # Atualizar resultado do job
        async with (await get_checkpoint_connection()).connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    UPDATE generation_jobs
                    SET result = %s, status = %s, progress = 100, updated_at = CURRENT_TIMESTAMP
                    WHERE job_id = %s
                """, (
                    json.dumps({"resource_id": resource_id, "title": final_title, "blob_path": blob_name}),
                    JobStatus.completed.value,
                    uuid.UUID(job_id)
                ))
        
        logger.info(f"Geração de recurso didático {resource_id} concluída com sucesso!")
        
    except Exception as e:
        logger.error(f"Erro na geração do recurso didático {resource_id}: {e}", exc_info=True)
        await update_status(JobStatus.failed.value, 0, None, str(e))
        await update_resource(status=ResourceStatus.failed.value, error=str(e))


@app.get("/didactic-resource/status/{job_id}", response_model=JobStatusResponse, dependencies=[Depends(verify_token)])
async def get_didactic_resource_status(job_id: str):
    """
    Retorna o status atual de um job de geração de recurso didático.
    """
    logger.info(f"Endpoint /didactic-resource/status/{job_id} chamado")
    
    try:
        async with (await get_checkpoint_connection()).connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute("""
                    SELECT status, progress, current_step, result, error
                    FROM generation_jobs
                    WHERE job_id = %s
                """, (uuid.UUID(job_id),))
                record = await cur.fetchone()
        
        if not record:
            raise HTTPException(status_code=404, detail="Job não encontrado.")
        
        result = record['result']
        if isinstance(result, str):
            result = json.loads(result)
        
        return JobStatusResponse(
            job_id=job_id,
            status=record['status'],
            progress=record['progress'],
            current_step=record['current_step'],
            result=result,
            error=record['error']
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao buscar status do job {job_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno ao buscar status.")


@app.get("/didactic-resources/{plan_id}", response_model=DidacticResourceListResponse, dependencies=[Depends(verify_token)])
async def list_didactic_resources(plan_id: str):
    """
    Lista todos os recursos didáticos gerados para um plano.
    """
    logger.info(f"Endpoint /didactic-resources/{plan_id} chamado")
    
    try:
        async with (await get_checkpoint_connection()).connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute("""
                    SELECT id, plan_id, sa_index, title, blob_path, num_chapters, status, error, created_at, updated_at
                    FROM didactic_resources
                    WHERE plan_id = %s
                    ORDER BY created_at DESC
                """, (uuid.UUID(plan_id),))
                records = await cur.fetchall()
        
        container_name = os.getenv("AZURE_PLANS_CONTAINER")
        
        resources = []
        for r in records:
            blob_url = None
            if r['blob_path']:
                blob_url = f"azure://{container_name}/{r['blob_path']}"
            
            resources.append(DidacticResourceResponse(
                id=str(r['id']),
                plan_id=str(r['plan_id']),
                sa_index=r['sa_index'],
                title=r['title'],
                blob_url=blob_url,
                num_chapters=r['num_chapters'],
                status=ResourceStatus(r['status']),
                error=r['error'],
                created_at=r['created_at'],
                updated_at=r['updated_at']
            ))
        
        return DidacticResourceListResponse(plan_id=plan_id, resources=resources)
        
    except Exception as e:
        logger.error(f"Erro ao listar recursos do plano {plan_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno ao listar recursos.")


@app.get("/didactic-resource/download/{resource_id}", dependencies=[Depends(verify_token)])
async def download_didactic_resource(resource_id: str):
    """
    Baixa o arquivo DOCX de um recurso didático.
    """
    logger.info(f"Endpoint /didactic-resource/download/{resource_id} chamado")
    
    try:
        from .document_store import _download_bytes_from_azure, AZURE_PLANS_CONTAINER as DL_PLANS_CONTAINER
        from fastapi.responses import StreamingResponse
        
        async with (await get_checkpoint_connection()).connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute("""
                    SELECT title, blob_path, status
                    FROM didactic_resources
                    WHERE id = %s
                """, (uuid.UUID(resource_id),))
                record = await cur.fetchone()
        
        if not record:
            raise HTTPException(status_code=404, detail="Recurso não encontrado.")
        
        if record['status'] != ResourceStatus.completed.value:
            raise HTTPException(status_code=400, detail="Recurso ainda não está pronto para download.")
        
        if not record['blob_path']:
            raise HTTPException(status_code=404, detail="Arquivo não encontrado no armazenamento.")
        
        # Baixar do Azure Blob Storage
        content = await _download_bytes_from_azure(DL_PLANS_CONTAINER, record['blob_path'])
        if content is None:
            raise HTTPException(status_code=404, detail="Arquivo não encontrado no armazenamento.")
        
        # Nome do arquivo para download
        safe_title = "".join(c for c in record['title'] if c.isalnum() or c in (' ', '-', '_')).strip()
        filename = f"{safe_title[:50]}.docx"
        
        return StreamingResponse(
            iter([content]),
            media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            headers={'Content-Disposition': f'attachment; filename="{filename}"'}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao baixar recurso {resource_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno ao baixar recurso.")


# ============================================================
# ENDPOINTS DE SLIDES (PPTX)
# ============================================================

@app.post("/slides/generate", response_model=SlideResourceJobResponse, dependencies=[Depends(verify_token)])
async def generate_slides_endpoint(
    request: GenerateSlidesRequest,
    background_tasks: BackgroundTasks,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Inicia a geração assíncrona de slides para uma SA de um plano.
    """
    logger.info(f"Iniciando geração de slides para plano {request.plan_id}, SA index {request.sa_index}")
    
    try:
        # Buscar dados do plano via GCS
        plan_data = await get_plan_data_for_resource(request.plan_id)
        if not plan_data:
            raise HTTPException(status_code=404, detail="Plano não encontrado.")
        
        # Buscar user_id do plano
        async with (await get_checkpoint_connection()).connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    "SELECT user_id FROM user_plans WHERE id = %s",
                    (uuid.UUID(request.plan_id),)
                )
                plan_record = await cur.fetchone()
                
                if not plan_record:
                    raise HTTPException(status_code=404, detail="Plano não encontrado.")
        
        # Gerar IDs
        job_id = str(uuid.uuid4())
        resource_id = str(uuid.uuid4())
        user_id = plan_record['user_id']
        
        # Criar registro do job
        async with (await get_checkpoint_connection()).connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    INSERT INTO generation_jobs (job_id, user_id, thread_id, status, progress, current_step, request_payload)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (
                    uuid.UUID(job_id),
                    user_id,
                    f"slides_{resource_id}",
                    JobStatus.pending.value,
                    0,
                    "Iniciando geração de slides...",
                    json.dumps({"plan_id": request.plan_id, "sa_index": request.sa_index, "num_slides": request.num_slides, "template": request.template.value})
                ))
        
        # Criar registro do recurso
        async with (await get_checkpoint_connection()).connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    INSERT INTO slide_resources (id, plan_id, sa_index, num_slides, status, user_id)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (
                    uuid.UUID(resource_id),
                    uuid.UUID(request.plan_id),
                    request.sa_index,
                    request.num_slides,
                    SlideResourceStatus.PENDING.value,
                    user_id
                ))
        
        # Iniciar processamento em background
        background_tasks.add_task(
            process_slides_generation,
            job_id=job_id,
            resource_id=resource_id,
            plan_id=request.plan_id,
            sa_index=request.sa_index,
            num_slides=request.num_slides,
            template=request.template.value,
            plan_data=plan_data,
            user_id=user_id
        )
        
        return SlideResourceJobResponse(
            job_id=job_id,
            resource_id=resource_id,
            status=JobStatus.pending.value,
            message="Geração de slides iniciada com sucesso."
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao iniciar geração de slides: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno ao iniciar geração.")




async def process_slides_generation(
    job_id: str,
    resource_id: str,
    plan_id: str,
    sa_index: int,
    num_slides: int,
    template: str,
    plan_data: dict,
    user_id: str
):
    """Processa a geração de slides em background."""
    from src.agents.slides_agent import generate_slides
    from src.document_store import _upload_bytes_to_azure, AZURE_PLANS_CONTAINER as SLIDES_CONTAINER
    
    logger.info(f"Processando slides {resource_id} para plano {plan_id}")
    
    async def update_status(status: str, progress: int, step: str = None, error: str = None):
        async with (await get_checkpoint_connection()).connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    UPDATE generation_jobs
                    SET status = %s, progress = %s, current_step = %s, error = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE job_id = %s
                """, (status, progress, step, error, uuid.UUID(job_id)))
    
    async def update_resource(title: str = None, blob_path: str = None, num_slides: int = None, status: str = None, error: str = None):
        async with (await get_checkpoint_connection()).connection() as conn:
            async with conn.cursor() as cur:
                updates = ["updated_at = CURRENT_TIMESTAMP"]
                params = []
                
                if title:
                    updates.append("title = %s")
                    params.append(title)
                if blob_path:
                    updates.append("blob_path = %s")
                    params.append(blob_path)
                if num_slides:
                    updates.append("num_slides = %s")
                    params.append(num_slides)
                if status:
                    updates.append("status = %s")
                    params.append(status)
                if error:
                    updates.append("error = %s")
                    params.append(error)
                
                params.append(uuid.UUID(resource_id))
                
                await cur.execute(f"""
                    UPDATE slide_resources
                    SET {', '.join(updates)}
                    WHERE id = %s
                """, tuple(params))
    
    try:
        await update_status(JobStatus.processing.value, 5, "Preparando dados da SA...")
        await update_resource(status=SlideResourceStatus.PROCESSING.value)
        
        # Extrair plan_content do plan_data
        plan_content = plan_data.get("plan_content", {})
        if isinstance(plan_content, str):
            plan_content = json.loads(plan_content)
        
        plano_ensino = plan_content.get("plano_de_ensino", {})
        situacoes = plano_ensino.get("situacoes_aprendizagem", [])
        info_curso = plano_ensino.get("informacoes_curso", {})
        
        # Determinar quais SAs processar
        if sa_index == -1:
            sas_to_process = list(enumerate(situacoes))
        else:
            if sa_index < 0 or sa_index >= len(situacoes):
                raise ValueError(f"Índice de SA inválido: {sa_index}")
            sas_to_process = [(sa_index, situacoes[sa_index])]
        
        await update_status(JobStatus.processing.value, 10, f"Processando {len(sas_to_process)} SA(s)...")
        
        all_pptx_bytes = []
        final_title = ""
        final_num_slides = 0
        
        for idx, (sa_idx, sa) in enumerate(sas_to_process):
            progress = 10 + int((idx / len(sas_to_process)) * 80)
            sa_tema = sa.get("tema_desafio", sa.get("descricao", f"SA {sa_idx + 1}"))
            await update_status(JobStatus.processing.value, progress, f"Gerando slides para SA {sa_idx + 1}: {sa_tema[:30]}...")
            
            result = await generate_slides(
                sa_tema=sa_tema,
                sa_capacidades_tecnicas=sa.get("capacidades_tecnicas", []),
                sa_capacidades_socioemocionais=sa.get("capacidades_socioemocionais", []),
                sa_estrategia=sa.get("estrategia", ""),
                sa_conhecimentos=sa.get("conhecimentos", []),
                curso_nome=info_curso.get("curso", ""),
                uc_nome=info_curso.get("unidade_curricular", ""),
                area_tecnologica=info_curso.get("area_tecnologica", ""),
                num_slides=num_slides,
                template=template
            )
            
            if result.get("status") == "completed" and result.get("pptx_bytes"):
                all_pptx_bytes.append(result["pptx_bytes"])
                if not final_title:
                    final_title = result.get("title", sa_tema)
                final_num_slides += result.get("num_slides", 0)
            else:
                raise Exception(result.get("error", "Erro desconhecido na geração de slides"))
        
        if not all_pptx_bytes:
            raise Exception("Nenhum slide foi gerado.")
        
        # Para múltiplas SAs, usar o primeiro arquivo (poderia combinar no futuro)
        final_pptx = all_pptx_bytes[0]
        
        await update_status(JobStatus.processing.value, 90, "Salvando no armazenamento...")
        
        # Salvar no Azure Blob Storage
        blob_name = f"slides/{user_id}/{resource_id}.pptx"
        
        await _upload_bytes_to_azure(SLIDES_CONTAINER, final_pptx, blob_name, content_type='application/vnd.openxmlformats-officedocument.presentationml.presentation')
        
        logger.info(f"Slides salvos em Azure Blob: {blob_name}")
        
        # Atualizar registros
        await update_resource(title=final_title, blob_path=blob_name, num_slides=final_num_slides, status=SlideResourceStatus.COMPLETED.value)
        
        await update_status(JobStatus.completed.value, 100, "Concluído", error=None)
        
        # Atualizar resultado do job
        async with (await get_checkpoint_connection()).connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    UPDATE generation_jobs
                    SET result = %s, status = %s, progress = 100, updated_at = CURRENT_TIMESTAMP
                    WHERE job_id = %s
                """, (
                    json.dumps({"resource_id": resource_id, "title": final_title, "blob_path": blob_name, "num_slides": final_num_slides}),
                    JobStatus.completed.value,
                    uuid.UUID(job_id)
                ))
        
        logger.info(f"Geração de slides {resource_id} concluída com sucesso!")
        
    except Exception as e:
        logger.error(f"Erro na geração de slides {resource_id}: {e}", exc_info=True)
        await update_status(JobStatus.failed.value, 0, None, str(e))
        await update_resource(status=SlideResourceStatus.FAILED.value, error=str(e))


@app.get("/slides/status/{job_id}", response_model=JobStatusResponse, dependencies=[Depends(verify_token)])
async def get_slides_status(job_id: str):
    """Retorna o status de um job de geração de slides."""
    logger.info(f"Endpoint /slides/status/{job_id} chamado")
    
    try:
        async with (await get_checkpoint_connection()).connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    "SELECT * FROM generation_jobs WHERE job_id = %s",
                    (uuid.UUID(job_id),)
                )
                job = await cur.fetchone()
                
                if not job:
                    raise HTTPException(status_code=404, detail="Job não encontrado.")
                
                result = None
                if job.get('result'):
                    result = job['result'] if isinstance(job['result'], dict) else json.loads(job['result'])
                
                return JobStatusResponse(
                    job_id=str(job['job_id']),
                    status=JobStatus(job['status']),
                    progress=job['progress'],
                    current_step=job.get('current_step'),
                    result=result,
                    error=job.get('error'),
                    created_at=job['created_at'],
                    updated_at=job['updated_at']
                )
                
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao obter status do job {job_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno.")


@app.get("/slides/{plan_id}", response_model=SlideResourceListResponse, dependencies=[Depends(verify_token)])
async def list_slide_resources(plan_id: str):
    """Lista todos os recursos de slides gerados para um plano."""
    logger.info(f"Endpoint /slides/{plan_id} chamado")
    
    try:
        async with (await get_checkpoint_connection()).connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute("""
                    SELECT * FROM slide_resources 
                    WHERE plan_id = %s
                    ORDER BY created_at DESC
                """, (uuid.UUID(plan_id),))
                resources = await cur.fetchall()
                
                return SlideResourceListResponse(
                    resources=[
                        SlideResourceResponse(
                            id=str(r['id']),
                            plan_id=str(r['plan_id']),
                            sa_index=r['sa_index'],
                            title=r.get('title'),
                            num_slides=r.get('num_slides'),
                            status=SlideResourceStatus(r['status']),
                            blob_path=r.get('blob_path'),
                            error=r.get('error'),
                            created_at=r.get('created_at'),
                            updated_at=r.get('updated_at')
                        )
                        for r in resources
                    ],
                    total=len(resources)
                )
                
    except Exception as e:
        logger.error(f"Erro ao listar slides do plano {plan_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno.")


@app.get("/slides/download/{resource_id}", dependencies=[Depends(verify_token)])
async def download_slides(resource_id: str):
    """Baixa o arquivo PPTX de um recurso de slides."""
    logger.info(f"Endpoint /slides/download/{resource_id} chamado")
    from .document_store import _download_bytes_from_azure, AZURE_PLANS_CONTAINER as DL_SLIDES_CONTAINER
    
    try:
        async with (await get_checkpoint_connection()).connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    "SELECT * FROM slide_resources WHERE id = %s",
                    (uuid.UUID(resource_id),)
                )
                record = await cur.fetchone()
                
                if not record:
                    raise HTTPException(status_code=404, detail="Recurso não encontrado.")
                
                if record['status'] != SlideResourceStatus.COMPLETED.value:
                    raise HTTPException(status_code=400, detail=f"Recurso não está pronto. Status: {record['status']}")
                
                if not record.get('blob_path'):
                    raise HTTPException(status_code=404, detail="Arquivo não encontrado.")
        
        # Baixar do Azure Blob Storage
        content = await _download_bytes_from_azure(DL_SLIDES_CONTAINER, record['blob_path'])
        if content is None:
            raise HTTPException(status_code=404, detail="Arquivo não encontrado no armazenamento.")
        
        # Nome do arquivo para download
        title = record.get('title') or 'Apresentacao'
        safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).strip()
        filename = f"{safe_title[:50]}.pptx"
        
        return StreamingResponse(
            iter([content]),
            media_type='application/vnd.openxmlformats-officedocument.presentationml.presentation',
            headers={'Content-Disposition': f'attachment; filename="{filename}"'}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao baixar slides {resource_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno ao baixar recurso.")


# ============================================================
# ENDPOINTS DE EXERCÍCIOS
# ============================================================

async def process_exercises_generation(
    job_id: str,
    resource_id: str,
    plan_id: str,
    sa_index: int,
    quantities: Dict[str, int],
    plan_data: Dict[str, Any],
    user_id: str
):
    """Processa a geração de exercícios em background."""
    logger.info(f"Iniciando job de exercícios {job_id} para usuário {user_id}")
    
    async def update_job_status(status: str, progress: int, step: str = None, error: str = None):
        async with (await get_checkpoint_connection()).connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    UPDATE generation_jobs
                    SET status = %s, progress = %s, current_step = %s, error = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE job_id = %s
                """, (status, progress, step, error, uuid.UUID(job_id)))
    
    async def update_resource(title: str = None, blob_path: str = None, status: str = None, error: str = None):
        async with (await get_checkpoint_connection()).connection() as conn:
            async with conn.cursor() as cur:
                updates = ["updated_at = CURRENT_TIMESTAMP"]
                params = []
                
                if title:
                    updates.append("title = %s")
                    params.append(title)
                if blob_path:
                    updates.append("blob_path = %s")
                    params.append(blob_path)
                if status:
                    updates.append("status = %s")
                    params.append(status)
                if error:
                    updates.append("error = %s")
                    params.append(error)
                    
                params.append(uuid.UUID(resource_id))
                
                query = f"UPDATE didactic_resources SET {', '.join(updates)} WHERE id = %s"
                await cur.execute(query, params)
    
    try:
        await update_job_status(JobStatus.processing.value, 10, "Extraindo contexto da SA...")
        await update_resource(status=ResourceStatus.processing.value)
        
        # Extrair plan_content do plan_data
        plan_content = plan_data.get("plan_content", {})
        if isinstance(plan_content, str):
            plan_content = json.loads(plan_content)
        
        plano_ensino = plan_content.get("plano_de_ensino", {})
        situacoes = plano_ensino.get("situacoes_aprendizagem", [])
        
        # sa_index -1 significa todas as SAs
        if sa_index < 0:
            # Combinar conhecimentos de todas as SAs
            all_conhecimentos = []
            all_capacidades = []
            tema = "Todas as Situações de Aprendizagem"
            for sa in situacoes:
                for c in sa.get("conhecimentos", []):
                    if c not in all_conhecimentos:
                        all_conhecimentos.append(c)
                for cap in sa.get("capacidades_tecnicas", []):
                    if cap not in all_capacidades:
                        all_capacidades.append(cap)
            sa_conhecimentos = all_conhecimentos
            sa_capacidades = all_capacidades
        else:
            if sa_index >= len(situacoes):
                raise ValueError(f"Índice de SA inválido: {sa_index}")
            sa = situacoes[sa_index]
            tema = sa.get("tema_desafio", sa.get("descricao", f"SA {sa_index + 1}"))
            sa_conhecimentos = sa.get("conhecimentos", [])
            sa_capacidades = sa.get("capacidades_tecnicas", [])
        
        await update_job_status(JobStatus.processing.value, 30, "Gerando questões com IA...")
        
        # Chamar agente de exercícios
        result = await generate_exercises(
            sa_tema=tema,
            sa_capacidades_tecnicas=sa_capacidades,
            sa_conhecimentos=sa_conhecimentos,
            quantities=quantities
        )
        
        if result.get("status") == "failed":
            raise Exception(result.get("error", "Erro desconhecido na geração"))
            
        await update_job_status(JobStatus.processing.value, 70, "Salvando arquivo...")
        
        # Salvar no GCS
        docx_bytes = result.get("docx_bytes")
        if not docx_bytes:
            raise Exception("Nenhum arquivo DOCX gerado")
            
        from src.document_store import _upload_bytes_to_azure, AZURE_PLANS_CONTAINER as EX_CONTAINER
        user_folder = str(user_id)
        blob_name = f"exercises/{user_folder}/{resource_id}.docx"
        
        await _upload_bytes_to_azure(EX_CONTAINER, docx_bytes, blob_name, content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
        
        await update_job_status(JobStatus.processing.value, 90, "Finalizando...")
        
        # Atualizar recurso com título e GCS
        title = result.get("title", f"Lista de Exercícios - {tema[:50]}")
        await update_resource(title=title, blob_path=blob_name, status=ResourceStatus.completed.value)
        
        # Finalizar job com resultado
        async with (await get_checkpoint_connection()).connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    UPDATE generation_jobs
                    SET status = %s, progress = %s, current_step = %s, result = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE job_id = %s
                """, (
                    JobStatus.completed.value,
                    100,
                    "Concluído!",
                    json.dumps({"resource_id": resource_id, "title": title}),
                    uuid.UUID(job_id)
                ))
        
        logger.info(f"Job {job_id} concluído com sucesso.")

    except Exception as e:
        logger.error(f"Erro no job de exercícios {job_id}: {e}", exc_info=True)
        await update_job_status(JobStatus.failed.value, 0, None, str(e))
        await update_resource(status=ResourceStatus.failed.value, error=str(e))


@app.post("/exercises/generate", response_model=DidacticResourceJobResponse)
async def generate_exercises_endpoint(
    request: GenerateExercisesRequest,
    background_tasks: BackgroundTasks,
    token: HTTPAuthorizationCredentials = Depends(verify_token)
):
    """Gera lista de exercícios e retorna Job ID."""
    logger.info(f"Recebida solicitação de exercícios: {request}")
    
    try:
        # Validar Plano
        plan_data = await get_plan_data_for_resource(str(request.plan_id))
        
        if not plan_data:
             raise HTTPException(status_code=404, detail="Plano não encontrado")

        job_id = uuid.uuid4()
        resource_id = uuid.uuid4()
        
        async with (await get_checkpoint_connection()).connection() as conn:
            async with conn.cursor() as cur:
                # Criar registro do recurso em didactic_resources
                await cur.execute("""
                    INSERT INTO didactic_resources (id, plan_id, sa_index, title, blob_path, num_chapters, status, user_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    resource_id,
                    uuid.UUID(request.plan_id),
                    request.sa_index,
                    "Lista de Exercícios",
                    "",
                    1,  # num_chapters não se aplica, mas é obrigatório
                    ResourceStatus.pending.value,
                    request.user_id
                ))
                
                # Criar job de geração em generation_jobs
                await cur.execute("""
                    INSERT INTO generation_jobs (job_id, user_id, thread_id, status, progress, current_step, request_payload)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (
                    job_id,
                    request.user_id,
                    str(resource_id),
                    JobStatus.pending.value,
                    0,
                    "Iniciando geração de exercícios...",
                    json.dumps({"resource_id": str(resource_id), "plan_id": request.plan_id, "sa_index": request.sa_index, "quantities": request.quantities})
                ))
        
        # Enviar para background
        background_tasks.add_task(
            process_exercises_generation,
            str(job_id),
            str(resource_id),
            request.plan_id,
            request.sa_index,
            request.quantities,
            plan_data,
            request.user_id
        )
        
        return DidacticResourceJobResponse(
            job_id=str(job_id),
            resource_id=str(resource_id),
            status=ResourceStatus.pending,
            message="Geração de lista de exercícios iniciada."
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao iniciar geração de exercícios: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv('PORT'))
    logger.info(f"Servidor FastAPI será iniciado na porta {port}")
    uvicorn.run(app, host="0.0.0.0", port=port, timeout_keep_alive=300)


# ============================================================
# ENDPOINTS DE PREVIEW (VISUALIZAÇÃO DE DOCUMENTOS)
# ============================================================

@app.get("/plan/{plan_id}/preview", dependencies=[Depends(verify_token)])
async def preview_plan(plan_id: str):
    """
    Retorna PDF do plano de ensino para visualização.
    Gera o DOCX on-demand e converte para PDF (com cache).
    """
    from .utils.pdf_converter import convert_to_pdf
    from .document_store import _download_bytes_from_azure, _upload_bytes_to_azure, _generate_sas_url, AZURE_PLANS_CONTAINER as PREVIEW_CONTAINER
    
    logger.info(f"Endpoint /plan/{plan_id}/preview chamado")
    
    try:
        pdf_blob_name = f"previews/plans/{plan_id}.pdf"
        
        # Verificar cache
        cached_pdf = await _download_bytes_from_azure(PREVIEW_CONTAINER, pdf_blob_name)
        if cached_pdf:
            logger.info(f"PDF do plano encontrado em cache: {pdf_blob_name}")
            signed_url = _generate_sas_url(PREVIEW_CONTAINER, pdf_blob_name)
            return RedirectResponse(url=signed_url)
        
        # PDF não existe, precisa gerar
        logger.info(f"Gerando PDF para plano {plan_id}...")
        
        # Buscar dados do plano
        plan_data = await get_plan_data_for_resource(plan_id)
        if not plan_data:
            raise HTTPException(status_code=404, detail="Plano não encontrado.")
        
        # Gerar DOCX
        plan_content = plan_data.get("plan_content", {})
        if isinstance(plan_content, str):
            plan_content = json.loads(plan_content)
        
        # Buscar departamento_regional do plano
        departamento_regional = plan_data.get("departamento_regional")
        
        # Usar o exportador existente
        docx_buffer = generate_docx(plan_content, departamento_regional)
        docx_bytes = docx_buffer.getvalue()
        
        # Converter para PDF
        pdf_bytes = convert_to_pdf(docx_bytes, f"plano_{plan_id}.docx")
        if not pdf_bytes:
            raise HTTPException(status_code=500, detail="Erro na conversão para PDF.")
        
        # Salvar no cache (Azure Blob)
        await _upload_bytes_to_azure(PREVIEW_CONTAINER, pdf_bytes, pdf_blob_name, content_type="application/pdf")
        logger.info(f"PDF do plano salvo em cache: {pdf_blob_name}")
        
        # Gerar URL com SAS token
        signed_url = _generate_sas_url(PREVIEW_CONTAINER, pdf_blob_name)
        return RedirectResponse(url=signed_url)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao gerar preview do plano {plan_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro ao gerar visualização.")


@app.get("/didactic-resource/{resource_id}/preview", dependencies=[Depends(verify_token)])
async def preview_didactic_resource(resource_id: str):
    """
    Retorna PDF do recurso didático (caderno de estudo) para visualização.
    """
    from .utils.pdf_converter import convert_to_pdf
    from .document_store import _download_bytes_from_azure, _upload_bytes_to_azure, _generate_sas_url, AZURE_PLANS_CONTAINER as PREVIEW_DR_CONTAINER
    
    logger.info(f"Endpoint /didactic-resource/{resource_id}/preview chamado")
    
    try:
        # Buscar informações do recurso
        async with (await get_checkpoint_connection()).connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute("""
                    SELECT title, blob_path, status
                    FROM didactic_resources
                    WHERE id = %s
                """, (uuid.UUID(resource_id),))
                record = await cur.fetchone()
        
        if not record:
            raise HTTPException(status_code=404, detail="Recurso não encontrado.")
        
        if record['status'] != ResourceStatus.completed.value:
            raise HTTPException(status_code=400, detail="Recurso ainda não está pronto.")
        
        if not record['blob_path']:
            raise HTTPException(status_code=404, detail="Arquivo não encontrado.")
        
        source_blob_name = record['blob_path']
        pdf_blob_name = source_blob_name.replace('.docx', '.pdf').replace('.DOCX', '.pdf')
        
        # Verificar cache
        cached_pdf = await _download_bytes_from_azure(PREVIEW_DR_CONTAINER, pdf_blob_name)
        if cached_pdf:
            logger.info(f"PDF do recurso encontrado em cache: {pdf_blob_name}")
            signed_url = _generate_sas_url(PREVIEW_DR_CONTAINER, pdf_blob_name)
            return RedirectResponse(url=signed_url)
        
        # PDF não existe, converter
        logger.info(f"Convertendo recurso didático para PDF: {source_blob_name}")
        
        docx_bytes = await _download_bytes_from_azure(PREVIEW_DR_CONTAINER, source_blob_name)
        if not docx_bytes:
            raise HTTPException(status_code=404, detail="Arquivo fonte não encontrado.")
        
        pdf_bytes = convert_to_pdf(docx_bytes, f"{record['title']}.docx")
        if not pdf_bytes:
            raise HTTPException(status_code=500, detail="Erro na conversão para PDF.")
        
        # Salvar no cache (Azure Blob)
        await _upload_bytes_to_azure(PREVIEW_DR_CONTAINER, pdf_bytes, pdf_blob_name, content_type="application/pdf")
        logger.info(f"PDF do recurso salvo em cache: {pdf_blob_name}")
        
        signed_url = _generate_sas_url(PREVIEW_DR_CONTAINER, pdf_blob_name)
        return RedirectResponse(url=signed_url)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao gerar preview do recurso {resource_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro ao gerar visualização.")


@app.get("/slides/{resource_id}/preview", dependencies=[Depends(verify_token)])
async def preview_slides(resource_id: str):
    """
    Retorna PDF dos slides para visualização.
    """
    from .utils.pdf_converter import convert_to_pdf
    from .document_store import _download_bytes_from_azure, _upload_bytes_to_azure, _generate_sas_url, AZURE_PLANS_CONTAINER as PREVIEW_SLIDES_CONTAINER
    
    logger.info(f"Endpoint /slides/{resource_id}/preview chamado")
    
    try:
        # Buscar informações do recurso
        async with (await get_checkpoint_connection()).connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute("""
                    SELECT title, blob_path, status
                    FROM slide_resources
                    WHERE id = %s
                """, (uuid.UUID(resource_id),))
                record = await cur.fetchone()
        
        if not record:
            raise HTTPException(status_code=404, detail="Recurso não encontrado.")
        
        if record['status'] != SlideResourceStatus.COMPLETED.value:
            raise HTTPException(status_code=400, detail="Recurso ainda não está pronto.")
        
        if not record.get('blob_path'):
            raise HTTPException(status_code=404, detail="Arquivo não encontrado.")
        
        source_blob_name = record['blob_path']
        pdf_blob_name = source_blob_name.replace('.pptx', '.pdf').replace('.PPTX', '.pdf')
        
        # Verificar cache
        cached_pdf = await _download_bytes_from_azure(PREVIEW_SLIDES_CONTAINER, pdf_blob_name)
        if cached_pdf:
            logger.info(f"PDF dos slides encontrado em cache: {pdf_blob_name}")
            signed_url = _generate_sas_url(PREVIEW_SLIDES_CONTAINER, pdf_blob_name)
            return RedirectResponse(url=signed_url)
        
        # PDF não existe, converter
        logger.info(f"Convertendo slides para PDF: {source_blob_name}")
        
        pptx_bytes = await _download_bytes_from_azure(PREVIEW_SLIDES_CONTAINER, source_blob_name)
        if not pptx_bytes:
            raise HTTPException(status_code=404, detail="Arquivo fonte não encontrado.")
        
        title = record.get('title') or 'Apresentacao'
        pdf_bytes = convert_to_pdf(pptx_bytes, f"{title}.pptx")
        if not pdf_bytes:
            raise HTTPException(status_code=500, detail="Erro na conversão para PDF.")
        
        # Salvar no cache (Azure Blob)
        await _upload_bytes_to_azure(PREVIEW_SLIDES_CONTAINER, pdf_bytes, pdf_blob_name, content_type="application/pdf")
        logger.info(f"PDF dos slides salvo em cache: {pdf_blob_name}")
        
        signed_url = _generate_sas_url(PREVIEW_SLIDES_CONTAINER, pdf_blob_name)
        return RedirectResponse(url=signed_url)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao gerar preview dos slides {resource_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro ao gerar visualização.")


@app.get("/exercises/{resource_id}/preview", dependencies=[Depends(verify_token)])
async def preview_exercises(resource_id: str):
    """
    Retorna PDF da lista de exercícios para visualização.
    Reutiliza a mesma lógica do recurso didático (ambos são DOCX).
    """
    from .utils.pdf_converter import convert_to_pdf
    from .document_store import _download_bytes_from_azure, _upload_bytes_to_azure, _generate_sas_url, AZURE_PLANS_CONTAINER as PREVIEW_EX_CONTAINER
    
    logger.info(f"Endpoint /exercises/{resource_id}/preview chamado")
    
    try:
        # Buscar informações do recurso (exercícios usam mesma tabela de didactic_resources)
        async with (await get_checkpoint_connection()).connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute("""
                    SELECT title, blob_path, status
                    FROM didactic_resources
                    WHERE id = %s
                """, (uuid.UUID(resource_id),))
                record = await cur.fetchone()
        
        if not record:
            raise HTTPException(status_code=404, detail="Recurso não encontrado.")
        
        if record['status'] != ResourceStatus.completed.value:
            raise HTTPException(status_code=400, detail="Recurso ainda não está pronto.")
        
        if not record['blob_path']:
            raise HTTPException(status_code=404, detail="Arquivo não encontrado.")
        
        source_blob_name = record['blob_path']
        pdf_blob_name = source_blob_name.replace('.docx', '.pdf').replace('.DOCX', '.pdf')
        
        # Verificar cache
        cached_pdf = await _download_bytes_from_azure(PREVIEW_EX_CONTAINER, pdf_blob_name)
        if cached_pdf:
            logger.info(f"PDF dos exercícios encontrado em cache: {pdf_blob_name}")
            signed_url = _generate_sas_url(PREVIEW_EX_CONTAINER, pdf_blob_name)
            return RedirectResponse(url=signed_url)
        
        # PDF não existe, converter
        logger.info(f"Convertendo exercícios para PDF: {source_blob_name}")
        
        docx_bytes = await _download_bytes_from_azure(PREVIEW_EX_CONTAINER, source_blob_name)
        if not docx_bytes:
            raise HTTPException(status_code=404, detail="Arquivo fonte não encontrado.")
        
        pdf_bytes = convert_to_pdf(docx_bytes, f"{record['title']}.docx")
        if not pdf_bytes:
            raise HTTPException(status_code=500, detail="Erro na conversão para PDF.")
        
        # Salvar no cache (Azure Blob)
        await _upload_bytes_to_azure(PREVIEW_EX_CONTAINER, pdf_bytes, pdf_blob_name, content_type="application/pdf")
        logger.info(f"PDF dos exercícios salvo em cache: {pdf_blob_name}")
        
        signed_url = _generate_sas_url(PREVIEW_EX_CONTAINER, pdf_blob_name)
        return RedirectResponse(url=signed_url)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao gerar preview dos exercícios {resource_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro ao gerar visualização.")


# ============================================================================
# ENDPOINTS DE NOTIFICAÇÕES
# ============================================================================

@app.get("/notifications", response_model=NotificationListResponse, dependencies=[Depends(verify_token)])
async def get_notifications(user_id: str, limit: int = 50, offset: int = 0, unread_only: bool = False):
    """
    Retorna as notificações de um usuário.
    """
    logger.info(f"Endpoint /notifications chamado por user_id: {user_id}")
    try:
        async with (await get_checkpoint_connection()).connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                # Buscar notificações
                where_clause = "WHERE user_id = %s"
                params = [user_id]
                
                if unread_only:
                    where_clause += " AND is_read = FALSE"
                
                query = f"""
                SELECT id, user_id, plan_id, type, message, is_read, created_at, read_at, metadata
                FROM notifications
                {where_clause}
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s;
                """
                params.extend([limit, offset])
                await cur.execute(query, params)
                records = await cur.fetchall()
                
                # Contar não lidas
                count_query = "SELECT COUNT(*) as count FROM notifications WHERE user_id = %s AND is_read = FALSE;"
                await cur.execute(count_query, (user_id,))
                unread_count = (await cur.fetchone())['count']
        
        notifications = [
            NotificationResponse(
                id=str(r['id']),
                user_id=r['user_id'],
                plan_id=str(r['plan_id']) if r['plan_id'] else None,
                type=r['type'],
                message=r['message'],
                is_read=r['is_read'],
                created_at=r['created_at'].isoformat() if r['created_at'] else None,
                read_at=r['read_at'].isoformat() if r['read_at'] else None,
                metadata=r['metadata']
            )
            for r in records
        ]
        
        return NotificationListResponse(
            notifications=notifications,
            unread_count=unread_count
        )
    except Exception as e:
        logger.error(f"Erro ao buscar notificações: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno ao buscar notificações.")


@app.post("/notifications/mark-read", dependencies=[Depends(verify_token)])
async def mark_notifications_as_read(body: MarkAsReadRequest, user_id: str):
    """
    Marca notificações como lidas.
    """
    logger.info(f"Endpoint /notifications/mark-read chamado por user_id: {user_id}")
    try:
        async with (await get_checkpoint_connection()).connection() as conn:
            async with conn.cursor() as cur:
                # Validar que as notificações pertencem ao usuário
                notification_uuids = [uuid.UUID(nid) for nid in body.notification_ids]
                
                query = """
                UPDATE notifications
                SET is_read = TRUE, read_at = CURRENT_TIMESTAMP
                WHERE id = ANY(%s) AND user_id = %s;
                """
                await cur.execute(query, (notification_uuids, user_id))
        
        return {"message": "Notificações marcadas como lidas."}
    except Exception as e:
        logger.error(f"Erro ao marcar notificações como lidas: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno.")

