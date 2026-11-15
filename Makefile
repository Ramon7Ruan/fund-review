.PHONY: help setup dev backend frontend check lint typecheck test test-backend test-frontend build probe clean

VENV := .venv
# 允许用 make check PY=/path/to/python 指定解释器（CI 与特殊环境用）
PY ?= $(VENV)/bin/python
# uv 可选：装了更快，没装自动回退到 python3 -m venv + pip
UV := $(shell command -v uv 2>/dev/null)

help:
	@echo "make setup    安装后端与前端依赖"
	@echo "make dev      同时启动后端(8000)与前端(5173)"
	@echo "make backend  只启动后端"
	@echo "make frontend 只启动前端"
	@echo "make check    类型检查 + 全部测试 + 前端构建（提 PR 前必跑）"
	@echo "make probe    用真实网络验证数据源（不进 CI）"

setup: $(VENV) web/node_modules
ifdef UV
	$(UV) pip install --python $(PY) -r requirements.txt -r requirements-dev.txt
else
	$(PY) -m pip install -r requirements.txt -r requirements-dev.txt
endif
	@echo "提示：真实抓数需要 akshare，执行 $(PY) -m pip install akshare"

$(VENV):
ifdef UV
	$(UV) venv $(VENV)
else
	python3 -m venv $(VENV)
endif

web/node_modules: web/package.json
	npm --prefix web install

dev:
	@trap 'kill 0' INT TERM; \
	$(PY) -m uvicorn api.app:app --reload --port 8000 & \
	npm --prefix web run dev; \
	wait

backend:
	$(PY) -m uvicorn api.app:app --reload --port 8000

frontend:
	npm --prefix web run dev

check: lint test build
	@echo "check 全部通过"

lint:
	$(PY) -m ruff check .
	$(PY) -m ruff format --check .

typecheck:
	$(PY) -m ruff check .

test: test-backend test-frontend

test-backend:
	$(PY) -m pytest

test-frontend:
	npm --prefix web run test -- --run

build:
	npm --prefix web run build

probe:
	$(PY) scripts/probe_sources.py

clean:
	rm -rf $(VENV) web/node_modules web/dist .pytest_cache .ruff_cache
	find . -name "__pycache__" -type d -not -path "./.venv/*" -exec rm -rf {} +
