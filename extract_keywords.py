#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sqlite3
import json

def extract_keywords_from_db():
    """기존 data.db에서 키워드 데이터 추출"""
    try:
        conn = sqlite3.connect('data.db')
        cursor = conn.cursor()
        
        # 지점 데이터 가져오기
        cursor.execute("SELECT id, name FROM branches ORDER BY id")
        branches = cursor.fetchall()
        print("=== 지점 데이터 ===")
        for branch_id, name in branches:
            print(f"ID: {branch_id}, 이름: {name}")
        
        # 키워드 데이터 가져오기
        cursor.execute("""
            SELECT b.name, k.text 
            FROM keywords k 
            JOIN branches b ON k.branch_id = b.id 
            ORDER BY b.id, k.id
        """)
        keywords = cursor.fetchall()
        
        print("\n=== 키워드 데이터 ===")
        branch_keywords = {}
        for branch_name, keyword in keywords:
            if branch_name not in branch_keywords:
                branch_keywords[branch_name] = []
            branch_keywords[branch_name].append(keyword)
            print(f"{branch_name}: {keyword}")
        
        # JSON으로 저장
        with open('extracted_keywords.json', 'w', encoding='utf-8') as f:
            json.dump(branch_keywords, f, ensure_ascii=False, indent=2)
        
        print(f"\n키워드 데이터가 extracted_keywords.json에 저장되었습니다.")
        print(f"총 {len(branch_keywords)}개 지점의 키워드가 추출되었습니다.")
        
        conn.close()
        return branch_keywords
        
    except Exception as e:
        print(f"데이터베이스 읽기 오류: {e}")
        return {}

if __name__ == "__main__":
    extract_keywords_from_db()
