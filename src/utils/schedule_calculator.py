"""
Módulo para cálculo de cronograma de aulas.

Este módulo calcula as datas específicas das aulas baseado em:
- Data de início e fim do período letivo
- Dias da semana e horários das aulas
- Carga horária total da Situação de Aprendizagem
"""

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

# Mapeamento dos dias da semana em português para número (0 = segunda, 6 = domingo)
DIAS_SEMANA_MAP = {
    "segunda-feira": 0,
    "terça-feira": 1,
    "terca-feira": 1,  # Sem acento
    "quarta-feira": 2,
    "quinta-feira": 3,
    "sexta-feira": 4,
    "sábado": 5,
    "sabado": 5,  # Sem acento
    "domingo": 6,
}

# Mapeamento reverso para exibição
DIAS_SEMANA_DISPLAY = {
    0: "Segunda-feira",
    1: "Terça-feira",
    2: "Quarta-feira",
    3: "Quinta-feira",
    4: "Sexta-feira",
    5: "Sábado",
    6: "Domingo",
}


def parse_time(time_str: str) -> tuple:
    """
    Converte string de hora (HH:MM) para tupla (hour, minute).
    
    Args:
        time_str: String no formato "HH:MM"
        
    Returns:
        Tupla (hora, minuto)
    """
    try:
        parts = time_str.split(":")
        return int(parts[0]), int(parts[1])
    except (ValueError, IndexError):
        logger.warning(f"Formato de hora inválido: {time_str}. Usando 00:00.")
        return 0, 0


def calcular_duracao_bloco(hora_inicio: str, hora_fim: str) -> float:
    """
    Calcula a duração em horas de um bloco de aula.
    
    Args:
        hora_inicio: Horário de início no formato "HH:MM"
        hora_fim: Horário de término no formato "HH:MM"
        
    Returns:
        Duração em horas (float)
    """
    h_ini, m_ini = parse_time(hora_inicio)
    h_fim, m_fim = parse_time(hora_fim)
    
    inicio_minutos = h_ini * 60 + m_ini
    fim_minutos = h_fim * 60 + m_fim
    
    duracao_minutos = fim_minutos - inicio_minutos
    
    if duracao_minutos <= 0:
        logger.warning(f"Duração inválida: {hora_inicio} a {hora_fim}. Assumindo 1h.")
        return 1.0
    
    return duracao_minutos / 60.0


def calcular_horas_semanais(horarios: List[Dict[str, str]]) -> float:
    """
    Calcula o total de horas de aula por semana.
    
    Args:
        horarios: Lista de dicionários com 'dia', 'horaInicio', 'horaFim'
        
    Returns:
        Total de horas por semana
    """
    total = 0.0
    for horario in horarios:
        duracao = calcular_duracao_bloco(
            horario.get("horaInicio", "00:00"),
            horario.get("horaFim", "00:00")
        )
        total += duracao
    return total


def get_dia_semana_numero(dia_str: str) -> int:
    """
    Converte nome do dia da semana para número (0-6).
    
    Args:
        dia_str: Nome do dia em português (ex: "Segunda-feira")
        
    Returns:
        Número do dia (0 = segunda, 6 = domingo) ou -1 se inválido
    """
    dia_normalizado = dia_str.lower().strip()
    return DIAS_SEMANA_MAP.get(dia_normalizado, -1)


