modeloCabecalhoPlanoEnsino="""
# Plano de Ensino segundo a MSEP

## Informações do Curso

**Curso:** [Nome do curso]

**Turma:** [Nome da turma]

**Unidade Curricular (UC):** [Nome da unidade curricular]

**Módulo:** [Básico ou Específico]

**Carga Horária total na UC:** [Carga horária total do curso]

**Objetivo da Unidade Curricular:** [Objetivo geral da unidade curricular de acordo com o plano de curso]

**Modalidade de ensino:** [Presencial, EAD ou Híbrida]

**Professor Titular:** [Nome do professor titular]

**Departamento Regional:** [Departamento Regional]

**Unidade:** [Escola Senai]
"""
modeloItem2CapacidadesSA="""
## Capacidades a serem desenvolvidas:

### Capacidades Básicas [Somente para Módulo Básico]:

[
    -Liste aqui todas as capacidades Básicas que foram passadas para o prompt, escolhidas pelo professor, independente da quantidade.
    -Cada capacidade deve ficar em uma linha separada.
    -Caso não tenha sido passado nenhuma capacidade, escolha no máximo cinco capacidades básicas que são necessárias o desenvolvimento da situação de aprendizagem proposta.
    -Liste somente as capacidades escolhidas e nada mais, respeitado a quantiadade máximo de cinco capacidades, quando escolhidas de forma automática e aleatória.
] 

### Capacidades Técnicas [Somente para Módulo Específico]:

[
    -Liste aqui todas as capacidades Técnicas que foram passadas para o prompt, escolhidas pelo professor, independente da quantidade.
    -Cada capacidade deve ficar em uma linha separada.
    -Caso não tenha sido passado nenhuma capacidade, escolha no máximo cinco técnicas que são necessárias o desenvolvimento da situação de aprendizagem proposta.
    -Liste somente as capacidades escolhidas e nada mais, respeitado a quantiadade máximo de cinco capacidades, quando escolhidas de forma automática e aleatória.
]

### Capacidades Socioemocionais:

[
    -Liste aqui todas as capacidades Socioemocionais que foram passadas para o prompt, escolhidas pelo professor, independente da quantidade.
    -Cada capacidade deve ficar em uma linha separada.
    -Caso não tenha sido passado nenhuma capacidade, escolha no máximo três capacidades socioemocionais que são necessárias para o desenvolvimento da situação de aprendizagem proposta.
    -Liste somente as capacidades escolhidas e nada mais, respeitado a quantiadade máximo de três capacidades, quando escolhidas de forma automática e aleatória.
]

[
    - Nesse campo, precisamos selecionar algumas (não todas) capacidades que serão desenvolvidas na Situação de Aprendizagem (sejam básicas, técnicas e socioemocionais).
    - Ao selecionarmos as capacidades que serão desenvolvidas, precisamos cuidar da gradualidade das capacidades, trabalhando com propostas que contemplem capacidades de menor complexidade para maior complexidade.
    - Importante: não podemos alterar as capacidades previstas no plano de curso.
    - Exemplo: do verbo identificar para o verbo configurar, temos uma diferença grande na complexidade da capacidade preterida.
    - Escolher somente as capacidades que são necessárias para o desenvolvimento da situação de aprendizagem, de acordo com a unidade curricular do plano de curso, se atentando para não escolher todas as capacidades da unidade curricular.
]
"""
modeloItem3ConhecimentosSA="""
## Conhecimentos:

[
    - Crie uma lista numerada e hierárquica.
    - Use indentação (espaços no início da linha) para organizar os subtópicos.
    - Cada tópico e subtópico deve estar em sua própria linha.
    - É muito importante que a lista não tenha todos os conhecimentos da unidade curricular, pois outras situações de aprendizagem podem ser criadas com os conhecimentos não selecionados.
    - Escolher somente os conhecimentos que são necessários para o desenvolvimento da situação de aprendizagem, de acordo com as capacidades escolhidas no item Capacidades a serem desenvolvidas, se atentando para não escolher todos os conhecimentos da unidade curricular em questão.

    Exemplo de formatação correta:
    1. Sistema Gerenciador de Banco de Dados (SGBD)
        1.1. Definição
        1.2. Tipos
            1.2.1. Relacional
            1.2.2. Não relacional
        1.3. Características
    2. Modelo relacional
        2.1. Modelagem
            2.1.1. Dicionário de dados
]
"""

