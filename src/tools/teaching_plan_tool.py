import logging
import json
import os
from typing import Optional, List, Any, Dict
from langchain_core.tools import tool
from langchain_openai import AzureChatOpenAI
from src.utils.token_tracker import TokenUsage, extract_tokens
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from src.document_store import get_markdown_document
from src.prompts import (
    modeloCabecalhoPlanoEnsino,
    modeloItem2CapacidadesSA,
    modeloItem3ConhecimentosSA,
    modeloItem4EstrategiaSA_Base,
    modeloPlanoDeEnsinoSP,
    modeloPlanoDeEnsinoEC,
    modeloPlanoDeEnsinoP,
    modeloPlanoDeEnsinoPA,
    modeloPlanoDeEnsinoPI,
    modeloAvaliacaoAtual,
    modeloPlanoAulaAtual
)

logger = logging.getLogger(__name__)


def filter_course_plan_by_ucs(markdown_content: str, situacoes_aprendizagem: List[Dict[str, Any]], nome_uc: str) -> str:
    """
    Filtra o plano de curso para incluir apenas as UCs que serão usadas na geração.
    Isso reduz significativamente o consumo de tokens.
    
    Args:
        markdown_content: Conteúdo JSON do plano de curso completo
        situacoes_aprendizagem: Lista de SAs com as UCs selecionadas
        nome_uc: Nome da UC principal (para estratégias não-PI)
    
    Returns:
        JSON filtrado contendo apenas as UCs necessárias
    """
    try:
        # Tentar fazer parse do JSON
        course_plan = json.loads(markdown_content)
        
        # Coletar nomes de todas as UCs que serão usadas
        ucs_necessarias = set()
        
        # Adicionar a UC principal se fornecida
        if nome_uc:
            ucs_necessarias.add(nome_uc.strip().lower())
        
        # Adicionar UCs de cada SA (incluindo Projeto Integrador)
        for sa in situacoes_aprendizagem:
            # UCs de projeto integrador ou outras estratégias
            unidades_curriculares = sa.get("unidades_curriculares", [])
            for uc in unidades_curriculares:
                uc_nome = uc.get("nomeUC", "")
                if uc_nome:
                    ucs_necessarias.add(uc_nome.strip().lower())
        
        # Se não há UCs especificadas, retornar o conteúdo original
        if not ucs_necessarias:
            logger.warning("Nenhuma UC especificada para filtro, retornando plano completo.")
            return markdown_content
        
        # Filtrar as unidades curriculares
        if "unidadesCurriculares" in course_plan:
            original_count = len(course_plan["unidadesCurriculares"])
            course_plan["unidadesCurriculares"] = [
                uc for uc in course_plan["unidadesCurriculares"]
                if uc.get("nomeUC", "").strip().lower() in ucs_necessarias
            ]
            filtered_count = len(course_plan["unidadesCurriculares"])
            logger.info(f"Plano de curso filtrado: {original_count} -> {filtered_count} UCs (necessárias: {list(ucs_necessarias)})")
        
        return json.dumps(course_plan, ensure_ascii=False)
    
    except json.JSONDecodeError:
        # Se não for JSON válido, retornar como está
        logger.warning("Conteúdo do plano de curso não é JSON válido, retornando sem filtro.")
        return markdown_content
    except Exception as e:
        logger.error(f"Erro ao filtrar plano de curso: {e}")
        return markdown_content

# ============================================================================
# FUNÇÕES AUXILIARES PARA CONSTRUÇÃO DO PROMPT UNIFICADO
# ============================================================================

def get_strategy_template_content(strategy_key: str, tematica_sa: str) -> str:
    """Retorna o template de conteúdo específico para a estratégia."""
    strategy_map = {
        "situacao-problema": modeloPlanoDeEnsinoSP,
        "estudo-caso": modeloPlanoDeEnsinoEC,
        "projetos": modeloPlanoDeEnsinoP,
        "pesquisa-aplicada": modeloPlanoDeEnsinoPA,
        "projeto-integrador": modeloPlanoDeEnsinoPI,
    }
    template = strategy_map.get(strategy_key.lower().replace(" ", "-"))
    if template:
        # Formatar com temática se o template suportar
        try:
            return template.format(tematica_sa=tematica_sa if tematica_sa else "Não especificada")
        except KeyError:
            return template
    logger.warning(f"Template de conteúdo não encontrado para estratégia: {strategy_key}")
    return "[ERRO INTERNO: Conteúdo da estratégia não pôde ser gerado devido a template não encontrado]"

