"""
RAG Service para Chat MSEP usando FAISS + Sentence Transformers.
Gerencia o vectorstore para busca semântica no documento msep.md.
"""
import os
import logging
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

logger = logging.getLogger(__name__)

# Configurações
VECTORDB_PATH = os.getenv("VECTORDB_PATH", "/data/msep_faiss")
MSEP_FILE = "msep.md"
EMBEDDING_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200
DEFAULT_K = 5  # Número de chunks a retornar por padrão

# Variáveis globais do módulo
embeddings = None
vectorstore = None


async def init_rag():
    """
    Inicializa ou carrega o vectorstore FAISS.
    Chamado no lifespan do FastAPI ao iniciar o servidor.
    """
    global embeddings, vectorstore
    
    logger.info("Inicializando RAG service...")
    
    # Inicializa o modelo de embeddings (multilíngue para português)
    embeddings = HuggingFaceEmbeddings(
        model_name=EMBEDDING_MODEL,
        model_kwargs={'device': 'cpu'},
        encode_kwargs={'normalize_embeddings': True}
    )
    logger.info(f"Modelo de embeddings '{EMBEDDING_MODEL}' carregado.")
    
    # Verifica se já existe um índice válido (pasta E arquivo index.faiss)
    index_file = os.path.join(VECTORDB_PATH, "index.faiss")
    if os.path.exists(VECTORDB_PATH) and os.path.exists(index_file):
        logger.info(f"Carregando vectorstore existente de '{VECTORDB_PATH}'...")
        vectorstore = FAISS.load_local(
            VECTORDB_PATH, 
            embeddings, 
            allow_dangerous_deserialization=True
        )
        logger.info("Vectorstore FAISS carregado com sucesso.")
    else:
        logger.info(f"Vectorstore não encontrado. Criando a partir de '{MSEP_FILE}'...")
        
        # Verifica se o arquivo msep.md existe
        if not os.path.exists(MSEP_FILE):
            logger.error(f"Arquivo '{MSEP_FILE}' não encontrado!")
            raise FileNotFoundError(f"Arquivo '{MSEP_FILE}' não encontrado para indexação.")
        
        # Lê o conteúdo do documento
        with open(MSEP_FILE, 'r', encoding='utf-8') as f:
            content = f.read()
        
        logger.info(f"Documento lido: {len(content)} caracteres")
        
        # Divide em chunks
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP,
            separators=["\n\n", "\n", ". ", " ", ""]
        )
        docs = splitter.create_documents([content])
        logger.info(f"Documento dividido em {len(docs)} chunks.")
        
        # Cria o vectorstore
        vectorstore = FAISS.from_documents(docs, embeddings)
        
        # Salva para uso futuro
        vectorstore.save_local(VECTORDB_PATH)
        logger.info(f"Vectorstore FAISS criado e salvo em '{VECTORDB_PATH}'.")


def get_relevant_context(query: str, k: int = DEFAULT_K) -> str:
    """
    Retorna contexto relevante do documento msep.md para a query.
    
    Args:
        query: Pergunta do usuário
        k: Número de chunks a retornar (mais = mais contexto)
    
    Returns:
        String com os chunks relevantes concatenados
    """
    if vectorstore is None:
        logger.error("Vectorstore não inicializado! Chame init_rag() primeiro.")
        return ""
    
    docs = vectorstore.similarity_search(query, k=k)
    context = "\n\n---\n\n".join([doc.page_content for doc in docs])
    
    logger.debug(f"RAG: Query '{query[:50]}...' retornou {len(docs)} chunks, {len(context)} chars")
    
    return context


def is_initialized() -> bool:
    """Verifica se o RAG service está inicializado."""
    return vectorstore is not None
