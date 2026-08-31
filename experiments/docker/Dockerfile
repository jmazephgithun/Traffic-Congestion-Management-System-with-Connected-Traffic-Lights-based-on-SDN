# Ryu (framework abandonne, incompatible Python >= 3.10) tourne ici sous Python 3.9,
# isole du reste du projet qui utilise Python 3.12. Open vSwitch fonctionne en
# datapath "netdev" (espace utilisateur), sans module noyau. La creation des
# namespaces/veth exige toutefois NET_ADMIN et /dev/net/tun (declares dans Compose).
FROM python:3.9-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    openvswitch-switch openvswitch-common \
    iproute2 iptables iputils-ping \
    iperf \
    curl procps jq netcat-openbsd \
    libx11-6 libxext6 libxrender1 libgl1 libexpat1 \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir "setuptools<58" wheel \
    && pip install --no-cache-dir "eventlet==0.30.2" "ryu==4.34" \
       eclipse-sumo sumolib traci requests

WORKDIR /experiments
COPY pyfilesTrue/ pyfilesTrue/
COPY sumo_one_junction/ sumo_one_junction/
COPY tools/ tools/
COPY scripts/ scripts/
COPY tests/ tests/
COPY docker/ /experiments/docker/
RUN chmod +x /experiments/docker/*.sh

HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8080/health || exit 1

ENTRYPOINT ["/experiments/docker/entrypoint.sh"]