modeloItem4EstrategiaSA_Base="""
## Estratégia de aprendizagem desafiadora: *{estrategia_nome_formatado}*

[
    Indicar o tipo de estratégia de aprendizagem escolhida em itálico
]

**Nº de aulas previstas para desenvolver esta Situação de Aprendizagem:** [Estimar com base na complexidade, carga horária da UC e horários disponíveis. Ex: 10 aulas]\n
**Carga horária prevista para o desenvolvimento desta Situação de Aprendizagem:** [Estimar em horas. Ex: 30 horas]\n

### Título da Situação de Aprendizagem:
[
    - Inserir título da Situação de Aprendizagem, relacionado à unidade curricular selecionada.
    - O título deve ser claro, objetivo e refletir o tema da situação de aprendizagem.
]	

{template_especifico_da_estrategia_aqui}
"""
modeloPlanoDeEnsinoSP="""
[
    Propor uma Situação de Aprendizagem de acordo com as capacidades escolhidas no item Capacidades a serem desenvolvidas e com os conhecimentos escolhidos no item anterior.
    Esse texto não deve conter no plano é apenas a referência de como elaborar a situação de aprendizagem.
]

### Contextualização:

[ 
    - Descrição da contextualização da Situação de Aprendizagem.
    - Nesse campo, a abordagem contextualizada é pensada para construir cenários reais da situação de trabalho que o aluno vai enfrentar. Por isso, é importante que o aluno encontre máquinas, equipamentos, instrumentos, ferramentas, materiais e condições de trabalho bem semelhantes às dos ambientes em que vai atuar.
    - Recomendamos abordar a área tecnológica da empresa, nº de funcionários, perfil do cliente interno (técnico ou gestor), do cliente externo, explanar sobre o tipo de serviço prestado pela empresa, dados atuais versus dados pretendidos com a implementação do trabalho proposto, visando ampliar o repertório do aluno.
    - Para planejarmos a SA(Situação de Aprendizagem), a MSEP sugere que tenhamos respostas para 5 perguntas:
        - O que? Para que? Como? Com o que? Onde?
    - Com as respostas às essas perguntas, precisamos considerar 3 requisitos para o planejamento:
        - Mobilização.
        - Resolução de problemas com tomada de decisão.
        - Máximo de circulação de informações possíveis.
    - Estimulamos as competências de visão sistêmica e de criatividade com a Situação de Aprendizagem?
    - Sugerir a necessidade de inclusão de figuras, esquemas, desenhos, leiaute, formulários, etc, para complementar a sitação de aprendizagem e descrever que imagem deve ser incluída, se for o caso.
]

### Desafio:

[
    - Descrição do desafio proposto na Situação de Aprendizagem.
    - A MSEP recomenda que o desafio da SA precisa ser diferente do que o aluno já realizou, mas isso não significa que precisa ser inédito.
    - Precisa ser fruto de muita reflexão, tomada de decisão, da realização de uma ou mais atividades. Precisamos ficar atentos ao que chamamos de “resposta pronta”.
    - Quando as capacidades e conhecimentos requerem análise de dados, comparação ou correlação de soluções alternativas, como a escola propôs, é interessante abordar na perspectiva do estudo de caso e os alunos precisam trazer soluções de sucesso ou insucesso.
]

### Resultados Esperados:

[
    - Descrição detalhada dos resultados esperados dos alunos.
    - A MSEP nos orienta que, ao redigir a estratégia de aprendizagem desafiadora, o docente deve informar claramente o que espera do aluno como um produto final: relatório, trabalho escrito, projeto, protótipo, produto (bem ou serviço), maquete, softwares, vídeos, manuais, pareceres, leiaute, entre outros. Esses resultados devem ser adequados e proporcionais à contextualização e ao nível de exigência do desafio proposto. (p.138 MSEP)
]

NÃO INCLUIR ESSA SESSÃO NO PLANO DE ENSINO, APENAS PARA USO DO PROMPT
[
    Observações:
    - Utilize a linguagem clara e objetiva.
    - Inclua exemplos e informações relevantes para cada item.
    - Mantenha a coerência entre as diferentes etapas do plano de ensino.
    - Use a MSEP para entender como elaborar cada item solicitado.
    - A contextualização da estratégia de aprendizagem deve ser de acordo com o perfil profissional e trazer situações reais do mundo do trabalho.
    - Esta obeservação é apenas para o prompt, não deve conter no plano de ensino.
]
"""

