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
        print("Firebase DB가 초기화되지 않음")
        return []
    
    try:
        print(f"=== 키워드 조회 시작 - branch_id: {branch_id} ===")
        
        # stores 컬렉션에서 branch_id에 해당하는 storeId 찾기
        stores_ref = db.collection('stores')
        print(f"stores 컬렉션 조회 중...")
        store_docs = stores_ref.where('id', '==', branch_id).limit(1).stream()
        store_doc = next(store_docs, None)
        
        if not store_doc:
            print(f"❌ 지점 ID {branch_id}에 해당하는 store를 찾을 수 없음")
            # 모든 stores 문서 확인
            all_stores = stores_ref.stream()
            print("현재 stores 컬렉션의 모든 문서:")
            for doc in all_stores:
                data = doc.to_dict()
                print(f"  - ID: {data.get('id')}, Name: {data.get('name')}, DocID: {doc.id}")
            return []
        
        store_id = store_doc.id  # Firestore 문서 ID
        store_data = store_doc.to_dict()
        print(f"✅ 지점 ID {branch_id} -> Store ID: {store_id}, Name: {store_data.get('name')}")
        
        # keywords 컬렉션에서 해당 storeId의 키워드들 가져오기 (신규 스키마)
        keywords_ref = db.collection('keywords')
        print(f"keywords 컬렉션에서 storeId={store_id} 조회 중...")
        query = keywords_ref.where('storeId', '==', store_id).where('isActive', '==', True).order_by('order')
        docs = list(query.stream())
        
        print(f"Firebase에서 {len(docs)}개 문서 발견")
        
        keywords = []
        for i, doc in enumerate(docs):
            data = doc.to_dict()
            keyword_text = data.get("keyword", "")
            is_active = data.get("isActive", False)
            print(f"  문서 {i+1}: keyword='{keyword_text}', isActive={is_active}")
            if keyword_text and is_active:
                keywords.append(keyword_text)

        # 레거시 스키마 지원: branch_id + text 형태 문서도 함께 읽음
        try:
            legacy_query = db.collection('keywords').where('branch_id', '==', branch_id)
            legacy_docs = list(legacy_query.stream())
            print(f"레거시 키워드 문서 {len(legacy_docs)}개 발견")
            for j, ldoc in enumerate(legacy_docs):
                ldata = ldoc.to_dict()
                ltext = ldata.get('text')
                if ltext and ltext not in keywords:
                    keywords.append(ltext)
                    print(f"  레거시 문서 {j+1}: text='{ltext}' 포함")
        except Exception as le:
            print(f"레거시 키워드 조회 중 오류: {le}")
        
        print(f"✅ 최종 키워드 {len(keywords)}개: {keywords}")
        return keywords
    except Exception as e:
        print(f"❌ Firebase 키워드 조회 오류: {e}")
        import traceback
        traceback.print_exc()
        return []

