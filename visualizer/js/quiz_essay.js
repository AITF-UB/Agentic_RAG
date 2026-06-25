function renderQuizEssay(content) {
    const container = document.getElementById("view-quiz-essay");
    container.innerHTML = "";
    
    window.currentEssayContent = content;
    
    content.pertanyaan.forEach((q, idx) => {
        const fixImgUrl = (text) => text.replace(/!\[(.*?)\]\((?!http)(.*?)\)/g, "![$1](http://localhost:8000/extraction/$2)");
        const soalStr = Array.isArray(q.question) ? q.question.join('\n') : String(q.question || "");
        
        let soalHtml = marked.parse(fixImgUrl(soalStr));
        
        let stimulusHtml = "";
        if (q.stimulus && typeof q.stimulus === 'string' && q.stimulus.trim() !== "") {
            stimulusHtml = `<div class="quiz-stimulus" style="font-style: italic; margin-bottom: 16px; padding: 12px 16px; background: var(--bg-hover); border-left: 4px solid var(--accent); border-radius: 4px; color: var(--text-muted);">${marked.parse(fixImgUrl(q.stimulus))}</div>`;
        }
        
        if (q.visuals && typeof q.visuals === 'string' && q.visuals.startsWith("data:image")) {
            soalHtml = `<img src="${q.visuals}" alt="Ilustrasi Soal" style="max-width: 100%; border-radius: 8px; margin-bottom: 1rem;" />\n` + soalHtml;
        } else if (q.image_path && typeof q.image_path === 'string' && q.image_path.trim() !== "") {
            soalHtml = `<img src="http://localhost:8000/extraction/${q.image_path}" alt="Ilustrasi Soal" style="max-width: 100%; border-radius: 8px; margin-bottom: 1rem;" />\n` + soalHtml;
        }
        
        container.innerHTML += `
            <div class="quiz-card" id="essay-card-${idx}">
                ${stimulusHtml}
                <div class="quiz-q">${idx+1}. ${soalHtml}</div>
                <textarea class="essay-textarea" id="ans-${idx}" placeholder="${q.placeholder || 'Ketik jawabanmu di sini...'}"></textarea>
            </div>
        `;
    });
    
    container.innerHTML += `
        <div style="margin-top: 24px; display: flex; flex-direction: column; align-items: center;">
            <button class="btn-eval" id="btn-eval-all" onclick="evaluateAllEssays()" style="width: 100%; padding: 14px; font-size: 16px;">✨ Evaluasi Seluruh Essay (AI)</button>
        </div>
        <div id="eval-all-result" style="display: none; margin-top: 32px;"></div>
    `;
    
    container.classList.add("active");
}

async function evaluateAllEssays() {
    if (!window.currentEssayContent || !window.currentEssayContent.pertanyaan) return;
    
    const questions = window.currentEssayContent.pertanyaan;
    const payload = [];
    
    for (let idx = 0; idx < questions.length; idx++) {
        const q = questions[idx];
        const ans = document.getElementById(`ans-${idx}`).value;
        if (!ans.trim()) {
            alert(`Jawaban untuk soal nomor ${idx + 1} masih kosong!`);
            return;
        }
        
        payload.push({
            jawaban_siswa: ans,
            soal: Array.isArray(q.question) ? q.question.join('\n') : String(q.question || ""),
            rubrik: Array.isArray(q.rubric_points) ? q.rubric_points.join('\n') : String(q.rubric_points || ""),
            stimulus: q.stimulus || "",
            penjelasan: q.explanation || ""
        });
    }
    
    const btn = document.getElementById("btn-eval-all");
    btn.textContent = "Mengevaluasi Seluruh Jawaban (Mohon Tunggu)..."; 
    btn.disabled = true;

    try {
        const res = await fetch("http://localhost:8000/siswa/quiz/essay", {
            method: "POST", 
            headers: {"Content-Type": "application/json"}, 
            body: JSON.stringify(payload)
        });
        
        if (!res.ok) throw new Error(`HTTP Error ${res.status}`);
        const json = await res.json();
        const data = json.data;
        
        const resContainer = document.getElementById("eval-all-result");
        let html = `
            <div style="background: var(--bg-card); padding: 24px; border-radius: 12px; border: 1px solid var(--accent); text-align: center; margin-bottom: 32px;">
                <h2 style="margin-top: 0; color: var(--text-main);">Skor Total Essay</h2>
                <div style="font-size: 48px; font-weight: 800; color: var(--success);">${data.total_skor}</div>
            </div>
            <h3 style="margin-bottom: 20px; color: var(--accent);">Detail Evaluasi per Soal:</h3>
        `;
        
        data.evaluasi.forEach((ev, i) => {
            const p = payload[i]; // get original submitted data
            html += `
                <div style="background: var(--bg-card); padding: 20px; border-radius: 12px; margin-bottom: 24px; border-left: 4px solid var(--accent);">
                    <div style="font-size: 16px; font-weight: bold; margin-bottom: 12px;">Soal ${i+1}</div>
                    ${p.stimulus ? `<div style="font-style: italic; color: var(--text-muted); margin-bottom: 12px; padding: 10px; background: var(--bg-hover); border-radius: 6px;">${p.stimulus}</div>` : ''}
                    <div style="margin-bottom: 12px;"><strong>Pertanyaan:</strong><br>${p.soal}</div>
                    
                    <div style="display: flex; gap: 16px; margin-bottom: 16px;">
                        <div style="flex: 1; background: rgba(59, 130, 246, 0.1); padding: 12px; border-radius: 8px; border: 1px solid rgba(59, 130, 246, 0.2);">
                            <strong>Jawaban Anda:</strong><br>${p.jawaban_siswa}
                        </div>
                        <div style="flex: 1; background: rgba(16, 185, 129, 0.1); padding: 12px; border-radius: 8px; border: 1px solid rgba(16, 185, 129, 0.2);">
                            <strong>Kunci / Rubrik:</strong><br>${p.rubrik}
                        </div>
                    </div>
                    
                    <div style="background: var(--bg-dark); padding: 16px; border-radius: 8px;">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <strong style="color: var(--accent);">Penilaian AI:</strong>
                            <span style="font-size: 20px; font-weight: bold; color: var(--success);">Skor: ${ev.skor}</span>
                        </div>
                    </div>
                </div>
            `;
        });
        
        resContainer.innerHTML = html;
        resContainer.style.display = "block";
        resContainer.scrollIntoView({ behavior: 'smooth' });
        
    } catch(e) {
        alert("Gagal evaluasi: " + e.message);
    } finally {
        btn.textContent = "✨ Evaluasi Seluruh Essay (AI)"; 
        btn.disabled = false;
    }
}