modeloPlanoDeEnsinoEC="""
### Título do Estudo de Caso:
[
    Insira um título que seja interessante e que reflita o tema do caso.
]

### Contextualização (A Narrativa do Caso):
[
    Descreva uma narrativa completa e detalhada de uma situação real ou fictícia. Apresente a empresa, o setor, os personagens envolvidos e o contexto que levou ao problema. Descreva o problema ou a oportunidade que surgiu. Crucialmente, narre a(s) solução(ões) que foi(ram) implementada(s) pela empresa e os resultados (positivos ou negativos) que se seguiram. O caso deve ser "complexo e polêmico", como define a MSEP, apresentando múltiplos fatores para análise.
]

### O Desafio do Caso (Análise e Proposição):
[
    Defina a missão dos alunos. Com base na narrativa apresentada, o que eles devem fazer? O desafio não é resolver o problema do zero (ele já foi "resolvido" na narrativa), mas sim analisar o caso criticamente. Exemplos de desafios: "Analisar a solução implementada, identificando seus pontos fortes e fracos com base nos conhecimentos da UC.", "Propor uma solução alternativa, justificando por que ela poderia ser mais eficaz.", "Avaliar as implicações éticas, financeiras e operacionais da decisão tomada pela empresa.", "Elaborar um parecer técnico concordando ou discordando da solução adotada no caso, com base em normas e princípios técnicos."[cite: 1594, 1598].
]

### Resultados Esperados:
[
    Liste os produtos concretos que os alunos devem entregar como resultado de sua análise, e não o passo a passo. O resultado deve refletir a conclusão da análise crítica do desafio. Exemplos: Relatório de análise comparativa; Apresentação em grupo defendendo um ponto de vista sobre o caso; Parecer técnico fundamentado; Mapa mental detalhando as causas, ações e consequências do caso.
]

NÃO INCLUIR ESSA SESSÃO NO PLANO DE ENSINO, APENAS PARA USO DO PROMPT
[
    Dicas:
    - Utilize uma linguagem clara e concisa.
    - Apresente a situação de forma envolvente e desafiadora.
    - Mantenha a relevância e a conexão com a realidade profissional.
    - Incentive a criatividade e o pensamento crítico.
    - Esta obeservação é apenas para o prompt, não deve conter no plano de ensino.
]
"""

modeloPlanoDeEnsinoP="""
### Título do Projeto:
[
    Insira o título do projeto, relacionado ao tema da unidade curricular
]

### Objetivo do Projeto:
[
    Descreva o objetivo geral do projeto, alinhado com as capacidades a serem desenvolvidas na unidade curricular.
]

### Público Alvo:
[
    Indique o público-alvo do projeto, considerando o nível de ensino, a experiência profissional dos alunos e as necessidades específicas da turma.
]

### Contexto:
[
    Apresente um cenário real ou fictício, contextualizado com a área de atuação profissional e os desafios que o projeto visa solucionar. A contextualização deve ser relevante para os alunos e despertar o interesse.
]

### Desafio:
[
    Defina o problema ou desafio que o projeto pretende resolver. O desafio deve ser específico, complexo e instigante para os alunos, desafiando-os a mobilizar conhecimentos e habilidades.
]

### Resultados Esperados:
[
    Descreva os resultados tangíveis que se espera alcançar com o projeto. Os resultados devem ser mensuráveis e devem estar diretamente relacionados com as capacidades a serem desenvolvidas.
]

### Etapas do Projeto:
[
    Divida o projeto em etapas com prazos e entregas definidas. Detalhe as atividades a serem realizadas em cada etapa e os recursos necessários.
]

### Possibilidade de aplicação no mundo do trabalho:
[
    Descreva como o projeto pode ser aplicado em situações reais do mundo do trabalho, mostrando a relevância prática da aprendizagem.
]

NÃO INCLUIR ESSA SESSÃO NO PLANO DE ENSINO, APENAS PARA USO DO PROMPT
[
    Observações:
    - O projeto deve ser flexível e permitir adaptações durante o processo de desenvolvimento.
    - O Docente deve atuar como mediador do projeto, orientando e apoiando os alunos em cada etapa.
    - O projeto deve incentivar a autonomia, a criatividade e a colaboração entre os alunos.
    - Esta obeservação é apenas para o prompt, não deve conter no plano de ensino.
]
"""

