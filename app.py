import os, time, requests
from typing import List, Dict
from urllib.parse import urlparse
from datetime import datetime, timezone

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# DB
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, ForeignKey, UniqueConstraint
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

# ===== env & constants =====
try:
    load_dotenv()
    NAVER_ID = os.getenv("NAVER_ID", "test_id")
    NAVER_SECRET = os.getenv("NAVER_SECRET", "test_secret")
except:
    NAVER_ID = "test_id"
    NAVER_SECRET = "test_secret"

API_URL = "https://openapi.naver.com/v1/search/blog.json"
DEFAULT_BRANCHES = [
    "카페드로잉 석촌호수점",
    "카페드로잉 동탄점",
    "카페드로잉 분당점",
    "청담장어마켓 동탄점",
    "청담장어마켓 송파점",
]

# ===== app & static =====
app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# ===== DB setup =====
# Vercel에서는 파일 시스템에 쓸 수 없으므로 메모리 DB 사용
engine = create_engine("sqlite:///:memory:", future=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
Base = declarative_base()

# Vercel 환경에서는 정적 데이터 사용
import os
IS_VERCEL = os.getenv("VERCEL") == "1"

class Branch(Base):
    __tablename__ = "branches"
    id   = Column(Integer, primary_key=True)
    name = Column(String(200), unique=True, index=True)

class Keyword(Base):
    __tablename__ = "keywords"
    id        = Column(Integer, primary_key=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), index=True)
    text      = Column(String(300), index=True)
    __table_args__ = (UniqueConstraint('branch_id','text', name='uq_branch_keyword'),)
    branch = relationship("Branch")

class Result(Base):
    __tablename__ = "results"
    id        = Column(Integer, primary_key=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), index=True, nullable=True)
    keyword   = Column(String(200), index=True)
    rank      = Column(Integer)
    blog_id   = Column(String(200), index=True)
    url       = Column(Text)
    fetched_at= Column(DateTime, default=lambda: datetime.now(timezone.utc))
    branch = relationship("Branch")

Base.metadata.create_all(engine)

def seed_branches():
    with SessionLocal() as s:
        # 메모리 DB이므로 매번 새로 생성
        s.query(Keyword).delete()  # 키워드 먼저 삭제
        s.query(Branch).delete()   # 지점 삭제
        
        # 기본 지점 생성
        branch_map = {}
        for name in DEFAULT_BRANCHES:
            branch = Branch(name=name)
            s.add(branch)
            s.flush()  # ID 생성
            branch_map[name] = branch.id
        
        # 기존 키워드 데이터 마이그레이션 (로컬에서만)
        try:
            import sqlite3
            old_conn = sqlite3.connect('data.db')
            old_cursor = old_conn.cursor()
            
            # 기존 지점명 매핑
            old_cursor.execute('SELECT id, name FROM branches')
            old_branches = {name: old_id for old_id, name in old_cursor.fetchall()}
            
            # 기존 키워드 가져오기
            old_cursor.execute('SELECT branch_id, text FROM keywords')
            old_keywords = old_cursor.fetchall()
            
            # 키워드 마이그레이션
            migrated_count = 0
            for old_branch_id, keyword_text in old_keywords:
                # 기존 지점명 찾기
                old_cursor.execute('SELECT name FROM branches WHERE id = ?', (old_branch_id,))
                old_branch_name = old_cursor.fetchone()
                if old_branch_name:
                    old_branch_name = old_branch_name[0]
                    # 새 지점 ID 찾기
                    new_branch_id = branch_map.get(old_branch_name)
                    if new_branch_id:
                        s.add(Keyword(branch_id=new_branch_id, text=keyword_text))
                        migrated_count += 1
            
            old_conn.close()
            print(f"기존 키워드 {migrated_count}개 마이그레이션 완료")
            
        except Exception as e:
            print(f"키워드 마이그레이션 실패 (로컬이 아닌 환경): {e}")
        
        s.commit()
        print(f"지점 {len(DEFAULT_BRANCHES)}개 생성 완료")

def update_branch_names():
    """기존 지점명을 새로운 형식으로 업데이트"""
    name_mapping = {
        "카페드로잉석촌호수점": "카페드로잉 석촌호수점",
        "카페드로잉동탄점": "카페드로잉 동탄점", 
        "카페드로잉분당점": "카페드로잉 분당점",
        "청담장어마켓동탄점": "청담장어마켓 동탄점",
    }
    
    with SessionLocal() as s:
        updated = 0
        for old_name, new_name in name_mapping.items():
            # 기존 이름의 지점이 있고, 새 이름의 지점이 없는 경우만 업데이트
            old_branch = s.query(Branch).filter(Branch.name == old_name).first()
            new_branch = s.query(Branch).filter(Branch.name == new_name).first()
            
            if old_branch and not new_branch:
                old_branch.name = new_name
                updated += 1
            elif old_branch and new_branch:
                # 새 이름이 이미 존재하면 기존 지점 삭제 (키워드도 함께)
                s.query(Keyword).filter(Keyword.branch_id == old_branch.id).delete()
                s.delete(old_branch)
                updated += 1
        if updated: 
            s.commit()
            print(f"지점명 {updated}개 업데이트 완료")

# 앱 시작 시 데이터 초기화
seed_branches()
update_branch_names()

# 앱 시작 후 데이터 확인
with SessionLocal() as s:
    branch_count = s.query(Branch).count()
    keyword_count = s.query(Keyword).count()
    print(f"앱 시작 완료 - 지점: {branch_count}개, 키워드: {keyword_count}개")

