function renderQuizEssay(content) {
    const container = document.getElementById("view-quiz-essay");
    container.innerHTML = "";
    
    content.pertanyaan.forEach((q, idx) => {
        const fixImgUrl = (text) => text.replace(/!\[(.*?)\]\((?!http)(.*?)\)/g, "![$1](http://localhost:8000/extraction/$2)");
        const soalStr = Array.isArray(q.soal) ? q.soal.join('\n') : String(q.soal || "");
        const rubrikStr = Array.isArray(q.rubrik) ? q.rubrik.join('\n') : String(q.rubrik || "");
        
        let soalHtml = marked.parse(fixImgUrl(soalStr));
        
        if (q.image_path && typeof q.image_path === 'string' && q.image_path.trim() !== "") {
            soalHtml = `<img src="http://localhost:8000/extraction/${q.image_path}" alt="Ilustrasi Soal" style="max-width: 100%; border-radius: 8px; margin-bottom: 1rem;" />\n` + soalHtml;
        }
        
        container.innerHTML += `
            <div class="quiz-card" id="essay-card-${q.id}">
                <div class="quiz-q">${idx+1}. ${soalHtml}</div>
                <textarea class="essay-textarea" id="ans-${q.id}" placeholder="${q.placeholder || 'Ketik jawabanmu di sini...'}"></textarea>
                <button class="btn-eval" onclick="evaluateEssay('${q.id}', \`${soalStr.replace(/`/g, "'")}\`, \`${rubrikStr.replace(/`/g, "'")}\`)">Kirim & Evaluasi (AI)</button>
                
                <div class="eval-result" id="res-${q.id}">
                    <div class="eval-skor" id="skor-${q.id}"></div>
                    <div id="feed-${q.id}"></div>
                </div>
            </div>
        `;
    });
    
    container.classList.add("active");
}

async function evaluateEssay(qId, soal, rubrik) {
    const ans = document.getElementById(`ans-${qId}`).value;
    if(!ans.trim()) return alert("Jawaban kosong!");
    
    const btn = document.querySelector(`#essay-card-${qId} .btn-eval`);
    btn.textContent = "Mengevaluasi..."; 
    btn.disabled = true;

    // Menyiapkan payload sesuai kontrak endpoint evaluasi terbaru
    const payload = {
        publish_id: "test",
        mapel_id: lastGeneratedData.mapel_id,
        elemen_id: lastGeneratedData.elemen_id,
        elemen_label: lastGeneratedData.elemen_id,
        materi: lastGeneratedData.materi_id,
        materi_id: lastGeneratedData.materi_id,
        level: lastGeneratedData.level,
        soal: { [qId]: soal },
        rubrik: { [qId]: rubrik },
        jawaban: { [qId]: ans }
    };

    try {
        const res = await fetch("http://localhost:8000/siswa/test_user/quiz/essay", {
            method: "POST", 
            headers: {"Content-Type": "application/json"}, 
            body: JSON.stringify(payload)
        });
        const json = await res.json();
        
        const evaluasi = json.data.evaluasi[qId];
        document.getElementById(`res-${qId}`).style.display = "block";
        document.getElementById(`skor-${qId}`).innerText = `Nilai: ${evaluasi.skor}/100`;
        document.getElementById(`feed-${qId}`).innerText = evaluasi.feedback;
    } catch(e) {
        alert("Gagal evaluasi: " + e.message);
    } finally {
        btn.textContent = "Kirim & Evaluasi (AI)"; 
        btn.disabled = false;
    }
}
