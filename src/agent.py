import os
import logging
import colorlog
from dotenv import load_dotenv
from langgraph.graph import StateGraph, END
from typing import TypedDict, Annotated, Optional, List, Dict, Any, cast
from langgraph.prebuilt import ToolNode
from src.tools import tools
from langchain_openai import AzureChatOpenAI
from langchain_core.prompts import PromptTemplate
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg import AsyncConnection
from psycopg import AsyncConnection
from psycopg_pool import AsyncConnectionPool
from src.database import get_db_pool, init_db_pool # Import from new module
import json
from src.models.models import SituacaoAprendizagemInput
from src.utils.token_tracker import TokenUsage, extract_tokens, upsert_thread_tokens

# --- Configuração do Logging com Cores ---
# Define o nível de log a partir de uma variável de ambiente, com 'INFO' como padrão.
log_level_str = os.getenv("LOG_LEVEL", "INFO").upper()
log_levels = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}
log_level = log_levels.get(log_level_str, logging.INFO)

# Configura o logging com cores no console
handler = colorlog.StreamHandler()
handler.setFormatter(colorlog.ColoredFormatter(
    '%(log_color)s%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    log_colors={
        'DEBUG': 'cyan',
        'INFO': 'green',
        'WARNING': 'yellow',
        'ERROR': 'red',
        'CRITICAL': 'bold_red',
    }
))
logging.basicConfig(level=log_level, handlers=[handler])
logger = logging.getLogger(__name__)

# Carrega variáveis do .env
load_dotenv()

# Variáveis Azure OpenAI são lidas do .env automaticamente via load_dotenv()

STRING_POSTGRES="postgresql://"+os.getenv("PG_USER")+":"+os.getenv("PG_PASSWORD")+"@"+os.getenv("PG_HOST")+":"+os.getenv("PG_PORT")+"/"+os.getenv("PG_DATABASE")+"?sslmode=require&options=-c%20plan_cache_mode%3Dforce_custom_plan"

# Global DB Pool
# Moved to src.database.py

async def get_user_config(user_id: str):
    try:
        pool = await get_db_pool()
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                query = """
                SELECT temperature, top_p 
                FROM user_configs 
                WHERE user_id = %s
                """
                await cur.execute(query, (user_id,))
                result = await cur.fetchone()
                if result:
                    return {"temperature": result[0], "top_p": result[1]}
                # Retorna valores padrão se não houver configuração
                return {"temperature": 0.7, "top_p": 1.0}
    except Exception as e:
        logger.error(f"Erro ao recuperar configuração do usuário {user_id}: {str(e)}")
        return {"temperature": 0.7, "top_p": 1.0}

# Configuração inicial do LLM via Azure OpenAI (não mais global)
# llm será criado por requisição
async def get_llm(user_id: str):
    config = await get_user_config(user_id)
    return AzureChatOpenAI(
        azure_deployment=os.getenv("MODEL_ID"),
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
        temperature=config["temperature"],
        top_p=config["top_p"],
        max_tokens=8192
    )
    
async def get_llm_title(user_id: str):
    config = await get_user_config(user_id)
    return AzureChatOpenAI(
        azure_deployment=os.getenv("MODEL_ID_TITLE"),
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
        temperature=config["temperature"],
        top_p=config["top_p"],
        max_tokens=8192
    )

# Configuração do checkpointer com asyncpg
# Configuração do checkpointer com asyncpg
# Alterado para retornar o POOL, já que o AsyncPostgresSaver suporta pool
async def get_checkpoint_connection():
    return await get_db_pool()

async def setup_checkpointer():
    """Cria as tabelas necessárias para o AsyncPostgresSaver, se não existirem."""
    try:
        pool = await get_db_pool()
        # AsyncPostgresSaver com pool gerencia as conexões internamente? 
        # Para setup, talvez precisemos de uma conexão direta ou o saver com pool funciona.
        # A documentação sugere passar o pool.
        checkpointer = AsyncPostgresSaver(conn=pool)
        await checkpointer.setup()  # Cria as tabelas
        logger.info("Tabelas do checkpointer criadas ou verificadas com sucesso")
    except Exception as e:
        logger.error(f"Erro ao configurar o checkpointer: {e}")
        raise
    
