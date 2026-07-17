FROM python@sha256:db3ff2e1800a8581e2c48a27c3995339d47bdf046da21c7627accd3d51053a93

RUN set -eux; \
    if command -v apt-get >/dev/null 2>&1; then \
        apt-get update; \
        DEBIAN_FRONTEND=noninteractive \
        apt-get install -y --no-install-recommends \
            bash \
            ca-certificates \
            coreutils \
            findutils \
            git \
            grep \
            procps \
            sed; \
        rm -rf /var/lib/apt/lists/*; \
    elif command -v apk >/dev/null 2>&1; then \
        apk add --no-cache \
            bash \
            ca-certificates \
            coreutils \
            findutils \
            git \
            grep \
            procps \
            sed; \
    else \
        echo "Gestionnaire de paquets non supporté" >&2; \
        exit 1; \
    fi; \
    mkdir -p /home/worker /workspace; \
    chown -R 1000:1000 /home/worker /workspace

ENV HOME=/home/worker
WORKDIR /workspace
CMD ["sleep", "infinity"]