def format_estrategia_nome_for_display(strategy_key: str) -> str:
    """Formata o nome da estratégia para exibição no título do Item 4."""
    return strategy_key.replace("-", " ").title()

def build_item1_prompt(
    nome_curso: str,
    turma: str,
    modalidade: str,
    nome_uc: str,
    docente: str,
    unidade_operacional: str,
    departamento_regional: str,
    data_inicio: str = None,
    data_fim: str = None
) -> str:
    """Constrói o prompt para o Item 1 (Cabeçalho)."""
    prompts_dates = ""
    if data_inicio and data_fim:
        prompts_dates = f"\n- Data Início: {data_inicio}\n- Data Fim: {data_fim}"

    return f"""Com base nas informações fornecidas e no conteúdo do plano de curso em anexo, preencha somente o Item 1 (Informações da Unidade Curricular) do Plano de Ensino.

Informações disponíveis (USE EXATAMENTE ESTAS INFORMAÇÕES):
- Nome do Curso Técnico: {nome_curso}
- Turma: {turma}
- Modalidade: {modalidade} (Copie EXATAMENTE este valor, não invente)
- Nome da Unidade Curricular: {nome_uc}
- Professor Titular: {docente}
- Unidade Operacional (Escola): {unidade_operacional}
- Departamento Regional: {departamento_regional}{prompts_dates}

Use o seguinte template para o Item 1 (preencha os campos com os dados acima):
{modeloCabecalhoPlanoEnsino}"""

def build_item2_prompt(
    sa_num: int,
    capacidades_tecnicas: str,
    capacidades_socioemocionais: str
) -> str:
    """Constrói o prompt para o Item 2 (Capacidades)."""
    return f"""Preencha somente o Item 2 seguindo o template abaixo.
Utilize as seguintes capacidades técnicas/básicas:
{capacidades_tecnicas}
Utilize as seguintes capacidades socioemocionais:
{capacidades_socioemocionais}
Inicie com: 
# Situação de Aprendizagem {sa_num}
{modeloItem2CapacidadesSA}"""

def build_item3_prompt(sa_num: int, nome_uc: str, nomes_ucs_lista: List[str] = None) -> str:
    """Constrói o prompt para o Item 3 (Conhecimentos)."""
    if nomes_ucs_lista and len(nomes_ucs_lista) > 1:
        nomes_ucs_texto = ", ".join(nomes_ucs_lista)
        return f"""Preencha somente o Item 3 seguindo o template abaixo considerando os conhecimentos das seguintes unidades curriculares: {nomes_ucs_texto} contidas no plano de curso.
{modeloItem3ConhecimentosSA}"""
    else:
        return f"""Preencha somente o Item 3 seguindo o template abaixo considerando os conhecimentos da unidade curricular {nome_uc} contidas no plano de curso.
{modeloItem3ConhecimentosSA}"""

def build_item4_prompt(estrategia_key: str, tematica: str) -> str:
    """Constrói o prompt para o Item 4 (Estratégia)."""
    conteudo_especifico = get_strategy_template_content(estrategia_key, tematica)
    estrategia_formatada = format_estrategia_nome_for_display(estrategia_key)
    
    template_base = modeloItem4EstrategiaSA_Base.format(
        estrategia_nome_formatado=estrategia_formatada,
        template_especifico_da_estrategia_aqui=conteudo_especifico
    )
    
    return f"""Preencha somente o item 4 (Estratégia de Aprendizagem Desafiadora) do plano de ensino.
Leve em consideração a temática da Situação de Aprendizagem: '{tematica}' e as capacidades e conhecimentos elaborados anteriormente.
Use o seguinte template:
{template_base}"""

def build_item5_prompt(capacidades_tecnicas: str, capacidades_socioemocionais: str) -> str:
    """Constrói o prompt para o Item 5 (Avaliação)."""
    return f"""Preencha somente o Item 5 (Critérios de Avaliação para esta Situação de Aprendizagem) usando o template abaixo.
Considere todas as capacidades básicas/técnicas:
{capacidades_tecnicas}
E socioemocionais:
{capacidades_socioemocionais}
{modeloAvaliacaoAtual}"""

