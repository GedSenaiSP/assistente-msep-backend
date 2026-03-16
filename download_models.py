import logging
import os
import platform

# Configura variáveis de ambiente para evitar erro de symlink durante o download
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "0"
os.environ["HF_HUB_CACHE_SYMLINKS"] = "0"

# Importa a função de setup que já contém a lógica de inicialização do docling
from src.docling_converter import setup_optimized_converter

logging.basicConfig(level=logging.INFO)
_log = logging.getLogger(__name__)

if __name__ == "__main__":
    _log.info("Iniciando o download e cache dos modelos do docling...")
    
    # Instanciar o converter irá disparar o download de todos os modelos necessários
    # para a configuração definida (OCR, Table Structure, etc.)
    converter = setup_optimized_converter()

    _log.info("Download e cache dos modelos do docling concluídos com sucesso.")
