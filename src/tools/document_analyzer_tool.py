from langchain_core.tools import tool
import logging
from langchain_openai import AzureChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
import os

# Instrução de sistema para a nova ferramenta
system_instruction = """
Você é um assistente de IA especialista em análise de documentos. Sua principal tarefa é responder à pergunta do usuário utilizando o conteúdo do documento fornecido como sua principal fonte de verdade.

- Priorize as informações contidas no documento para formular sua resposta.
- Você pode usar seu conhecimento geral para complementar a resposta, mas deixe claro quando a informação vem do documento e quando não vem. Por exemplo: "De acordo com o documento,..." ou "Além do que está no documento, é importante notar que...".
- Se a pergunta não pode ser respondida nem pelo documento nem pelo seu conhecimento geral, informe que não foi possível encontrar a resposta.
- Responda de forma completa e clara.
"""

# Inicializa o LLM para esta ferramenta
analyzer_llm = AzureChatOpenAI(
    azure_deployment=os.getenv("MODEL_ID"),
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
    temperature=0.2,
    max_tokens=8192,
)

@tool
async def document_analyzer(question: str, document_content: str) -> str:
    """
    Responde a uma pergunta do usuário com base no conteúdo de um documento fornecido, podendo usar conhecimento geral para complementar.
    Use esta ferramenta quando a pergunta do usuário for sobre um documento que ele enviou.
    """
    logging.info('Ferramenta document_analyzer executada.')
    try:
        prompt = f"""
        Conteúdo do Documento:
        ---
        {document_content}
        ---

        Pergunta do Usuário: {question}
        """

        response = await analyzer_llm.ainvoke([
            SystemMessage(content=system_instruction),
            HumanMessage(content=prompt)
        ])
        
        return response.content

    except Exception as e:
       logging.error(f"Erro na ferramenta document_analyzer: {e}")
       return f"Ocorreu um erro ao analisar o documento: {str(e)}"

tool = document_analyzer
