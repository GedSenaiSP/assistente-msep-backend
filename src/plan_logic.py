import logging
from typing import List, Optional

logger = logging.getLogger(__name__)

# --- Seus Modelos de Prompt (Adaptados do seu src/prompts.py e discussões) ---
modeloPlanoDeEnsinoSP = """
# Plano de Ensino MSEP - Estratégia: Situação-Problema

## 1. IDENTIFICAÇÃO
- **Unidade Curricular:** {{params.uc}}
- **Curso:** {{params.curso}}
- **Turma:** (A ser preenchido)
- **Carga Horária da UC:** (A ser preenchido com base no documento original)
- **Docente:** {{params.docente}}
- **Unidade Operacional:** {{params.unidade}}

## 2. COMPETÊNCIAS E CAPACIDADES
### 2.1. Competência(s) da UC (Conforme Plano de Curso Original):
(Extrair e listar do CONTEÚDO DO DOCUMENTO ORIGINAL)

### 2.2. Capacidades a Serem Desenvolvidas:
#### Capacidades Técnicas/Básicas:
{{#each params.capacidadesTecnicas}}
- {{this}}
{{/each}}
{{#if (not params.capacidadesTecnicas)}}
- (A serem detalhadas pela IA com base no CONTEÚDO DO DOCUMENTO ORIGINAL e na Situação de Aprendizagem)
{{/if}}

#### Capacidades Socioemocionais:
{{#each params.capacidadesSocioemocionais}}
- {{this}}
{{/each}}
{{#if (not params.capacidadesSocioemocionais)}}
- (A serem detalhadas pela IA com base no CONTEÚDO DO DOCUMENTO ORIGINAL e na Situação de Aprendizagem)
{{/if}}

## 3. SITUAÇÃO DE APRENDIZAGEM (SA)
### 3.1. Título da SA:
(Criar um título pertinente{{#if params.tematica}} ao tema "{{params.tematica}}"{{/if}})

### 3.2. Descrição da SA (Desafio):
(Desenvolver uma descrição detalhada da Situação de Aprendizagem, contextualizada com o CONTEÚDO DO DOCUMENTO ORIGINAL e o tema gerador, se houver. Deve ser um desafio claro para os alunos.)

### 3.3. Produtos/Entregas da SA:
(Listar os produtos ou entregas esperados dos alunos ao final da SA.)

### 3.4. Conhecimentos, Habilidades e Atitudes Mobilizados na SA:
(Detalhar com base no CONTEÚDO DO DOCUMENTO ORIGINAL e na SA descrita)
- **Conhecimentos:**
  - ...
- **Habilidades:**
  - ...
- **Atitudes:**
  - ...

## 4. ESTRATÉGIAS DE ENSINO-APRENDIZAGEM E RECURSOS
(Descrever as estratégias e recursos a serem utilizados durante a SA)
- Aulas expositivas e dialogadas
- Pesquisas orientadas
- Trabalho em equipe
- Uso de laboratórios/oficinas (especificar quais, se aplicável, baseado no CONTEÚDO DO DOCUMENTO ORIGINAL)
- Materiais de referência (livros, artigos, manuais, vídeos - citar exemplos baseados no CONTEÚDO DO DOCUMENTO ORIGINAL)
- Ferramentas e softwares (especificar quais, se aplicável)
""" # Adicione os modelos para EC, P, PA de forma similar

modeloPlanoDeEnsinoEC = """
# Plano de Ensino MSEP - Estratégia: Estudo de Caso
## 1. IDENTIFICAÇÃO
... (similar ao SP)
## 2. COMPETÊNCIAS E CAPACIDADES
... (similar ao SP)
## 3. ESTUDO DE CASO (EC)
### 3.1. Título do EC:
...
### 3.2. Descrição do Caso:
...
### 3.3. Questões Norteadoras para Análise do Caso:
...
### 3.4. Conhecimentos, Habilidades e Atitudes Mobilizados no EC:
...
## 4. ESTRATÉGIAS DE ENSINO-APRENDIZAGEM E RECURSOS
...
"""

modeloPlanoDeEnsinoP = """
# Plano de Ensino MSEP - Estratégia: Projetos
## 1. IDENTIFICAÇÃO
...
## 2. COMPETÊNCIAS E CAPACIDADES
...
## 3. PROJETO INTEGRADOR/DISCIPLINAR
### 3.1. Título do Projeto:
...
### 3.2. Justificativa e Problema a ser Resolvido:
...
### 3.3. Objetivos do Projeto (Geral e Específicos):
...
### 3.4. Etapas e Cronograma Previsto:
...
### 3.5. Produtos/Entregas do Projeto:
...
### 3.6. Conhecimentos, Habilidades e Atitudes Mobilizados no Projeto:
...
## 4. ESTRATÉGIAS DE ENSINO-APRENDIZAGEM E RECURSOS
...
"""

