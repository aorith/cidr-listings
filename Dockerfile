FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Virtual environment
ENV VIRTUAL_ENV="/opt/venv"
RUN python3 -m venv "${VIRTUAL_ENV}"
ENV PATH="${VIRTUAL_ENV}/bin:${PATH}"

# Requirements
COPY ./requirements/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
        && pip install --no-cache-dir -r "/tmp/requirements.txt" \
        && rm -f /tmp/requirements.txt

# Code
WORKDIR /CODE
COPY ./src/app /CODE/app

# Bytecode optimizations
RUN python -c "import compileall; compileall.compile_path(maxlevels=10)" \
        && python -m compileall /CODE/app

ENTRYPOINT ["uvicorn"]
CMD ["app.main:app", "--host", "0.0.0.0", "--port", "8000"]
