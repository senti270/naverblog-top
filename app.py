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

# 네이버 API 설정
try:
    NAVER_ID = os.getenv("NAVER_ID")
    NAVER_SECRET = os.getenv("NAVER_SECRET")
    if not NAVER_ID or not NAVER_SECRET:
        raise ValueError("NAVER_ID 또는 NAVER_SECRET이 설정되지 않음")
except:
    NAVER_ID = "test_id"
    NAVER_SECRET = "test_secret"

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
    """Firebase에서 키워드 목록 가져오기 (기존 keywords 컬렉션 구조 사용)"""
    if not db:
        return []
    
    try:
        # stores 컬렉션에서 branch_id에 해당하는 storeId 찾기
        stores_ref = db.collection('stores')
        store_docs = stores_ref.where('id', '==', branch_id).limit(1).stream()
        store_doc = next(store_docs, None)
        
        if not store_doc:
            print(f"지점 ID {branch_id}에 해당하는 store를 찾을 수 없음")
            return []
        
        store_id = store_doc.id  # Firestore 문서 ID
        print(f"지점 ID {branch_id} -> Store ID: {store_id}")
        
        # keywords 컬렉션에서 해당 storeId의 키워드들 가져오기
        keywords_ref = db.collection('keywords')
        query = keywords_ref.where('storeId', '==', store_id).where('isActive', '==', True).order_by('order')
        docs = query.stream()
        
        keywords = []
        for doc in docs:
            data = doc.to_dict()
            keyword_text = data.get("keyword", "")
            if keyword_text:
                keywords.append(keyword_text)
        
        print(f"키워드 {len(keywords)}개 발견: {keywords}")
        return keywords
    except Exception as e:
        print(f"Firebase 키워드 조회 오류: {e}")
        return []

def add_keyword_to_firebase(branch_id: int, keyword: str) -> bool:
    """Firebase에 키워드 추가 (기존 keywords 컬렉션 구조 사용)"""
    if not db:
        return False
    
    try:
        # stores 컬렉션에서 branch_id에 해당하는 storeId 찾기
        stores_ref = db.collection('stores')
        store_docs = stores_ref.where('id', '==', branch_id).limit(1).stream()
        store_doc = next(store_docs, None)
        
        if not store_doc:
            print(f"지점 ID {branch_id}에 해당하는 store를 찾을 수 없음")
            return False
        
        store_id = store_doc.id
        
        # 중복 체크
        existing = db.collection('keywords').where('storeId', '==', store_id).where('keyword', '==', keyword).limit(1).stream()
        if list(existing):
            print(f"키워드 '{keyword}'가 이미 존재함")
            return False
        
        # 최대 order 값 찾기
        order_query = db.collection('keywords').where('storeId', '==', store_id).order_by('order', direction=firestore.Query.DESCENDING).limit(1)
        order_docs = list(order_query.stream())
        max_order = order_docs[0].to_dict().get('order', 0) if order_docs else 0
        
        # 키워드 추가
        doc_ref = db.collection('keywords').document()
        doc_ref.set({
            'keyword': keyword,
            'storeId': store_id,
            'isActive': True,
            'order': max_order + 1,
            'mobileVolume': 0,
            'monthlySearchVolume': 0,
            'pcVolume': 0,
            'createdAt': firestore.SERVER_TIMESTAMP,
            'updatedAt': firestore.SERVER_TIMESTAMP
        })
        
        print(f"키워드 '{keyword}' 추가 완료 (order: {max_order + 1})")
        return True
    except Exception as e:
        print(f"Firebase 키워드 추가 오류: {e}")
        return False

def delete_keyword_from_firebase(branch_id: int, keyword: str) -> bool:
    """Firebase에서 키워드 삭제 (기존 keywords 컬렉션 구조 사용)"""
    if not db:
        return False
    
    try:
        # stores 컬렉션에서 branch_id에 해당하는 storeId 찾기
        stores_ref = db.collection('stores')
        store_docs = stores_ref.where('id', '==', branch_id).limit(1).stream()
        store_doc = next(store_docs, None)
        
        if not store_doc:
            print(f"지점 ID {branch_id}에 해당하는 store를 찾을 수 없음")
            return False
        
        store_id = store_doc.id
        
        # 키워드 찾기 및 삭제 (isActive를 False로 변경)
        query = db.collection('keywords').where('storeId', '==', store_id).where('keyword', '==', keyword).where('isActive', '==', True)
        docs = query.stream()
        
        deleted = False
        for doc in docs:
            doc.reference.update({
                'isActive': False,
                'updatedAt': firestore.SERVER_TIMESTAMP
            })
            deleted = True
            print(f"키워드 '{keyword}' 비활성화 완료")
        
        return deleted
    except Exception as e:
        print(f"Firebase 키워드 삭제 오류: {e}")
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
    if db:
        # Firebase 사용
        branches = get_branches_from_firebase()
        if branches:
            return branches
    
    # Firebase가 없거나 데이터가 없으면 기본값 반환
    default_branches = [
        {"id": 1, "name": "청담장어마켓 송파점"},
        {"id": 2, "name": "청담장어마켓 동탄점"},
        {"id": 3, "name": "카페드로잉 석촌호수점"},
        {"id": 4, "name": "카페드로잉 분당점"},
        {"id": 5, "name": "카페드로잉 동탄점"}
    ]
    return default_branches

@app.get("/api/keywords")
def get_keywords(branch_id: int = Query(..., ge=1)):
    """지점 키워드 조회"""
    if db:
        # Firebase 사용
        keywords = get_keywords_from_firebase(branch_id)
        return {"branch_id": branch_id, "keywords": keywords}
    
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
    
    success = add_keyword_to_firebase(branch_id, keyword)
    if success:
        return {"ok": True, "message": "키워드가 추가되었습니다."}
    else:
        return {"ok": False, "message": "키워드 추가에 실패했습니다. (중복 또는 오류)"}

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
