import logging
import json
import os
from typing import Optional, List, Dict, Any, Tuple # Adicionado Tuple
from langchain_core.tools import tool
from langchain_openai import AzureChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from src.utils.token_tracker import TokenUsage, extract_tokens
import asyncio # Para chamadas concorrentes ao LLM para capacidades

instrucao_sistema = "Você é um assistente eficiente em extrair informações específicas de textos. Responda apenas com a informação solicitada, de forma concisa e nada mais."

logger = logging.getLogger(__name__)

# Semaphore para limitar chamadas concorrentes ao LLM (evita rate limiting 429)
# Ajuste MAX_CONCURRENT_LLM_CALLS conforme seu limite de cota do Vertex AI
MAX_CONCURRENT_LLM_CALLS = int(os.getenv("MAX_CONCURRENT_LLM_CALLS", "5"))
logger.debug(f"MAX_CONCURRENT_LLM_CALLS: {MAX_CONCURRENT_LLM_CALLS}")
llm_semaphore = asyncio.Semaphore(MAX_CONCURRENT_LLM_CALLS)

extraction_llm = AzureChatOpenAI(
        azure_deployment=os.getenv("MODEL_ID_TITLE"),
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
        temperature=0.1,
        top_p=0.95,
        max_tokens=65535,
    )
    
def sanitize_text(text: str) -> str:
    if not text:
        return ""

    # 1. Escapar backslashes PRIMEIRO
    text = text.replace('\\', '\\\\')
    # 2. Escapar aspas duplas
    text = text.replace('"', '\\"')
    # 3. Substituir quebras de linha literais por espaço (ou por \\n se quiser mantê-las no JSON)
    #    Se você quer que a quebra de linha seja parte do valor da string no JSON:
    #    text = text.replace('\r\n', '\\n').replace('\n', '\\n').replace('\r', '\\n')
    #    Se você quer remover as quebras de linha e substituí-las por espaço:
    text = text.replace('\r\n', ' ').replace('\n', ' ').replace('\r', ' ')

    text = text.strip() # Remover espaços no início/fim após as substituições

    # Remove múltiplos espaços que podem ter sido introduzidos
    while '  ' in text:
        text = text.replace('  ', ' ')

    # Opcional: Remover outros caracteres de controle problemáticos,
    # mas os acima são os mais críticos para JSON strings.
    # A linha abaixo pode ser muito agressiva, vamos testar sem ela primeiro se as escapes resolverem.
    # text = ''.join(char for char in text if ord(char) >= 32 or char in ['\\t']) # Permitir tab escapado se necessário

    return text

