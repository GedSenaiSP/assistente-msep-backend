"""
Utilitário para conversão de documentos DOCX/PPTX para PDF.
Usa um serviço de conversão externo (LibreOffice headless ou similar).
"""

import os
import logging
import requests
from typing import Optional
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv()

# Configurações do serviço de conversão
CONVERTER_SERVICE_URL = os.getenv("CONVERTER_SERVICE_URL")
CONVERTER_API_KEY = os.getenv("CONVERTER_API_KEY")


def convert_to_pdf(file_bytes: bytes, filename: str, timeout: int = 120) -> Optional[bytes]:
    """
    Converte um arquivo DOCX ou PPTX para PDF usando serviço externo.
    
    Args:
        file_bytes: Conteúdo do arquivo em bytes
        filename: Nome do arquivo (com extensão)
        timeout: Tempo limite para a conversão em segundos
        
    Returns:
        bytes do PDF convertido, ou None em caso de erro
    """
    logger.info(f"Iniciando conversão para PDF: {filename}")
    
    try:
        headers = {}
        if CONVERTER_API_KEY:
            headers["X-API-Key"] = CONVERTER_API_KEY
        
        # Determinar o content-type baseado na extensão
        ext = filename.lower().split('.')[-1] if '.' in filename else ''
        if ext == 'pptx':
            content_type = 'application/vnd.openxmlformats-officedocument.presentationml.presentation'
        else:  # docx ou padrão
            content_type = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        
        response = requests.post(
            f"{CONVERTER_SERVICE_URL}/convert",
            headers=headers,
            files={"file": (filename, file_bytes, content_type)},
            timeout=timeout
        )
        
        if response.status_code != 200:
            logger.error(f"Erro no serviço de conversão: {response.status_code} - {response.text}")
            return None
        
        pdf_bytes = response.content
        logger.info(f"PDF gerado com sucesso: {len(pdf_bytes)} bytes")
        return pdf_bytes
        
    except requests.exceptions.Timeout:
        logger.error(f"Timeout na conversão de {filename}")
        return None
    except requests.exceptions.ConnectionError:
        logger.error(f"Erro de conexão com serviço de conversão: {CONVERTER_SERVICE_URL}")
        return None
    except Exception as e:
        logger.error(f"Erro ao converter {filename} para PDF: {e}")
        return None


async def get_or_create_pdf(
    source_blob_name: str,
    pdf_blob_name: str,
    container_name: str
) -> Optional[str]:
    """
    Obtém PDF do cache ou cria a partir do arquivo fonte.
    
    Args:
        source_blob_name: Nome do blob do arquivo fonte (DOCX/PPTX) no Azure Blob
        pdf_blob_name: Nome do blob para o PDF no Azure Blob
        container_name: Nome do container Azure
        
    Returns:
        URL com SAS token do PDF, ou None em caso de erro
    """
    from src.document_store import _download_bytes_from_azure, _upload_bytes_to_azure, _generate_sas_url
    
    logger.info(f"Verificando PDF em cache: {pdf_blob_name}")
    
    try:
        # Verificar se PDF já existe em cache
        cached_pdf = await _download_bytes_from_azure(container_name, pdf_blob_name)
        if cached_pdf:
            logger.info(f"PDF encontrado em cache: {pdf_blob_name}")
            signed_url = _generate_sas_url(container_name, pdf_blob_name)
            return signed_url
        
        # PDF não existe, precisa converter
        logger.info(f"PDF não encontrado em cache, convertendo {source_blob_name}...")
        
        # Baixar arquivo fonte
        source_bytes = await _download_bytes_from_azure(container_name, source_blob_name)
        if not source_bytes:
            logger.error(f"Arquivo fonte não encontrado: {source_blob_name}")
            return None
        
        filename = source_blob_name.split('/')[-1]
        
        # Converter para PDF
        pdf_bytes = convert_to_pdf(source_bytes, filename)
        if not pdf_bytes:
            logger.error("Falha na conversão para PDF")
            return None
        
        # Salvar PDF no Azure Blob
        await _upload_bytes_to_azure(container_name, pdf_bytes, pdf_blob_name, content_type="application/pdf")
        logger.info(f"PDF salvo em cache: {pdf_blob_name}")
        
        # Gerar URL com SAS token
        signed_url = _generate_sas_url(container_name, pdf_blob_name)
        return signed_url
        
    except Exception as e:
        logger.error(f"Erro ao obter/criar PDF: {e}", exc_info=True)
        return None
