import logging
import os
from langchain_openai import AzureChatOpenAI
# Import your prompt templates (or define them here/load from another file)
from .prompts import modeloPlanoDeEnsinoSP, modeloPlanoDeEnsinoEC, modeloPlanoDeEnsinoP, modeloPlanoDeEnsinoPA, modeloPlanoDeEnsinoPI, modeloAvaliacaoAtual, modeloPlanoAulaAtual # Assuming you move prompts here
from models.models import PlanGenerationBody

logger = logging.getLogger(__name__)

# You can pass the initialized LLM or initialize one here
# Make sure it's configured appropriately (temp, tokens etc.)
# llm = AzureChatOpenAI(...) # If initializing here

# Helper to format the initial prompt
def format_initial_prompt(params: PlanGenerationBody):
    capacidadesTecnicas_str = ", ".join(params.capacidadesTecnicas) if params.capacidadesTecnicas else "a critério da IA"
    capacidadesSocioemocionais_str = ", ".join(params.capacidadesSocioemocionais) if params.capacidadesSocioemocionais else "a critério da IA"

    # Base prompt common to all strategies
    base_prompt = (
        f"Elabore um plano de ensino da unidade curricular {params.uc}, do curso {params.curso}, "
        f"utilizando a estratégia de aprendizagem de {params.estrategia}, com base na Metodologia "
        f"SENAI de Educação Profissional (MSEP). Siga o modelo abaixo, sem nenhuma "
        f"modificação ou adição de item não solicitado e contendo somente os campos "
        f"que é solicitado. Usar a MSEP apenas para entender como criar o plano de "
        f"ensino, mas obedecer o modelo dado. O nome da escola é {params.unidade}. O nome do "
        f"docente é {params.docente}. Considere as capacidades técnicas/básicas sendo "
        f"{capacidadesTecnicas_str}. Considere as capacidades socioemocionais sendo "
        f"{capacidadesSocioemocionais_str}. Algumas palavras ou termos são inerentes a "
        f"unidade curricular e podem soar ofensivas ou inseguras, mas desconsidere e siga em frente."
    )
    # Add theme if relevant for the strategy
    if params.estrategia == "Situação-Problema" and params.tematica:
         base_prompt += f"\nPara elaborar a situação de aprendizagem, considere o tema sugerido: {params.tematica}"
    # Add more conditions if other strategies use 'tematica' or similar fields

    # Append the specific strategy template
    if params.estrategia == "Situação-Problema":
        strategy_template = modeloPlanoDeEnsinoSP
    elif params.estrategia == "Estudo de Caso":
        strategy_template = modeloPlanoDeEnsinoEC
    elif params.estrategia == "Projetos":
        strategy_template = modeloPlanoDeEnsinoP
    elif params.estrategia == "Pesquisa Aplicada":
        strategy_template = modeloPlanoDeEnsinoPA
    elif params.estrategia in ["Projeto Integrador", "projeto-integrador"]:
        strategy_template = modeloPlanoDeEnsinoPI
    else:
        raise ValueError(f"Estratégia desconhecida: {params.estrategia}")

    return base_prompt + "\n\n" + strategy_template

async def generate_teaching_plan(params: PlanGenerationBody, llm: AzureChatOpenAI) -> tuple[str, "TokenUsage"]:
    """
    Generates the full teaching plan by calling the LLM sequentially for each section.
    Returns a tuple of (plan_markdown, token_usage) to allow caller to save tokens.
    """
    # Import here to avoid circular imports
    from src.utils.token_tracker import TokenUsage, extract_tokens
    
    logger.info(f"Iniciando geração do plano para UC: {params.uc}, Estratégia: {params.estrategia}")
    full_plan_md = ""
    generated_context_for_followups = "" # Store parts needed for subsequent prompts
    total_tokens = TokenUsage()

    try:
        # --- Section 1-4: Initial Plan Structure based on Strategy ---
        initial_prompt = format_initial_prompt(params)
        logger.debug(f"Prompt Seção 1-4:\n{initial_prompt[:500]}...") # Log beginning
        response_part1 = await llm.ainvoke(initial_prompt)
        total_tokens = total_tokens + extract_tokens(response_part1)
        plan_part1 = response_part1.content
        full_plan_md += plan_part1 + "\n\n"
        generated_context_for_followups += plan_part1 # Pass this context if needed

        logger.info("Seção 1-4 (Estrutura inicial) gerada.")

        # --- Section 5: Critérios de Avaliação ---
        # Context might be needed from part 1 (the generated SA/EC/P/PA)
        prompt_part2 = f"""Com base na situação de aprendizagem/estudo de caso/projeto/pesquisa aplicada descrita abaixo:
        {plan_part1}

        Elabore somente o item 5. Critérios de Avaliação de acordo com o modelo a seguir. Não preciso do restante, somente o item 5.
        {modeloAvaliacaoAtual}""" # Passar o contexto gerado anteriormente se necessário
        logger.debug(f"Prompt Seção 5:\n{prompt_part2[:500]}...")
        response_part2 = await llm.ainvoke(prompt_part2)
        total_tokens = total_tokens + extract_tokens(response_part2)
        plan_part2 = response_part2.content
        full_plan_md += plan_part2 + "\n\n"
        generated_context_for_followups += "\n\n" + plan_part2 # Update context

        logger.info("Seção 5 (Avaliação) gerada.")

        # --- Section 6: Plano de Aula ---
        # Context needed from previous parts
        prompt_part3 = f"""Com base na situação de aprendizagem e nos critérios de avaliação descritos abaixo:
        {generated_context_for_followups}

        Elabore somente o item 6. Plano de Aula de acordo com o modelo a seguir. Não preciso do restante, somente o item 6.
        {modeloPlanoAulaAtual}"""
        logger.debug(f"Prompt Seção 6:\n{prompt_part3[:500]}...")
        response_part3 = await llm.ainvoke(prompt_part3)
        total_tokens = total_tokens + extract_tokens(response_part3)
        plan_part3 = response_part3.content
        full_plan_md += plan_part3 + "\n\n"
        generated_context_for_followups += "\n\n" + plan_part3 # Update context

        logger.info("Seção 6 (Plano de Aula) gerada.")

        # --- Section 7: Perguntas Mediadoras (Assuming it's part of the last prompt in Streamlit version) ---
        # Modify prompt_part3 if Perguntas Mediadoras was a separate step
        # If it was part of the Plano de Aula prompt (like in your streamlit code where only 3 main calls seem to happen),
        # it should be included in plan_part3 already.
        # If it needs a separate call:
        # prompt_part4 = f"""Com base no plano de ensino completo gerado até agora:
        # {full_plan_md}
        #
        # Elabore somente o item 7. Perguntas Mediadoras de acordo com as diretrizes. Não preciso do restante.
        # [Your prompt description for Perguntas Mediadoras here]"""
        # response_part4 = await llm.ainvoke(prompt_part4)
        # plan_part4 = response_part4.content
        # full_plan_md += plan_part4
        # logger.info("Seção 7 (Perguntas Mediadoras) gerada.")


        logger.info(f"Geração completa do plano finalizada. Tokens usados: {total_tokens.input_tokens} entrada, {total_tokens.output_tokens} saída")
        return full_plan_md.strip(), total_tokens

    except Exception as e:
        logger.error(f"Erro durante a geração do plano: {e}", exc_info=True)
        raise # Re-raise the exception to be caught by the API endpoint