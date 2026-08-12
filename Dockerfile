# MOVE-AI 선사 UI — 단일 컨테이너 배포
#
# 프론트엔드를 빌드해 백엔드가 함께 서빙하므로 접속 URL이 하나다.
# Render / Railway / Fly.io 어디서든 동일하게 동작한다.

# ---------------------------------------------------------------- 1) 프론트 빌드
FROM node:22-slim AS frontend

WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci

COPY frontend/ ./
RUN npm run build


# ------------------------------------------------------------------ 2) 실행 이미지
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ ./backend/
# MILP 결과 파일이 모든 수치의 정본이므로 이미지에 포함한다.
COPY optimizer/ ./optimizer/
COPY --from=frontend /app/frontend/dist ./frontend/dist

# 실제 선사 배포이므로 개발용 carrier selector 를 노출하지 않는다.
ENV DEV_MODE=false \
    FRONTEND_DIST_DIR=/app/frontend/dist

WORKDIR /app/backend

EXPOSE 8000

# 플랫폼이 주입하는 $PORT 를 우선 사용한다 (Render/Railway 공통).
CMD ["sh", "-c", "python -m uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000}"]
