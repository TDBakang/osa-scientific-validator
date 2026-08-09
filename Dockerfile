FROM python:3.12-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt-lists/*

COPY pyproject.toml README.md ./
COPY src/ ./src/
COPY tests/ ./tests/

# Installation du package local + pytest pour le stage builder
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir . pytest

RUN python3 -c "from rocsa_generator import RocsaRegistry, RocsaEngine; \
    from pathlib import Path; \
    registry = RocsaRegistry(); \
    registry.scan_directory(Path('src/rocsa_generator/definitions/catalog')); \
    engine = RocsaEngine(output_dir='./src'); \
    engine.generate_sdk(registry, target_dir='./src/rocsa')"

# Validation des tests unitaires pendant le build Docker
RUN python3 -m pytest -v

# Stage Final Runtime
FROM python:3.12-slim AS runtime

WORKDIR /app

COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /app/src /app/src
COPY --from=builder /app/pyproject.toml /app/

ENV PYTHONPATH="/app/src"

CMD ["python3", "-c", "from rocsa.integration import RMCSValidatorFacade; \
    from rocsa.core import CSAContext; \
    v = RMCSValidatorFacade.load_sdk('/app/src/rocsa'); \
    print('✓ Conteneur ROCSA opérationnel. Controls chargés :', v.loaded_controls_count); \
    ctx = CSAContext(execution_id='DOCKER-TEST', target_name='Docker Runtime Test'); \
    rep = v.audit_all(ctx); \
    print(rep.summary_text())"]
