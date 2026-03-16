from typing import List, Optional, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field

class RequestBody(BaseModel):
    message: str
    userId: str
    threadId: str
    
class PlanStatus(str, Enum):
    gerado = "gerado"
    submetido = "submetido"
    retornado = "retornado"
    aprovado = "aprovado"
       
# class PlanGenerationBody(BaseModel):
#     userId: str
#     threadId: str
#     docente: str
#     escola: str
#     planoCurso: str
#     curso: str
#     uc: str
#     capacidadesTecnicas: Optional[List[str]] = Field(default_factory=list)
#     capacidadesSocioemocionais: Optional[List[str]] = Field(default_factory=list)
#     estrategia: str
#     tematica: Optional[str] = ""

class PlanGenerationResponse(BaseModel):
    userId: str
    threadId: str
    plan_markdown: str
    
# Novos modelos para os endpoints
class GetThreadsRequest(BaseModel):
    userId: str = Field(..., alias="userId")

class GetThreadsResponse(BaseModel):
    userId: str
    all_threads: List[str]

class ChatHistoryRequest(BaseModel):
    threadId: str = Field(..., alias="threadId")

class MessageInfo(BaseModel):
    type: str
    content: str
    additional_info: dict
    timestamp: Optional[str] = None

class ChatHistoryResponse(BaseModel):
    threadId: str
    messages: List[MessageInfo]
    title: Optional[str] = None  # Adiciona o campo title como opcional
    
class ThreadInfo(BaseModel):
    thread_id: str
    title: str | None

class GetThreadsWithTitlesRequest(BaseModel):
    userId: str

class GetThreadsWithTitlesResponse(BaseModel):
    userId: str
    threads: List[ThreadInfo]
    
class ModelConfigRequest(BaseModel):
    temperature: float = Field(..., ge=0.0, le=2.0)  # Entre 0.0 e 1.0
    top_p: float = Field(..., ge=0.0, le=1.0)       # Entre 0.0 e 1.0
    user_id: str
    
class UCCapabilities(BaseModel):
    CapacidadesTecnicas_list: List[str] = Field(default_factory=list)
    CapacidadesSocioemocionais_list: List[str] = Field(default_factory=list)

class UCEntry(BaseModel):
    nomeUC: str
    capacidades: UCCapabilities
    conhecimentos: List[str] = Field(default_factory=list)

class FullPlanDetailsResponse(BaseModel):
    stored_markdown_id: str
    user_id: str
    thread_id: str # O thread_id da conversa original
    original_pdf_filename: Optional[str] = None
    nomeCurso: Optional[str] = None
    unidadesCurriculares: List[UCEntry] = Field(default_factory=list)
    objetivo_uc: Optional[str] = None
    referencias_bibliograficas: List[str] = Field(default_factory=list)

class HorarioAula(BaseModel): # Novo modelo para representar os horários
    dia: str
    horaInicio: str
    horaFim: str

# Modelo para UC com capacidades selecionadas (Projeto Integrador)
class UCCapacidadesInput(BaseModel):
    nomeUC: str
    capacidades_tecnicas: List[str] = Field(default_factory=list)
    capacidades_socioemocionais: List[str] = Field(default_factory=list)
    
class SituacaoAprendizagemInput(BaseModel):
    capacidades_tecnicas: List[str] = Field(default_factory=list)
    capacidades_socioemocionais: List[str] = Field(default_factory=list)
    estrategia: str # Ex: "situacao-problema", "projetos", "projeto-integrador"
    id: str
    tema_desafio: str # Usaremos como "tematica"
    carga_horaria: float = Field(default=20.0, description="Carga horária em horas para esta SA (suporta decimais)")
    # Para Projeto Integrador: lista de UCs com suas capacidades
    unidades_curriculares: Optional[List[UCCapacidadesInput]] = None

    
# Corpo da requisição para gerar o plano de ensino, usando o ID do markdown armazenado
class PlanGenerationBodyWithStoredId(BaseModel):
    stored_markdown_id: str
    user_id: str
    thread_id: str
    docente: str
    escola: str
    departamento_regional: str # Adicionado
    curso: str
    turma: str
    modalidade: str = Field(..., description="Modalidade do curso (Presencial, Híbrida, Online).")
    uc: str
    data_inicio: str = Field(..., description="Data de início do curso no formato YYYY-MM-DD.")
    data_fim: str = Field(..., description="Data de fim do curso no formato YYYY-MM-DD.")
    situacoes_aprendizagem: List[SituacaoAprendizagemInput] = Field(default_factory=list)
    horarios: List[HorarioAula] = Field(default_factory=list)

