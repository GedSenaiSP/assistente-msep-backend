import asyncio
import os
import json
import logging
from collections import Counter
import uuid
from dotenv import load_dotenv

from azure.storage.blob import BlobServiceClient
from psycopg import AsyncConnection
from src.database import get_db_pool

# --- Configuração do Script ---
# Configura o logging para vermos o que está acontecendo
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Carrega as variáveis de ambiente (credenciais do DB e Azure) do seu arquivo .env
load_dotenv()

# --- Conexões ---
AZURE_PLANS_CONTAINER = os.getenv("AZURE_PLANS_CONTAINER")
AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
STRING_POSTGRES = f"postgresql://{os.getenv('PG_USER')}:{os.getenv('PG_PASSWORD')}@{os.getenv('PG_HOST')}:{os.getenv('PG_PORT')}/{os.getenv('PG_DATABASE')}"

async def download_from_azure(container_name: str, blob_name: str) -> str | None:
    """Faz o download de um arquivo do Azure Blob Storage."""
    if not container_name:
        raise ValueError("Nome do container Azure não configurado.")
    try:
        service_client = BlobServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)
        blob_client = service_client.get_blob_client(container_name, blob_name)

        # Usa to_thread para não bloquear o loop de eventos asyncio
        exists = await asyncio.to_thread(blob_client.exists)
        if not exists:
            logging.warning(f"Blob Azure não encontrado: {container_name}/{blob_name}")
            return None

        downloader = await asyncio.to_thread(blob_client.download_blob)
        content_bytes = await asyncio.to_thread(downloader.readall)
        logging.info(f"Conteúdo baixado de Azure Blob: {container_name}/{blob_name}")
        return content_bytes.decode('utf-8')
    except Exception as e:
        logging.error(f"Erro ao baixar de Azure Blob ({container_name}/{blob_name}): {e}", exc_info=True)
        raise

async def main():
    """Função principal que orquestra o processo de backfill."""
    logging.info("Iniciando script de backfill para resumos de planos...")

    async with (await get_db_pool()).connection() as conn:
        async with conn.cursor() as cur:
            # 1. Encontra os planos que precisam de atualização (summary está nulo)
            await cur.execute("SELECT id, blob_path FROM user_plans WHERE summary IS NULL")
            plans_to_update = await cur.fetchall()

            if not plans_to_update:
                logging.info("Nenhum plano para atualizar. A coluna 'summary' já está preenchida em todos.")
                return

            logging.info(f"Encontrados {len(plans_to_update)} planos para processar.")

            # 2. Itera sobre cada plano
            for plan_id, blob_path in plans_to_update:
                plan_id_str = str(plan_id)
                logging.info(f"Processando plano ID: {plan_id_str}...")

                # 3. Baixa o conteúdo completo do Azure Blob Storage
                plan_json_content = await download_from_azure(AZURE_PLANS_CONTAINER, blob_path)

                if not plan_json_content:
                    logging.warning(f"  -> Conteúdo do plano ID {plan_id_str} não encontrado no Azure Blob (path: {blob_path}). Pulando.")
                    continue

                # 4. Extrai o resumo (mesma lógica usada na API)
                summary_data = {}
                try:
                    plan_data = json.loads(plan_json_content)
                    cabecalho = plan_data.get("informacoes_gerais", {})
                    summary_data = {
                        "nome_uc": cabecalho.get("unidade_curricular"),
                        "turma": cabecalho.get("turma"),
                        "escola": cabecalho.get("unidade_operacional"),
                    }
                    situacoes = plan_data.get("situacoes_aprendizagem", [])
                    tipos_sa = [sa.get("tipo_sa") for sa in situacoes if sa.get("tipo_sa")]
                    summary_data["contagem_sa_por_tipo"] = dict(Counter(tipos_sa))
                except Exception as e:
                    logging.error(f"  -> Falha ao extrair resumo para o plano ID {plan_id_str}. Erro: {e}. Pulando.")
                    continue

                # 5. Atualiza a coluna 'summary' no banco de dados
                try:
                    await cur.execute(
                        "UPDATE user_plans SET summary = %s WHERE id = %s",
                        (json.dumps(summary_data), plan_id)
                    )
                    logging.info(f"  -> Sucesso! Resumo do plano ID {plan_id_str} atualizado no banco de dados.")
                except Exception as e:
                    logging.error(f"  -> Falha ao atualizar o banco de dados para o plano ID {plan_id_str}. Erro: {e}")

    logging.info("Script de backfill concluído.")

if __name__ == "__main__":
    # Garante que o script pode ser executado diretamente
    # Ex: python backfill_summaries.py
    asyncio.run(main())