async def _extract_capabilities_for_single_uc(llm: AzureChatOpenAI, markdown_content: str, uc_name: str) -> Tuple[Dict[str, List[str]], TokenUsage]:
    """Função auxiliar para extrair capacidades de uma única UC. Retorna (dados, tokens)."""
    logger.debug(f"Extraindo capacidades para UC: {uc_name}")
    cap_details = {
        "CapacidadesTecnicas_list": [],
        "CapacidadesSocioemocionais_list": []
    }
    tokens = TokenUsage()
    
    try:
        # Prompt para capacidades técnicas com instruções mais específicas
        prompt_tec = f"""{markdown_content}

Extraia APENAS as capacidades técnicas (ou básicas) da Unidade Curricular '{uc_name}'.
Dependendo do plano de curso, as capacidades técnicas podem ser chamadas de "capacidades técnicas", "capacidades básicas", "competências técnicas" ou "FUNDAMENTOS TÉCNICOS CIENTÍFICOS". Avalie cada caso para identificar corretamente as capacidades técnicas do plano de curso. 

INSTRUÇÕES IMPORTANTES:
- Retorne apenas as capacidades na íntegra como aparecem no plano de curso, uma por linha.
- Devido a conversão do plano de pdf para markdown, uma capacidade pode estar dividida em várias linhas, então traga a frase completa da capacidade em uma única linha.
- Não use marcadores, números ou símbolos.

Capacidades técnicas:"""

        async with llm_semaphore:
            response_tec = await llm.ainvoke([
                SystemMessage(content=instrucao_sistema),
                HumanMessage(content=prompt_tec)
            ])
        tokens = tokens + extract_tokens(response_tec)
        if response_tec and response_tec.content:
            raw_capabilities = [sanitize_text(cap.strip()) for cap in response_tec.content.splitlines() if cap.strip()]
            cap_details["CapacidadesTecnicas_list"] = [cap for cap in raw_capabilities if cap]

        # Prompt para capacidades socioemocionais
        prompt_soc = f"""{markdown_content}

Extraia APENAS as capacidades socioemocionais da Unidade Curricular '{uc_name}'.
Dependendo do plano de curso, as capacidades socioemocionais podem ser chamadas de "capacidades sociais", "capacidades organizativas" ou "capacidades metodológicas". Dependendo do plano, podem conter as 3 separadamente, mas considere tudo como capacidades socioemocionais. Avalie cada caso para identificar corretamente as capacidades socioemocionais do plano de curso.

INSTRUÇÕES IMPORTANTES:
- Retorne apenas as capacidades na íntegra como aparecem no plano de curso, uma por linha.
- Devido a conversão do plano de pdf para markdown, uma capacidade pode estar dividida em várias linhas, então traga a frase completa da capacidade em uma única linha.
- Não use marcadores, números ou símbolos.

Capacidades socioemocionais:"""

        async with llm_semaphore:
            response_soc = await llm.ainvoke([
                SystemMessage(content=instrucao_sistema),
                HumanMessage(content=prompt_soc)
            ])
        tokens = tokens + extract_tokens(response_soc)
        if response_soc and response_soc.content:
            raw_capabilities = [sanitize_text(cap.strip()) for cap in response_soc.content.splitlines() if cap.strip()]
            cap_details["CapacidadesSocioemocionais_list"] = [cap for cap in raw_capabilities if cap]
            
        logger.debug(f"Capacidades extraídas para {uc_name}: {len(cap_details['CapacidadesTecnicas_list'])} técnicas, {len(cap_details['CapacidadesSocioemocionais_list'])} socioemocionais")
        
    except Exception as e:
        logger.error(f"Erro ao extrair capacidades para UC '{uc_name}': {e}")
        # Retorna listas vazias em caso de erro
    
    return cap_details, tokens

async def _extract_knowledge_for_single_uc(llm: AzureChatOpenAI, markdown_content: str, uc_name: str) -> Tuple[List[str], TokenUsage]:
    """Função auxiliar para extrair conhecimentos de uma única UC. Retorna (dados, tokens)."""
    logger.debug(f"Extraindo conhecimentos para UC: {uc_name}")
    knowledge_list: List[str] = []
    tokens = TokenUsage()
    
    try:
        prompt_knowledge = f"""{markdown_content}

Extraia APENAS a lista de conhecimentos da Unidade Curricular '{uc_name}'.

INSTRUÇÕES IMPORTANTES:
- Retorne apenas os conhecimentos na íntegra como aparecem no plano de curso, um por linha.
- Não use marcadores complexos, números de lista são aceitáveis se fizerem parte do texto original dos conhecimentos.
- Se os conhecimentos estiverem em tópicos e sub-tópicos, tente manter essa estrutura da melhor forma possível, mas cada item principal ou sub-item em uma nova linha.

Conhecimentos:"""

        async with llm_semaphore:
            response_knowledge= await llm.ainvoke([
                SystemMessage(content=instrucao_sistema),
                HumanMessage(content=prompt_knowledge)
            ])
        tokens = tokens + extract_tokens(response_knowledge)
        if response_knowledge and response_knowledge.content:
            raw_knowledge = [sanitize_text(k.strip()) for k in response_knowledge.content.splitlines() if k.strip()]
            knowledge_list = [k for k in raw_knowledge if k]

        logger.debug(f"Conhecimentos extraídos para {uc_name}: {len(knowledge_list)} itens.")

    except Exception as e:
        logger.error(f"Erro ao extrair conhecimentos para UC '{uc_name}': {e}")

    return knowledge_list, tokens