class GetPlansRequest(BaseModel):
    user_id: str = Field(..., description="ID do usuário para buscar os planos.", example="user_abc_12345")

class PlanSummary(BaseModel):
    plan_id: str
    nome_uc: Optional[str] = None
    turma: Optional[str] = None
    escola: Optional[str] = None
    departamento_regional: Optional[str] = None
    docente: Optional[str] = None
    curso: Optional[str] = None
    data_inicio: Optional[str] = None
    data_fim: Optional[str] = None
    contagem_sa_por_tipo: Optional[Dict[str, int]] = None
    status: PlanStatus = Field(PlanStatus.gerado, description="Status do plano (gerado, submetido, retornado, aprovado).")
    arquivado: Optional[bool] = None
    publico: Optional[bool] = None
    # Token metrics
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None

class GetPlansResponse(BaseModel):
    user_id: str
    plans: List[PlanSummary]
    
class GetPlanResponse(BaseModel):
    plan_id: str
    user_id: str
    thread_id: str
    course_plan_id: str
    created_at: str
    plan_content: Dict[str, Any]

class GetSinglePlanRequest(BaseModel):
    plan_id: str = Field(..., description="ID do plano de ensino a ser recuperado.")

class RenameThreadRequest(BaseModel):
    user_id: str = Field(..., description="ID do usuário que possui a conversa.")
    thread_id: str = Field(..., description="ID da conversa a ser renomeada.")
    new_title: str = Field(..., min_length=1, max_length=100, description="O novo título para a conversa.")

class SetDepartmentRequest(BaseModel):
    user_id: str = Field(..., description="ID do usuário.")
    departamento_regional: str = Field(..., min_length=2, description="Sigla do departamento regional (ex: SP, RJ).")

class GetUserConfigResponse(BaseModel):
    user_id: str
    departamento_regional: Optional[str] = None

class ExportPlanByIdRequest(BaseModel):
    plan_id: str = Field(..., description="ID do plano de ensino a ser exportado.")

class MetricItem(BaseModel):
    name: str
    user_count: int
    plan_count: int
    departamento_regional: Optional[str] = None
    escola: Optional[str] = None

class DailyPlanCount(BaseModel):
    date: str
    count: int

class MetricsResponse(BaseModel):
    total_users: int
    total_plans: int
    plans_per_day: List[DailyPlanCount]
    ranking_by_department: List[MetricItem]
    ranking_by_school: List[MetricItem]
    ranking_by_docente: List[MetricItem]
    contagem_geral_sa_por_tipo: Optional[Dict[str, int]] = None
    # Token metrics for PLANS only
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    avg_input_tokens_per_plan: float = 0.0
    avg_output_tokens_per_plan: float = 0.0
    # Token metrics for ALL CONVERSATIONS
    total_input_tokens_conversations: int = 0
    total_output_tokens_conversations: int = 0
    avg_input_tokens_per_conversation: float = 0.0
    avg_output_tokens_per_conversation: float = 0.0

# Modelos para o Plano Manual
class ManualInformacoesGerais(BaseModel):
    professor: str
    escola: str
    departamento_regional: str
    curso: str
    turma: str
    modalidade: Optional[str] = None
    unidade_curricular: str
    carga_horaria_total: Optional[str] = None # Added
    objetivo: Optional[str] = None # Added
    data_inicio: Optional[str] = None # Added to match frontend structure
    data_fim: Optional[str] = None # Added to match frontend structure

class ManualCriterio(BaseModel):
    id: Optional[str] = None # Made optional as new ones won't have it
    tipo: str
    capacidade: Optional[str] = None
    criterio: str
    nivel1: Optional[str] = None
    nivel2: Optional[str] = None
    nivel3: Optional[str] = None
    nivel4: Optional[str] = None

class ManualPlanoAula(BaseModel):
    id: Optional[str] = None # Made optional
    data: str
    hora_inicio: str = "" # Default empty
    hora_fim: str = "" # Default empty
    capacidades: List[str]
    conhecimentos: List[str]
    estrategias: str
    recursos: str
    criterios_avaliacao: List[str]
    instrumento: str
    referencias: str

