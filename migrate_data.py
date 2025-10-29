#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
기존 SQLite 데이터를 확인하고 마이그레이션하는 스크립트
"""
import sqlite3
import json

def check_existing_data():
    """기존 데이터 확인"""
    conn = sqlite3.connect('data.db')
    cursor = conn.cursor()
    
    # 지점 데이터
    cursor.execute('SELECT id, name FROM branches')
    branches = cursor.fetchall()
    print("=== 기존 지점 데이터 ===")
    for branch_id, name in branches:
        print(f"ID: {branch_id}, 이름: {name}")
    
    # 키워드 데이터
    cursor.execute('SELECT id, branch_id, text FROM keywords')
    keywords = cursor.fetchall()
    print("\n=== 기존 키워드 데이터 ===")
    for kw_id, branch_id, text in keywords:
        print(f"ID: {kw_id}, 지점ID: {branch_id}, 키워드: {text}")
    
    # 지점별 키워드 정리
    branch_keywords = {}
    for kw_id, branch_id, text in keywords:
        if branch_id not in branch_keywords:
            branch_keywords[branch_id] = []
        branch_keywords[branch_id].append(text)
    
    print("\n=== 지점별 키워드 정리 ===")
    for branch_id, kw_list in branch_keywords.items():
        branch_name = next((name for bid, name in branches if bid == branch_id), "Unknown")
        print(f"{branch_name} (ID: {branch_id}): {', '.join(kw_list)}")
    
    conn.close()
    return branches, keywords, branch_keywords

if __name__ == "__main__":
    check_existing_data()
