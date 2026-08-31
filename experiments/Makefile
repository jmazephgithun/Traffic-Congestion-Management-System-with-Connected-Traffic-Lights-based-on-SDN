.PHONY: build test smoke test-a1 test-a2 test-a3 test-b1 test-b2 test-b3 test-c test-d all-tests evaluate evaluate-30 clean

COMPOSE := docker compose

build:
	$(COMPOSE) build

test:
	$(COMPOSE) run --rm tests

smoke:
	mkdir -p results_docker
	$(COMPOSE) run --rm lab bash docker/tests_phase_b.sh

evaluate:
	mkdir -p results_docker
	$(COMPOSE) run --rm -e SKIP_NETWORK=1 lab python scripts/evaluate.py --seeds 42 --output results_docker/evaluation.json

evaluate-30:
	mkdir -p results_docker
	$(COMPOSE) run --rm -e SKIP_NETWORK=1 lab python scripts/evaluate.py --seeds 42,1-29 --output results_docker/evaluation-30.json

test-a1:
	mkdir -p results_docker
	$(COMPOSE) run --rm -e SKIP_NETWORK=1 lab python scripts/evaluate.py --mode baseline --seeds 42 --output results_docker/a1-baseline.json

test-a2:
	mkdir -p results_docker
	$(COMPOSE) run --rm -e SKIP_NETWORK=1 lab python scripts/evaluate.py --mode adaptive --seeds 42 --output results_docker/a2-adaptive.json

test-a3: evaluate

test-b1:
	mkdir -p results_docker
	$(COMPOSE) run --rm lab bash docker/network_scenario.sh noqos

test-b2:
	mkdir -p results_docker
	$(COMPOSE) run --rm lab bash docker/network_scenario.sh qos

test-b3: test-b1 test-b2
	@echo "Comparer results_docker/ctrl_noqos.json et ctrl_qos.json"

test-c:
	mkdir -p results_docker
	$(COMPOSE) run --rm lab bash docker/test_closed_loop.sh

test-d: test-a3 test-b3 test-c
	$(COMPOSE) run --rm -e SKIP_NETWORK=1 lab python scripts/report.py --out results_docker/report.md

all-tests: build test test-a1 test-a2 test-a3 test-b1 test-b2 test-c test-d

clean:
	$(COMPOSE) down --remove-orphans