async def _extract_objective_for_single_uc(llm: AzureChatOpenAI, markdown_content: str, uc_name: str) -> Tuple[Optional[str], TokenUsage]:
    """Função auxiliar para extrair o objetivo de uma única UC. Retorna (dados, tokens)."""
    logger.debug(f"Extraindo objetivo para UC: {uc_name}")
    objective: Optional[str] = None
    tokens = TokenUsage()

    try:
        prompt_objective = f"""{markdown_content}

Extraia APENAS o objetivo principal ou geral da Unidade Curricular '{uc_name}'.

INSTRUÇÕES IMPORTANTES:
- Retorne apenas o texto do objetivo da unidade curricular na íntegra, sem modificações.

Objetivo da Unidade Curricular '{uc_name}':"""

        async with llm_semaphore:
            response_objective= await llm.ainvoke([
                SystemMessage(content=instrucao_sistema),
                HumanMessage(content=prompt_objective)
            ])
        tokens = tokens + extract_tokens(response_objective)
        if response_objective and response_objective.content:
            objective_text = sanitize_text(response_objective.content.strip())
            if objective_text:
                objective = objective_text

        logger.debug(f"Objetivo extraído para {uc_name}: {'Sim' if objective else 'Não encontrado'}")

    except Exception as e:
        logger.error(f"Erro ao extrair objetivo para UC '{uc_name}': {e}")

    return objective, tokens

async def _extract_references_for_single_uc(llm: AzureChatOpenAI, markdown_content: str, uc_name: str) -> Tuple[List[str], TokenUsage]:
    """Função auxiliar para extrair referências bibliográficas de uma única UC. Retorna (dados, tokens)."""
    logger.debug(f"Extraindo referências bibliográficas para UC: {uc_name}")
    references_list: List[str] = []
    tokens = TokenUsage()

    try:
        prompt_references = f"""{markdown_content}

Extraia APENAS a lista de referências bibliográficas (básicas e complementares, se houver) da Unidade Curricular '{uc_name}'.

INSTRUÇÕES IMPORTANTES:
- Retorne apenas as referências, uma por linha.
- Não use marcadores, números ou símbolos.

Referências Bibliográficas da Unidade Curricular '{uc_name}':"""

        async with llm_semaphore:
            response_references = await llm.ainvoke([
                SystemMessage(content=instrucao_sistema),
                HumanMessage(content=prompt_references)
            ])
        tokens = tokens + extract_tokens(response_references)
        if response_references and response_references.content:
            raw_references = [sanitize_text(ref.strip()) for ref in response_references.content.splitlines() if ref.strip()]
            references_list = [ref for ref in raw_references if ref]

        logger.debug(f"Referências bibliográficas extraídas para {uc_name}: {len(references_list)} itens.")

    except Exception as e:
        logger.error(f"Erro ao extrair referências para UC '{uc_name}': {e}")

    return references_list, tokens

async def _extract_workload_for_single_uc(llm: AzureChatOpenAI, markdown_content: str, uc_name: str) -> Tuple[str, TokenUsage]:
    """Função auxiliar para extrair a carga horária total de uma única UC. Retorna (dados, tokens)."""
    logger.debug(f"Extraindo carga horária para UC: {uc_name}")
    workload: str = ""
    tokens = TokenUsage()

    try:
        prompt_workload = f"""{markdown_content}

Extraia APENAS a carga horária total em horas da Unidade Curricular '{uc_name}'.

INSTRUÇÕES IMPORTANTES:
- Retorne apenas a carga horaria total em horas, sem explicações adicionais.
- Não use marcadores, números ou símbolos.

Carga horária total '{uc_name}':"""

        async with llm_semaphore:
            response_workload = await llm.ainvoke([
                SystemMessage(content=instrucao_sistema),
                HumanMessage(content=prompt_workload)
            ])
        tokens = tokens + extract_tokens(response_workload)
        if response_workload:
            workload = sanitize_text(response_workload.content.strip())

        logger.debug(f"Carga horária total extraídas para {uc_name}: {workload} horas.")

    except Exception as e:
        logger.error(f"Erro ao extrair carga horária para UC '{uc_name}': {e}")

    return workload, tokens