def add_keyword_to_firebase(branch_id: int, keyword: str) -> bool:
    """Firebase에 키워드 추가 (기존 keywords 컬렉션 구조 사용)"""
    if not db:
        print("Firebase DB가 초기화되지 않음")
        return False
    
    try:
        print(f"=== 키워드 추가 시작 - branch_id: {branch_id}, keyword: '{keyword}' ===")
        
        # stores 컬렉션에서 branch_id에 해당하는 storeId 찾기
        stores_ref = db.collection('stores')
        store_docs = stores_ref.where('id', '==', branch_id).limit(1).stream()
        store_doc = next(store_docs, None)
        
        if not store_doc:
            print(f"❌ 지점 ID {branch_id}에 해당하는 store를 찾을 수 없음")
            return False
        
        store_id = store_doc.id
        store_data = store_doc.to_dict()
        print(f"✅ 지점 ID {branch_id} -> Store ID: {store_id}, Name: {store_data.get('name')}")
        
        # 중복/비활성 여부 체크 (신규 스키마)
        print(f"중복 체크 중... storeId={store_id}, keyword='{keyword}'")
        same_keyword_docs = list(
            db.collection('keywords')
              .where('storeId', '==', store_id)
              .where('keyword', '==', keyword)
              .stream()
        )
        # 활성 문서가 있으면 중복 처리
        for d in same_keyword_docs:
            data = d.to_dict()
            if data.get('isActive') is True:
                print(f"❌ 키워드 '{keyword}'가 이미 활성 상태로 존재함")
                return False
        # 비활성 문서가 있으면 재활성화 처리
        for d in same_keyword_docs:
            data = d.to_dict()
            if data.get('isActive') is False:
                print(f"♻️ 비활성 상태 키워드 재활성화: '{keyword}'")
                # 최대 order 계산
                order_query = db.collection('keywords').where('storeId', '==', store_id).order_by('order', direction=firestore.Query.DESCENDING).limit(1)
                order_docs = list(order_query.stream())
                max_order = order_docs[0].to_dict().get('order', 0) if order_docs else 0
                d.reference.update({
                    'isActive': True,
                    'order': data.get('order') or (max_order + 1),
                    'updatedAt': firestore.SERVER_TIMESTAMP
                })
                print(f"✅ 재활성화 완료 (order: {data.get('order') or (max_order + 1)})")
                return True
        # 레거시 스키마 문서가 있으면 마이그레이션 후 사용
        legacy_dups = list(
            db.collection('keywords')
              .where('branch_id', '==', branch_id)
              .where('text', '==', keyword)
              .stream()
        )
        if legacy_dups:
            print(f"🧩 레거시 문서 {len(legacy_dups)}개 발견 → 신규 스키마로 업데이트")
            # 최대 order 계산
            order_query = db.collection('keywords').where('storeId', '==', store_id).order_by('order', direction=firestore.Query.DESCENDING).limit(1)
            order_docs = list(order_query.stream())
            max_order = order_docs[0].to_dict().get('order', 0) if order_docs else 0
            for d in legacy_dups:
                d.reference.update({
                    'keyword': keyword,
                    'storeId': store_id,
                    'isActive': True,
                    'order': max_order + 1,
                    'mobileVolume': 0,
                    'monthlySearchVolume': 0,
                    'pcVolume': 0,
                    'createdAt': firestore.SERVER_TIMESTAMP,
                    'updatedAt': firestore.SERVER_TIMESTAMP,
                })
            print("✅ 레거시 문서 업데이트 완료")
            return True

        print(f"✅ 동일 키워드 문서 없음 → 신규 생성 진행")
        
        # 최대 order 값 찾기
        print(f"최대 order 값 찾는 중...")
        order_query = db.collection('keywords').where('storeId', '==', store_id).order_by('order', direction=firestore.Query.DESCENDING).limit(1)
        order_docs = list(order_query.stream())
        max_order = order_docs[0].to_dict().get('order', 0) if order_docs else 0
        print(f"최대 order: {max_order}, 새 order: {max_order + 1}")
        
        # 키워드 추가
        print(f"키워드 추가 중...")
        doc_ref = db.collection('keywords').document()
        doc_data = {
            'keyword': keyword,
            'storeId': store_id,
            'isActive': True,
            'order': max_order + 1,
            'mobileVolume': 0,
            'monthlySearchVolume': 0,
            'pcVolume': 0,
            'createdAt': firestore.SERVER_TIMESTAMP,
            'updatedAt': firestore.SERVER_TIMESTAMP
        }
        print(f"추가할 데이터: {doc_data}")
        doc_ref.set(doc_data)
        
        print(f"✅ 키워드 '{keyword}' 추가 완료 (order: {max_order + 1})")
        return True
    except Exception as e:
        print(f"❌ Firebase 키워드 추가 오류: {e}")
        import traceback
        traceback.print_exc()
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

        store_id = store_doc.id

        # 중복 체크
        existing = db.collection('keywords').where('storeId', '==', store_id).where('keyword', '==', keyword).limit(1).stream()
        if list(existing):
            return {"ok": False, "message": "이미 존재하는 키워드입니다."}

        added = add_keyword_to_firebase(branch_id, keyword)
        if added:
            return {"ok": True, "message": "키워드가 추가되었습니다."}
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
