# 네이버 블로그 상위 3 URL 서비스 배포 스크립트 (PowerShell)

Write-Host "🚀 네이버 블로그 상위 3 URL 서비스 배포를 시작합니다..." -ForegroundColor Green

# 환경변수 파일 확인
if (-not (Test-Path ".env")) {
    Write-Host "❌ .env 파일이 없습니다. .env.example을 참고하여 .env 파일을 생성해주세요." -ForegroundColor Red
    exit 1
}

# Docker 설치 확인
try {
    docker --version | Out-Null
} catch {
    Write-Host "❌ Docker가 설치되지 않았습니다. Docker를 먼저 설치해주세요." -ForegroundColor Red
    exit 1
}

# Docker Compose 설치 확인
try {
    docker-compose --version | Out-Null
} catch {
    Write-Host "❌ Docker Compose가 설치되지 않았습니다. Docker Compose를 먼저 설치해주세요." -ForegroundColor Red
    exit 1
}

Write-Host "📦 Docker 이미지를 빌드합니다..." -ForegroundColor Yellow
docker-compose build

Write-Host "🔄 기존 컨테이너를 중지하고 제거합니다..." -ForegroundColor Yellow
docker-compose down

Write-Host "🚀 새로운 컨테이너를 시작합니다..." -ForegroundColor Yellow
docker-compose up -d

Write-Host "⏳ 서비스가 시작될 때까지 잠시 기다립니다..." -ForegroundColor Yellow
Start-Sleep -Seconds 10

# 헬스체크
Write-Host "🔍 서비스 상태를 확인합니다..." -ForegroundColor Yellow
try {
    $response = Invoke-WebRequest -Uri "http://localhost:8000/api/branches" -UseBasicParsing
    if ($response.StatusCode -eq 200) {
        Write-Host "✅ 서비스가 성공적으로 배포되었습니다!" -ForegroundColor Green
        Write-Host "🌐 접속 URL: http://localhost:8000" -ForegroundColor Cyan
    } else {
        throw "서비스 응답 오류"
    }
} catch {
    Write-Host "❌ 서비스 시작에 실패했습니다. 로그를 확인해주세요." -ForegroundColor Red
    docker-compose logs
    exit 1
}

Write-Host "📊 서비스 상태:" -ForegroundColor Yellow
docker-compose ps
