"""
Modelos Pydantic para Recursos Didáticos.
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


class ResourceStatus(str, Enum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class GenerateResourceRequest(BaseModel):
    """Requisição para gerar recurso didático."""
    plan_id: str = Field(..., description="ID do plano de ensino")
    sa_index: int = Field(..., description="Índice da SA (-1 para gerar para todas)")
    num_chapters: int = Field(..., ge=1, le=100, description="Número de capítulos (1-100)")
    user_id: str = Field(..., description="ID do usuário")


class DidacticResourceResponse(BaseModel):
    """Resposta com dados de um recurso didático."""
    id: str
    plan_id: str
    sa_index: int
    title: str
    blob_url: Optional[str] = None
    num_chapters: int
    status: ResourceStatus
    error: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class DidacticResourceListResponse(BaseModel):
    """Lista de recursos didáticos de um plano."""
    plan_id: str
    resources: List[DidacticResourceResponse]


class DidacticResourceJobResponse(BaseModel):
    """Resposta com dados do job de geração."""
    job_id: str
    resource_id: str
    status: ResourceStatus
    message: str
