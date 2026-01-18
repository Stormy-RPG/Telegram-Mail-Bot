# Copyright (C) 2026 Stormy-RPG
# SPDX-License-Identifier: AGPL-3.0-only
FROM python:3.13-slim

WORKDIR /app

COPY ./requirements.txt /app/requirements.txt

RUN apt update
RUN pip install --upgrade --root-user-action=ignore pip
RUN pip install --no-cache-dir --upgrade --root-user-action=ignore -r /app/requirements.txt

COPY . .

EXPOSE 4022
ENTRYPOINT ["python", "main.py"]