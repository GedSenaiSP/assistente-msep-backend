# Assistente Virtual MSEP (Metodologia SENAI de Educação Profissional)

## Descrição

Este projeto implementa um assistente virtual especializado na Metodologia SENAI de Educação Profissional (MSEP). Seu objetivo é auxiliar professores e instrutores na compreensão e aplicação da MSEP para a elaboração de planos de ensino, cronogramas, planos de aula e outros instrumentos da prática pedagógica. O assistente é construído utilizando tecnologias de Processamento de Linguagem Natural (PLN) e IA Generativa, com foco no modelo Gemini do Google, integrado através do Vertex AI.

O núcleo do conhecimento do assistente é baseado no documento `msep.md`, que detalha a Metodologia SENAI de Educação Profissional, abrangendo desde a definição de Perfis Profissionais, passando pelo Desenho Curricular, até a Prática Pedagógica.

## Funcionalidades Principais

* **Chat Interativo**: Permite que os usuários façam perguntas e recebam orientações sobre a MSEP e a criação de documentos pedagógicos.
* **Geração de Títulos de Conversa**: Cria automaticamente títulos descritivos para as sessões de chat.
* **Gerenciamento de Histórico de Conversas**: Armazena e recupera o histórico de interações por usuário e por thread de conversa, utilizando PostgreSQL como backend de checkpoint.
* **Ferramenta Especializada (`chatmsep`)**: Um tool dedicado para responder perguntas especificamente sobre a MSEP, utilizando o conteúdo do arquivo `msep.md` como base de conhecimento.
* **Busca na Web (`web_search`)**: Capacidade de realizar buscas na web para informações gerais, com foco em cursos e oportunidades do SENAI quando o assunto é relacionado a educação e vagas.

## Tecnologias Utilizadas

O projeto utiliza as seguintes tecnologias e bibliotecas principais (conforme `requirements.txt`):

* **Backend Framework**: FastAPI
* **Servidor ASGI**: Uvicorn
* **Orquestração de Agentes de IA**: LangGraph
* **Desenvolvimento com LLMs**: LangChain, LangChain Core
* **Modelo de Linguagem**: Google Gemini (via `langchain-google-vertexai`, `google-cloud-aiplatform`, `google.generativeai`)
* **Banco de Dados (Checkpoint)**: PostgreSQL (via `psycopg-binary`, `psycopg2-binary`, `psycopg-pool`, `langgraph-checkpoint-postgres`)
* **Validação de Dados**: Pydantic
* **Gerenciamento de Variáveis de Ambiente**: python-dotenv
* **Autenticação (JWT)**: python-jose
* **Outras**: `uuid`, `tempfile2`, `google.cloud`, `google-cloud-texttospeech`

## Estrutura do Projeto
```
backend-assistente/
├── logs/                     # Arquivos de log
│   ├── app.log
│   └── msep.log
├── src/                      # Código fonte principal
│   ├── models/               # Modelos Pydantic para requisições e respostas
│   │   └── models.py
│   ├── tools/                # Ferramentas customizadas para o agente LangGraph
│   │   ├── init.py
│   │   ├── chatmsep.py       # Ferramenta de chat especializada na MSEP
│   │   └── web_search.py     # Ferramenta de busca na web
│   ├── utils/                # Funções utilitárias
│   │   └── utils.py
│   ├── agent.py              # Lógica do agente LangGraph e LLM
│   ├── api.py                # Endpoints da API FastAPI
│   ├── plan_generator.py     # Lógica para geração de planos (não totalmente detalhada nos arquivos)
│   └── prompts.py            # Templates de prompts para o LLM
├── .env                      # Arquivo para variáveis de ambiente (NÃO versionar)
├── chatbot.json              # Credenciais da conta de serviço do Google Cloud
├── consolidate_code.py       # Script para consolidar arquivos de código (utilitário)
├── msep.md                   # Documento base da Metodologia SENAI de Educação Profissional
└── requirements.txt          # Dependências do projeto Python
```

## Configuração e Instalação

1.  **Pré-requisitos**:
    * Python 3.11 ou posterior
    * PostgreSQL Server
    * Conta no Google Cloud com Vertex AI e API do Gemini habilitadas.

2.  **Clonar o Repositório (se aplicável)**:
    ```bash
    git clone <URL_DO_REPOSITORIO>
    cd backend-assistente-msep
    ```