modeloPlanoDeEnsinoPA="""
### Título:
[
    Inserir título da pesquisa aplicada, relacionado à unidade curricular selecionada
]

### Contextualização:
[
    Descreva um cenário realista e detalhado, simulando um ambiente de trabalho (empresa, departamento, setor industrial). Apresente a situação atual, os personagens envolvidos (se houver) e os processos de trabalho pertinentes. A contextualização deve preparar o terreno para o problema que será apresentado, tornando-o crível e relevante para o aluno.
]

### O Problema/Desafio:
[
    Com base na contextualização, descreva de forma clara e concisa o problema central que precisa ser resolvido ou o desafio a ser superado. Este não é o objetivo da pesquisa, mas sim a "dor" ou a oportunidade que motiva a investigação. Siga o exemplo do feedback: o problema são as "falhas de comunicação que geram insatisfação", e não "pesquisar a comunicação". O problema é o sintoma visível que impacta o negócio ou o processo.
]

### A Missão da Pesquisa Aplicada:
[
    Defina a missão dos alunos. O que eles devem investigar para entender e resolver o problema? Esta etapa deve orientar a pesquisa para um resultado prático. A missão deve ir além de "pesquisar sobre X" e focar em "investigar as causas de X", "analisar o impacto de Y nos resultados da empresa", "identificar as melhores práticas para solucionar Z" e, crucialmente, "propor uma solução/melhoria fundamentada nos dados coletados e analisados".
]

### Entregas Esperadas:
[
    Liste os produtos concretos que os alunos devem entregar ao final da pesquisa. Isso torna a avaliação mais objetiva e dá aos alunos uma meta clara. Exemplos: Relatório de diagnóstico com análise de causa raiz, Apresentação executiva com propostas de solução e indicadores de sucesso, Plano de ação para implementação da melhoria, Protótipo conceitual de um novo processo/ferramenta, etc.
]

NÃO INCLUIR ESSA SESSÃO NO PLANO DE ENSINO, APENAS PARA USO DO PROMPT
[
    Observações:
    - Utilize a linguagem clara e objetiva.
    - Inclua exemplos e informações relevantes para cada item.
    - Mantenha a coerência entre as diferentes etapas do plano de ensino.
    - Use a MSEP para entender como elaborar cada item solicitado.
    - A contextualização da estratégia de aprendizagem deve ser de acordo com o perfil profissional e trazer situações reais do mundo do trabalho.
    - Esta obeservação é apenas para o prompt, não deve conter no plano de ensino.
]
"""

