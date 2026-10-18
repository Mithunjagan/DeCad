FROM debian:trixie-slim AS qucs_builder
RUN apt-get update && apt-get install -y --no-install-recommends build-essential cmake flex bison gperf libreadline-dev qt6-base-dev qt6-tools-dev qt6-tools-dev-tools qt6-svg-dev ca-certificates curl && rm -rf /var/lib/apt/lists/*
WORKDIR /src
RUN curl -fsSL https://github.com/ra3xdh/qucs_s/releases/download/26.1.1/qucs-s-26.1.1.tar.gz -o qucs.tar.gz && tar -xzf qucs.tar.gz --strip-components=1 && cmake -S . -B build -DCMAKE_BUILD_TYPE=Release && cmake --build build --target qucs-s -j2
FROM debian:trixie-slim
ENV DEBIAN_FRONTEND=noninteractive DISPLAY=:1 PYTHONUNBUFFERED=1 KICAD_EMBEDDED=true
RUN apt-get update && apt-get install -y --no-install-recommends \
    kicad kicad-symbols kicad-footprints ngspice xvfb x11vnc novnc websockify openbox ca-certificates xdotool procps \
    python3 python3-venv git fonts-dejavu-core curl tesseract-ocr librsvg2-bin libqt6widgets6 libqt6svg6 libqt6svgwidgets6 libqt6xml6 libqt6printsupport6 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=qucs_builder /src/build/qucs/qucs-s /usr/local/bin/qucs-s
COPY --from=qucs_builder /src/qucs.tar.gz /usr/share/qucs-s/source.tar.gz
WORKDIR /app/backend
COPY backend/requirements.txt backend/requirements-ocr.txt /app/backend/
RUN python3 -m venv /opt/venv && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt \
    && /opt/venv/bin/pip install --no-cache-dir --no-deps --ignore-requires-python -r requirements-ocr.txt
ENV PATH=/opt/venv/bin:$PATH WORKSPACE_ROOT=/workspaces STATE_ROOT=/state DATASET_ROOT=/datasets
COPY backend/app /app/backend/app
COPY backend/models /app/backend/models
COPY docker/kicad/embedded.html /usr/share/novnc/embedded.html
COPY docker/kicad/start.sh /start.sh
COPY docker/kicad/entrypoint.sh /entrypoint.sh
COPY docker/kicad/switch-project.sh /usr/local/bin/switch-project.sh
RUN chmod +x /entrypoint.sh /start.sh /usr/local/bin/switch-project.sh
EXPOSE 8000 6080
CMD ["/entrypoint.sh"]