async def create_user_configs_table(conn):
    """Cria a tabela user_configs se ela não existir."""
    try:
        async with conn.cursor() as cur:
            query = """
            CREATE TABLE IF NOT EXISTS user_configs (
                user_id VARCHAR(255) PRIMARY KEY,
                temperature FLOAT NOT NULL DEFAULT 0.7,
                top_p FLOAT NOT NULL DEFAULT 1.0,
                departamento_regional VARCHAR(255),
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
            await cur.execute(query)
            logger.info("Tabela user_configs verificada/criada com sucesso")
    except Exception as e:
        logger.error(f"Erro ao criar/verificar tabela user_configs: {e}")
        raise
    
async def create_user_plans_table(conn):
    """Cria a tabela user_plans se ela não existir."""
    try:
        async with conn.cursor() as cur:
            query = """
            CREATE TABLE IF NOT EXISTS user_plans (
                    id UUID PRIMARY KEY,
                    user_id VARCHAR(255) NOT NULL,
                    thread_id VARCHAR(255) NOT NULL,
                    course_plan_id VARCHAR(255) NOT NULL,
                    blob_path VARCHAR(1024) NOT NULL, -- Caminho para o arquivo no GCS
                    summary JSONB, -- Coluna para armazenar o resumo JSON
                    departamento_regional VARCHAR(2),
                    escola VARCHAR(100),
                    docente VARCHAR(255),
                    curso VARCHAR(255),
                    data_inicio DATE,
                    data_fim DATE,
                    status VARCHAR(50) DEFAULT 'gerado', -- Alterado de BOOLEAN para VARCHAR com default 'gerado'
                    arquivado BOOLEAN DEFAULT FALSE,
                    publico BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
            """
            await cur.execute(query)
            logger.info("Tabela user_plans verificada/criada com sucesso")
    except Exception as e:
        logger.error(f"Erro ao criar/verificar tabela user_plans: {e}")
        raise

async def create_users_table(conn):
    """Cria a tabela users se ela não existir."""
    try:
        async with conn.cursor() as cur:
            query = """
            CREATE TABLE IF NOT EXISTS users (
                user_id VARCHAR(255) PRIMARY KEY,
                full_name VARCHAR(255) NOT NULL,
                email VARCHAR(255),
                role VARCHAR(50) NOT NULL,
                departamento_regional VARCHAR(2),
                escola VARCHAR(100),
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
            """
            await cur.execute(query)
            logger.info("Tabela users verificada/criada com sucesso")
    except Exception as e:
        logger.error(f"Erro ao criar/verificar tabela users: {e}")
        raise

async def create_generation_jobs_table(conn):
    """Cria a tabela generation_jobs para jobs assíncronos de geração de planos."""
    try:
        async with conn.cursor() as cur:
            query = """
            CREATE TABLE IF NOT EXISTS generation_jobs (
                job_id UUID PRIMARY KEY,
                user_id VARCHAR(255) NOT NULL,
                thread_id VARCHAR(255) NOT NULL,
                status VARCHAR(50) NOT NULL DEFAULT 'pending',
                progress INTEGER NOT NULL DEFAULT 0,
                current_step VARCHAR(255),
                request_payload JSONB NOT NULL,
                result JSONB,
                error TEXT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_generation_jobs_user_id ON generation_jobs(user_id);
            CREATE INDEX IF NOT EXISTS idx_generation_jobs_status ON generation_jobs(status);
            """
            await cur.execute(query)
            logger.info("Tabela generation_jobs verificada/criada com sucesso")
    except Exception as e:
        logger.error(f"Erro ao criar/verificar tabela generation_jobs: {e}")
        raise
    
async def create_didactic_resources_table(conn):
    """Cria a tabela didactic_resources se ela não existir."""
    try:
        async with conn.cursor() as cur:
            query = """
            CREATE TABLE IF NOT EXISTS didactic_resources (
                id UUID PRIMARY KEY,
                plan_id UUID REFERENCES user_plans(id) ON DELETE CASCADE,
                sa_index INTEGER NOT NULL,  -- Índice da SA no plano (-1 = todas as SAs)
                title VARCHAR(255) NOT NULL,
                blob_path VARCHAR(1024) NOT NULL,
                num_chapters INTEGER NOT NULL,
                status VARCHAR(50) NOT NULL DEFAULT 'pending',  -- pending, processing, completed, failed
                user_id VARCHAR(255) NOT NULL,
                error TEXT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_didactic_resources_plan_id ON didactic_resources(plan_id);
            CREATE INDEX IF NOT EXISTS idx_didactic_resources_user_id ON didactic_resources(user_id);
            """
            await cur.execute(query)
            logger.info("Tabela didactic_resources verificada/criada com sucesso")
    except Exception as e:
        logger.error(f"Erro ao criar/verificar tabela didactic_resources: {e}")
        raise

async def create_slide_resources_table(conn):
    """Cria a tabela slide_resources se ela não existir."""
    try:
        async with conn.cursor() as cur:
            query = """
            CREATE TABLE IF NOT EXISTS slide_resources (
                id UUID PRIMARY KEY,
                plan_id UUID REFERENCES user_plans(id) ON DELETE CASCADE,
                sa_index INTEGER NOT NULL,  -- Índice da SA no plano (-1 = todas as SAs)
                title VARCHAR(255),
                blob_path VARCHAR(1024),
                num_slides INTEGER,
                status VARCHAR(50) NOT NULL DEFAULT 'pending',  -- pending, processing, completed, failed
                user_id VARCHAR(255) NOT NULL,
                error TEXT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_slide_resources_plan_id ON slide_resources(plan_id);
            CREATE INDEX IF NOT EXISTS idx_slide_resources_user_id ON slide_resources(user_id);
            """
            await cur.execute(query)
            logger.info("Tabela slide_resources verificada/criada com sucesso")
    except Exception as e:
        logger.error(f"Erro ao criar/verificar tabela slide_resources: {e}")
        raise
    
async def create_thread_tokens_table(conn):
    """Cria a tabela thread_tokens se ela não existir."""
    try:
        async with conn.cursor() as cur:
            query = """
            CREATE TABLE IF NOT EXISTS thread_tokens (
                thread_id VARCHAR(255) PRIMARY KEY,
                user_id VARCHAR(255) NOT NULL,
                input_tokens INTEGER DEFAULT 0,
                output_tokens INTEGER DEFAULT 0,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_thread_tokens_user_id ON thread_tokens(user_id);
            """
            await cur.execute(query)
            logger.info("Tabela thread_tokens verificada/criada com sucesso")
    except Exception as e:
        logger.error(f"Erro ao criar/verificar tabela thread_tokens: {e}")
        raise

async def create_notifications_table(conn):
    """Cria a tabela notifications se ela não existir."""
    try:
        async with conn.cursor() as cur:
            query = """
            CREATE TABLE IF NOT EXISTS notifications (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id VARCHAR(255) NOT NULL,
                plan_id UUID,
                type VARCHAR(50) NOT NULL,
                message TEXT NOT NULL,
                is_read BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                read_at TIMESTAMP WITH TIME ZONE,
                metadata JSONB
            );
            CREATE INDEX IF NOT EXISTS idx_notifications_user_id ON notifications(user_id);
            CREATE INDEX IF NOT EXISTS idx_notifications_is_read ON notifications(is_read);
            CREATE INDEX IF NOT EXISTS idx_notifications_created_at ON notifications(created_at DESC);
            """
            await cur.execute(query)
            logger.info("Tabela notifications verificada/criada com sucesso")
    except Exception as e:
        logger.error(f"Erro ao criar/verificar tabela notifications: {e}")
        raise

async def create_plan_status_history_table(conn):
    """Cria a tabela plan_status_history para armazenar histórico de mudanças de status com comentários."""
    try:
        async with conn.cursor() as cur:
            query = """
            CREATE TABLE IF NOT EXISTS plan_status_history (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                plan_id UUID NOT NULL REFERENCES user_plans(id) ON DELETE CASCADE,
                previous_status VARCHAR(50),
                new_status VARCHAR(50) NOT NULL,
                comment TEXT,
                changed_by_user_id VARCHAR(255) NOT NULL,
                changed_by_name VARCHAR(255),
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_plan_status_history_plan_id ON plan_status_history(plan_id);
            CREATE INDEX IF NOT EXISTS idx_plan_status_history_created_at ON plan_status_history(created_at DESC);
            """
            await cur.execute(query)
            logger.info("Tabela plan_status_history verificada/criada com sucesso")
    except Exception as e:
        logger.error(f"Erro ao criar/verificar tabela plan_status_history: {e}")
        raise

async def setup_tables():
    """Cria as tabelas necessárias para o user_configs, se não existir."""
    try:
        pool = await get_db_pool()
        async with pool.connection() as conn:
            await create_user_configs_table(conn)  # Cria a tabela user_configs
            await create_user_plans_table(conn) # Cria a tabela user_plans
            await create_users_table(conn) # Cria a tabela users
            await create_generation_jobs_table(conn) # Cria a tabela generation_jobs
            await create_didactic_resources_table(conn) # Cria a tabela didactic_resources
            await create_slide_resources_table(conn) # Cria a tabela slide_resources
            await create_thread_tokens_table(conn) # Cria a tabela thread_tokens
            await create_notifications_table(conn) # Cria a tabela notifications
            await create_plan_status_history_table(conn) # Cria a tabela plan_status_history
            logger.info("Tabelas do usuário verificadas/criadas com sucesso")
        # await conn.close() # Não fechar conexão do pool aqui, o context manager cuida disso
    except Exception as e:
        logger.error(f"Erro ao configurar as tabelas do usuário: {e}")
        raise

tool_details = ""
for tool in tools:
    tool_details += f"- Ferramenta: `{tool.name}`\n  Descrição: {tool.description}\n\n"

# 2. Cria o novo template de prompt inteligente
prompt_template_string = f"""
Você é um agente roteador inteligente. Sua tarefa é escolher a melhor ferramenta para responder à solicitação do usuário.

Aqui estão as ferramentas disponíveis:
{tool_details}
Analise a seguinte solicitação do usuário e retorne APENAS o nome da ferramenta mais apropriada.

Se a solicitação do usuário for uma pergunta geral, uma saudação, ou se nenhuma outra ferramenta parecer adequada, retorne "chatmsep".

Solicitação do Usuário:
"{{input}}"

Nome da Ferramenta:
"""

tool_prompt = PromptTemplate.from_template(prompt_template_string)

response_prompt = PromptTemplate.from_template("""
{tool_result}
Retorne o resultado sem modificações. Não adicione notação de bloco de código ou json. Não adicione ```json```.
""")

title_prompt = PromptTemplate.from_template("""
Com base no input do usuário e na resposta do sistema, gere um único título curto e descritivo para esta conversa.
O título deve ser conciso (no máximo 7 palavras), objetivo e capturar a essência do assunto discutido. Não gere sugestões de títulos, gere apenas o título conforme diretrizes.

Input do usuário: {input}
Resposta do sistema: {response}

Título do da conversa
""")

class AgentState(TypedDict):
    input: str
    user_id: str
    thread_id: str
    tool_call: str
    tool_result: str
    response: str
    title: str  # Campo para armazenar o título da conversa
    current_plan_id: Optional[str] # ID do plano de ensino atualmente ativo na conversa
    save_plan_result: Optional[Dict[str, str]] # Resultado da execução da ferramenta save_plan
    document_content: Optional[str] # Conteúdo do documento para análise
    messages: Annotated[list[str], "Mensagens acumuladas da conversa"]
    
    # Token tracking - accumulates across nodes
    _tokens: Optional[Any]  # TokenUsage object for tracking LLM token usage
    
    # Campos para processamento de PDF e Geração de Plano
    # Para extração inicial (a ferramenta recebe o markdown diretamente)
    pdf_markdown_content: Optional[str]

    # Para geração do plano (a ferramenta recebe o ID e busca o markdown)
    stored_markdown_id: Optional[str]
    
    plan_docente: Optional[str]
    plan_unidade_operacional: Optional[str]
    plan_departamento_regional: Optional[str]
    plan_nome_curso: Optional[str] # Pode vir do input do usuário ou da extração anterior
    plan_turma: Optional[str]
    plan_modalidade: Optional[str] # Adicionado
    plan_nome_uc: Optional[str]     # Pode vir do input do usuário ou da extração anterior
    plan_data_inicio: Optional[str] # Adicionado
    plan_data_fim: Optional[str]    # Adicionado
    
    # A lista de SAs, onde cada SA tem seus próprios detalhes
    plan_situacoes_aprendizagem: Optional[List[Dict[str, Any]]] # Lista de SAs como dicts
                                                                # Cada dict terá: capacidades_tecnicas, socioemocionais, estrategia, tema_desafio
                                                                
    plan_horarios: Optional[List[Dict[str, str]]] # Horários gerais para a UC
    
    plan_extracted_data: Optional[Dict[str, Any]] # Usado pela ferramenta de extração, não diretamente pela de geração
    
tool_map = {tool.name if hasattr(tool, 'name') else tool.__name__: tool for tool in tools}
tool_executor = ToolNode(tools)

# Mapeamento de argumentos para cada ferramenta
TOOL_ARGUMENTS = {
    "chatmsep": {"message": "input"},
    "document_analyzer": {
        "question": "input",
        "document_content": "document_content"
    },
    # "web_search": {"message": "input"}, # Se estiver usando
    "extract_full_plan_details": {
        "markdown_content": "pdf_markdown_content" # Vem do AgentState
    },
    "generate_teaching_plan": {
        "stored_markdown_id": "stored_markdown_id",
        "docente": "plan_docente",
        "unidade_operacional": "plan_unidade_operacional",
        "departamento_regional": "plan_departamento_regional",
        "nome_curso": "plan_nome_curso",
        "turma": "plan_turma",
        "modalidade": "plan_modalidade",
        "nome_uc": "plan_nome_uc",
        "data_inicio": "plan_data_inicio",
        "data_fim": "plan_data_fim",
        "situacoes_aprendizagem_param": "plan_situacoes_aprendizagem",
        "horarios_param": "plan_horarios"
    },
    "modify_teaching_plan": {
        "modification_request": "input",
        "history": "messages",
        "current_plan_id": "current_plan_id"
    },
    "save_plan": {
        "user_id": "user_id",
        "thread_id": "thread_id",
        "plan_json": "response", # The JSON is in the response of the previous step
        "course_plan_id": "stored_markdown_id",
        "departamento_regional": "plan_departamento_regional",
        "escola": "plan_unidade_operacional",
        "docente": "plan_docente",
        "curso": "plan_nome_curso",
        "data_inicio": "plan_data_inicio",
        "data_fim": "plan_data_fim"
    }
}

async def identify_tool(state: AgentState) -> AgentState:
    user_input = state["input"]
    logger.info(f"Identificando ferramenta para input (comando): {user_input}...")
    
    current_messages = state.get("messages", []) # Preserva histórico de chat
    update_payload = {
        "tool_call": None, 
        "tool_result": None,
        "messages": current_messages
    } # Não resete outros campos do estado aqui
    
    # Inicializa rastreamento de tokens
    tokens = TokenUsage()

    if user_input.startswith("CMD_ANALYZE_DOCUMENT:"):
        question = user_input.replace("CMD_ANALYZE_DOCUMENT:", "").strip()
        state["input"] = question
        update_payload["tool_call"] = "document_analyzer"
        logger.info(f"Comando direto para análise de documento. Roteando para: {update_payload['tool_call']}")

    elif user_input.startswith("CMD_EXTRACT_FULL_PLAN_DETAILS:"): # NOVO COMANDO
        update_payload["tool_call"] = "extract_full_plan_details" # Nome da nova ferramenta
        # pdf_markdown_content é preenchido pelo endpoint no initial_payload
        logger.info(f"Comando direto para ferramenta de extração completa: {update_payload['tool_call']}")

    elif user_input.startswith("CMD_GENERATE_TEACHING_PLAN:"):
        update_payload["tool_call"] = "generate_teaching_plan" # Nome da nova ferramenta
        # Os campos stored_markdown_id, plan_docente, etc.
        # são preenchidos no AgentState pelo endpoint da API ANTES de chamar run_agent.
        logger.info(f"Comando direto para ferramenta de Geração de Plano: {update_payload['tool_call']}")
    else: # Lógica de chat normal (como antes)
        logger.info("Nenhum comando direto, usando LLM para chat.")
        prompt = tool_prompt.format(input=user_input)
        try:
            llm_for_tool_choice = await get_llm(state["user_id"])
            tool_choice_response = await llm_for_tool_choice.ainvoke(prompt)
            # Captura tokens da chamada de identificação de ferramenta
            tokens = extract_tokens(tool_choice_response)
            identified_tool = tool_choice_response.content.strip()
            
            if identified_tool and identified_tool.lower() != "none" and identified_tool in tool_map:
                update_payload["tool_call"] = identified_tool
            else:
                update_payload["tool_call"] = "chatmsep" 
            logger.info(f"LLM escolheu/default para chat: {update_payload['tool_call']}")
        except Exception as e:
            logger.error(f"Erro ao invocar LLM para identificação de ferramenta de chat: {e}", exc_info=True)
            update_payload["tool_result"] = json.dumps({"error": f"Erro ao identificar ferramenta de chat: {str(e)}"})
            # tool_call continua None, ou poderia default para chatmsep mesmo em erro

    # Usar type assertion para state
    cast_state = cast(Dict[str, Any], state)
    cast_state.update(update_payload)
    # Armazena tokens acumulados no estado
    cast_state["_tokens"] = tokens
    return state

async def execute_tool(state: AgentState) -> AgentState:
    if state["tool_call"]:
        logger.info(f"Executando ferramenta: {state['tool_call']}")
        if state["tool_call"] not in tool_map:
            state["tool_result"] = f"Ferramenta '{state['tool_call']}' não encontrada"
            logger.error(state["tool_result"])
            return state
        
        tool = tool_map[state["tool_call"]]
        
        # Preparar os argumentos dinamicamente com base no mapeamento
        tool_args_mapping = TOOL_ARGUMENTS.get(state["tool_call"], {})
        tool_input : Dict[str, Any] = {} # Definir o tipo explicitamente
        for arg_name, state_key in tool_args_mapping.items():
            tool_input[arg_name] = state.get(state_key)
        logger.debug(f"Chamando ferramenta {state['tool_call']} com input: {tool_input}")   
        try:
            logger.info(tool_input)
            state["tool_result"] = await tool.ainvoke(tool_input)
            logger.info(f"Resultado da ferramenta {state['tool_call']}: {state['tool_result']}")
        except Exception as e:
            logger.error(f"Erro ao executar ferramenta {state['tool_call']}: {str(e)}", exc_info=True)
            state["tool_result"] = f"Erro ao executar {state['tool_call']}: {str(e)}"      
    else:
        logger.info("Nenhuma ferramenta a ser executada")
    return state

async def generate_response(state: AgentState) -> AgentState:
    logger.info(f"Gerando resposta final para tool_call: {state.get('tool_call')}")
    
    current_tool_call = state.get("tool_call")
    tool_result = state.get("tool_result", "")
    final_agent_response = None
    
    # Recupera tokens acumulados
    tokens = state.get("_tokens", TokenUsage())

    # Ferramentas cuja saída de texto vai direto para o usuário
    if current_tool_call == "document_analyzer":
        final_agent_response = tool_result
        logger.info(f"Usando tool_result diretamente como resposta para a ferramenta de texto '{current_tool_call}'.")
    
    # chatmsep retorna JSON com content e tokens
    elif current_tool_call == "chatmsep":
        try:
            result_json = json.loads(tool_result)
            final_agent_response = result_json.get("content", tool_result)
            # Acumula tokens da ferramenta chatmsep
            tool_input_tokens = result_json.get("input_tokens", 0)
            tool_output_tokens = result_json.get("output_tokens", 0)
            tokens = tokens + TokenUsage(input_tokens=tool_input_tokens, output_tokens=tool_output_tokens)
            logger.info(f"chatmsep tokens: +{tool_input_tokens} entrada, +{tool_output_tokens} saída")
        except (json.JSONDecodeError, TypeError):
            # Fallback se não for JSON (compatibilidade com versão antiga)
            final_agent_response = tool_result
            logger.warning(f"chatmsep retornou texto puro, sem dados de tokens.")
        logger.info(f"Usando tool_result diretamente como resposta para a ferramenta de texto '{current_tool_call}'.")

    # Ferramentas cuja saída JSON vai direto para o usuário (e agora inclui tokens)
    elif current_tool_call in ["generate_teaching_plan", "extract_full_plan_details", "modify_teaching_plan"]:
        try:
            result_json = json.loads(tool_result)
            final_agent_response = tool_result
            
            # Acumula tokens das ferramentas de plano
            tool_input_tokens = result_json.get("input_tokens", 0)
            tool_output_tokens = result_json.get("output_tokens", 0)
            if tool_input_tokens > 0 or tool_output_tokens > 0:
                tokens = tokens + TokenUsage(input_tokens=tool_input_tokens, output_tokens=tool_output_tokens)
                logger.info(f"{current_tool_call} tokens: +{tool_input_tokens} entrada, +{tool_output_tokens} saída")
            
            logger.info(f"Usando tool_result JSON diretamente como resposta para a ferramenta de dados '{current_tool_call}'.")
        except (json.JSONDecodeError, TypeError):
            logger.error(f"Tool_result da ferramenta '{current_tool_call}' não é JSON válido. Conteúdo: {tool_result[:200]}...")
            final_agent_response = json.dumps({"error": f"Resultado inválido da ferramenta {current_tool_call}."})
    
    # Se nenhuma regra de resposta direta foi aplicada, usa o LLM para gerar a resposta final
    if final_agent_response is None:
        logger.info(f"Nenhuma regra de resposta direta aplicável para '{current_tool_call}'. Usando LLM para gerar resposta final.")
        llm = await get_llm(state["user_id"])
        prompt_str_for_llm = response_prompt.format(
            messages="\n".join(state.get("messages", [])),
            input=state.get("input", ""),
            tool_result=tool_result if tool_result else "Nenhuma ação de ferramenta específica foi realizada."
        )
        try:
            response = await llm.ainvoke(prompt_str_for_llm)
            # Captura tokens da chamada de geração de resposta
            tokens = tokens + extract_tokens(response)
            final_agent_response = response.content
            logger.info("Resposta final gerada pelo LLM do nó generate_response.")
        except Exception as e_llm_resp:
            logger.error(f"Erro ao gerar resposta com LLM no nó generate_response: {e_llm_resp}", exc_info=True)
            final_agent_response = json.dumps({"error": "Falha crítica ao processar a resposta final."})

    state["response"] = final_agent_response
    state["messages"] = state.get("messages", []) + [f"User: {state.get('input', '')}", f"Agent: {state['response']}"]
    # Atualiza tokens acumulados no estado
    state["_tokens"] = tokens
    logger.info(f"Nó generate_response concluído. Resposta (início): {state['response'][:200]}...")
    return state

async def generate_title(state: AgentState) -> AgentState:
    """Gera um título para a conversa baseado no input do usuário e na resposta."""
    # Recupera tokens acumulados
    tokens = state.get("_tokens", TokenUsage())
    
    # Se já tiver um título, mantém o mesmo
    if state.get("title"):
        logger.info(f"Mantendo título existente: {state['title']}")
    # Título estático para planos de ensino - não usa LLM
    elif state.get("tool_call") in ["generate_teaching_plan", "modify_teaching_plan"]:
        nome_uc = (state.get("plan_nome_uc") or "").strip() or "UC"
        turma = (state.get("plan_turma") or "").strip() or "Turma"
        state["title"] = f"PLANO DE ENSINO - {nome_uc} - {turma}"
        logger.info(f"Título estático gerado para plano: {state['title']}")
    # Gera um novo título via LLM para outras conversas
    elif state["input"] and state["response"]:
        logger.info("Gerando título para a conversa via LLM")
        prompt = title_prompt.format(
            input=state["input"],
            response=state["response"]
        )
        
        try:
            llm = await get_llm_title(state["user_id"])
            title_response = await llm.ainvoke(prompt)
            # Captura tokens da geração de título
            tokens = tokens + extract_tokens(title_response)
            state["title"] = title_response.content.strip()
            logger.info(f"Título gerado via LLM: {state['title']}")
        except Exception as e:
            logger.error(f"Erro ao gerar título: {str(e)}")
            state["title"] = "Nova Conversa"  # Título padrão em caso de falha
    else:
        logger.info("Definindo título padrão 'Nova Conversa'")
        state["title"] = "Nova Conversa"  # Título padrão
    
    # Salva tokens acumulados no banco de dados
    if tokens.input_tokens > 0 or tokens.output_tokens > 0:
        try:
            pool = await get_db_pool()
            async with pool.connection() as conn:
                await upsert_thread_tokens(
                    conn, 
                    state.get("thread_id", "unknown"),
                    state.get("user_id", "unknown"),
                    tokens
                )
            # await conn.close() -> Context manager handles it
            logger.info(f"Tokens salvos para thread {state.get('thread_id')}: {tokens.input_tokens} entrada, {tokens.output_tokens} saída")
        except Exception as e:
            logger.error(f"Erro ao salvar tokens: {e}", exc_info=True)
            # Não propaga o erro - tracking de tokens não deve quebrar o fluxo principal
        
    return state

async def save_plan_node(state: AgentState) -> AgentState:
    """Executa a ferramenta save_plan com os dados do estado."""
    logger.info("Nó save_plan_node: executando salvamento do plano.")
    try:
        response_json = json.loads(state["response"])

        # Check if the response contains an error
        if "error" in response_json:
            logger.error(f"Não foi possível salvar o plano devido a um erro na geração: {response_json['error']}")
            state["save_plan_result"] = {"error": response_json["error"]}
            return state

        plan_json = response_json.get("plan_json")

        if not plan_json:
            raise ValueError("'plan_json' não encontrado na resposta do estado.")

        tool_input = {
            "user_id": state["user_id"],
            "thread_id": state["thread_id"],
            "plan_json": plan_json,
            "course_plan_id": state.get("stored_markdown_id", "manual"),
            "departamento_regional": state.get("plan_departamento_regional"),
            "escola": state.get("plan_unidade_operacional"),
            "docente": state.get("plan_docente"),
            "curso": state.get("plan_nome_curso"),
            "data_inicio": state.get("plan_data_inicio"),
            "data_fim": state.get("plan_data_fim"),
        }
        
        save_tool = tool_map['save_plan']
        save_result = await save_tool.ainvoke(tool_input)
        state["save_plan_result"] = save_result
        logger.info(f"Resultado do save_plan_node: {save_result}")

    except (json.JSONDecodeError, ValueError, KeyError) as e:
        logger.error(f"Erro no save_plan_node: {e}", exc_info=True)
        state["save_plan_result"] = {"error": f"Falha ao preparar ou executar o salvamento do plano: {str(e)}"}
    
    return state

async def update_plan_id_node(state: AgentState) -> AgentState:
    """Atualiza o current_plan_id no estado com base no resultado do salvamento."""
    logger.info("Nó update_plan_id_node: atualizando o ID do plano no estado.")
    save_result = state.get("save_plan_result")
    if save_result and "new_plan_id" in save_result:
        new_id = save_result["new_plan_id"]
        state["current_plan_id"] = new_id
        logger.info(f"current_plan_id no estado foi atualizado para: {new_id}")
    elif save_result and "error" in save_result:
        logger.error(f"Não foi possível atualizar o plan_id devido a um erro no passo de salvamento: {save_result['error']}")
    else:
        logger.warning("Nenhum new_plan_id encontrado no resultado do salvamento para atualizar o estado.")
    return state

def should_save_plan(state: AgentState) -> str:
    """Verifica se a última ferramenta executada foi de geração ou modificação de plano."""
    last_tool = state.get("tool_call")
    if last_tool in ["generate_teaching_plan", "modify_teaching_plan"]:
        logger.info(f"Decisão: A ferramenta '{last_tool}' requer salvamento. Roteando para save_plan_node.")
        return "save_plan_node"
    logger.info(f"Decisão: A ferramenta '{last_tool}' não requer salvamento. Roteando para generate_title.")
    return "generate_title"

# Construção do grafo
workflow = StateGraph(AgentState)
workflow.add_node("identify_tool", identify_tool)
workflow.add_node("execute_tool", execute_tool)
workflow.add_node("generate_response", generate_response)
workflow.add_node("save_plan_node", save_plan_node) # Novo nó
workflow.add_node("update_plan_id_node", update_plan_id_node) # Novo nó
workflow.add_node("generate_title", generate_title)

workflow.set_entry_point("identify_tool")
workflow.add_edge("identify_tool", "execute_tool")
workflow.add_edge("execute_tool", "generate_response")

# Roteamento condicional após gerar a resposta
workflow.add_conditional_edges(
    "generate_response",
    should_save_plan,
    {
        "save_plan_node": "save_plan_node",
        "generate_title": "generate_title"
    }
)

workflow.add_edge("save_plan_node", "update_plan_id_node")
workflow.add_edge("update_plan_id_node", "generate_title")
workflow.add_edge("generate_title", END)

# Compila o grafo com checkpointer
# agent = workflow.compile(checkpointer=checkpointer)
agent=None

async def initialize_agent():
    global agent
    if agent is None:
        pool = await get_db_pool()
        checkpointer = AsyncPostgresSaver(conn=pool)
        await checkpointer.setup()  # Garante que as tabelas sejam criadas
        agent = workflow.compile(checkpointer=checkpointer)
    return agent

async def save_manual_plan_with_checkpoint(
    user_id: str,
    thread_id: str,
    plan_json: dict,
    plan_json_content: str,
    course_plan_id: str = "manual",
    departamento_regional: str = None,
    escola: str = None,
    docente: str = None,
    curso: str = None,
    turma: str = "",
    data_inicio: str = "",
    data_fim: str = "",
) -> Dict[str, str]:
    """
    Saves a manual plan and creates a LangGraph checkpoint without consuming LLM tokens.
    This enables the "Edit with AI" feature to work with manually saved plans.
    
    Uses agent.aupdate_state() to insert the plan state directly into the checkpoint store.
    """
    from src.tools.save_plan_tool import store_plan_document
    from src.utils.utils import convert_plan_json_to_markdown
    
    await initialize_agent()
    
    logger.info(f"save_manual_plan_with_checkpoint: Salvando plano manual com checkpoint para user_id={user_id}, thread_id={thread_id}")
    
    # 1. Save the plan document to GCS/DB (same as create_manual_plan does)
    stored_plan_id = await store_plan_document(
        user_id=user_id,
        thread_id=thread_id,
        plan_json_content=plan_json_content,
        course_plan_id=course_plan_id,
        departamento_regional=departamento_regional,
        escola=escola,
        docente=docente,
        curso=curso,
        data_inicio=data_inicio,
        data_fim=data_fim
    )
    logger.info(f"save_manual_plan_with_checkpoint: Plano salvo no BD com id={stored_plan_id}")
    
    # 2. Create a checkpoint with the plan state using agent.aupdate_state()
    config = {"configurable": {"thread_id": thread_id}, "metadata": {"user_id": user_id}}
    
    # Build the response in the same format that generate_response produces
    # Including plan_markdown so the plan content renders in the chat
    try:
        plan_markdown = convert_plan_json_to_markdown(plan_json)
    except Exception:
        plan_markdown = "Plano de ensino salvo manualmente."
    
    plan_response = json.dumps({
        "plan_json": plan_json,
        "plan_markdown": plan_markdown,
        "message": "Plano de ensino salvo manualmente."
    }, ensure_ascii=False)
    
    plan_title = f"PLANO DE ENSINO - {curso} - {turma}" if curso else "Plano Manual"
    
    # Messages must use the "User: " / "Agent: " format that: 
    # - generate_response node produces (agent.py line 658)
    # - get_chat_history endpoint reads (api.py)
    # - the frontend parses in loadConversationContent (use-conversations.tsx)
    user_message = "User: Plano de ensino criado manualmente."
    agent_message = f"Agent: {plan_response}"
    
    # Build the state that will be checkpointed
    checkpoint_state = {
        "input": "Plano de ensino criado manualmente.",
        "user_id": user_id,
        "thread_id": thread_id,
        "tool_call": "generate_teaching_plan",
        "tool_result": "Plano gerado com sucesso.",
        "response": plan_response,
        "title": plan_title,
        "current_plan_id": stored_plan_id,
        "save_plan_result": {"new_plan_id": stored_plan_id},
        "document_content": None,
        "messages": [user_message, agent_message],
        "_tokens": None,
        "pdf_markdown_content": None,
        "stored_markdown_id": course_plan_id,
        "plan_docente": docente,
        "plan_unidade_operacional": escola,
        "plan_departamento_regional": departamento_regional,
        "plan_nome_curso": curso,
        "plan_turma": None,
        "plan_modalidade": None,
        "plan_nome_uc": None,
        "plan_data_inicio": data_inicio,
        "plan_data_fim": data_fim,
        "plan_situacoes_aprendizagem": [],
        "plan_horarios": [],
        "plan_extracted_data": None,
    }
    
    # Insert the state as a checkpoint (no LLM call)
    await agent.aupdate_state(config, checkpoint_state)
    logger.info(f"save_manual_plan_with_checkpoint: Checkpoint criado para thread_id={thread_id}, plan_id={stored_plan_id}")
    
    # 3. Register in thread_tokens so the thread shows up in getUserThreads
    try:
        pool = await get_db_pool()
        async with pool.connection() as conn:
            await upsert_thread_tokens(
                conn,
                thread_id,
                user_id,
                TokenUsage()  # Zero tokens since no LLM was used
            )
        logger.info(f"save_manual_plan_with_checkpoint: thread_tokens registrado para thread_id={thread_id}")
    except Exception as e:
        logger.warning(f"save_manual_plan_with_checkpoint: Falha ao registrar thread_tokens: {e}")
    
    return {"plan_id": stored_plan_id, "thread_id": thread_id}


# Função assíncrona para rodar o agente
async def run_agent(
    input_command_or_message: str,
    user_id: str,
    thread_id: str,
    initial_payload: Optional[Dict[str, Any]] = None
) -> Dict:
    logger.info(f"Iniciando agente para user_id={user_id}, thread_id={thread_id}, input='{input_command_or_message}...'")
    config = {"configurable": {"thread_id": thread_id}, "metadata": {"user_id": user_id}}
    
    current_state_dict = {}
    if not initial_payload:
        previous_state_tuple = await agent.aget_state(config)
        if previous_state_tuple:
            current_state_dict = previous_state_tuple.values
            logger.info(f"Estado anterior recuperado para thread_id={thread_id}")
        else:
            logger.info(f"Nenhum estado anterior encontrado para thread_id={thread_id}, iniciando novo.")

    initial_messages = current_state_dict.get("messages", [])
    current_title = current_state_dict.get("title")
    
    # Cria um dicionário com todos os campos esperados por AgentState e seus tipos default/None
    current_state_dict.update({
        "input": input_command_or_message,
        "user_id": user_id,
        "thread_id": thread_id,  # Added for token tracking
        "_tokens": TokenUsage(),  # Initialize fresh token counter for this run
        "tool_call": None,
        "tool_result": None,
        "response": None,
    })
    
    if "messages" not in current_state_dict:
        current_state_dict["messages"] = []

    if initial_payload:
        logger.info(f"Aplicando initial_payload ao estado: {list(initial_payload.keys())}")
        current_state_dict.update(initial_payload)
        if "input" in initial_payload: # Se o payload definir um input, ele tem precedência
            current_state_dict["input"] = initial_payload["input"]
        # Para operações como Geração de Plano ou Extração, o histórico de chat não deve ser carregado do checkpoint,
        # pois são operações discretas.
        if "CMD_GENERATE_TEACHING_PLAN" in input_command_or_message or \
           "CMD_EXTRACT_FULL_PLAN_DETAILS" in input_command_or_message:
            if "messages" not in initial_payload: # A menos que o payload force mensagens
                 current_state_dict["messages"] = []
            if "title" not in initial_payload: # E não deve carregar título anterior
                current_state_dict["title"] = None

    # Garantir que todos os Optional[List] sejam listas e não None antes de passar para AgentState
    for key in ["plan_situacoes_aprendizagem", "plan_horarios"]:
        if current_state_dict.get(key) is None:
            current_state_dict[key] = []
    
    # O `initial_payload` fornecido por `api.py` para generate_teaching_plan
    # já conterá "plan_situacoes_aprendizagem" devidamente preenchido.
    if "plan_situacoes_aprendizagem" in initial_payload if initial_payload else False:
        # Certificando que o que está em current_state_dict é o que veio do initial_payload
        # e que é uma lista de dicts, como esperado pela ferramenta.
        # O Pydantic já validou o formato em api.py
        valid_sas = []
        if isinstance(initial_payload.get("plan_situacoes_aprendizagem"), list): # type: ignore
            for sa_input in initial_payload["plan_situacoes_aprendizagem"]: # type: ignore
                if isinstance(sa_input, dict): # Se já for dict, ótimo
                    valid_sas.append(sa_input)
                elif hasattr(sa_input, 'model_dump'): # Se for um objeto Pydantic
                    valid_sas.append(sa_input.model_dump())
                else:
                    logger.warning(f"Item SA não é dict nem Pydantic model no initial_payload: {type(sa_input)}")
            current_state_dict["plan_situacoes_aprendizagem"] = valid_sas
        else:
            logger.warning("plan_situacoes_aprendizagem no initial_payload não é uma lista.")
            current_state_dict["plan_situacoes_aprendizagem"] = []

    # Converte o dicionário para AgentState, o LangGraph lida com a tipagem.
    # O `cast` é usado para satisfazer o mypy, mas o LangGraph internamente
    # espera um dicionário que corresponda às chaves e tipos do TypedDict.
    final_initial_state_for_agent = cast(AgentState, current_state_dict)
    logger.debug(f"Estado inicial para a invocação do agente (thread {thread_id}): { {k: (str(v)[:100] + '...' if isinstance(v, str) and len(v) > 100 else v) for k, v in final_initial_state_for_agent.items()} }")
    result = await agent.ainvoke(final_initial_state_for_agent, config=config)
    
    logger.info(f"Agente (thread {thread_id}) concluído. Resposta: '{str(result.get('response'))}...', Título: {result.get('title')}")
    return {
        "response": result.get("response"),
        "title": result.get("title"),
        "thread_id": thread_id,
        "user_id": user_id
    }
