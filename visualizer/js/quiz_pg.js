function renderQuizPG(content) {
    const container = document.getElementById("view-quiz-pg");
    container.innerHTML = "";
    
    content.soal.forEach((q, idx) => {
        const fixImgUrl = (text) => text.replace(/!\[(.*?)\]\((?!http)(.*?)\)/g, "![$1](http://localhost:8000/extraction/$2)");
        
        const soalStr = Array.isArray(q.soal) ? q.soal.join('\n') : String(q.soal || "");
        let soalHtml = marked.parse(fixImgUrl(soalStr));
        
        if (q.image_path && typeof q.image_path === 'string' && q.image_path.trim() !== "") {
            soalHtml = `<img src="http://localhost:8000/extraction/${q.image_path}" alt="Ilustrasi Soal" style="max-width: 100%; border-radius: 8px; margin-bottom: 1rem;" />\n` + soalHtml;
        }
        
        const penHtml = marked.parse(fixImgUrl(String(q.penjelasan || "")));
        
        let optsHtml = q.pilihan.map((opt, i) => `
            <div class="quiz-opt" onclick="this.parentElement.querySelectorAll('.quiz-opt').forEach(el=>el.classList.remove('selected')); this.classList.add('selected'); document.getElementById('expl-${q.id}').style.display='block';">
                <strong>${String.fromCharCode(65+i)}.</strong> ${opt}
            </div>
        `).join('');

        container.innerHTML += `
            <div class="quiz-card">
                <div class="quiz-q">${idx+1}. ${soalHtml}</div>
                <div class="opts-container">${optsHtml}</div>
                <div class="quiz-explanation" id="expl-${q.id}">
                    <strong>Kunci: ${String.fromCharCode(65+q.jawaban)}</strong><br>
                    ${penHtml}
                </div>
            </div>
        `;
    });
    
    container.classList.add("active");
}