async def _extract_module_for_single_uc(llm: AzureChatOpenAI, markdown_content: str, uc_name: str) -> Tuple[str, TokenUsage]:
    """Função auxiliar para extrair o tipo de módulo de uma única UC. Retorna (dados, tokens)."""
    logger.debug(f"Extraindo o tipo de módulo: {uc_name}")
    module: str = ""
    tokens = TokenUsage()

    try:
        prompt_module = f"""{markdown_content}

Extraia APENAS o tipo de módulo (básico, específico, etc) da Unidade Curricular '{uc_name}'.

INSTRUÇÕES IMPORTANTES:
- Retorne apenas o tipo de módulo da unidade curricular, sem explicações adicionais.
- Não use marcadores, números ou símbolos.

Módulo da UC '{uc_name}':"""

        async with llm_semaphore:
            response_module= await llm.ainvoke([
                SystemMessage(content=instrucao_sistema),
                HumanMessage(content=prompt_module)
            ])
        tokens = tokens + extract_tokens(response_module)
        if response_module and response_module.content:
            module = sanitize_text(response_module.content.strip())

        logger.debug(f"Tipo de módulo extraído para {uc_name}: {module}.")

    except Exception as e:
        logger.error(f"Erro ao extrair tipo de módulo para UC '{uc_name}': {e}")

    return module, tokens

