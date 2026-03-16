import os
import logging
from typing import Optional
from psycopg_pool import AsyncConnectionPool
from dotenv import load_dotenv

# Configurações de logging
logger = logging.getLogger(__name__)

# Carrega variáveis do .env
load_dotenv()

# Global DB Pool
DB_POOL: Optional[AsyncConnectionPool] = None

async def init_db_pool():
    global DB_POOL
    if DB_POOL is None:
        # Configurar connection string
        if not os.getenv("PG_USER") or not os.getenv("PG_HOST"):
             logger.error("Variaveis de ambiente de banco de dados nao configuradas!")
             return

        STRING_POSTGRES = f"postgresql://{os.getenv('PG_USER')}:{os.getenv('PG_PASSWORD')}@{os.getenv('PG_HOST')}:{os.getenv('PG_PORT')}/{os.getenv('PG_DATABASE')}?sslmode=require&options=-c%20plan_cache_mode%3Dforce_custom_plan"
        
        # Inicializa o pool
        DB_POOL = AsyncConnectionPool(
            conninfo=STRING_POSTGRES,
            open=False, # Será aberto explicitamente
            min_size=1,
            max_size=20, # Ajuste conforme necessário para produção
            kwargs={"autocommit": True, "prepare_threshold": 0}
        )
        await DB_POOL.open()
        logger.info("Pool de conexões PostgreSQL inicializado.")

async def close_db_pool():
    global DB_POOL
    if DB_POOL:
        await DB_POOL.close()
        logger.info("Pool de conexões PostgreSQL fechado.")
        DB_POOL = None

async def get_db_pool() -> AsyncConnectionPool:
    if DB_POOL is None:
        await init_db_pool()
    if DB_POOL is None:
         raise Exception("Falha ao inicializar DB_POOL")
    return DB_POOL