def gerar_cronograma_aulas(
    data_inicio: str,
    data_fim: str,
    horarios: List[Dict[str, str]],
    carga_horaria_sa: float
) -> List[Dict[str, Any]]:
    """
    Gera a lista completa de aulas com datas específicas.
    
    Args:
        data_inicio: Data de início no formato "YYYY-MM-DD"
        data_fim: Data de término no formato "YYYY-MM-DD"
        horarios: Lista de horários semanais disponíveis
        carga_horaria_sa: Carga horária total da Situação de Aprendizagem em horas
        
    Returns:
        Lista de dicionários com informações de cada aula:
        - data: Data no formato "DD/MM/YYYY"
        - dia_semana: Nome do dia da semana
        - hora_inicio: Horário de início
        - hora_fim: Horário de término
        - duracao: Duração em horas
    """
    if not horarios:
        logger.warning("Nenhum horário fornecido. Retornando lista vazia.")
        return []
    
    if carga_horaria_sa <= 0:
        logger.warning(f"Carga horária inválida: {carga_horaria_sa}. Usando 20h como padrão.")
        carga_horaria_sa = 20.0
    
    try:
        dt_inicio = datetime.strptime(data_inicio, "%Y-%m-%d")
        dt_fim = datetime.strptime(data_fim, "%Y-%m-%d")
    except ValueError as e:
        logger.error(f"Erro ao parsear datas: {e}")
        return []
    
    if dt_fim < dt_inicio:
        logger.warning("Data final anterior à data inicial. Invertendo datas.")
        dt_inicio, dt_fim = dt_fim, dt_inicio
    
    # Preparar lista de slots semanais ordenados por dia da semana
    slots_semanais = []
    for horario in horarios:
        dia_num = get_dia_semana_numero(horario.get("dia", ""))
        if dia_num >= 0:
            slots_semanais.append({
                "dia_num": dia_num,
                "dia_nome": DIAS_SEMANA_DISPLAY.get(dia_num, horario.get("dia", "")),
                "hora_inicio": horario.get("horaInicio", "08:00"),
                "hora_fim": horario.get("horaFim", "09:00"),
                "duracao": calcular_duracao_bloco(
                    horario.get("horaInicio", "08:00"),
                    horario.get("horaFim", "09:00")
                )
            })
    
    if not slots_semanais:
        logger.warning("Nenhum dia de aula válido encontrado nos horários.")
        return []
    
    # Ordenar por dia da semana
    slots_semanais.sort(key=lambda x: x["dia_num"])
    
    # Gerar cronograma
    cronograma = []
    horas_acumuladas = 0.0
    data_atual = dt_inicio
    
    # Limitar para evitar loop infinito (máximo de 365 dias)
    max_iteracoes = 365
    iteracao = 0
    
    while horas_acumuladas < carga_horaria_sa and data_atual <= dt_fim and iteracao < max_iteracoes:
        dia_semana_atual = data_atual.weekday()  # 0 = segunda
        
        # Verificar se há aula neste dia
        for slot in slots_semanais:
            if slot["dia_num"] == dia_semana_atual:
                # Adicionar aula
                aula = {
                    "data": data_atual.strftime("%d/%m/%Y"),
                    "dia_semana": slot["dia_nome"],
                    "hora_inicio": slot["hora_inicio"],
                    "hora_fim": slot["hora_fim"],
                    "duracao": slot["duracao"]
                }
                cronograma.append(aula)
                horas_acumuladas += slot["duracao"]
                
                if horas_acumuladas >= carga_horaria_sa:
                    break
        
        # Próximo dia
        data_atual += timedelta(days=1)
        iteracao += 1
    
    # Se não conseguiu preencher toda a carga horária dentro do período
    if horas_acumuladas < carga_horaria_sa:
        logger.warning(
            f"Período insuficiente para carga horária. "
            f"Necessário: {carga_horaria_sa}h, Disponível: {horas_acumuladas}h. "
            f"Continuando além da data fim."
        )
        
        # Continuar gerando até completar a carga horária
        while horas_acumuladas < carga_horaria_sa and iteracao < max_iteracoes:
            dia_semana_atual = data_atual.weekday()
            
            for slot in slots_semanais:
                if slot["dia_num"] == dia_semana_atual:
                    aula = {
                        "data": data_atual.strftime("%d/%m/%Y"),
                        "dia_semana": slot["dia_nome"],
                        "hora_inicio": slot["hora_inicio"],
                        "hora_fim": slot["hora_fim"],
                        "duracao": slot["duracao"]
                    }
                    cronograma.append(aula)
                    horas_acumuladas += slot["duracao"]
                    
                    if horas_acumuladas >= carga_horaria_sa:
                        break
            
            data_atual += timedelta(days=1)
            iteracao += 1
    
    logger.info(
        f"Cronograma gerado: {len(cronograma)} aulas, "
        f"{horas_acumuladas}h de {carga_horaria_sa}h planejadas"
    )
    
    return cronograma

def formatar_duracao(horas: float) -> str:
    """
    Formata duração em horas para string 'Xh' ou 'Xh Ymin'.
    Ex: 2.0 -> "2h", 2.5 -> "2h 30min", 0.5 -> "30min"
    """
    if horas == int(horas):
        return f"{int(horas)}h"
    
    h = int(horas)
    m = int(round((horas - h) * 60))
    
    if h == 0:
        return f"{m}min"
    return f"{h}h {m}min"


def formatar_cronograma_para_prompt(cronograma: List[Dict[str, Any]]) -> str:
    """
    Formata o cronograma calculado para inclusão no prompt do LLM.
    
    Args:
        cronograma: Lista de aulas gerada por gerar_cronograma_aulas
        
    Returns:
        String formatada para o prompt
    """
    if not cronograma:
        return "Nenhuma aula calculada. O plano de aula deve ser genérico."
    
    linhas = []
    for i, aula in enumerate(cronograma, 1):
        linhas.append(
            f"- Aula {i}: {aula['data']} ({aula['dia_semana']}) "
            f"das {aula['hora_inicio']} às {aula['hora_fim']} ({formatar_duracao(aula['duracao'])})"
        )
    
    return "\n".join(linhas)