@tool
async def extract_full_plan_details(markdown_content: str) -> str:
    """
    Extrai o nome do curso, lista de UCs, e para cada UC, suas capacidades, 
    conhecimentos, objetivo e referências bibliográficas a partir de um conteúdo Markdown.
    Usa uma única chamada LLM com JSON Schema para reduzir consumo de tokens.
    Retorna uma string JSON com todos os dados agregados incluindo tokens utilizados.
    """
    logger.info("Tool: extract_full_plan_details (versão unificada com JSON Schema) chamada.")
    if not markdown_content:
        logger.warning("Conteúdo Markdown não fornecido para extração completa.")
        return json.dumps({"error": "Conteúdo Markdown não fornecido.", "input_tokens": 0, "output_tokens": 0}, ensure_ascii=False, indent=2)

    # Acumulador de tokens para todas as chamadas LLM
    total_tokens = TokenUsage()

    try:
        # LLM configurado para retornar JSON usando MODEL_ID_TITLE
        extraction_llm_unified = AzureChatOpenAI(
            azure_deployment=os.getenv("MODEL_ID_TITLE"),
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
            api_key=os.getenv("AZURE_OPENAI_API_KEY"),
            api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
            temperature=0.1,
            top_p=0.95,
            max_tokens=65535,
            model_kwargs={"response_format": {"type": "json_object"}},
        )

        # JSON Schema com descrições para orientar a extração
        json_schema = '''{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "Plano de Curso - Modelo de Dados",
  "type": "object",
  "description": "Extração completa do plano de curso com todas as Unidades Curriculares.",
  "required": ["nome_curso", "modalidade", "unidades_curriculares"],
  "properties": {
    "nome_curso": {
      "type": "string",
      "description": "Nome completo do curso."
    },
    "modalidade": {
      "type": "string",
      "description": "Modalidade de ensino: presencial, híbrida ou EAD."
    },
    "unidades_curriculares": {
      "type": "array",
      "description": "Coleção de Unidades Curriculares extraídas do plano de curso.",
      "items": {
        "type": "object",
        "required": [
          "unidade_curricular", "carga_horaria", "modulo", "objetivo",
          "capacidades_basicas_ou_tecnicas", "capacidades_socioemocionais",
          "conhecimentos", "referencias_bibliograficas"
        ],
        "properties": {
          "unidade_curricular": {
            "type": "string",
            "description": "Nome da Unidade Curricular."
          },
          "carga_horaria": {
            "type": "string",
            "description": "Carga horária total da unidade (ex: 75h)."
          },
          "modulo": {
            "type": "string",
            "description": "Módulo básico ou Módulo específico."
          },
          "objetivo": {
            "type": "string",
            "description": "Descrição do objetivo educacional da unidade."
          },
          "capacidades_basicas_ou_tecnicas": {
            "type": "array",
            "description": "Lista de capacidades técnicas e/ou básicas a serem desenvolvidas. Podem ser chamadas de 'capacidades técnicas', 'capacidades básicas', 'competências técnicas' ou 'FUNDAMENTOS TÉCNICOS CIENTÍFICOS'.",
            "items": {"type": "string"}
          },
          "capacidades_socioemocionais": {
            "type": "array",
            "description": "Lista de competências comportamentais e socioemocionais. Podem ser chamadas de 'capacidades sociais', 'capacidades organizativas' ou 'capacidades metodológicas'.",
            "items": {"type": "string"}
          },
          "conhecimentos": {
            "type": "array",
            "description": "Lista detalhada dos tópicos de conhecimento abordados.",
            "items": {"type": "string"}
          },
          "referencias_bibliograficas": {
            "type": "object",
            "description": "Objeto contendo as referências literárias do curso.",
            "required": ["basicas", "complementares"],
            "properties": {
              "basicas": {
                "type": "array",
                "description": "Lista de referências bibliográficas básicas.",
                "items": {"type": "string"}
              },
              "complementares": {
                "type": "array",
                "description": "Lista de referências bibliográficas complementares.",
                "items": {"type": "string"}
              }
            }
          }
        }
      }
    }
  }
}'''

        # Prompt único para extrair todas as informações
        prompt = f"""A partir do modelo de dados JSON Schema abaixo, extraia as informações do plano de curso para TODAS as unidades curriculares.

{json_schema}

INSTRUÇÕES IMPORTANTES:
- Extraia TODAS as unidades curriculares do documento.
- Para cada capacidade, conhecimento e referência, traga o texto na íntegra como aparece no plano.
- Devido à conversão do plano de PDF para markdown, uma frase pode estar dividida em várias linhas - junte-as em uma única linha.
- Retorne APENAS o JSON válido, sem explicações ou texto adicional.

DOCUMENTO DO PLANO DE CURSO:
{markdown_content}

JSON:"""

        logger.info("Executando extração unificada com JSON Schema...")
        
        async with llm_semaphore:
            response = await extraction_llm_unified.ainvoke([
                SystemMessage(content="Você é um assistente especializado em extrair informações estruturadas de planos de curso. Responda apenas com JSON válido."),
                HumanMessage(content=prompt)
            ])
        
        total_tokens = extract_tokens(response)
        logger.info(f"Extração unificada concluída. Tokens: {total_tokens.input_tokens} entrada, {total_tokens.output_tokens} saída")
        
        if not response or not response.content:
            raise Exception("LLM não retornou resposta.")
        
        # Parse do JSON retornado
        raw_content = response.content.strip()
        
        # Remover possíveis blocos de código markdown
        if raw_content.startswith("```json"):
            raw_content = raw_content[7:]
        if raw_content.startswith("```"):
            raw_content = raw_content[3:]
        if raw_content.endswith("```"):
            raw_content = raw_content[:-3]
        raw_content = raw_content.strip()

        # Verifica truncamento via metadados
        finish_reason = response.response_metadata.get("finish_reason")
        is_truncated = finish_reason in ["MAX_TOKENS", "length"]
        
        extracted_data = {}
        parsing_error = False
        try:
            extracted_data = json.loads(raw_content)
        except json.JSONDecodeError as e:
            parsing_error = True
            logger.warning(f"JSON inválido na extração única: {e}. Conteúdo parcial: {raw_content[:200]}...")

        # Lógica de Fallback: Se houve truncamento ou erro de parse, usa o método robusto (mais caro/lento)
        if is_truncated or parsing_error:
            logger.warning(f"Falha na extração única (Truncado: {is_truncated}, JSON Erro: {parsing_error}). Acionando fallback para extração passo-a-passo (extract_full_again_plan_details)...")
            return await extract_full_again_plan_details(markdown_content)

        
        # Mapear para o formato esperado pelo frontend (compatibilidade)
        results = {
            "nomeCurso": extracted_data.get("nome_curso"),
            "modalidade": extracted_data.get("modalidade"),
            "unidadesCurriculares": []
        }
        
        ucs_raw = extracted_data.get("unidades_curriculares", [])
        for uc in ucs_raw:
            # Extrair referências
            refs = uc.get("referencias_bibliograficas", {})
            if isinstance(refs, dict):
                refs_list = refs.get("basicas", []) + refs.get("complementares", [])
            else:
                refs_list = []
            
            results["unidadesCurriculares"].append({
                "nomeUC": uc.get("unidade_curricular"),
                "tipoModulo": uc.get("modulo"),
                "carga_horaria_total": uc.get("carga_horaria"),
                "objetivo_uc": uc.get("objetivo"),
                "capacidades": {
                    "CapacidadesTecnicas_list": uc.get("capacidades_basicas_ou_tecnicas", []),
                    "CapacidadesSocioemocionais_list": uc.get("capacidades_socioemocionais", [])
                },
                "conhecimentos": uc.get("conhecimentos", []),
                "referencias_bibliograficas": refs_list
            })
        
        logger.info(f"Extração unificada finalizada: {len(results['unidadesCurriculares'])} UCs processadas.")
        
        # Incluir tokens no resultado
        results["input_tokens"] = total_tokens.input_tokens
        results["output_tokens"] = total_tokens.output_tokens
        
        json_result = json.dumps(results, ensure_ascii=False, indent=2, separators=(',', ': '))
        
        # Validar JSON gerado
        try:
            json.loads(json_result)
            logger.info("JSON de extração completada com sucesso.")
        except json.JSONDecodeError as e:
            logger.error(f"JSON inválido gerado após mapeamento: {e}. Conteúdo (início): {json_result[:500]}...")
            return json.dumps({"error": f"Erro na serialização JSON da extração: {str(e)}", "input_tokens": total_tokens.input_tokens, "output_tokens": total_tokens.output_tokens}, ensure_ascii=False)
        
        return json_result

    except Exception as e:
        logger.error(f"Erro em extract_full_plan_details (versão unificada): {e}", exc_info=True)
        return json.dumps({"error": f"Falha ao extrair detalhes completos do plano: {str(e)}", "input_tokens": 0, "output_tokens": 0}, ensure_ascii=False)


