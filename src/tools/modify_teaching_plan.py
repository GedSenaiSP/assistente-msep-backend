import json
import os
import logging
from typing import List, Optional
from langchain_core.tools import tool
from langchain_openai import AzureChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from src.utils.token_tracker import extract_tokens

logger = logging.getLogger(__name__)

@tool
def modify_teaching_plan(modification_request: str, history: list, current_plan_id: Optional[str]) -> str:
    """
    Use esta ferramenta SEMPRE que o usuário pedir para modificar, alterar, adicionar ou remover algo de um plano de ensino que já existe no histórico da conversa.
    A entrada deve ser o pedido específico de modificação do usuário.
    Exemplos: 'adicione mais dois critérios de avaliação', 'mude o nome do curso para X', 'remova o segundo objetivo de aprendizagem'.
    NÃO use esta ferramenta para perguntas gerais sobre a MSEP que não alterem o plano.
    """
    logger.info(f"Executando modify_teaching_plan. ID do plano atual (base): {current_plan_id}")
    
    # 1. Encontrar o plano de ensino mais recente no histórico
    latest_plan = ""
    for message_str in reversed(history):
        if isinstance(message_str, str) and message_str.startswith("Agent:"):
            content = message_str[len("Agent:"):].strip()
            try:
                content_data = json.loads(content)
                if 'plan_markdown' in content_data:
                    latest_plan = content_data['plan_markdown']
                    logger.info("Encontrado plan_markdown no histórico recente.")
                    break
            except (json.JSONDecodeError, TypeError):
                # O conteúdo pode não ser JSON, continue procurando
                continue
    
    if not latest_plan:
        logger.error("Não foi possível encontrar um 'plan_markdown' no histórico da conversa.")
        return json.dumps({"error": "Não encontrei um plano de ensino no histórico para modificar.", "input_tokens": 0, "output_tokens": 0})

    # 2. Configurar o LLM para fazer a modificação
    llm = AzureChatOpenAI(
        azure_deployment=os.getenv("MODEL_ID"),
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
        temperature=0.2,
        top_p=0.95,
        max_tokens=8192
    )
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", 
         """Você é um especialista em reescrever Planos de Ensino em Markdown para a Metodologia SENAI (MSEP).
        Sua tarefa é receber um plano de ensino existente e uma solicitação de modificação.
        Você deve retornar o plano de ensino COMPLETO, em formato Markdown, com a modificação aplicada.
        Mantenha toda a estrutura e conteúdo original que não foi afetado pela modificação.
        NÃO adicione nenhum texto conversacional como 'Claro, aqui está o plano atualizado...'. A sua saída deve ser APENAS o Markdown do plano completo."""),
        ("human", 
         """Aqui está o plano de ensino atual:
        ---
        {current_plan}
        ---

        Agora, por favor, aplique a seguinte modificação: "{modification}"
        """ + "Lembre-se, sua saída deve ser apenas o plano em markdown, completo e atualizado.")
    ])
    
    chain = prompt | llm
    
    # 3. Invocar o LLM para obter o plano modificado
    response = chain.invoke({
        "current_plan": latest_plan,
        "modification": modification_request,
    })
    
    # 4. Extrair tokens e retornar o plano
    tokens = extract_tokens(response)
    logger.info(f"Plano de ensino modificado pelo LLM com sucesso. Tokens: {tokens.input_tokens} entrada, {tokens.output_tokens} saída")
    return json.dumps({
        "plan_markdown": response.content,
        "input_tokens": tokens.input_tokens,
        "output_tokens": tokens.output_tokens
    })