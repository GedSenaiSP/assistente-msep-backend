"""
Modelos para gerenciamento de jobs assíncronos de geração de planos.
"""
from enum import Enum
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    """Status possíveis de um job de geração."""
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class JobCreateResponse(BaseModel):
    """Resposta ao criar um job de geração."""
    job_id: str = Field(..., description="ID único do job criado.")
    status: JobStatus = Field(JobStatus.pending, description="Status inicial do job.")
    message: str = Field("Geração de plano iniciada. Use o endpoint de status para acompanhar o progresso.", 
                         description="Mensagem informativa.")


class JobStatusResponse(BaseModel):
    """Resposta ao consultar o status de um job."""
    job_id: str = Field(..., description="ID do job.")
    status: JobStatus = Field(..., description="Status atual do job.")
    progress: int = Field(0, ge=0, le=100, description="Progresso da geração (0-100%).")
    current_step: Optional[str] = Field(None, description="Etapa atual do processamento.")
    result: Optional[Dict[str, Any]] = Field(None, description="Resultado final quando concluído.")
    error: Optional[str] = Field(None, description="Mensagem de erro se falhou.")