# ===== helpers =====
def top3_urls(keyword: str, sort: str = "sim") -> List[str]:
    r = requests.get(
        API_URL,
        headers={"X-Naver-Client-Id": NAVER_ID, "X-Naver-Client-Secret": NAVER_SECRET},
        params={"query": keyword, "display": 3, "sort": sort},
        timeout=10
    )
    if r.status_code != 200:
        try: err = r.json()
        except Exception: err = {"raw": r.text[:200]}
        raise HTTPException(502, f"Naver API error: {err}")
    data = r.json()
    return [it.get("link") for it in data.get("items", []) if it.get("link")]

def extract_blog_id(url: str) -> str:
    try:
        p = urlparse(url)
        parts = [x for x in p.path.split("/") if x]
        return parts[0] if parts else ""
    except Exception:
        return ""

# ===== routes =====
@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/guide", response_class=HTMLResponse)
def guide(request: Request):
    return templates.TemplateResponse("guide.html", {"request": request})

# 지점 목록
@app.get("/api/branches")
def get_branches():
    if IS_VERCEL:
        # Vercel에서는 정적 데이터 반환
        return [{"id": i+1, "name": name} for i, name in enumerate(DEFAULT_BRANCHES)]
    else:
        # 로컬에서는 DB 사용
        with SessionLocal() as s:
            items = s.query(Branch).order_by(Branch.name.asc()).all()
            
            # 데이터가 없으면 다시 초기화
            if not items:
                print("지점 데이터가 없어서 다시 초기화합니다...")
                seed_branches()
                items = s.query(Branch).order_by(Branch.name.asc()).all()
                print(f"재초기화 완료 - 지점 {len(items)}개")
            
            return [{"id": b.id, "name": b.name} for b in items]

# 지점 키워드 불러오기
@app.get("/api/keywords")
def get_keywords(branch_id: int = Query(..., ge=1)):
    if IS_VERCEL:
        # Vercel에서는 정적 데이터 반환
        print(f"Vercel 키워드 요청 - branch_id: {branch_id}")
        
        # 지점 ID로 지점명 찾기
        if 1 <= branch_id <= len(DEFAULT_BRANCHES):
            branch_name = DEFAULT_BRANCHES[branch_id - 1]
            print(f"지점명: {branch_name}")
            
            if branch_name == "청담장어마켓 송파점":
                print("청담장어마켓 송파점 키워드 반환")
                return {"branch_id": branch_id, "keywords": ["송파점", "장어마켓"]}
        
        print("키워드 없음")
        return {"branch_id": branch_id, "keywords": []}
    else:
        # 로컬에서는 DB 사용
        with SessionLocal() as s:
            items = s.query(Keyword).filter(Keyword.branch_id == branch_id).order_by(Keyword.id.asc()).all()
            return {"branch_id": branch_id, "keywords": [k.text for k in items]}

# 지점 키워드 저장(덮어쓰기)
@app.post("/api/keywords")
def save_keywords(payload: Dict):
    branch_id = payload.get("branch_id")
    kws = payload.get("keywords", [])
    if not branch_id: raise HTTPException(400, "branch_id 필요")
    with SessionLocal() as s:
        if not s.get(Branch, branch_id): raise HTTPException(404, "지점 없음")
        s.query(Keyword).filter(Keyword.branch_id == branch_id).delete()
        for t in kws:
            t = (t or "").strip()
            if t: s.add(Keyword(branch_id=branch_id, text=t))
        s.commit()
        return {"ok": True, "count": len(kws)}

# 개별 키워드 추가
@app.post("/api/keywords/add")
def add_keyword(payload: Dict):
    branch_id = payload.get("branch_id")
    keyword = payload.get("keyword", "").strip()
    if not branch_id: raise HTTPException(400, "branch_id 필요")
    if not keyword: raise HTTPException(400, "keyword 필요")
    
    with SessionLocal() as s:
        if not s.get(Branch, branch_id): raise HTTPException(404, "지점 없음")
        # 중복 체크
        existing = s.query(Keyword).filter(
            Keyword.branch_id == branch_id, 
            Keyword.text == keyword
        ).first()
        if existing: raise HTTPException(409, "이미 존재하는 키워드")
        
        s.add(Keyword(branch_id=branch_id, text=keyword))
        s.commit()
        return {"ok": True, "message": "키워드 추가 완료"}

# 개별 키워드 삭제
@app.delete("/api/keywords/delete")
def delete_keyword(payload: Dict):
    branch_id = payload.get("branch_id")
    keyword = payload.get("keyword", "").strip()
    if not branch_id: raise HTTPException(400, "branch_id 필요")
    if not keyword: raise HTTPException(400, "keyword 필요")
    
    with SessionLocal() as s:
        if not s.get(Branch, branch_id): raise HTTPException(404, "지점 없음")
        deleted = s.query(Keyword).filter(
            Keyword.branch_id == branch_id, 
            Keyword.text == keyword
        ).delete()
        s.commit()
        if deleted == 0: raise HTTPException(404, "키워드 없음")
        return {"ok": True, "message": "키워드 삭제 완료"}

# 지점 저장 키워드로 상위 3위씩 조회
@app.post("/api/run")
def run_saved(payload: Dict):
    branch_id = payload.get("branch_id")
    if not branch_id: raise HTTPException(400, "branch_id 필요")
    rows = []
    with SessionLocal() as s:
        b = s.get(Branch, branch_id)
        if not b: raise HTTPException(404, "지점 없음")
        kw_list = [k.text for k in s.query(Keyword).filter(Keyword.branch_id == branch_id).all()]
    for kw in kw_list:
        urls = top3_urls(kw, sort="sim")
        for idx, u in enumerate(urls, start=1):
            rows.append({
                "branch": branch_id,
                "keyword": kw,
                "rank": idx,
                "blog_id": extract_blog_id(u),
                "url": u
            })
        time.sleep(0.25)
    return rows