3.  **Configurar Variáveis de Ambiente**:
    Crie um arquivo `.env` na raiz do projeto, baseado nos exemplos ou variáveis necessárias encontradas no código (ex: `src/agent.py`, `src/api.py`). Ele deve incluir:
    ```env
    PROJECT_ID="seu-project-id-google-cloud"
    LOCATION="us-central1" # ou sua região
    MODEL_ID="gemini-2.5-flash" # ou o modelo Gemini desejado
    PG_USER="seu_usuario_postgres"
    PG_PASSWORD="sua_senha_postgres"
    PG_HOST="localhost" # ou o host do seu DB
    PG_PORT="5432" # ou a porta do seu DB
    PG_DATABASE="sua_database_postgres"
    GOOGLE_APPLICATION_CREDENTIALS="./chatbot.json" # Caminho para o arquivo de credenciais
    PORT=8000 # Porta para a API
    GCS_MARKDOWN_BUCKET_NAME=<nome do bucket>
    GCS_PLANS_BUCKET_NAME=<nome do bucket>
    ```
    **Atenção**: Certifique-se de que o arquivo `chatbot.json` (credenciais da conta de serviço) esteja no local correto e referenciado no `GOOGLE_APPLICATION_CREDENTIALS`.

4.  **Criar e Ativar um Ambiente Virtual (Recomendado)**:
    ```bash
    python -m venv .venv
    # No Windows
    .\.venv\Scripts\activate
    # No macOS/Linux
    source .venv/bin/activate
    ```

5.  **Instalar Dependências**:
    ```bash
    pip install -r requirements.txt
    ```

6.  **Configurar o Banco de Dados PostgreSQL**:
    * Certifique-se de que o servidor PostgreSQL esteja rodando.
    * Crie o banco de dados especificado em `PG_DATABASE`.
    * As tabelas para o checkpoint do LangGraph (`checkpoints`) serão criadas automaticamente ao iniciar a aplicação pela primeira vez, devido à função `setup_checkpointer` em `src/agent.py` [cite: 40] e sua chamada indireta.

## Uso (Executando a API)

Para iniciar o servidor da API FastAPI:

```bash
uvicorn src.api:app --host 0.0.0.0 --port ${PORT:-8000} --reload
```

Onde `${PORT:-8000}` usa a variável de ambiente PORT ou 8000 como padrão.

A API estará disponível em `http://localhost:8000` (ou a porta configurada).

### Endpoints Principais (conforme `src/api.py` ):

- **`POST /chat/`**:
    - **Descrição**: Processa uma mensagem do usuário, executa o agente e retorna a resposta do assistente e o título da conversa.
    - **Corpo da Requisição** (`RequestBody`):
    ```json
        {
          "message": "string",
          "userId": "string",
          "threadId": "string"
        }
    ```
        
    - **Resposta**:
    ```json
        {
          "message": "string",
          "title": "string",
          "user_id": "string",
          "thread_id": "string"
        }
    ```
        
- **`GET /health/`**:
    - **Descrição**: Verifica o status da aplicação.
    - **Resposta**:
    ```json
        {
          "status": "servidor rodando"
        }
    ```
        
- **`POST /get_threads/`**:
    - **Descrição**: Retorna todos os `thread_id`s associados a um `userId`.
    - **Corpo da Requisição** (`GetThreadsRequest`):
    ```json
        {
          "userId": "string"
        }
    ```
        
    - **Resposta** (`GetThreadsResponse`):
    ```json
        `{
          "userId": "string",
          "all_threads": ["string"]
        }
    ```
        
- **`POST /chat_history/`**:
    - **Descrição**: Retorna o histórico de mensagens e o título para um `threadId` específico.
    - **Corpo da Requisição** (`ChatHistoryRequest`):
    ```json
        {
          "threadId": "string"
        }
    ```
        
    - **Resposta** (`ChatHistoryResponse`):
    ```json 
        {
          "threadId": "string",
          "messages": [
            {
              "type": "string", // ex: "HumanMessage", "AIMessage", "ToolMessage"
              "content": "string",
              "additional_info": {}
            }
          ],
          "title": "string" // opcional
        }
    ```
        

## Funcionamento do Agente (`src/agent.py` )

O agente é construído usando LangGraph e opera da seguinte forma:

1. **`identify_tool`**: O LLM determina qual ferramenta (ex: `chatmsep`, `web_search`) deve ser usada com base na entrada do usuário. Por padrão, tenta usar `chatmsep`.
2. **`execute_tool`**: Se uma ferramenta for identificada, ela é executada com os argumentos apropriados.
3. **`generate_response`**: O LLM gera uma resposta final ao usuário, considerando a entrada original e o resultado da ferramenta (se houver). As mensagens são acumuladas no estado.
4. **`generate_title`**: Um título para a conversa é gerado (ou mantido, se já existir) com base na entrada do usuário e na resposta do sistema.

O estado da conversa (`AgentState` ) é persistido usando `AsyncPostgresSaver` para permitir conversas contínuas.

## Logs

Os logs da aplicação são configurados para serem salvos em `logs/msep.log` e também exibidos no console.
