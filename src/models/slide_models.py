"""
Modelos Pydantic para recursos de slides.
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


class SlideResourceStatus(str, Enum):
    """Status do recurso de slides."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class TemplateType(str, Enum):
    """Tipos de template disponíveis para slides."""
    DN = "dn"  # Departamento Nacional
    SP = "sp"  # São Paulo


class GenerateSlidesRequest(BaseModel):
    """Request para gerar slides."""
    plan_id: str = Field(..., description="ID do plano de ensino")
    sa_index: int = Field(..., description="Índice da SA (-1 para todas)")
    num_slides: int = Field(default=30, ge=30, le=300, description="Número de slides (30-300)")
    template: TemplateType = Field(default=TemplateType.DN, description="Template a ser usado (dn=Departamento Nacional, sp=São Paulo)")


class SlideResourceResponse(BaseModel):
    """Resposta com informações do recurso de slides."""
    id: str
    plan_id: str
    sa_index: int
    title: Optional[str] = None
    num_slides: Optional[int] = None
    status: SlideResourceStatus
    blob_path: Optional[str] = None
    error: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class SlideResourceListResponse(BaseModel):
    """Lista de recursos de slides."""
    resources: List[SlideResourceResponse]
    total: int


class SlideResourceJobResponse(BaseModel):
    """Resposta ao iniciar geração de slides."""
    job_id: str
    resource_id: str
    status: SlideResourceStatus
    message: str