modeloPlanoDeEnsinoPA = """
# Plano de Ensino MSEP - Estratégia: Pesquisa Aplicada
## 1. IDENTIFICAÇÃO
...
## 2. COMPETÊNCIAS E CAPACIDADES
...
## 3. PESQUISA APLICADA
### 3.1. Tema/Problema da Pesquisa:
...
### 3.2. Justificativa e Relevância:
...
### 3.3. Objetivos da Pesquisa (Geral e Específicos):
...
### 3.4. Metodologia da Pesquisa:
...
### 3.5. Cronograma Previsto:
...
### 3.6. Resultados Esperados/Formato de Apresentação:
...
### 3.7. Conhecimentos, Habilidades e Atitudes Mobilizados na Pesquisa:
...
## 4. ESTRATÉGIAS DE ENSINO-APRENDIZAGEM E RECURSOS
...
"""

modeloPlanoDeEnsinoPI = """
# Plano de Ensino MSEP - Estratégia: Projeto Integrador

## 1. IDENTIFICAÇÃO
- **Unidades Curriculares Integradas:** {{params.ucs_integradas}}
- **Curso:** {{params.curso}}
- **Turma:** (A ser preenchido)
- **Carga Horária Total do PI:** (Somar as cargas horárias das UCs envolvidas ou definir especificamente)
- **Docente(s) Responsável(is):** {{params.docente}}
- **Unidade Operacional:** {{params.unidade}}

## 2. COMPETÊNCIAS E CAPACIDADES (POR UNIDADE CURRICULAR)
(Para cada UC integrada, listar as capacidades que serão desenvolvidas)

{{#each params.ucs}}
### 2.{{@index+1}}. UC: {{this.nomeUC}}
**Capacidades Técnicas/Básicas:**
{{#each this.capacidades_tecnicas}}
- {{this}}
{{/each}}

**Capacidades Socioemocionais:**
{{#each this.capacidades_socioemocionais}}
- {{this}}
{{/each}}
{{/each}}

## 3. PROJETO INTEGRADOR (PI)
### 3.1. Título do Projeto Integrador:
(Criar um título que reflita a natureza interdisciplinar, envolvendo as múltiplas UCs)

### 3.2. Justificativa da Integração:
(Explicar por que essas UCs estão sendo integradas e como seus conteúdos se complementam no contexto profissional)

### 3.3. Contexto Interdisciplinar e Desafio:
(Apresentar um cenário real ou simulado que exija conhecimentos e habilidades de TODAS as UCs envolvidas. O desafio deve ser complexo o suficiente para justificar a integração.)

### 3.4. Objetivo Geral do Projeto Integrador:
(Descrever o objetivo demonstrando como as diferentes UCs contribuem para um resultado comum)

### 3.5. Etapas e Cronograma Previsto:
(Dividir o projeto em etapas, indicando quais UCs são mais relevantes em cada fase)

### 3.6. Produtos/Entregas do Projeto Integrador:
(Descrever os produtos que evidenciem a integração dos conhecimentos de todas as UCs)

### 3.7. Conhecimentos, Habilidades e Atitudes Mobilizados no PI:
(Detalhar, integrando os conhecimentos das múltiplas UCs)

## 4. ESTRATÉGIAS DE ENSINO-APRENDIZAGEM E RECURSOS
(Descrever estratégias que promovam a integração das áreas)
- Aulas integradas com participação de docentes das diferentes UCs (se aplicável)
- Trabalho em equipe multidisciplinar
- Pesquisas que conectem as áreas de conhecimento
- Uso de laboratórios/oficinas de múltiplas áreas
- Materiais de referência interdisciplinares
"""

modeloAvaliacaoAtual = """
## 5. CRITÉRIOS DE AVALIAÇÃO
### 5.1. Indicadores de Desempenho:
(Listar os indicadores observáveis que demonstram o desenvolvimento das capacidades)
- Indicador 1 (relacionado à capacidade X)
- Indicador 2 (relacionado à capacidade Y)

### 5.2. Técnicas e Instrumentos de Avaliação:
(Descrever como e com quais instrumentos os indicadores serão avaliados. Ex: Observação direta em atividades práticas, Análise de portfólio, Prova prática simulada, Apresentação de projeto, Autoavaliação, Avaliação por pares, etc.)
- Técnica 1: (Instrumento A, Instrumento B)
- Técnica 2: (Instrumento C)

### 5.3. Momentos da Avaliação:
(Diagnóstica, Formativa, Somativa - descrever brevemente quando ocorrerão)
"""

