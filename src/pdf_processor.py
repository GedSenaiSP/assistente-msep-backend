import logging
import tempfile
import os
from fastapi import UploadFile, HTTPException
import PyPDF2

logger = logging.getLogger(__name__)

async def convert_pdf_to_markdown(file: UploadFile) -> str:
    """
    Converte um arquivo PDF enviado para texto usando PyPDF2.
    O arquivo é salvo temporariamente para processamento.
    """
    tmp_pdf_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_pdf:
            content = await file.read()
            if not content:
                logger.warning(f"Arquivo PDF '{file.filename}' está vazio.")
                raise HTTPException(status_code=400, detail=f"Arquivo PDF '{file.filename}' está vazio.")
            tmp_pdf.write(content)
            tmp_pdf_path = tmp_pdf.name

        logger.info(f"Arquivo PDF temporário salvo em: {tmp_pdf_path} para extração de texto.")

        text = ""
        with open(tmp_pdf_path, "rb") as pdf_file:
            pdf_reader = PyPDF2.PdfReader(pdf_file)
            for page in pdf_reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text

        if not text.strip():
            logger.warning(f"Texto extraído do PDF '{file.filename}' está vazio ou contém apenas espaços.")
            raise HTTPException(status_code=400, detail="Não foi possível extrair conteúdo textual do PDF. O PDF pode ser uma imagem ou estar corrompido.")

        logger.info(f"PDF '{file.filename}' convertido para texto com sucesso (tamanho: {len(text)}).")
        return text

    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Erro durante a extração de texto do PDF ('{file.filename}'): {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erro inesperado ao extrair texto do PDF: {str(e)}")
    finally:
        if tmp_pdf_path and os.path.exists(tmp_pdf_path):
            try:
                os.remove(tmp_pdf_path)
                logger.info(f"Arquivo PDF temporário '{tmp_pdf_path}' removido.")
            except Exception as e_remove:
                logger.error(f"Erro ao remover arquivo PDF temporário '{tmp_pdf_path}': {e_remove}", exc_info=True)
        # Não é necessário fechar explicitamente UploadFile aqui


def convert_pdf_bytes_to_text(pdf_bytes: bytes, filename: str = "unknown.pdf") -> str:
    """
    Converte bytes de um arquivo PDF para texto usando PyPDF2.
    Usada para processamento em background tasks onde não temos UploadFile.
    """
    tmp_pdf_path = None
    try:
        if not pdf_bytes:
            logger.warning(f"Arquivo PDF '{filename}' está vazio.")
            raise ValueError(f"Arquivo PDF '{filename}' está vazio.")
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_pdf:
            tmp_pdf.write(pdf_bytes)
            tmp_pdf_path = tmp_pdf.name

        logger.info(f"Arquivo PDF temporário salvo em: {tmp_pdf_path} para extração de texto.")

        text = ""
        with open(tmp_pdf_path, "rb") as pdf_file:
            pdf_reader = PyPDF2.PdfReader(pdf_file)
            for page in pdf_reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text

        if not text.strip():
            logger.warning(f"Texto extraído do PDF '{filename}' está vazio ou contém apenas espaços.")
            raise ValueError("Não foi possível extrair conteúdo textual do PDF. O PDF pode ser uma imagem ou estar corrompido.")

        logger.info(f"PDF '{filename}' convertido para texto com sucesso (tamanho: {len(text)}).")
        return text

    except ValueError:
        raise
    except Exception as e:
        logger.error(f"Erro durante a extração de texto do PDF ('{filename}'): {e}", exc_info=True)
        raise ValueError(f"Erro inesperado ao extrair texto do PDF: {str(e)}")
    finally:
        if tmp_pdf_path and os.path.exists(tmp_pdf_path):
            try:
                os.remove(tmp_pdf_path)
                logger.info(f"Arquivo PDF temporário '{tmp_pdf_path}' removido.")
            except Exception as e_remove:
                logger.error(f"Erro ao remover arquivo PDF temporário '{tmp_pdf_path}': {e_remove}", exc_info=True)
