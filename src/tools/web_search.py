from langchain_core.tools import tool
import logging
from langchain_openai import AzureChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
import os
from dotenv import load_dotenv

load_dotenv()

system_instruction_generico = """Você é uma ferramenta genérica para buscar informações na Internet, entretanto, quando o assunto for relacionado a busca de cursos, treinamentos, capacitações, vagas e oportunidades de estudo, buscará somente informações sobre o SENAI. Não buscará de nenhuma outra instituição. Se possível retorne links de referências para que o usuário possa navegar."""


chat_llm = AzureChatOpenAI(
    azure_deployment=os.getenv("MODEL_ID"),
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
    temperature=0.1,
    max_tokens=8192,
)

@tool
async def web_search(message: str) -> str:
    """Realiza uma busca na web por um termo

    Args:
        query (str): o termo a ser buscado

    Returns:
        str: os resultados da busca
    """
    logging.info('Endpoint generico acessado')
    try:
        # Gera a resposta usando o modelo
        response = await chat_llm.ainvoke([
            SystemMessage(content=system_instruction_generico),
            HumanMessage(content=message)
        ])
        
        # Retorna o texto da resposta
        return response.content

    except Exception as e:
       logging.error(f"Erro ao fazer a requisição generico: {e}")
    return {"error": str(e)}

tool = web_search