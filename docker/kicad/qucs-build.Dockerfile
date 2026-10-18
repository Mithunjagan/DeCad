FROM debian:trixie-slim AS builder
RUN apt-get update && apt-get install -y --no-install-recommends build-essential cmake flex bison gperf libreadline-dev qt6-base-dev qt6-tools-dev qt6-tools-dev-tools qt6-svg-dev ca-certificates curl && rm -rf /var/lib/apt/lists/*
WORKDIR /src
RUN curl -fsSL https://github.com/ra3xdh/qucs_s/releases/download/26.1.1/qucs-s-26.1.1.tar.gz -o qucs.tar.gz && tar -xzf qucs.tar.gz --strip-components=1 && cmake -S . -B build -DCMAKE_BUILD_TYPE=Release && cmake --build build --target qucs-s -j2
FROM debian:trixie-slim
COPY --from=builder /src/build/qucs/qucs-s /usr/local/bin/qucs-s
COPY --from=builder /src /usr/share/qucs-s-source
