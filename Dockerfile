FROM python:3.13-slim-trixie

# 1. Copiar o binário do uv diretamente da imagem oficial
# Isso é muito mais rápido do que rodar 'pip install uv'
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# 2. Configurações de ambiente para o uv
# UV_COMPILE_BYTECODE=1: Compila arquivos .pyc na instalação (startup mais rápido)
# UV_LINK_MODE=copy: Garante cópia de arquivos em vez de hardlinks (mais seguro em container)
ENV UV_COMPILE_BYTECODE=0
ENV UV_LINK_MODE=copy

COPY requirements.txt .

# Install system dependencies
# libgl1 e libglib2.0-0 são para OpenCV
# libgomp1 é para FAISS/PyTorch
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# 3. Install dependencies
# Forçamos opencv-python-headless antes para evitar puxar dependências gráficas pesadas
RUN uv pip install --system --no-cache opencv-python-headless

# Instala o restante (o uv vai pular opencv-python se considerar satisfeito ou instalar por cima, 
# mas as libs do sistema já estarão enxutas)
RUN uv pip install --system --no-cache -r requirements.txt --extra-index-url https://download.pytorch.org/whl/cpu --index-strategy unsafe-best-match

# Set HF_HOME to a predictable location and configure symlinks
ENV HF_HOME=/app/huggingface_cache
ENV HF_HUB_DISABLE_SYMLINKS_WARNING=1
ENV HF_HUB_ENABLE_HF_TRANSFER=0
ENV HF_HUB_CACHE_SYMLINKS=0

# Copy the application code
COPY src/ ./src/
COPY logs/ ./logs/
COPY msep.md .

# Copy and run the model downloader script
COPY download_models.py .
RUN python download_models.py

# Command to run the application
CMD ["uvicorn", "src.api:app", "--host", "0.0.0.0", "--port", "8000"]