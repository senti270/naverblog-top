import os, requests
from dotenv import load_dotenv
load_dotenv()
cid, csec = os.getenv("NAVER_ID"), os.getenv("NAVER_SECRET")
r = requests.get(
    "https://openapi.naver.com/v1/search/blog.json",
    headers={"X-Naver-Client-Id": cid, "X-Naver-Client-Secret": csec},
    params={"query":"장어구이","display":3,"sort":"sim"},
    timeout=10
)
print(r.status_code, r.text[:500])