.PHONY: help build test smoke memoire evolue all-tests \
        test-a1 test-a1w test-a2 test-a3 evaluate evaluate-30 \
        test-b1 test-b2 test-b3 test-c test-c30 rapport test-d \
        test-solibra replay gui test-secteurs demo clean

COMPOSE := docker compose
RUN     := $(COMPOSE) run --rm
RUN_SIM := $(COMPOSE) run --rm -e SKIP_NETWORK=1

help:
	@echo "Niveau 1, reproduction du memoire : make memoire"
	@echo "Niveau 2, option evoluee          : make evolue   (interface graphique : make gui)"
	@echo "Demonstration visuelle commentee  : make demo     -> results_docker/demo.html"
	@echo "Detail des cibles                 : voir README.md"

build:
	$(COMPOSE) build lab tests

test:
	$(RUN) tests

smoke: results_docker
	$(RUN) lab bash docker/tests_phase_b.sh

results_docker:
	mkdir -p results_docker

# ---------------------------------------------------------------- niveau 1
# Phase A : mobilite et commande des feux (tableau 3.4, trente graines, Webster)
test-a1: results_docker
	$(RUN_SIM) lab python scripts/evaluate.py --mode baseline --seeds 42 --output results_docker/a1-baseline.json

test-a2: results_docker
	$(RUN_SIM) lab python scripts/evaluate.py --mode adaptive --seeds 42 --output results_docker/a2-adaptive.json

evaluate test-a3: results_docker
	$(RUN_SIM) lab python scripts/evaluate.py --seeds 42 --output results_docker/evaluation.json

evaluate-30: results_docker
	$(RUN_SIM) lab python scripts/evaluate.py --seeds 42,1-29 --output results_docker/evaluation-30.json

test-a1w: results_docker
	$(RUN_SIM) lab python scripts/evaluate.py --mode baseline --plan webster --seeds 42,1-29 --output results_docker/webster-30.json

# Phase B : reseau sature sans puis avec QoS SDN (tableau 3.5)
test-b1: results_docker
	$(RUN) lab bash docker/network_scenario.sh noqos

test-b2: results_docker
	$(RUN) lab bash docker/network_scenario.sh qos

test-b3: test-b1 test-b2

# Boucle fermee SUMO -> orchestrateur -> Ryu -> OpenFlow, puis decision sur trente graines
test-c: results_docker
	$(RUN) lab bash docker/test_closed_loop.sh

test-c30: results_docker
	$(RUN_SIM) lab python scripts/mesurer_boucle_fermee.py --seeds 42,1-29 --output results_docker/boucle-fermee-30.json

# Rapport consolide : valeurs mesurees a cote des valeurs publiees dans le memoire
rapport test-d: results_docker
	$(RUN_SIM) lab python scripts/report.py --out results_docker/rapport_memoire.md

memoire: build test test-a3 evaluate-30 test-a1w test-b1 test-b2 test-c test-c30 rapport
	@echo "Niveau 1 termine : results_docker/rapport_memoire.md"

# ---------------------------------------------------------------- niveau 2
test-solibra: results_docker
	$(RUN_SIM) lab python scripts/evaluate.py --plan solibra --seeds 42,1-29 --output results_docker/solibra-30.json

replay: results_docker
	$(RUN_SIM) lab python scripts/generer_replay_web.py --out results_docker/replay.html

demo: results_docker
	$(RUN_SIM) lab python scripts/generer_demo.py --out results_docker/demo.html
	@echo "Ouvrir results_docker/demo.html dans un navigateur"

gui:
	$(COMPOSE) --profile gui up -d --build gui
	@echo "Interface SUMO : http://localhost:6080/vnc.html?autoconnect=true&resize=scale"

test-secteurs: results_docker
	$(RUN_SIM) lab bash docker/test_secteurs.sh

evolue: build test-secteurs test-solibra replay demo
	@echo "Niveau 2 termine : demo.html, secteurs.json, solibra-30.json, replay.html ; en direct : make gui"

all-tests: memoire evolue

clean:
	$(COMPOSE) down --remove-orphans
