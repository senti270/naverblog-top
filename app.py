#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
from typing import Dict, List, Optional
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import requests
from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials, firestore

# ===== 환경변수 =====
load_dotenv()

# 네이버 API 설정 (indentation 이슈 방지를 위해 단순화)
NAVER_ID = os.getenv("NAVER_ID") or "test_id"
NAVER_SECRET = os.getenv("NAVER_SECRET") or "test_secret"

API_URL = "https://openapi.naver.com/v1/search/blog.json"

# Firebase 설정
try:
    # Firebase 서비스 계정 키 (환경변수에서 JSON 문자열로 읽기)
    firebase_config = os.getenv("FIREBASE_CONFIG")
    if firebase_config:
        cred = credentials.Certificate(json.loads(firebase_config))
        firebase_admin.initialize_app(cred)
        db = firestore.client()
        print("Firebase 초기화 성공")
    else:
        print("FIREBASE_CONFIG 환경변수가 설정되지 않음 - Firebase 비활성화")
        db = None
except Exception as e:
    print(f"Firebase 초기화 실패: {e}")
    db = None

# ===== app & static =====
app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# favicon (avoid 500 when icon missing)
from fastapi.responses import FileResponse, Response
@app.get("/favicon.ico", include_in_schema=False)
async def favicon_handler():
    icon_path = os.path.join("static", "favicon.ico")
    if os.path.exists(icon_path):
        return FileResponse(icon_path)
    return Response(status_code=204)

# ===== Pydantic models =====
class KeywordAdd(BaseModel):
    branch_id: int
    keyword: str

class KeywordDelete(BaseModel):
    branch_id: int
    keyword: str