modeloPlanoDeEnsinoPI="""
### Título do Projeto Integrador:
[
    Insira o título do projeto integrador, relacionado às unidades curriculares integradas.
    O título deve refletir a natureza interdisciplinar do projeto.
]

### Unidades Curriculares Integradas:
[
    Liste as UCs que serão trabalhadas de forma integrada neste projeto:
    - UC 1: [Nome da UC]
    - UC 2: [Nome da UC]
    (adicionar mais conforme necessário)
]

### Objetivo do Projeto Integrador:
[
    Descreva o objetivo geral do projeto, demonstrando como as diferentes UCs contribuem para um resultado comum.
    O objetivo deve evidenciar a interdisciplinaridade e a integração das capacidades de distintas unidades curriculares.
]

### Público Alvo:
[
    Indique o público-alvo do projeto, considerando o nível de ensino, a experiência profissional dos alunos e as necessidades específicas da turma.
]

### Contexto Interdisciplinar:
[
    Apresente um cenário real ou fictício que demande conhecimentos e habilidades de múltiplas áreas.
    A contextualização deve conectar naturalmente os conteúdos das diferentes UCs, mostrando como elas se complementam na prática profissional.
    Deve simular uma situação de trabalho que exija visão sistêmica do aluno.
]

### Desafio Integrador:
[
    Defina o problema ou desafio que exige a mobilização de capacidades de todas as UCs envolvidas.
    O desafio deve ser complexo o suficiente para justificar a integração curricular.
    Deve promover a tomada de decisão e resolução de problemas que transcendam uma única área de conhecimento.
]

### Capacidades por Unidade Curricular:
[
    Para cada UC, liste as capacidades que serão desenvolvidas:
    
    **UC: [Nome da UC 1]**
    - Capacidades Técnicas: [listar as capacidades técnicas selecionadas]
    - Capacidades Socioemocionais: [listar as capacidades socioemocionais selecionadas]
    
    **UC: [Nome da UC 2]**
    - Capacidades Técnicas: [listar as capacidades técnicas selecionadas]
    - Capacidades Socioemocionais: [listar as capacidades socioemocionais selecionadas]
    
    (Repetir para todas as UCs integradas)
]

### Resultados Esperados:
[
    Descreva os produtos que evidenciem a integração dos conhecimentos de todas as UCs.
    Os resultados devem demonstrar a capacidade do aluno de articular diferentes áreas de conhecimento.
    Exemplos: protótipo funcional, relatório integrado, solução técnica documentada, apresentação demonstrando domínio multidisciplinar.
]

### Etapas do Projeto Integrador:
[
    Divida o projeto em etapas, indicando quais UCs são mais relevantes em cada fase.
    Cada etapa deve promover a integração progressiva dos conhecimentos.
    Indicar prazos e entregas parciais que demonstrem o avanço interdisciplinar.
]

### Possibilidade de aplicação no mundo do trabalho:
[
    Descreva como o projeto integrador prepara o aluno para situações reais do mundo do trabalho,
    onde a atuação profissional frequentemente exige conhecimentos de múltiplas áreas.
]

NÃO INCLUIR ESSA SESSÃO NO PLANO DE ENSINO, APENAS PARA USO DO PROMPT
[
    Observações:
    - O projeto integrador deve promover diálogo entre as diferentes áreas de conhecimento.
    - Deve haver momentos de trabalho conjunto e momentos específicos de cada UC.
    - A avaliação deve considerar a integração demonstrada pelo aluno.
    - O docente deve atuar como mediador, facilitando as conexões entre as UCs.
    - Esta observação é apenas para o prompt, não deve conter no plano de ensino.
]
"""

