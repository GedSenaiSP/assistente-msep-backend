"""
Testes unitários para o módulo schedule_calculator.

Para rodar os testes:
    cd c:\Users\sn1050759\Desktop\Projetos de Software\Assistente MSEP\Senai DN\backend-assistente
    python -m pytest src/tests/test_schedule_calculator.py -v
"""

import pytest
from datetime import datetime
from src.utils.schedule_calculator import (
    calcular_duracao_bloco,
    calcular_horas_semanais,
    get_dia_semana_numero,
    gerar_cronograma_aulas,
    formatar_cronograma_para_prompt,
)


class TestCalcularDuracaoBloco:
    """Testes para a função calcular_duracao_bloco."""
    
    def test_uma_hora(self):
        """Teste: bloco de 1 hora."""
        assert calcular_duracao_bloco("08:00", "09:00") == 1.0
    
    def test_duas_horas(self):
        """Teste: bloco de 2 horas."""
        assert calcular_duracao_bloco("19:00", "21:00") == 2.0
    
    def test_tres_horas(self):
        """Teste: bloco de 3 horas."""
        assert calcular_duracao_bloco("08:00", "11:00") == 3.0
    
    def test_meia_hora(self):
        """Teste: bloco de 30 minutos."""
        assert calcular_duracao_bloco("10:00", "10:30") == 0.5
    
    def test_uma_hora_e_meia(self):
        """Teste: bloco de 1h30."""
        assert calcular_duracao_bloco("14:00", "15:30") == 1.5


class TestCalcularHorasSemanais:
    """Testes para a função calcular_horas_semanais."""
    
    def test_dois_dias_uma_hora_cada(self):
        """Teste: 2 dias com 1 hora cada = 2 horas semanais."""
        horarios = [
            {"dia": "Segunda-feira", "horaInicio": "08:00", "horaFim": "09:00"},
            {"dia": "Sexta-feira", "horaInicio": "10:00", "horaFim": "11:00"},
        ]
        assert calcular_horas_semanais(horarios) == 2.0
    
    def test_tres_dias_diferentes(self):
        """Teste: 3 dias com diferentes durações."""
        horarios = [
            {"dia": "Segunda-feira", "horaInicio": "08:00", "horaFim": "10:00"},  # 2h
            {"dia": "Quarta-feira", "horaInicio": "14:00", "horaFim": "17:00"},   # 3h
            {"dia": "Sexta-feira", "horaInicio": "08:00", "horaFim": "09:00"},    # 1h
        ]
        assert calcular_horas_semanais(horarios) == 6.0


class TestGetDiaSemanaNumero:
    """Testes para a função get_dia_semana_numero."""
    
    def test_segunda_feira(self):
        assert get_dia_semana_numero("Segunda-feira") == 0
    
    def test_sexta_feira(self):
        assert get_dia_semana_numero("Sexta-feira") == 4
    
    def test_sabado(self):
        assert get_dia_semana_numero("Sábado") == 5
    
    def test_dia_invalido(self):
        assert get_dia_semana_numero("Dia inválido") == -1


class TestGerarCronogramaAulas:
    """Testes para a função gerar_cronograma_aulas."""
    
    def test_cenario_usuario_20h_segunda_sexta(self):
        """
        Cenário proposto pelo usuário:
        - Segunda 08:00-09:00 (1h)
        - Sexta 10:00-11:00 (1h)
        - Carga horária SA: 20h
        - Resultado esperado: 20 linhas na tabela
        """
        horarios = [
            {"dia": "Segunda-feira", "horaInicio": "08:00", "horaFim": "09:00"},
            {"dia": "Sexta-feira", "horaInicio": "10:00", "horaFim": "11:00"},
        ]
        
        # Data início: 13/01/2026 (terça-feira)
        # Primeira aula deve ser na sexta 17/01/2026
        cronograma = gerar_cronograma_aulas(
            data_inicio="2026-01-13",
            data_fim="2026-06-30",
            horarios=horarios,
            carga_horaria_sa=20
        )
        
        # Deve ter exatamente 20 aulas
        assert len(cronograma) == 20
        
        # Verificar que todas as aulas são em segunda ou sexta
        for aula in cronograma:
            assert aula["dia_semana"] in ["Segunda-feira", "Sexta-feira"]
        
        # Verificar que cada aula tem 1h de duração
        for aula in cronograma:
            assert aula["duracao"] == 1.0
    
    def test_primeira_aula_correta_quando_inicio_nao_cai_em_dia_de_aula(self):
        """
        Se o período começa em uma terça-feira e as aulas são segunda e sexta,
        a primeira aula deve ser na sexta, não antes.
        """
        horarios = [
            {"dia": "Segunda-feira", "horaInicio": "08:00", "horaFim": "09:00"},
            {"dia": "Sexta-feira", "horaInicio": "10:00", "horaFim": "11:00"},
        ]
        
        # 13/01/2026 é terça-feira
        cronograma = gerar_cronograma_aulas(
            data_inicio="2026-01-13",
            data_fim="2026-03-31",
            horarios=horarios,
            carga_horaria_sa=4  # Apenas 4h para teste rápido
        )
        
        # Primeira aula: sexta-feira 17/01/2026
        assert cronograma[0]["data"] == "17/01/2026"
        assert cronograma[0]["dia_semana"] == "Sexta-feira"
        
        # Segunda aula: segunda-feira 20/01/2026
        assert cronograma[1]["data"] == "20/01/2026"
        assert cronograma[1]["dia_semana"] == "Segunda-feira"
    
    def test_blocos_maiores(self):
        """Teste com blocos de 4 horas."""
        horarios = [
            {"dia": "Segunda-feira", "horaInicio": "08:00", "horaFim": "12:00"},  # 4h
        ]
        
        cronograma = gerar_cronograma_aulas(
            data_inicio="2026-01-13",
            data_fim="2026-06-30",
            horarios=horarios,
            carga_horaria_sa=20
        )
        
        # 20h dividido por 4h por aula = 5 aulas
        assert len(cronograma) == 5
        
        for aula in cronograma:
            assert aula["duracao"] == 4.0
    
    def test_lista_vazia_sem_horarios(self):
        """Deve retornar lista vazia se nenhum horário é fornecido."""
        cronograma = gerar_cronograma_aulas(
            data_inicio="2026-01-13",
            data_fim="2026-06-30",
            horarios=[],
            carga_horaria_sa=20
        )
        
        assert cronograma == []


class TestFormatarCronogramaParaPrompt:
    """Testes para a função formatar_cronograma_para_prompt."""
    
    def test_formatacao_basica(self):
        """Testa a formatação do cronograma para o prompt."""
        cronograma = [
            {"data": "17/01/2026", "dia_semana": "Sexta-feira", "hora_inicio": "10:00", "hora_fim": "11:00", "duracao": 1.0},
            {"data": "20/01/2026", "dia_semana": "Segunda-feira", "hora_inicio": "08:00", "hora_fim": "09:00", "duracao": 1.0},
        ]
        
        resultado = formatar_cronograma_para_prompt(cronograma)
        
        assert "Aula 1: 17/01/2026 (Sexta-feira)" in resultado
        assert "Aula 2: 20/01/2026 (Segunda-feira)" in resultado
        assert "10:00 às 11:00" in resultado
        assert "08:00 às 09:00" in resultado
    
    def test_lista_vazia(self):
        """Testa retorno para lista vazia."""
        resultado = formatar_cronograma_para_prompt([])
        assert "Nenhuma aula calculada" in resultado


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
