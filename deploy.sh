#!/bin/bash

# 네이버 블로그 상위 3 URL 서비스 배포 스크립트

echo "🚀 네이버 블로그 상위 3 URL 서비스 배포를 시작합니다..."

# 환경변수 파일 확인
if [ ! -f .env ]; then
    echo "❌ .env 파일이 없습니다. .env.example을 참고하여 .env 파일을 생성해주세요."
    exit 1
fi

# Docker 설치 확인
if ! command -v docker &> /dev/null; then
    echo "❌ Docker가 설치되지 않았습니다. Docker를 먼저 설치해주세요."
    exit 1
fi

# Docker Compose 설치 확인
if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose가 설치되지 않았습니다. Docker Compose를 먼저 설치해주세요."
    exit 1
fi

echo "📦 Docker 이미지를 빌드합니다..."
docker-compose build

echo "🔄 기존 컨테이너를 중지하고 제거합니다..."
docker-compose down

echo "🚀 새로운 컨테이너를 시작합니다..."
docker-compose up -d

echo "⏳ 서비스가 시작될 때까지 잠시 기다립니다..."
sleep 10

# 헬스체크
echo "🔍 서비스 상태를 확인합니다..."
if curl -f http://localhost:8000/api/branches > /dev/null 2>&1; then
    echo "✅ 서비스가 성공적으로 배포되었습니다!"
    echo "🌐 접속 URL: http://localhost:8000"
else
    echo "❌ 서비스 시작에 실패했습니다. 로그를 확인해주세요."
    docker-compose logs
    exit 1
fi

echo "📊 서비스 상태:"
docker-compose ps