modeloAvaliacaoAtual="""

## Critérios de Avaliação:
[
### Critérios Dicotômicos
    
    Tabela contendo como título "### Instrumento de Registro" 
        Nome do aluno:______________________________________________    Turma:_______________________\n
    - Colunas:
        Capacidades básicas/técnicas e socioemocionais
            [
                Colocar uma capacidades basicas ou técnicas e socioemocionais selecionadas para a situação de aprendizagem por linha.
            ]
        Critérios de Avaliação:
            [
                Para cada capacidade, elaborar dois critérios de avaliação pelo método Dicotômico.
                A MSEP enfatiza a importância de critérios objetivos que:
                    - Sejam específicos para cada tarefa, produto ou comportamento a ser avaliado: Os critérios devem ser elaborados de forma precisa, indicando exatamente o que se espera do aluno.
                    - Descrevam níveis de desempenho esperados: Os critérios devem detalhar diferentes níveis de proficiência, permitindo que o docente avalie o progresso do aluno em relação aos objetivos de aprendizagem.
                    - Representem, no conjunto, um resultado que permita concluir se a capacidade foi desenvolvida: A combinação dos critérios deve fornecer uma visão completa sobre o desenvolvimento da capacidade do aluno.
                    - Deve ser objetivo e possível mensurar ou quantificar, para que se torne um critério concreto, livre de subjetividade.
            ]
        Autoavaliação: [célula em branco]
        Avaliação Professor: [célula em branco]
    - Legenda:
        S=Atingiu/N=Não Atingiu [não preencher na tabela]
    
    Para quebras de linha dentro de uma célula, utilize a formatação de lista do Markdown (itens com '-').
    Obedecer a seguinte formatação da tabela em markdown e adequar seguindo o modelo para a quantidade de capacidades:
    
| Capacidades   | Critérios de Avaliação | Autoavaliação | Avaliação |
| --------------| ---------------------- | ------------- | --------- |
| [capacidade1] | [Critério Dicotômico1] |               |           |
|               | [Critério Dicotômico2] |               |           |
| [capacidade2] | [Critério Dicotômico1] |               |           |
|               | [Critério Dicotômico2] |               |           |
| [capacidade3] | [Critério Dicotômico1] |               |           |
|               | [Critério Dicotômico2] |               |           |

### Critérios Graduais

    Tabela contendo como título "### Instrumento de Registro"
        Nome do aluno:______________________________________________Turma:_______________________\n
    - Colunas:
        Capacidades básicas/técnicas e socioemocionais
            [
                Colocar uma capacidades basicas ou técnicas e socioemocionais selecionadas para a situação de aprendizagem por linha. Devem ser as mesmas selecionadas no item Critérios Dicotômicos.
            ]
        Critérios de Avaliação
            [
                Para cada capacidade criar um criterio de avaliacao que seja objetivo e possível mensurar ou quantificar, para que se torne um critério concreto, livre de subjetividade.
            ]
        Nível 4: Descreve o desempenho mínimo esperado do aluno, com características de falta de conhecimento ou domínio.
        Nível 3: Descreve o desempenho do aluno que demonstra alguma compreensão da capacidade, mas ainda precisa de auxílio.
        Nível 2: Descreve o desempenho do aluno que demonstra domínio da capacidade, realizando a tarefa com autonomia e segurança.
        Nível 1: Descreve o desempenho do aluno que demonstra excelência na capacidade, com iniciativa, criatividade e domínio aprofundado.
        
    Os níveis devem ser elaborados de forma objetiva e possível mensurar ou quantificar, para que se torne um critério concreto, livre de subjetividade, e devem considerar o critério de avaliação correspondente.
    Obedecer a seguinte formatação da tabela em markdown e adequar seguindo o modelo para a quantidade de capacidades e criterios de avaliação:
        
| **Capacidades**   | **Critérios de Avaliação**   | **Nível 1**      | **Nível 2**      | **Nível 3**      | **Nível 4**      |
|:-----------------:|:----------------------------:|:----------------:|:----------------:|:----------------:|:----------------:|
| [capacidade]      |[critério de avaliação]       |[critério nível 1]|[critério nível 2]|[critério nível 3]|[critério nível 4]|
| [capacidade]      |[critério de avaliação]       |[critério nível 1]|[critério nível 2]|[critério nível 3]|[critério nível 4]|

Legenda:\n
Nível 1: desempenho autônomo – apresenta desempenho esperado da competência com autonomia, sem intervenções do docente;\n
Nível 2: desempenho parcialmente autônomo – apresenta desempenho esperado da competência, com intervenções pontuais do docente;\n
Nível 3: desempenho apoiado – ainda não apresenta desempenho esperado da competência, exigidas intervenções constantes do docente;\n
Nível 4: desempenho não satisfatório – ainda não apresenta desempenho esperado da competência, mesmo com intervenções constantes do docente.\n

]
"""
modeloPlanoAula="""

## Plano de Aula:
[
    Tabela contendo como título "Plano de Aula"
    - Colulas:
        -Nº horas/aula e data:
            [carga horária em horas e data da aula no formato (DD/MM/AAAA)]
        -Capacidades a serem desenvolvidas:
            [ Listar as capacidades selecionadas anteriormente para a situação de aprendizagem.]
        -Conhecimentos relacionados:
            [ Listar os conhecimentos selecionados anteriormente para o desenvolvimento da situação de aprendizagem.]
        -Estratégias de ensino e instrumentos de avaliação:
            [ Por exemplo:
                - Exposição dialogada: explorar sobre os principais conhecimentos associados ao mercado no que tange às normas e legislações.
                - Simulação: elaboração e aplicação de ficha de análise de investigação de acidentes.
                - Dinâmica de grupo: conversando com as famílias das vítimas de acidente de trabalho.
            ]
        -Recursos e ambientes pedagógicos:
            [Computador, internet, notion, Microsoft Teams, Microsoft Learn, Plataforma de Gamificação Quizziz, Forms, Mentimeter, Kahoot, entre outros.]
        -Critérios de Avaliação:
            [ Listar os critérios de avaliação, críticos e desejáveis, elaborados anteriormente necessários para a avaliação da situação de aprendizagem proposta.]
        -Instrumento de Avaliação:
            [ Definir instrumentos de avaliação de forma a evidenciar os critérios de avaliação, em função das estratégias de ensino.]
        -Referências bibliográficas de acordo com o plano de curso:
            [livros, apostilas, sites, blogs, artigos, etc]
    
    O Plano de Aula deve contemplar toda a carga horária e número de aulas previstas para o desenvolvimento da Situação de Aprendizagem. O plano deve conter exatamente a quantidade de carga horária e aulas previstas no Item Cabeçalho. Informações do Curso. 
    
    Para quebras de linha dentro de uma célula, utilize a formatação de lista do Markdown (itens com '-').
    Obedecer a seguinte formatação da tabela e adequar seguindo o modelo para a quantidade de capacidades:
    
| Horas/Aulas e Data    | Capacidades| Conhecimentos | Estratégias | Recursos e ambientes pedagógicos | Critérios de Avaliação   | Instrumento de Avaliação | Referências |
|-----------------------|------------|---------------|-------------|----------------------------------|--------------------------|--------------------------|-------------|
| XX horas - DD/MM/AAAA |[capacidade]|               |             |                                  |[critério crítico]        |                          |             |
|                       |            |               |             |                                  |[critério desejável]      |                          |             |
| XX horas - DD/MM/AAAA |[capacidade]|               |             |                                  |[critério crítico]        |                          |             |
|                       |            |               |             |                                  |[critério desejável]      |                          |             |

]

Incluir ao final deste bloco:⚠️ Este Plano de Ensino foi gerado por IA e deve ser avaliado por um docente.\n\n

## Perguntas Mediadoras:
[
    - Elabore 5 pergundas mediadoras de acordo com a situação de aprendizagem propostas.
    - Considere as seguintes diretrizes para a elaboração de perguntas mediadoras, usando como base a Metodologia SENAI de Educação Profissional:
        Contextualização: As perguntas devem ser relacionadas ao contexto real de trabalho da ocupação, fazendo ligações com o que o aluno irá vivenciar no seu dia a dia profissional.
        Desafio: As perguntas devem desafiar o aluno a pensar além do básico, a buscar soluções criativas, a analisar diferentes perspectivas e a conectar os conhecimentos aprendidos com novas situações.
        Integração: As perguntas devem promover a integração entre teoria e prática, incentivando o aluno a aplicar o conhecimento em situações concretas.
        Abordagem: As perguntas devem ter uma abordagem que estimule o diálogo, a participação ativa e a colaboração entre os alunos.
        Níveis Cognitivos: As perguntas devem ser formuladas de forma a atingir diferentes níveis cognitivos da taxonomia de Bloom (lembrar, entender, aplicar, analisar, avaliar e criar).
]
"""
modeloPlanoAulaAtual="""

## Plano de Aula:
[
    Tabela contendo:
    - Colulas:
        -Nº horas/aula e data:
            [carga horária em horas e data da aula no formato (DD/MM/AAAA)]
        -Capacidades a serem desenvolvidas:
            [ Listar as capacidades selecionadas anteriormente para a situação de aprendizagem.]
        -Conhecimentos relacionados:
            [ Listar os conhecimentos selecionados anteriormente para o desenvolvimento da situação de aprendizagem.]
        -Estratégias de ensino e instrumentos de avaliação:
            [ Por exemplo:
                - Exposição dialogada: explorar sobre os principais conhecimentos associados ao mercado no que tange às normas e legislações.
                - Simulação: elaboração e aplicação de ficha de análise de investigação de acidentes.
                - Dinâmica de grupo: conversando com as famílias das vítimas de acidente de trabalho.
            ]
        -Recursos e ambientes pedagógicos:
            [Computador, internet, notion, Microsoft Teams, Microsoft Learn, Plataforma de Gamificação Quizziz, Forms, Mentimeter, Kahoot, entre outros.]
        -Critérios de Avaliação:
            [ 
                Listar os critérios de avaliação, elaborados anteriormente no item Critérios de Avaliação necessários para a avaliação da situação de aprendizagem proposta.
                Para cada critério de avaliação que for selecionado para ser trabalhado na aula, deve ser indicado todos os critérios de avaliação que foram definidos anteriormente.
            ]
        -Instrumentos de Avaliação:
            [ 
                O instrumento de avaliação é a ferramenta utilizada para medir e analisar o desempenho dos alunos em relação aos critérios de avaliação definidos.
                Ele pode ser de diversas formas, como:
                    - Provas: escritas, práticas ou orais, que avaliam o conhecimento teórico e prático dos alunos.
                    - Trabalhos: individuais ou em grupo, que exigem pesquisa, análise e aplicação dos conhecimentos.
                    - Portfólios: um conjunto de trabalhos, projetos e evidências que demonstram o desenvolvimento do aluno ao longo do curso.
                    - Observação: do professor sobre o desempenho do aluno em sala de aula, durante as atividades práticas ou em projetos.
                    - Autoavaliação: a própria análise do aluno sobre seu próprio aprendizado e desenvolvimento.
            ]
        -Referências bibliográficas de acordo com o plano de curso:
            [livros, apostilas, sites, blogs, artigos, etc]
            [incluir referências de acordo com as indicadas na Unidade Curricular e também indicar referências externas, que sejam pertinentes ao plano de aula e a unidade curricular.]
            [toda aula deve ter pelo menos uma referência bibliográfica.]
    
    O Plano de Aula deve contemplar toda a carga horária e número de aulas previstas para o desenvolvimento da Situação de Aprendizagem. O plano deve conter exatamente a quantidade de carga horária e aulas previstas no Item Cabeçalho. Informações do Curso. 
    
    Para quebras de linha dentro de uma célula, utilize a formatação de lista do Markdown (itens com '-').
    Obedecer rigorosamente a seguinte formatação da tabela e adequar seguindo o modelo para a quantidade de capacidades:
    
| Horas/Aulas e Data | Capacidades | Conhecimentos | Estratégias | Recursos e ambientes pedagógicos | Critérios de Avaliação | Instrumento de Avaliação | Referências |
|:---|:---|:---|:---|:---|:---|:---|:---|
| XX horas - DD/MM/AAAA |[capacidade]|   |   |   |[critérios de avaliação] |   |   |
| XX horas - DD/MM/AAAA |[capacidade]|   |   |   |[critérios de avaliação] |   |   |
 
]

## Perguntas Mediadoras:
[
    - Elabore 5 pergundas mediadoras de acordo com a situação de aprendizagem propostas.
    - Considere as seguintes diretrizes para a elaboração de perguntas mediadoras, usando como base a Metodologia SENAI de Educação Profissional:
        Contextualização: As perguntas devem ser relacionadas ao contexto real de trabalho da ocupação, fazendo ligações com o que o aluno irá vivenciar no seu dia a dia profissional.
        Desafio: As perguntas devem desafiar o aluno a pensar além do básico, a buscar soluções criativas, a analisar diferentes perspectivas e a conectar os conhecimentos aprendidos com novas situações.
        Integração: As perguntas devem promover a integração entre teoria e prática, incentivando o aluno a aplicar o conhecimento em situações concretas.
        Abordagem: As perguntas devem ter uma abordagem que estimule o diálogo, a participação ativa e a colaboração entre os alunos.
        Níveis Cognitivos: As perguntas devem ser formuladas de forma a atingir diferentes níveis cognitivos da taxonomia de Bloom (lembrar, entender, aplicar, analisar, avaliar e criar).
]
"""