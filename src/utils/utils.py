import logging
import os
from langchain_openai import AzureChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
import json

logger = logging.getLogger(__name__)

# Forçar saída JSON via response_format
json_converter_llm = AzureChatOpenAI(
    azure_deployment=os.getenv("MODEL_ID"),
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
    temperature=0.1,
    top_p=0.95,
    max_tokens=65536,
    model_kwargs={"response_format": {"type": "json_object"}},
)

async def cleanup_temp_file(file_path: str):
    """Remove o arquivo temporário após o envio."""
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"Arquivo temporário deletado: {file_path}")
    except Exception as e:
        logger.error(f"Erro ao deletar arquivo temporário {file_path}: {str(e)}")
        
async def convert_markdown_to_json(markdown_str: str):
    """Converte o plano de ensino em Markdown para um dicionário JSON."""
    
    # Instrução simplificada, já que o LLM vai retornar JSON puro
    instrucao_sistema = """Você é um conversor de markdown para JSON de alta performance. 
Converta o plano de ensino em markdown para a estrutura JSON especificada.
Retorne APENAS o JSON válido, sem texto adicional.

Estrutura esperada:
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
      "departamento_regional": "string"
    },
    "situacoes_aprendizagem": [
      {
        "titulo": "string",
        "capacidades": {
          "basicas": ["string"],
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
"""
    
    prompt_usuario = f"Converta o seguinte markdown para JSON:\n\n{markdown_str}"

    try:
        response = await json_converter_llm.ainvoke([
            SystemMessage(content=instrucao_sistema),
            HumanMessage(content=prompt_usuario)
        ])
        response_content = response.content

        # Com response_mime_type, a resposta já deve ser JSON puro
        # Mas mantemos a limpeza por segurança
        cleaned_json_string = extract_json_from_response(response_content)
        
        # Valida o JSON
        parsed = json.loads(cleaned_json_string)
        logger.info("JSON validado com sucesso")
        
        return cleaned_json_string
        
    except json.JSONDecodeError as e:
        logger.error(f"Erro ao fazer parse do JSON: {e}")
        logger.error(f"Conteúdo recebido: {response_content[:500]}...")
        return '{"error": "JSON inválido retornado pelo LLM."}'
    except Exception as e:
        logger.error(f"Erro ao converter markdown para JSON: {e}", exc_info=True)
        return '{"error": "Falha ao converter o conteúdo para JSON."}'
    
def extract_json_from_response(raw_response: str) -> str:
    """
    Extrai JSON válido de uma string, removendo marcadores markdown se existirem.
    """
    try:
        # Remove ```json e ``` se existirem
        cleaned = raw_response.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        elif cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()
        
        # Encontra o primeiro '{' e o último '}'
        start_index = cleaned.find('{')
        end_index = cleaned.rfind('}')
        
        if start_index != -1 and end_index != -1 and end_index > start_index:
            json_str = cleaned[start_index : end_index + 1]
            return json_str
        else:
            return cleaned
            
    except Exception as e:
        logger.error(f"Erro ao extrair JSON: {e}")
        return raw_response


