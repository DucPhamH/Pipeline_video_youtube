.PHONY: bootstrap up down logs api-dev fe-dev test

bootstrap:
	cp -n crawl-service/.env.example crawl-service/.env || true
	cp -n frontend/.env.example frontend/.env || true
	cd frontend && npm install
	cd crawl-service && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

up:
	docker compose up --build -d

down:
	docker compose down

logs:
	docker compose logs -f --tail=100

api-dev:
	cd crawl-service/src && PYTHONPATH=. ../.venv/bin/uvicorn main:app --host 127.0.0.1 --port 8090 --reload

translate-dev:
	cd translate-service && PYTHONPATH=src .venv/bin/uvicorn main:app --host 127.0.0.1 --port 8010 --reload

fe-dev:
	cd frontend && npm run dev -- --host 127.0.0.1 --port 5173

test:
	cd crawl-service && PYTHONPATH=src .venv/bin/pytest -q