def build_item6_prompt(cronograma_texto: str, total_aulas: int, carga_horaria: float, data_inicio: str, data_fim: str, horarios_texto: str) -> str:
    """Constrói o prompt para o Item 6 (Plano de Aula)."""
    if total_aulas > 0:
        return f"""Crie o cronograma de aulas (Plano de Aula) para esta Situação de Aprendizagem.
ATENÇÃO IMPORTANTE: O cronograma com as datas e horários JÁ FOI CALCULADO abaixo. 
Você DEVE usar EXATAMENTE estas datas e horários, sem inventar outras:
{cronograma_texto}
INSTRUÇÕES OBRIGATÓRIAS:
1. A tabela do Plano de Aula deve ter EXATAMENTE {total_aulas} linhas.
2. Cada linha acima corresponde a UMA linha na tabela.
3. Use a data e horário EXATAMENTE como aparecem acima.
4. Distribua as capacidades, conhecimentos e atividades ao longo das aulas.
Preencha somente o Item 6 usando o template:
{modeloPlanoAulaAtual}"""
    else:
        return f"""Agora, crie o cronograma de aulas para esta Situação de Aprendizagem. 
Considere que o período letivo total da Unidade Curricular vai de {data_inicio} até {data_fim}. 
A carga horária desta SA é de {carga_horaria} horas.
Distribua as aulas de forma realista dentro deste período. 
Os horários gerais disponíveis para a UC são:
{horarios_texto}
Preencha somente o Item 6 (Plano de Aula) usando o template:
{modeloPlanoAulaAtual}"""

# JSON Schema de saída
OUTPUT_JSON_SCHEMA = '''
Use o schema JSON abaixo para a saída:
{
  "plano_de_ensino": {
    "informacoes_curso": {
      "curso": "string",
      "turma": "string",
      "unidade_curricular": "string",
      "modulo": "string",
      "carga_horaria_total": "string",
      "objetivo": "string",
      "modalidade": "string",
      "professor": "string",
      "unidade": "string",
      "departamento_regional": "string",
      "data_inicio": "string",
      "data_fim": "string"
    },
    "situacoes_aprendizagem": [
      {
        "titulo": "string",
        "capacidades": {
          "basicas": ["string"],
          "tecnicas": ["string"],
          "socioemocionais": ["string"]
        },
        "conhecimentos": [
          {
            "topico": "string",
            "subtopicos": [
              {
                "descricao": "string",
                "subtopicos": []
              }
            ]
          }
        ],
        "estrategia_aprendizagem": {
          "tipo": "string",
          "aulas_previstas": "string",
          "carga_horaria": "string",
          "detalhes": {
            "titulo_sa": "string",
            "contextualizacao": "string",
            "desafio": "string",
            "resultados_esperados": "string"
          }
        },
        "criterios_avaliacao": {
          "dicotomicos": [
            {
              "capacidade": "string",
              "criterios": ["string"]
            }
          ],
          "graduais": [
            {
              "capacidade": "string",
              "criterios": ["string"],
              "niveis": {
                "nivel_1": "string",
                "nivel_2": "string",
                "nivel_3": "string",
                "nivel_4": "string"
              }
            }
          ]
        },
        "plano_de_aula": [
          {
            "horas_aulas_data": "string",
            "capacidades": "string",
            "conhecimentos": "string",
            "estrategias": "string",
            "recursos_ambientes": "string",
            "criterios_avaliacao": "string",
            "instrumento_avaliacao": "string",
            "referencias": "string"
          }
        ],
        "perguntas_mediadoras": ["string"]
      }
    ]
  }
}
'''

