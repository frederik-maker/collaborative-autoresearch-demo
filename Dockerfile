# Multi-stage build:
#   1. Compile the AXL Go node binary.
#   2. Run the Python web UI + orchestrator. The orchestrator spawns the
#      four AXL nodes and four agent processes inside this same container
#      when the user clicks "Start Simulation" in the browser.

FROM golang:1.25 AS axl
ARG AXL_REF=main
WORKDIR /src
RUN git clone --depth=1 --branch ${AXL_REF} https://github.com/gensyn-ai/axl.git
WORKDIR /src/axl
RUN make build && cp node /out_node || (mkdir -p /out && cp node /out/node)

FROM python:3.12-slim AS runtime
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir uv

WORKDIR /app
COPY pyproject.toml ./
COPY uv.lock ./
RUN uv sync --frozen --no-install-project

COPY sim ./sim
COPY configs ./configs
COPY scripts ./scripts

COPY --from=axl /src/axl/node /app/bin/axl
RUN chmod +x /app/bin/axl

ENV PORT=8080
ENV SIM_STATE_DIR=/app/state
EXPOSE 8080

CMD ["uv", "run", "python", "-m", "sim.server"]
