.PHONY: check-ffmpeg bootstrap up down logs api-dev fe-dev translate-dev tts-dev tts-vieneu write-dev ai-dev test

bootstrap:
	cp -n crawl-service/.env.example crawl-service/.env || true
	cp -n translate-service/.env.example translate-service/.env || true
	cp -n tts-service/.env.example tts-service/.env || true
	cp -n write-service/.env.example write-service/.env || true
	cp -n ai-service/.env.example ai-service/.env || true
	cp -n frontend/.env.example frontend/.env || true
	cd frontend && npm install
	cd crawl-service && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
	cd translate-service && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
	cd tts-service && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
	cd write-service && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
	cd ai-service && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
	@$(MAKE) --no-print-directory check-ffmpeg

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

tts-dev: check-ffmpeg
	cd tts-service && PYTHONPATH=src .venv/bin/uvicorn main:app --host 127.0.0.1 --port 8011 --reload

write-dev:
	cd write-service && PYTHONPATH=src .venv/bin/uvicorn main:app --host 127.0.0.1 --port 8012 --reload

ai-dev:
	cd ai-service && PYTHONPATH=src .venv/bin/uvicorn main:app --host 127.0.0.1 --port 8013 --reload

tts-vieneu:
	cd tts-service && .venv/bin/pip install -r requirements-vieneu.txt

fe-dev:
	cd frontend && npm run dev -- --host 127.0.0.1 --port 5173

test:
	cd crawl-service && PYTHONPATH=src .venv/bin/pytest -q
	cd translate-service && PYTHONPATH=src .venv/bin/pytest -q
	cd tts-service && PYTHONPATH=src .venv/bin/pytest -q
	cd write-service && PYTHONPATH=src .venv/bin/pytest -q
	cd ai-service && PYTHONPATH=src .venv/bin/pytest -q

# Chỉ cảnh báo, không tự cài (cần sudo, mỗi OS một lệnh). Docker image đã có ffmpeg.
check-ffmpeg:
	@if command -v ffmpeg >/dev/null 2>&1 && command -v ffprobe >/dev/null 2>&1; then \
		echo "ffmpeg: OK"; \
	else \
		echo "⚠ Không thấy ffmpeg/ffprobe — TTS xuất M4B sẽ lỗi (ZIP mp3 vẫn chạy)."; \
		echo "  Ubuntu/Debian: sudo apt install -y ffmpeg"; \
		echo "  macOS:         brew install ffmpeg"; \
		echo "  Windows:       winget install ffmpeg"; \
	fi
