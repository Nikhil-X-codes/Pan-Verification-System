SHELL := bash

COMPOSE = docker compose -f deploy/docker-compose.yml
TEST_COMPOSE = docker compose -f deploy/compose.test.yml

.PHONY: up down test load

up:
	$(COMPOSE) up --build -d --wait

down:
	$(COMPOSE) down

test:
	@set -e; trap '$(TEST_COMPOSE) down --volumes --remove-orphans' EXIT; $(TEST_COMPOSE) build; $(TEST_COMPOSE) run --rm backend-test; $(TEST_COMPOSE) run --rm frontend-test

load:
	$(COMPOSE) exec -T backend1 python loadtest.py --url http://gateway:8080/api --output /tmp/load-result.json
