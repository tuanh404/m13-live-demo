# Official multi-arch manifest digest recorded in L05-python-image.json.
FROM python:3.11-slim-bookworm@sha256:0a310eeecf4e1f5a0743f9a6520c90c88d089c903ca5fd283f501e3a805f5f89
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 MPLCONFIGDIR=/tmp/matplotlib \
    OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2
WORKDIR /app
COPY deployment/mvp/requirements.lock /tmp/requirements.lock
RUN pip install --no-cache-dir -r /tmp/requirements.lock
COPY pyproject.toml ./
COPY src/ ./src/
COPY configs/ ./configs/
COPY deployment/render/BDD100K-LICENSE.txt ./deployment/render/BDD100K-LICENSE.txt
RUN useradd --uid 10001 --create-home m13
USER 10001:10001
EXPOSE 8000
CMD ["python", "-m", "src.cli", "serve", "--host", "0.0.0.0", "--port", "8000"]
