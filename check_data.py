#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sqlite3

def check_data():
    conn = sqlite3.connect('data.db')
    cursor = conn.cursor()
    
    # 지점별 키워드 조회
    cursor.execute('''
        SELECT b.name, k.text 
        FROM branches b 
        LEFT JOIN keywords k ON b.id = k.branch_id 
        ORDER BY b.name, k.text
    ''')
    
    results = cursor.fetchall()
    print("지점별 키워드:")
    
    current_branch = None
    for branch, keyword in results:
        if branch != current_branch:
            print(f"\n{branch}:")
            current_branch = branch
        if keyword:
            print(f"  - {keyword}")
    
    conn.close()

if __name__ == "__main__":
    check_data()
