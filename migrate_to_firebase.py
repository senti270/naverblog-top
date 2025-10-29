#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sqlite3
import json
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime

def migrate_to_firebase():
    """기존 SQLite 데이터를 Firebase로 마이그레이션"""
    
    # Firebase 초기화 (로컬에서 실행)
    try:
        # Firebase 서비스 계정 키 파일 경로
        cred = credentials.Certificate("firebase-service-account.json")
        firebase_admin.initialize_app(cred)
        db = firestore.client()
        print("Firebase 초기화 성공")
    except Exception as e:
        print(f"Firebase 초기화 실패: {e}")
        return
    
    # SQLite에서 데이터 읽기
    try:
        conn = sqlite3.connect('data.db')
        cursor = conn.cursor()
        
        # 지점 데이터 읽기
        cursor.execute("SELECT id, name FROM branches ORDER BY id")
        branches = cursor.fetchall()
        print(f"지점 데이터 {len(branches)}개 발견")
        
        # 키워드 데이터 읽기
        cursor.execute("""
            SELECT b.id, b.name, k.text 
            FROM keywords k 
            JOIN branches b ON k.branch_id = b.id 
            ORDER BY b.id, k.id
        """)
        keywords = cursor.fetchall()
        print(f"키워드 데이터 {len(keywords)}개 발견")
        
        conn.close()
        
    except Exception as e:
        print(f"SQLite 읽기 오류: {e}")
        return
    
    # Firebase에 데이터 쓰기
    try:
        # 지점 데이터를 stores 컬렉션에 추가
        for branch_id, name in branches:
            doc_ref = db.collection('stores').document()
            doc_ref.set({
                'id': branch_id,
                'name': name,
                'migrated_at': datetime.now()
            })
            print(f"지점 추가: {name} (ID: {branch_id})")
        
        # 키워드 데이터를 keywords 컬렉션에 추가
        for branch_id, branch_name, keyword in keywords:
            doc_ref = db.collection('keywords').document()
            doc_ref.set({
                'branch_id': branch_id,
                'text': keyword,
                'created_at': datetime.now()
            })
            print(f"키워드 추가: {branch_name} - {keyword}")
        
        print("마이그레이션 완료!")
        
    except Exception as e:
        print(f"Firebase 쓰기 오류: {e}")

if __name__ == "__main__":
    migrate_to_firebase()