async def extract_full_again_plan_details(markdown_content: str) -> str:
    """
    Extrai o nome do curso, lista de UCs, e para cada UC, suas capacidades, 
    conhecimentos, objetivo e referências bibliográficas a partir de um conteúdo Markdown.
    Retorna uma string JSON com todos os dados agregados incluindo tokens utilizados.
    """
    logger.info("Tool: extract_full_plan_details (com objetivo e refs) chamada.")
    if not markdown_content:
        logger.warning("Conteúdo Markdown não fornecido para extração completa.")
        return json.dumps({"error": "Conteúdo Markdown não fornecido.", "input_tokens": 0, "output_tokens": 0}, ensure_ascii=False, indent=2)

    results: Dict[str, Any] = {
        "nomeCurso": None,
        "modalidade": None,
        "unidadesCurriculares": []
    }
    
    # Acumulador de tokens para todas as chamadas LLM
    total_tokens = TokenUsage()

    try:
        llm = extraction_llm

        # Etapa A: Extrair nome do curso (como antes)
        prompt_nome_curso = f"""{markdown_content}

Extraia o nome completo do curso descrito neste documento.
INSTRUÇÕES:
- Retorne somente o nome do curso.
- Não inclua explicações ou texto adicional.
Nome do curso:"""
        async with llm_semaphore:
            response_nome_curso = await llm.ainvoke([
                SystemMessage(content=instrucao_sistema),
                HumanMessage(content=prompt_nome_curso)
            ])
        total_tokens = total_tokens + extract_tokens(response_nome_curso)
        if response_nome_curso and response_nome_curso.content:
            results["nomeCurso"] = sanitize_text(response_nome_curso.content.strip())
            logger.info(f"Nome do curso extraído: {results['nomeCurso']}")

        # Etapa B: Extrair a modalidade de ensino
        prompt_modalidade = f"""{markdown_content}

Extraia a modalidade de ensino(presencial, híbrida ou EAD) do curso descrito neste documento.
INSTRUÇÕES:
- Retorne somente a modalidade de ensino.
- Não inclua explicações ou texto adicional.
Modalidade de Ensino:"""
        async with llm_semaphore:
            response_modalidade = await llm.ainvoke([
                SystemMessage(content=instrucao_sistema),
                HumanMessage(content=prompt_modalidade)
            ])
        total_tokens = total_tokens + extract_tokens(response_modalidade)
        if response_modalidade and response_modalidade.content:
            results["modalidade"] = sanitize_text(response_modalidade.content.strip())
            logger.info(f"Modalidade de Ensino extraído: {results['modalidade']}")
        
        # Etapa C: Extrair lista de UCs (como antes)
        prompt_ucs_list = f"""{markdown_content}

Extraia todas as Unidades Curriculares (UCs) do plano de curso.
INSTRUÇÕES IMPORTANTES:
- Retorne apenas os nomes das UCs, uma por linha.
- Não use marcadores, números ou símbolos no início de cada nome de UC.
- Não inclua frases introdutórias como "As UCs são:".
Lista de Unidades Curriculares:"""
        async with llm_semaphore:
            response_ucs_list = await llm.ainvoke([
                SystemMessage(content=instrucao_sistema),
                HumanMessage(content=prompt_ucs_list)
            ])
        total_tokens = total_tokens + extract_tokens(response_ucs_list)
        ucs_nomes = []
        if response_ucs_list and response_ucs_list.content:
            raw_ucs = [sanitize_text(uc.strip()) for uc in response_ucs_list.content.splitlines() if uc.strip()]
            ucs_nomes = [uc for uc in raw_ucs if uc] # Filtra strings vazias
            logger.info(f"UCs extraídas: {len(ucs_nomes)} unidades encontradas: {ucs_nomes}")


        # Etapa D: Para cada UC, extrair todos os detalhes
        capability_tasks = []
        knowledge_tasks = []
        objective_tasks = []
        reference_tasks = []
        workload_tasks = []
        module_tasks = []

        for uc_nome in ucs_nomes:
            if uc_nome:
                capability_tasks.append(_extract_capabilities_for_single_uc(llm, markdown_content, uc_nome))
                knowledge_tasks.append(_extract_knowledge_for_single_uc(llm, markdown_content, uc_nome))
                objective_tasks.append(_extract_objective_for_single_uc(llm, markdown_content, uc_nome))
                reference_tasks.append(_extract_references_for_single_uc(llm, markdown_content, uc_nome))
                workload_tasks.append(_extract_workload_for_single_uc(llm, markdown_content, uc_nome))
                module_tasks.append(_extract_module_for_single_uc(llm, markdown_content, uc_nome))

        # Executar todas as tarefas de extração em paralelo
        # (capacidades_results, conhecimentos_results, objetivos_results, referencias_results) = await asyncio.gather(
        #     asyncio.gather(*capability_tasks) if capability_tasks else asyncio.sleep(0, result=[]), # type: ignore
        #     asyncio.gather(*knowledge_tasks) if knowledge_tasks else asyncio.sleep(0, result=[]), # type: ignore
        #     asyncio.gather(*objective_tasks) if objective_tasks else asyncio.sleep(0, result=[]), # type: ignore
        #     asyncio.gather(*reference_tasks) if reference_tasks else asyncio.sleep(0, result=[]), # type: ignore
        # )
        # Simplificando o gather:
        all_gathered_results = []
        if ucs_nomes: # Só executa gather se houver UCs
            tasks_to_run = []
            for uc_nome_idx in range(len(ucs_nomes)):
                 # Para cada UC, agrupamos suas 4 tarefas de extração
                if ucs_nomes[uc_nome_idx]: # Checa se o nome da UC não é vazio
                    tasks_to_run.append(
                        asyncio.gather(
                            capability_tasks[uc_nome_idx],
                            knowledge_tasks[uc_nome_idx],
                            objective_tasks[uc_nome_idx],
                            reference_tasks[uc_nome_idx],
                            workload_tasks[uc_nome_idx],
                            module_tasks[uc_nome_idx]
                        )
                    )
            if tasks_to_run:
                logger.info(f"Iniciando extração detalhada para {len(tasks_to_run)} UCs...")
                all_gathered_results = await asyncio.gather(*tasks_to_run)
                logger.info("Extração detalhada de todas as UCs concluída.")


        # Montar o resultado final - agora cada função retorna (dados, tokens)
        for i, uc_nome in enumerate(ucs_nomes):
            if uc_nome and i < len(all_gathered_results):
                # all_gathered_results[i] será uma tupla de 6 tuplas: ((caps_dict, toks), (knowledge, toks), ...)
                (uc_capabilities, cap_toks), (uc_knowledge, know_toks), (uc_objective, obj_toks), (uc_references, ref_toks), (uc_workload, work_toks), (uc_module, mod_toks) = all_gathered_results[i]
                
                # Acumular tokens de todas as funções auxiliares
                total_tokens = total_tokens + cap_toks + know_toks + obj_toks + ref_toks + work_toks + mod_toks

                results["unidadesCurriculares"].append({
                    "nomeUC": uc_nome,
                    "tipoModulo": uc_module if uc_module else None,
                    "carga_horaria_total": uc_workload if uc_workload else None,
                    "objetivo_uc": uc_objective if uc_objective else None,
                    "capacidades": uc_capabilities if uc_capabilities else {"CapacidadesTecnicas_list": [], "CapacidadesSocioemocionais_list": []},
                    "conhecimentos": uc_knowledge if uc_knowledge else [],
                    "referencias_bibliograficas": uc_references if uc_references else []
                })

        logger.info(f"Extração completa finalizada: {len(results['unidadesCurriculares'])} UCs processadas. Tokens: {total_tokens.input_tokens} entrada, {total_tokens.output_tokens} saída")
        
        # Incluir tokens no resultado
        results["input_tokens"] = total_tokens.input_tokens
        results["output_tokens"] = total_tokens.output_tokens

        json_result = json.dumps(results, ensure_ascii=False, indent=2, separators=(',', ': '))

        try:
            json.loads(json_result)
            logger.info("JSON de extração completada sucesso.")
        except json.JSONDecodeError as e:
            logger.error(f"JSON inválido gerado pela extração completa: {e}. Conteúdo (início): {json_result}")
            return json.dumps({"error": f"Erro na serialização JSON da extração: {str(e)}", "input_tokens": total_tokens.input_tokens, "output_tokens": total_tokens.output_tokens}, ensure_ascii=False)
        return json_result

    except Exception as e:
        logger.error(f"Erro em extract_full_plan_details (com objetivo e refs): {e}", exc_info=True)
        return json.dumps({"error": f"Falha ao extrair detalhes completos do plano: {str(e)}", "input_tokens": 0, "output_tokens": 0}, ensure_ascii=False)

