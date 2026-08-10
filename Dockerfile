# AETHER — LAN daemon-raising game
#
# IMPORTANT: run with host networking so the game can see your real LAN:
#
#   docker build -t aether .
#   docker run -d --name aether --network host -v aether_data:/data aether
#
# With the default bridge network the container can only see Docker's internal
# network — scans would find nothing. Host networking (Linux) gives AETHER your
# actual ARP table and makes the UI reachable at http://<host-ip>:8787 with no
# port mapping. See docker-compose.yml for the ready-made setup.

FROM python:3.12-slim

# ping warms the ARP cache during scans; ip (iproute2) reads the neighbour
# table. procps gives a usable `ps` for debugging. Nothing else needed —
# Python deps are vendored in ./vendor (pure Python).
RUN apt-get update \
    && apt-get install -y --no-install-recommends iputils-ping iproute2 procps \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY app.py VERSION CHANGELOG.md README.md ./
COPY core/ ./core/
COPY static/ ./static/
COPY vendor/ ./vendor/

# Game state lives on a volume so it survives container upgrades.
ENV AETHER_DB=/data/aether.db \
    AETHER_PORT=8787 \
    PYTHONUNBUFFERED=1
VOLUME ["/data"]

EXPOSE 8787

HEALTHCHECK --interval=60s --timeout=5s --start-period=10s \
    CMD python -c "import urllib.request,os;urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"AETHER_PORT\",\"8787\")}/api/state',timeout=4)" || exit 1

CMD ["python", "app.py"]