modeloPlanoAulaAtual = """
## 6. PLANO DE AULA (SEQUÊNCIA DIDÁTICA DETALHADA)
| Encontro (Aula) | Data Prevista | Duração (h) | Conteúdos/Atividades Chave (Passo a Passo)                            | Recursos Didáticos Específicos | Observações/Ajustes Realizados |
|-----------------|---------------|-------------|-----------------------------------------------------------------------|--------------------------------|--------------------------------|
| 1               | (dd/mm/aaaa)  | (ex: 4h)    | 1. Apresentação da UC e da Situação de Aprendizagem/Projeto...        | Projetor, Slides, Documento da SA |                                |
|                 |               |             | 2. Formação de equipes...                                             |                                |                                |
| 2               | (dd/mm/aaaa)  | (ex: 4h)    | 1. Pesquisa orientada sobre o tema X (Conhecimento A)...              | Computadores com internet, links |                                |
| ...             | ...           | ...         | ...                                                                   | ...                            | ...                            |
| Último Encontro | (dd/mm/aaaa)  | (ex: 4h)    | 1. Apresentação final dos projetos/soluções...                        |                                |                                |
|                 |               |             | 2. Feedback e encerramento.                                           |                                |                                |

## 7. PERGUNTAS MEDIADORAS CHAVE
(Listar perguntas que o docente usará para estimular a reflexão, a resolução de problemas e a construção do conhecimento pelos alunos durante as aulas e atividades)
- Como podemos aplicar o conhecimento X para resolver o desafio Y da Situação de Aprendizagem?
- Quais são as principais dificuldades encontradas e como podemos superá-las em equipe?
- De que forma as capacidades socioemocionais Z contribuíram para o desenvolvimento do projeto?
- ...
"""

# Classe auxiliar para tipagem dos parâmetros dentro da função de formatação
class MockPlanParams:
    uc: str
    curso: str
    estrategia: str
    unidade: str # Corresponde a  'escola' no PlanGenerationBody
    docente: str
    capacidadesTecnicas: List[str]
    capacidadesSocioemocionais: List[str]
    tematica: Optional[str]

