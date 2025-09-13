const $ = (s) => document.querySelector(s);

function escapeHtml(s) {
  return s.replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
}

function renderTable(rows) {
  if (!rows.length) { $("#tableWrap").innerHTML = "<p>결과 없음</p>"; return; }
  let html = `<table border="1" cellspacing="0" cellpadding="6" style="width:100%; border-collapse:collapse;">
    <thead><tr>
      <th>지점</th><th>키워드</th><th>순위</th><th>블로그아이디</th><th>URL</th>
    </tr></thead><tbody>`;
  const branchName = $("#branch").selectedOptions[0]?.textContent || "";
  rows.forEach(r => {
    html += `<tr>
      <td>${escapeHtml(branchName)}</td>
      <td>${escapeHtml(r.keyword)}</td>
      <td style="text-align:center">${r.rank}</td>
      <td>${escapeHtml(r.blog_id)}</td>
      <td><a href="${r.url}" target="_blank" rel="noopener">${r.url}</a></td>
    </tr>`;
  });
  html += `</tbody></table>`;
  $("#tableWrap").innerHTML = html;
}

async function fetchBranches() {
  const token = $("#token").value.trim();
  const res = await fetch("/api/branches", { headers: { ...(token ? {"X-Access-Token": token} : {}) }});
  if (!res.ok) { alert("지점 목록 불러오기 실패"); return; }
  const data = await res.json();
  $("#branch").innerHTML = data.map(b => `<option value="${b.id}">${escapeHtml(b.name)}</option>`).join("");
}

// 초기 지점 목록 로딩
window.addEventListener("load", fetchBranches);

// 지점 키워드 불러오기
$("#loadBtn").onclick = async () => {
  const token = $("#token").value.trim();
  const branch_id = parseInt($("#branch").value, 10);
  const res = await fetch(`/api/keywords?branch_id=${branch_id}`, {
    headers: { ...(token ? {"X-Access-Token": token} : {}) }
  });
  if (!res.ok) { alert("불러오기 실패"); return; }
  const data = await res.json();
  $("#keywords").value = (data.keywords || []).join("\n");
  alert("불러오기 완료");
};

// 지점 키워드 저장
$("#saveBtn").onclick = async () => {
  const token = $("#token").value.trim();
  const branch_id = parseInt($("#branch").value, 10);
  const keywords = $("#keywords").value.split("\n").map(s=>s.trim()).filter(Boolean);
  const res = await fetch("/api/keywords", {
    method: "POST",
    headers: { "Content-Type":"application/json", ...(token ? {"X-Access-Token": token} : {}) },
    body: JSON.stringify({ branch_id, keywords })
  });
  if (!res.ok) { alert("저장 실패"); return; }
  alert("저장 완료");
};

// 연관키워드(첫 줄 기준)
$("#suggestBtn").onclick = async () => {
  const token = $("#token").value.trim();
  const firstKw = $("#keywords").value.split("\n").map(s=>s.trim()).filter(Boolean)[0];
  if (!firstKw) { alert("첫 번째 키워드를 입력하세요"); return; }
  $("#suggestBox").innerHTML = "조회 중...";
  try {
    const res = await fetch(`/api/related?keyword=${encodeURIComponent(firstKw)}&max=20`, {
      headers: { ...(token ? {"X-Access-Token": token} : {}) }
    });
    if (!res.ok) throw new Error("API 오류");
    const data = await res.json();
    if (!data.available) {
      $("#suggestBox").innerHTML = `<small>광고 API 미설정: 공식 연관키워드를 가져오려면 SearchAd API 자격이 필요합니다.</small>`;
      return;
    }
    const kws = (data.related || []).map(r => r.keyword);
    if (!kws.length) { $("#suggestBox").innerHTML = "<small>결과 없음</small>"; return; }
    $("#suggestBox").innerHTML = kws.map(k => `<button class="kwbtn" style="margin:4px">${escapeHtml(k)}</button>`).join("");
    document.querySelectorAll(".kwbtn").forEach(btn => {
      btn.onclick = () => {
        const cur = $("#keywords").value.trim();
        $("#keywords").value = (cur ? (cur + "\n") : "") + btn.textContent;
      };
    });
  } catch (e) {
    $("#suggestBox").innerHTML = "에러: " + e.message;
  }
};

// 조회(테이블)
$("#runBtn").onclick = async () => {
  const token = $("#token").value.trim();
  const branch_id = parseInt($("#branch").value, 10);
  const sort = $("#sort").value;
  const save = $("#save").checked;
  const keywords = $("#keywords").value.split("\n").map(s=>s.trim()).filter(Boolean);

  $("#tableWrap").innerHTML = "조회 중...";
  $("#out").textContent = "";

  try {
    const res = await fetch("/api/table", {
      method: "POST",
      headers: { "Content-Type": "application/json", ...(token ? {"X-Access-Token": token} : {}) },
      body: JSON.stringify({ branch_id, keywords, use_saved: keywords.length===0, sort, save })
    });
    if (!res.ok) throw new Error("API 오류");
    const rows = await res.json();
    renderTable(rows);

    $("#out").textContent = rows.map(r => r.url).join("\n"); // URL만
  } catch (e) {
    $("#tableWrap").innerHTML = "에러: " + e.message;
  }
};

// URL만 복사
$("#copyBtn").onclick = async () => {
  const txt = $("#out").textContent.trim();
  if (!txt) return;
  await navigator.clipboard.writeText(txt);
  alert("URL 복사되었습니다!");
};

// CSV 다운로드
$("#csvBtn").onclick = async () => {
  const token = $("#token").value.trim();
  const branch_id = parseInt($("#branch").value, 10);
  const sort = $("#sort").value;
  const keywords = $("#keywords").value.split("\n").map(s=>s.trim()).filter(Boolean);

  const res = await fetch("/download.csv", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(token ? {"X-Access-Token": token} : {}) },
    body: JSON.stringify({ branch_id, keywords, use_saved: keywords.length===0, sort })
  });
  if (!res.ok) { alert("CSV 생성 실패"); return; }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = "top3.csv";
  document.body.appendChild(a); a.click(); a.remove();
  URL.revokeObjectURL(url);
};