def build_unified_prompt(
    nome_curso: str,
    turma: str,
    modalidade: str,
    nome_uc: str,
    docente: str,
    unidade_operacional: str,
    departamento_regional: str,
    situacoes_aprendizagem: List[Dict[str, Any]],
    cronogramas: List[Dict],
    data_inicio: str,
    data_fim: str,
    horarios_param: List[Dict[str, str]]
) -> str:
    """Constrói o prompt unificado com todos os itens para todas as SAs."""
    from src.utils.schedule_calculator import formatar_cronograma_para_prompt
    
    prompt_parts = []
    
    num_sas = len(situacoes_aprendizagem)
    
    # Instrução inicial explícita para o modelo
    prompt_parts.append(f"""INSTRUÇÃO PRINCIPAL: Você deve gerar um Plano de Ensino COMPLETO em formato JSON.
O plano deve conter OBRIGATORIAMENTE:
1. O objeto "informacoes_curso" com todos os campos preenchidos.
2. O array "situacoes_aprendizagem" com EXATAMENTE {num_sas} elemento(s), cada um contendo TODOS os itens: capacidades, conhecimentos, estrategia_aprendizagem, criterios_avaliacao, plano_de_aula e perguntas_mediadoras.

NÃO retorne o array "situacoes_aprendizagem" vazio. Cada SA deve ter conteúdo detalhado e extenso.
Siga as instruções abaixo para preencher cada seção do plano:""")
    
    # --- Detectar Projeto Integrador e extrair nomes das UCs ---
    nome_uc_para_cabecalho = nome_uc
    todas_ucs_nomes = []
    
    for sa in situacoes_aprendizagem:
        estrategia = sa.get("estrategia", "").lower().replace(" ", "-")
        if estrategia == "projeto-integrador":
            unidades = sa.get("unidades_curriculares", [])
            for uc in unidades:
                uc_nome = uc.get("nomeUC", "")
                if uc_nome and uc_nome not in todas_ucs_nomes:
                    todas_ucs_nomes.append(uc_nome)
    
    if todas_ucs_nomes:
        nome_uc_para_cabecalho = " + ".join(todas_ucs_nomes)
    
    # Item 1 - Cabeçalho
    prompt_parts.append(build_item1_prompt(
        nome_curso, turma, modalidade, nome_uc_para_cabecalho, 
        docente, unidade_operacional, departamento_regional,
        data_inicio, data_fim
    ))
    
    # Loop por cada SA
    for i, sa_item in enumerate(situacoes_aprendizagem):
        sa_num = i + 1
        
        # Extrair capacidades
        unidades_curriculares = sa_item.get("unidades_curriculares", [])
        if unidades_curriculares:
            # Projeto Integrador: consolidar capacidades de múltiplas UCs
            todas_caps_tecnicas = []
            todas_caps_socio = []
            nomes_ucs = []
            
            for uc in unidades_curriculares:
                nomes_ucs.append(uc.get("nomeUC", "UC não identificada"))
                todas_caps_tecnicas.extend(uc.get("capacidades_tecnicas", []))
                todas_caps_socio.extend(uc.get("capacidades_socioemocionais", []))
            
            # Remover duplicatas
            todas_caps_tecnicas = list(dict.fromkeys(todas_caps_tecnicas))
            todas_caps_socio = list(dict.fromkeys(todas_caps_socio))
            
            caps_tecnicas_texto = "\n".join([f"- {cap}" for cap in todas_caps_tecnicas])
            caps_socio_texto = "\n".join([f"- {cap}" for cap in todas_caps_socio])
        else:
            # Outras estratégias
            caps_tecnicas_texto = "\n".join([f"- {cap}" for cap in sa_item.get("capacidades_tecnicas", [])])
            caps_socio_texto = "\n".join([f"- {cap}" for cap in sa_item.get("capacidades_socioemocionais", [])])
            nomes_ucs = None
        
        estrategia_key = sa_item.get("estrategia", "situacao-problema")
        tematica = sa_item.get("tema_desafio", "Não especificado")
        
        # Item 2 - Capacidades
        prompt_parts.append(build_item2_prompt(sa_num, caps_tecnicas_texto, caps_socio_texto))
        
        # Item 3 - Conhecimentos
        prompt_parts.append(build_item3_prompt(sa_num, nome_uc, nomes_ucs))
        
        # Item 4 - Estratégia
        prompt_parts.append(build_item4_prompt(estrategia_key, tematica))
        
        # Item 5 - Avaliação
        prompt_parts.append(build_item5_prompt(caps_tecnicas_texto, caps_socio_texto))
        
        # Item 6 - Plano de Aula
        cronograma = cronogramas[i] if i < len(cronogramas) else []
        cronograma_texto = formatar_cronograma_para_prompt(cronograma)
        total_aulas = len(cronograma)
        carga_horaria = sa_item.get("carga_horaria", 20)
        
        horarios_texto = "\n".join([
            f"- {h.get('dia', 'Não especificado')} das {h.get('horaInicio', 'HH:MM')} às {h.get('horaFim', 'HH:MM')}" 
            for h in horarios_param
        ]) if horarios_param else "Não fornecidos."
        
        prompt_parts.append(build_item6_prompt(
            cronograma_texto, total_aulas, carga_horaria, 
            data_inicio, data_fim, horarios_texto
        ))
    
    # Adicionar JSON Schema de saída
    prompt_parts.append(OUTPUT_JSON_SCHEMA)
    
    # Instrução final de reforço
    prompt_parts.append(f"""ATENÇÃO FINAL OBRIGATÓRIA:
- O JSON de saída DEVE conter "situacoes_aprendizagem" com EXATAMENTE {num_sas} elemento(s) completamente preenchido(s).
- Cada elemento DEVE conter TODOS os campos: capacidades (basicas, tecnicas, socioemocionais), conhecimentos (com tópicos e subtópicos detalhados), estrategia_aprendizagem (com detalhes completos), criterios_avaliacao (dicotômicos E graduais), plano_de_aula (com uma entrada para CADA aula do cronograma) e perguntas_mediadoras (mínimo 5 perguntas).
- NÃO deixe nenhum array ou campo vazio. Gere conteúdo detalhado e relevante para cada seção.
- A resposta deve ser SOMENTE o JSON válido, sem texto adicional antes ou depois.""")
    
    return "\n\n".join(prompt_parts)