# ===== 헬퍼 함수 =====
def search_naver_blog(query: str, display: int = 3) -> List[Dict]:
    """네이버 블로그 검색"""
    headers = {
        "X-Naver-Client-Id": NAVER_ID,
        "X-Naver-Client-Secret": NAVER_SECRET,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    params = {
        "query": query,
        "display": display,
        "sort": "sim"  # 유사도 정렬 고정
    }
    
    try:
        res = requests.get(API_URL, headers=headers, params=params, timeout=10)
        res.raise_for_status()
        data = res.json()
        
        items = []
        for item in data.get("items", []):
            items.append({
                "title": item["title"].replace("<b>", "").replace("</b>", ""),
                "link": item["link"],
                "description": item["description"].replace("<b>", "").replace("</b>", ""),
                "bloggername": item["bloggername"],
                "postdate": item["postdate"]
            })
        
        return items
    except Exception as e:
        print(f"네이버 API 호출 오류: {e}")
        return []

# ===== Firebase 헬퍼 함수 =====
def get_branches_from_firebase() -> List[Dict]:
    """Firebase에서 지점 목록 가져오기 (stores 컬렉션 사용)"""
    if not db:
        return []
    
    try:
        stores_ref = db.collection('stores')
        docs = stores_ref.order_by('id').stream()
        
        branches = []
        for doc in docs:
            data = doc.to_dict()
            branches.append({
                "id": data.get("id"),
                "name": data.get("name")
            })
        
        return branches
    except Exception as e:
        print(f"Firebase 지점 조회 오류: {e}")
        return []

def get_keywords_from_firebase(branch_id: int) -> List[str]:
    """Firebase에서 키워드 목록 가져오기 (stores 문서의 keywords 배열 사용)"""
    if not db:
        print("Firebase DB가 초기화되지 않음")
        return []
    
    try:
        print(f"=== 키워드 조회 시작 - branch_id: {branch_id} ===")
        
        # stores 컬렉션에서 branch_id에 해당하는 문서 찾기
        stores_ref = db.collection('stores')
        store_docs = stores_ref.where('id', '==', branch_id).limit(1).stream()
        store_doc = next(store_docs, None)
        
        if not store_doc:
            print(f"❌ 지점 ID {branch_id}에 해당하는 store를 찾을 수 없음")
            return []
        
        store_data = store_doc.to_dict()
        store_name = store_data.get('name', 'Unknown')
        keywords = store_data.get('keywords', [])
        
        print(f"✅ 지점 ID {branch_id} -> Name: {store_name}")
        print(f"✅ 키워드 {len(keywords)}개 발견: {keywords}")
        
        return keywords
    except Exception as e:
        print(f"❌ Firebase 키워드 조회 오류: {e}")
        import traceback
        traceback.print_exc()
        return []

def add_keyword_to_firebase(branch_id: int, keyword: str) -> bool:
    """Firebase에 키워드 추가 (stores 문서의 keywords 배열 사용)"""
    if not db:
        print("Firebase DB가 초기화되지 않음")
        return False
    
    try:
        print(f"=== 키워드 추가 시작 - branch_id: {branch_id}, keyword: '{keyword}' ===")
        
        # stores 컬렉션에서 branch_id에 해당하는 문서 찾기
        stores_ref = db.collection('stores')
        store_docs = stores_ref.where('id', '==', branch_id).limit(1).stream()
        store_doc = next(store_docs, None)
        
        if not store_doc:
            print(f"❌ 지점 ID {branch_id}에 해당하는 store를 찾을 수 없음")
            return False
        
        store_data = store_doc.to_dict()
        store_name = store_data.get('name', 'Unknown')
        current_keywords = store_data.get('keywords', [])
        
        print(f"✅ 지점 ID {branch_id} -> Name: {store_name}")
        print(f"현재 키워드: {current_keywords}")
        
        # 중복 체크
        if keyword in current_keywords:
            print(f"❌ 키워드 '{keyword}'가 이미 존재함")
            return False
        
        # 키워드 추가
        new_keywords = current_keywords + [keyword]
        store_doc.reference.update({
            'keywords': new_keywords,
            'updatedAt': firestore.SERVER_TIMESTAMP
        })
        
        print(f"✅ 키워드 '{keyword}' 추가 완료")
        print(f"새 키워드 목록: {new_keywords}")
        return True
    except Exception as e:
        print(f"❌ Firebase 키워드 추가 오류: {e}")
        import traceback
        traceback.print_exc()
        return False

def delete_keyword_from_firebase(branch_id: int, keyword: str) -> bool:
    """Firebase에서 키워드 삭제 (stores 문서의 keywords 배열 사용)"""
    if not db:
        print("Firebase DB가 초기화되지 않음")
        return False
    
    try:
        print(f"=== 키워드 삭제 시작 - branch_id: {branch_id}, keyword: '{keyword}' ===")
        
        # stores 컬렉션에서 branch_id에 해당하는 문서 찾기
        stores_ref = db.collection('stores')
        store_docs = stores_ref.where('id', '==', branch_id).limit(1).stream()
        store_doc = next(store_docs, None)
        
        if not store_doc:
            print(f"❌ 지점 ID {branch_id}에 해당하는 store를 찾을 수 없음")
            return False
        
        store_data = store_doc.to_dict()
        store_name = store_data.get('name', 'Unknown')
        current_keywords = store_data.get('keywords', [])
        
        print(f"✅ 지점 ID {branch_id} -> Name: {store_name}")
        print(f"현재 키워드: {current_keywords}")
        
        # 키워드 삭제
        if keyword not in current_keywords:
            print(f"❌ 키워드 '{keyword}'를 찾을 수 없음")
            return False
        
        new_keywords = [kw for kw in current_keywords if kw != keyword]
        store_doc.reference.update({
            'keywords': new_keywords,
            'updatedAt': firestore.SERVER_TIMESTAMP
        })
        
        print(f"✅ 키워드 '{keyword}' 삭제 완료")
        print(f"새 키워드 목록: {new_keywords}")
        return True
    except Exception as e:
        print(f"❌ Firebase 키워드 삭제 오류: {e}")
        import traceback
        traceback.print_exc()
        return False

# ===== 라우트 =====
@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/guide", response_class=HTMLResponse)
async def guide(request: Request):
    return templates.TemplateResponse("guide.html", {"request": request})

@app.get("/api/branches")
def get_branches():
    """지점 목록 조회"""
    if not db:
        return {"error": "Firebase가 설정되지 않았습니다. 관리자에게 문의하세요."}
    
    # Firebase 사용
    branches = get_branches_from_firebase()
    if not branches:
        return {"error": "저장된 지점이 없습니다. Firebase stores 컬렉션에 지점 데이터를 추가해주세요."}
    
    return branches

@app.get("/api/keywords")
def get_keywords(branch_id: int = Query(..., ge=1)):
    """지점 키워드 조회"""
    if db:
        # Firebase 사용
        try:
            keywords = get_keywords_from_firebase(branch_id)
            return {"branch_id": branch_id, "keywords": keywords}
        except Exception as e:
            return {"branch_id": branch_id, "keywords": [], "message": f"키워드 조회 실패: {str(e)}"}
    
    # Firebase가 없으면 기본값 반환
    if branch_id == 1:  # 청담장어마켓 송파점
        return {"branch_id": branch_id, "keywords": ["송파점", "장어마켓"]}
    
    return {"branch_id": branch_id, "keywords": []}

@app.post("/api/keywords/add")
def add_keyword(payload: KeywordAdd):
    """키워드 추가"""
    if not db:
        return {"ok": False, "message": "Firebase가 설정되지 않았습니다."}
    
    branch_id = payload.branch_id
    keyword = payload.keyword.strip()
    
    if not keyword:
        raise HTTPException(400, "키워드를 입력해주세요.")
    
    # 상세 에러 메시지 제공
    try:
        stores_ref = db.collection('stores')
        store_docs = stores_ref.where('id', '==', branch_id).limit(1).stream()
        store_doc = next(store_docs, None)
        if not store_doc:
            return {"ok": False, "message": f"지점 ID {branch_id}를 찾을 수 없습니다. stores 컬렉션의 id 필드를 확인하세요."}

        # 배열 기반 현재 키워드 확인
        current_keywords = store_doc.to_dict().get('keywords', [])
        if keyword in current_keywords:
            return {"ok": True, "message": "이미 존재하는 키워드입니다.", "keywords": current_keywords}

        added = add_keyword_to_firebase(branch_id, keyword)
        if added:
            # 최신 목록 반환
            refreshed = db.collection('stores').where('id', '==', branch_id).limit(1).stream()
            refreshed_doc = next(refreshed, None)
            keywords_now = refreshed_doc.to_dict().get('keywords', []) if refreshed_doc else []
            return {"ok": True, "message": "키워드가 추가되었습니다.", "keywords": keywords_now}
        return {"ok": False, "message": "추가 중 알 수 없는 오류가 발생했습니다."}
    except Exception as e:
        return {"ok": False, "message": f"추가 실패: {str(e)}"}

@app.delete("/api/keywords/delete")
def delete_keyword(payload: KeywordDelete):
    """키워드 삭제"""
    if not db:
        return {"ok": False, "message": "Firebase가 설정되지 않았습니다."}
    
    branch_id = payload.branch_id
    keyword = payload.keyword.strip()
    
    if not keyword:
        raise HTTPException(400, "키워드를 입력해주세요.")
    
    success = delete_keyword_from_firebase(branch_id, keyword)
    if success:
        return {"ok": True, "message": "키워드가 삭제되었습니다."}
    else:
        return {"ok": False, "message": "키워드를 찾을 수 없습니다."}

@app.post("/api/run")
def run_query(payload: Dict):
    """네이버 블로그 검색"""
    keywords = payload.get("keywords", [])
    if not keywords:
        raise HTTPException(400, "키워드를 입력해주세요.")
    
    try:
        results = []
        for kw in keywords:
            items = search_naver_blog(kw)
            results.extend(items)
        
        return {"ok": True, "results": results}
    except Exception as e:
        raise HTTPException(500, f"검색 실패: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