class ManualConhecimento(BaseModel):
    topico: str
    subtopicos: List['ManualConhecimento'] = Field(default_factory=list)

class ManualSituacaoAprendizagem(BaseModel):
    id: Optional[str] = None # Made optional
    tema: str
    desafio: str
    estrategia: str
    resultados_esperados: Optional[str] = None # Added
    perguntas_mediadoras: List[str] = Field(default_factory=list) # Added
    conhecimentos: List[ManualConhecimento | str] # Allow string for compat or object
    capacidades_tecnicas: List[str]
    capacidades_socioemocionais: List[str]
    criterios: List[ManualCriterio]
    plano_aula: List[ManualPlanoAula]

class ManualPlanRequest(BaseModel):
    user_id: str = Field(..., description="ID do usuário.")
    plan_id: Optional[str] = Field(None, description="ID do plano original (para referência/versionamento).")
    thread_id: Optional[str] = Field(None, description="ID da thread original para manter o contexto.")
    course_plan_id: Optional[str] = Field(None, description="ID do documento base (course_plan_id) para manter vínculo.")
    plan_content: Dict[str, Any] = Field(..., description="Conteúdo completo do plano (JSON aninhado: plano_de_ensino -> ...)")


class UserRole(str, Enum):
    docente = "docente"
    coordenador = "coordenador"
    administracao_regional = "administracao_regional"
    administracao_nacional = "administracao_nacional"



class CreateUserRequest(BaseModel):
    user_id: str = Field(..., description="ID único do usuário.")
    full_name: str = Field(..., description="Nome completo do usuário.")
    email: Optional[str] = Field(None, description="Email do usuário.")
    role: UserRole = Field(..., description="Função do usuário.")
    departamento_regional: Optional[str] = Field(None, description="Departamento regional do usuário (ex: SP, RJ).", max_length=2)
    escola: Optional[str] = Field(None, description="Nome da escola do usuário.", max_length=100)

class UserResponse(BaseModel):
    user_id: str
    full_name: str
    email: Optional[str] = None
    role: UserRole
    departamento_regional: Optional[str] = None
    escola: Optional[str] = None

class AllUsersResponse(BaseModel):
    users: List[UserResponse]

class UpdatePlanStatusRequest(BaseModel):
    plan_id: str = Field(..., description="ID do plano a ser atualizado.")
    new_state: PlanStatus = Field(..., description="O novo estado para o plano.")
    comment: Optional[str] = Field(None, description="Comentário ou feedback sobre a mudança de status.")
    user_id: str = Field(..., description="ID do usuário que está fazendo a alteração.")

class PlanStatusHistoryEntry(BaseModel):
    id: str
    previous_status: Optional[str] = None
    new_status: str
    comment: Optional[str] = None
    changed_by_user_id: str
    changed_by_name: Optional[str] = None
    created_at: str

class PlanStatusHistoryResponse(BaseModel):
    plan_id: str
    history: List[PlanStatusHistoryEntry]

class ArchivePlanRequest(BaseModel):
    plan_id: str = Field(..., description="ID do plano a ser arquivado/desarquivado.")
    archived: bool = Field(..., description="Definir como `true` para arquivar, `false` para desarquivar.")

class UserRoleResponse(BaseModel):
    role: UserRole

class TogglePublicRequest(BaseModel):
    plan_id: str = Field(..., description="ID do plano a ter a visibilidade alternada.")

# Modelos para Notificações
class NotificationType(str, Enum):
    plan_submitted = "plan_submitted"
    plan_returned = "plan_returned"
    plan_approved = "plan_approved"

class NotificationCreate(BaseModel):
    user_id: str
    plan_id: Optional[str] = None
    type: NotificationType
    message: str
    metadata: Optional[Dict[str, Any]] = None

class NotificationResponse(BaseModel):
    id: str
    user_id: str
    plan_id: Optional[str] = None
    type: NotificationType
    message: str
    is_read: bool
    created_at: str
    read_at: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

class NotificationListResponse(BaseModel):
    notifications: List[NotificationResponse]
    unread_count: int

class MarkAsReadRequest(BaseModel):
    notification_ids: List[str]