# ============================================================================
# FUNÇÃO PRINCIPAL - VERSÃO UNIFICADA (CHAMADA ÚNICA)
# ============================================================================

@tool
async def generate_teaching_plan(
    stored_markdown_id: str,
    docente: str,
    unidade_operacional: str,
    departamento_regional: str,
    nome_curso: str,
    turma: str,
    modalidade: str,
    nome_uc: str,
    data_inicio: str,
    data_fim: str,
    situacoes_aprendizagem_param: List[Dict[str, Any]],
    horarios_param: List[Dict[str, str]] = None,
    temperature: float = 0.7,
    top_p: float = 0.95,
) -> str:
    """
    Gera um plano de ensino detalhado usando UMA ÚNICA chamada LLM.
    
    Esta versão otimizada consolida todos os prompts em uma única chamada,
    reduzindo drasticamente o consumo de tokens em comparação com a versão anterior.
    """
    logger.info(f"Tool: generate_teaching_plan (versão unificada) chamada para stored_id: {stored_markdown_id}, UC: {nome_uc}")
    
    if horarios_param is None:
        horarios_param = []
    
    # Buscar conteúdo do plano de curso
    markdown_content = await get_markdown_document(stored_markdown_id)
    if not markdown_content:
        err_msg = f"Conteúdo Markdown não encontrado para o ID: {stored_markdown_id}"
        logger.error(err_msg)
        return json.dumps({"error": err_msg, "details": "Markdown content could not be retrieved from storage."})
    
    # Filtrar plano de curso para incluir apenas UCs necessárias (economia de tokens)
    markdown_content = filter_course_plan_by_ucs(
        markdown_content, 
        situacoes_aprendizagem_param, 
        nome_uc
    )
    
    total_tokens = TokenUsage()
    
    try:
        # Criar LLM com parâmetros do usuário
        plan_generation_llm = AzureChatOpenAI(
            azure_deployment=os.getenv('MODEL_ID'),
            azure_endpoint=os.getenv('AZURE_OPENAI_ENDPOINT'),
            api_key=os.getenv('AZURE_OPENAI_API_KEY'),
            api_version=os.getenv('AZURE_OPENAI_API_VERSION'),
            temperature=temperature,
            top_p=top_p,
            max_tokens=65535,
        )
        
        # Calcular cronogramas para todas as SAs
        from src.utils.schedule_calculator import gerar_cronograma_aulas
        from datetime import datetime, timedelta
        
        cronogramas = []
        proxima_data = data_inicio
        
        for sa_item in situacoes_aprendizagem_param:
            carga_horaria_sa = float(sa_item.get("carga_horaria", 20.0))
            if carga_horaria_sa <= 0:
                carga_horaria_sa = 20.0
            
            cronograma = gerar_cronograma_aulas(
                proxima_data, data_fim, horarios_param, carga_horaria_sa
            )
            cronogramas.append(cronograma)
            
            # Atualizar próxima data para SA seguinte
            if cronograma:
                ultima_aula = cronograma[-1]
                ultima_data = datetime.strptime(ultima_aula["data"], "%d/%m/%Y")
                proxima_data = (ultima_data + timedelta(days=1)).strftime("%Y-%m-%d")
        
        # Construir prompt unificado
        prompt_unificado = build_unified_prompt(
            nome_curso=nome_curso,
            turma=turma,
            modalidade=modalidade,
            nome_uc=nome_uc,
            docente=docente,
            unidade_operacional=unidade_operacional,
            departamento_regional=departamento_regional,
            situacoes_aprendizagem=situacoes_aprendizagem_param,
            cronogramas=cronogramas,
            data_inicio=data_inicio,
            data_fim=data_fim,
            horarios_param=horarios_param
        )
        
        # System message com contexto do plano de curso
        instrucao_sistema = f"""Você é um especialista em educação do Senai que elabora Planos de Ensino detalhados e bem estruturados, seguindo a Metodologia SENAI de Educação Profissional (MSEP). Tome como base o conteúdo do plano de curso anexado. As instruções entre colchetes são orientações específicas para você seguir e não devem aparecer no documento final.

REGRA FUNDAMENTAL: Você DEVE gerar o plano de ensino COMPLETO com TODAS as seções preenchidas. O array "situacoes_aprendizagem" NUNCA deve estar vazio — ele deve conter elementos com todos os itens (capacidades, conhecimentos, estratégia, critérios de avaliação, plano de aula e perguntas mediadoras) preenchidos de forma detalhada.

Aqui está o conteúdo do Plano de Curso desta Unidade Curricular (UC), que deve servir como base para as informações gerais e para a seleção de capacidades e conhecimentos específicos para cada Situação de Aprendizagem (SA):

{markdown_content}

Por favor, gere TODAS as seções do Plano de Ensino conforme solicitado no prompt do usuário. A resposta deve ser um JSON válido e completo."""
        
        logger.info(f"Executando chamada única ao LLM para gerar plano com {len(situacoes_aprendizagem_param)} SA(s)...")
        
        # UMA ÚNICA chamada ao LLM
        response = await plan_generation_llm.ainvoke([
            SystemMessage(content=instrucao_sistema),
            HumanMessage(content=prompt_unificado)
        ])
        
        total_tokens = extract_tokens(response)
        logger.info(f"Chamada LLM concluída. Tokens: {total_tokens.input_tokens} entrada, {total_tokens.output_tokens} saída")
        
        # Debug: verificar se resposta foi truncada
        finish_reason = response.response_metadata.get("finish_reason", "unknown")
        logger.info(f"finish_reason: {finish_reason}, tamanho da resposta: {len(response.content)} chars")
        if finish_reason == "length":
            logger.warning("⚠️ RESPOSTA TRUNCADA! O modelo atingiu o limite de max_tokens. Considere aumentar max_tokens ou reduzir o prompt.")
        
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
        
        try:
            plan_json = json.loads(raw_content)
        except json.JSONDecodeError as e:
            logger.error(f"JSON inválido retornado pelo LLM: {e}. Conteúdo (início): {raw_content[:500]}...")
            # Retornar como markdown se o parse falhar
            return json.dumps({
                "plan_markdown": raw_content,
                "input_tokens": total_tokens.input_tokens,
                "output_tokens": total_tokens.output_tokens,
                "warning": "Output não era JSON válido, retornado como markdown."
            }, ensure_ascii=False)
        
        logger.info(f"Plano de ensino gerado com sucesso para UC: {nome_uc}")
        
        # Retornar resultado com dados estruturados
        return json.dumps({
            "plan_json": plan_json,
            "input_tokens": total_tokens.input_tokens,
            "output_tokens": total_tokens.output_tokens
        }, ensure_ascii=False)
    
    except Exception as e:
        logger.error(f"Erro em generate_teaching_plan (versão unificada): {e}", exc_info=True)
        return json.dumps({"error": f"Falha ao gerar plano de ensino: {str(e)}"}, ensure_ascii=False)
