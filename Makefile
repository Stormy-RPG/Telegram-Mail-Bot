# Copyright (C) 2026 Stormy-RPG
# SPDX-License-Identifier: AGPL-3.0-only
dc = docker compose

up: build
	$(dc) up -d

build:
	$(dc) build

down:
	$(dc) down

stop:
	$(dc) stop
	
restart:
	$(dc) restart

update:
	git pull
	$(dc) build
	$(dc) up -d

logs: 
	$(dc) logs

logs-file: 
	$(dc) logs > compose.log