def format_initial_prompt_for_plan(params: MockPlanParams, original_markdown_content: str) -> str:
    """
    Formata o prompt inicial para a geração das seções 1-4 do plano de ensino,
    incluindo a Situação de Aprendizagem/Estudo de Caso/Projeto/Pesquisa Aplicada.
    """
    # Monta as strings de capacidades
    capacidadesTecnicas_str = ""
    if params.capacidadesTecnicas:
        capacidadesTecnicas_str = "\n".join([f"- {cap}" for cap in params.capacidadesTecnicas])
    else:
        capacidadesTecnicas_str = "- (A serem detalhadas pela IA com base no CONTEÚDO DO DOCUMENTO ORIGINAL e na Situação de Aprendizagem)"

    capacidadesSocioemocionais_str = ""
    if params.capacidadesSocioemocionais:
        capacidadesSocioemocionais_str = "\n".join([f"- {cap}" for cap in params.capacidadesSocioemocionais])
    else:
        capacidadesSocioemocionais_str = "- (A serem detalhadas pela IA com base no CONTEÚDO DO DOCUMENTO ORIGINAL e na Situação de Aprendizagem)"

    # Prompt base comum
    base_instruction = (
        f"Você é um especialista em desenvolvimento de Planos de Ensino seguindo a Metodologia SENAI de Educação Profissional (MSEP).\n"
        f"Sua tarefa é elaborar as seções iniciais (até a seção 4 inclusive) de um Plano de Ensino para a Unidade Curricular (UC) \"{params.uc}\" do curso \"{params.curso}\".\n"
        f"A ESTRATÉGIA DE APRENDIZAGEM designada é: \"{params.estrategia}\".\n"
        f"Informações adicionais: Docente: {params.docente}; Unidade Operacional: {params.unidade}.\n"
        f"As capacidades técnicas/básicas a serem consideradas são:\n{capacidadesTecnicas_str}\n"
        f"As capacidades socioemocionais a serem consideradas são:\n{capacidadesSocioemocionais_str}\n"
        f"O plano deve seguir RIGOROSAMENTE o modelo de template fornecido abaixo para a estratégia \"{params.estrategia}\".\n"
        f"É IMPERATIVO que você utilize o \"CONTEÚDO DO DOCUMENTO ORIGINAL\" (fornecido ao final) como a principal fonte de informação para:\n"
        f"  - Detalhar os conhecimentos, habilidades e atitudes a serem mobilizados.\n"
        f"  - Identificar as competências da UC conforme o plano de curso original (se presentes no documento).\n"
        f"  - Desenvolver a Situação de Aprendizagem (ou Estudo de Caso, Projeto, Pesquisa Aplicada) de forma rica, detalhada e contextualizada com o conteúdo do documento.\n"
        f"Não adicione seções ou itens não explicitamente solicitados no modelo. Se encontrar termos no documento original que pareçam ofensivos ou inseguros, mas são parte do jargão técnico da UC, mantenha-os no contexto apropriado do plano.\n"
    )

    if params.estrategia == "Situação-Problema" and params.tematica:
         base_instruction += f"Para a Situação de Aprendizagem, utilize o seguinte tema gerador como inspiração: \"{params.tematica}\".\n"
    
    # Seleciona o template da estratégia
    strategy_template_content = ""
    if params.estrategia == "Situação-Problema":
        strategy_template_content = modeloPlanoDeEnsinoSP
    elif params.estrategia == "Estudo de Caso":
        strategy_template_content = modeloPlanoDeEnsinoEC
    elif params.estrategia == "Projetos":
        strategy_template_content = modeloPlanoDeEnsinoP
    elif params.estrategia == "Pesquisa Aplicada":
        strategy_template_content = modeloPlanoDeEnsinoPA
    elif params.estrategia == "Projeto Integrador":
        strategy_template_content = modeloPlanoDeEnsinoPI
    else:
        logger.error(f"Template de estratégia não encontrado para: {params.estrategia}")
        return f"ERRO INTERNO: Template para a estratégia '{params.estrategia}' não foi encontrado."

    # Substitui os placeholders no template da estratégia (exemplo simples, pode usar Jinja2 para mais complexidade)
    # Por enquanto, vamos assumir que os placeholders {{params.uc}}, etc. no template são suficientes
    # e o LLM fará as substituições baseado no contexto, ou o template em si já é o "modelo" final.
    # Se os templates tiverem placeholders como {{params.uc}}, eles precisam ser processados aqui.
    # Para este exemplo, vou assumir que os templates são mais "descritivos" para o LLM preencher.
    
    # Renderiza os placeholders nos templates
    # (Usando substituição simples para este exemplo. Jinja2 seria mais robusto)
    processed_strategy_template = strategy_template_content.replace("{{params.uc}}", params.uc) \
                                                        .replace("{{params.curso}}", params.curso) \
                                                        .replace("{{params.docente}}", params.docente) \
                                                        .replace("{{params.unidade}}", params.unidade) \
                                                        .replace("{{#each params.capacidadesTecnicas}}...{{/each}}", capacidadesTecnicas_str) \
                                                        .replace("{{#if (not params.capacidadesTecnicas)}}...{{/if}}", "" if params.capacidadesTecnicas else capacidadesTecnicas_str) \
                                                        .replace("{{#each params.capacidadesSocioemocionais}}...{{/each}}", capacidadesSocioemocionais_str) \
                                                        .replace("{{#if (not params.capacidadesSocioemocionais)}}...{{/if}}", "" if params.capacidadesSocioemocionais else capacidadesSocioemocionais_str)
    if params.tematica:
        processed_strategy_template = processed_strategy_template.replace('{{#if params.tematica}} ao tema "{{params.tematica}}"{{/if}}', f' ao tema "{params.tematica}"')
    else:
        processed_strategy_template = processed_strategy_template.replace('{{#if params.tematica}} ao tema "{{params.tematica}}"{{/if}}', "")


    final_prompt = (
        f"{base_instruction}\n"
        f"MODELO DA ESTRATÉGIA \"{params.estrategia}\" (PREENCHA AS SEÇÕES ATÉ A 4 INCLUSIVE):\n"
        f"{processed_strategy_template}\n\n" # O template já contém os campos para as seções 1 a 4
        f"--- CONTEÚDO DO DOCUMENTO ORIGINAL (USE PARA SE BASEAR E DETALHAR O PLANO) ---\n"
        f"{original_markdown_content}"
    )
    return final_prompt