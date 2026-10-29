# Kaaval: the analog review app and its engine, with only open tools (ngspice + the open sky130 PDK).
# Build: docker build -t kaaval .      Run: docker run -p 7860:7860 [-e MUSE_API_KEY=...] kaaval
FROM python:3.12-slim-trixie

RUN apt-get update && apt-get install -y --no-install-recommends ngspice git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# the open sky130 PDK, pinned to the version Kaaval is tested with; only what simulation and netlisting read
ARG PDK_HASH=c6d73a35f524070e85faff4a6a9eef49553ebc2b
RUN pip install --no-cache-dir volare==0.20.6 \
    && volare enable --pdk sky130 --pdk-root /opt/pdk "$PDK_HASH" \
    && cd /opt/pdk/sky130A && find libs.ref -mindepth 1 -maxdepth 1 ! -name sky130_fd_pr -exec rm -rf {} + \
    && find libs.ref/sky130_fd_pr -mindepth 1 -maxdepth 1 ! -name spice -exec rm -rf {} + \
    && find libs.tech -mindepth 1 -maxdepth 1 ! -name ngspice ! -name xschem -exec rm -rf {} + \
    && rm -rf /opt/pdk/volare/sky130/versions/*/sky130B /root/.cache

# xschem's own symbol library (devices/*.sym), read as text by the netlister; xschem itself is not installed
RUN git clone --depth 1 https://github.com/StefanSchippers/xschem /tmp/xschem \
    && mkdir -p /opt/xschem && cp -r /tmp/xschem/xschem_library /opt/xschem/ && rm -rf /tmp/xschem

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn==23.0.0
COPY . .

ENV KAAVAL_PDK_ROOT=/opt/pdk/sky130A KAAVAL_XSCHEM_LIB=/opt/xschem/xschem_library \
    KAAVAL_DB=/data/kaaval.db KAAVAL_WORK=/data/repos KAAVAL_WS=/data/ws KAAVAL_PDK_CACHE=/data/pdk \
    KAAVAL_MAX_REVIEWS=2 PYTHONUNBUFFERED=1
RUN mkdir -p /data && useradd -m kaaval && chown -R kaaval /data /app
USER kaaval
EXPOSE 7860
# one process (the run state lives in it), threads for concurrent requests
CMD ["gunicorn", "-w", "1", "--threads", "16", "-b", "0.0.0.0:7860", "--timeout", "900", "app.server:app"]