def convert_plan_json_to_markdown(plan_json: dict) -> str:
    """
    Converte o JSON estruturado do plano de ensino para formato Markdown.
    Inclui tabelas formatadas para critérios de avaliação e plano de aula.
    """
    plano = plan_json.get("plano_de_ensino", {})
    info = plano.get("informacoes_curso", {})
    sas = plano.get("situacoes_aprendizagem", [])
    
    md = []
    
    # Título principal
    uc_name = info.get('unidade_curricular', 'Unidade Curricular')
    md.append(f"# Plano de Ensino - {uc_name}")
    md.append("")
    
    # 1. Informações do Curso
    md.append("## 1. Informações do Curso")
    md.append("")
    md.append(f"- **Curso**: {info.get('curso', '-')}")
    md.append(f"- **Turma**: {info.get('turma', '-')}")
    md.append(f"- **Unidade Curricular**: {info.get('unidade_curricular', '-')}")
    md.append(f"- **Módulo**: {info.get('modulo', '-')}")
    md.append(f"- **Carga Horária Total**: {info.get('carga_horaria_total', '-')}")
    md.append(f"- **Objetivo**: {info.get('objetivo', '-')}")
    md.append(f"- **Modalidade**: {info.get('modalidade', '-')}")
    md.append(f"- **Professor**: {info.get('professor', '-')}")
    md.append(f"- **Unidade**: {info.get('unidade', '-')}")
    md.append(f"- **Departamento Regional**: {info.get('departamento_regional', '-')}")
    md.append("")
    
    # Situações de Aprendizagem
    for i, sa in enumerate(sas, 1):
        titulo_sa = sa.get('titulo', f'Situação de Aprendizagem {i}')
        md.append(f"## {titulo_sa}")
        md.append("")
        
        # Capacidades
        capacidades = sa.get('capacidades', {})
        
        # Capacidades Técnicas (pode ser "tecnicas" ou "basicas")
        tecnicas = capacidades.get('tecnicas', capacidades.get('basicas', []))
        if tecnicas:
            md.append("### Capacidades Técnicas")
            md.append("")
            for cap in tecnicas:
                md.append(f"- {cap}")
            md.append("")
        
        # Capacidades Socioemocionais
        socioemocionais = capacidades.get('socioemocionais', [])
        if socioemocionais:
            md.append("### Capacidades Socioemocionais")
            md.append("")
            for cap in socioemocionais:
                md.append(f"- {cap}")
            md.append("")
        
        # Conhecimentos
        conhecimentos = sa.get('conhecimentos', [])
        if conhecimentos:
            md.append("### Conhecimentos")
            md.append("")
            for conhec in conhecimentos:
                topico = conhec.get('topico', '')
                md.append(f"- **{topico}**")
                subtopicos = conhec.get('subtopicos', [])
                for sub in subtopicos:
                    desc = sub.get('descricao', '')
                    md.append(f"  - {desc}")
                    sub_sub = sub.get('subtopicos', [])
                    for ss in sub_sub:
                        ss_desc = ss.get('descricao', '')
                        md.append(f"    - {ss_desc}")
            md.append("")
        
        # Estratégia de Aprendizagem
        estrategia = sa.get('estrategia_aprendizagem', {})
        if estrategia:
            tipo = estrategia.get('tipo', '-')
            md.append(f"### Estratégia de Aprendizagem - {tipo}")
            md.append("")
            md.append(f"- **Aulas Previstas**: {estrategia.get('aulas_previstas', '-')}")
            md.append(f"- **Carga Horária**: {estrategia.get('carga_horaria', '-')}")
            md.append("")
            
            detalhes = estrategia.get('detalhes', {})
            if detalhes:
                titulo_det = detalhes.get('titulo_sa', '')
                if titulo_det:
                    md.append(f"**Título**: {titulo_det}")
                    md.append("")
                
                contexto = detalhes.get('contextualizacao', '')
                if contexto:
                    md.append("**Contextualização**:")
                    md.append("")
                    md.append(contexto)
                    md.append("")
                
                desafio = detalhes.get('desafio', '')
                if desafio:
                    md.append("**Desafio**:")
                    md.append("")
                    md.append(desafio)
                    md.append("")
                
                resultados = detalhes.get('resultados_esperados', '')
                if resultados:
                    md.append("**Resultados Esperados**:")
                    md.append("")
                    md.append(resultados)
                    md.append("")
        
        # Critérios de Avaliação
        criterios = sa.get('criterios_avaliacao', {})
        
        # Critérios Dicotômicos - TABELA
        dicotomicos = criterios.get('dicotomicos', [])
        if dicotomicos:
            md.append("### Critérios de Avaliação - Dicotômicos")
            md.append("")
            md.append("| Capacidade | Critérios de Avaliação | Autoavaliação | Avaliação |")
            md.append("|------------|------------------------|---------------|-----------|")
            for dc in dicotomicos:
                cap = dc.get('capacidade', '-')
                criterios_list = dc.get('criterios', [])
                for idx, crit in enumerate(criterios_list):
                    # Primeira linha tem a capacidade, demais linhas deixam vazio
                    cap_cell = cap if idx == 0 else ""
                    md.append(f"| {cap_cell} | {crit} | | |")
            md.append("")
            md.append("*Legenda: S = Atingiu / N = Não Atingiu*")
            md.append("")
        
        # Critérios Graduais - TABELA
        graduais = criterios.get('graduais', [])
        if graduais:
            md.append("### Critérios de Avaliação - Graduais")
            md.append("")
            md.append("| Capacidade | Nível 1 | Nível 2 | Nível 3 | Nível 4 | Nível Alcançado |")
            md.append("|------------|---------|---------|---------|---------|-----------------|")
            for gr in graduais:
                cap = gr.get('capacidade', '-')
                niveis = gr.get('niveis', {})
                n1 = niveis.get('nivel_1', '-')
                n2 = niveis.get('nivel_2', '-')
                n3 = niveis.get('nivel_3', '-')
                n4 = niveis.get('nivel_4', '-')
                md.append(f"| {cap} | {n1} | {n2} | {n3} | {n4} | |")
            md.append("")
            md.append("*Legenda dos Níveis:*")
            md.append("- *Nível 1: Desempenho autônomo* - apresenta desempenho esperado da competência com autonomia, sem intervenções do docente.")
            md.append("- *Nível 2: Desempenho parcialmente autônomo* - apresenta desempenho esperado da competência, com intervenções pontuais do docente.")
            md.append("- *Nível 3: Desempenho apoiado* - ainda não apresenta desempenho esperado da competência, exigindo intervenções constantes do docente.")
            md.append("- *Nível 4: Desempenho não satisfatório* - ainda não apresenta desempenho esperado da competência, mesmo com intervenções constantes do docente.")
            md.append("")
        
        # Plano de Aula - TABELA
        plano_aula = sa.get('plano_de_aula', [])
        if plano_aula:
            md.append("### Plano de Aula")
            md.append("")
            md.append("| Horas/Aulas/Data | Capacidades | Conhecimentos | Estratégias | Recursos/Ambientes | Critérios de Avaliação | Instrumento de Avaliação | Referências |")
            md.append("|------------------|-------------|---------------|-------------|--------------------|-----------------------|-------------------------|-------------|")
            for aula in plano_aula:
                horas = aula.get('horas_aulas_data', '-').replace('\n', ' ')
                caps = aula.get('capacidades', '-').replace('\n', ' / ')
                conhec = aula.get('conhecimentos', '-').replace('\n', ' / ')
                estrat = aula.get('estrategias', '-').replace('\n', ' / ')
                recursos = aula.get('recursos_ambientes', '-').replace('\n', ' / ')
                crit_av = aula.get('criterios_avaliacao', '-').replace('\n', ' / ')
                instr = aula.get('instrumento_avaliacao', '-').replace('\n', ' / ')
                refs = aula.get('referencias', '-').replace('\n', ' / ')
                md.append(f"| {horas} | {caps} | {conhec} | {estrat} | {recursos} | {crit_av} | {instr} | {refs} |")
            md.append("")
        
        # Perguntas Mediadoras
        perguntas = sa.get('perguntas_mediadoras', [])
        if perguntas:
            md.append("### Perguntas Mediadoras")
            md.append("")
            for idx, pergunta in enumerate(perguntas, 1):
                md.append(f"{idx}. {pergunta}")
            md.append("")
    
    return "\n".join(md)