function renderQuizPG(content) {
    const container = document.getElementById("view-quiz-pg");
    container.innerHTML = "";
    
    content.soal.forEach((q, idx) => {
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
        
        const penHtml = marked.parse(fixImgUrl(String(q.explanation || "")));
        
        let optionsArr = Array.isArray(q.options) ? q.options : Object.values(q.options || {});
        let optsHtml = optionsArr.map((opt, i) => `
            <div class="quiz-opt" onclick="this.parentElement.querySelectorAll('.quiz-opt').forEach(el=>el.classList.remove('selected')); this.classList.add('selected'); document.getElementById('expl-${idx}').style.display='block';">
                <strong>${String.fromCharCode(65+i)}.</strong> ${opt}
            </div>
        `).join('');

        container.innerHTML += `
            <div class="quiz-card">
                ${stimulusHtml}
                <div class="quiz-q">${idx+1}. ${soalHtml}</div>
                <div class="opts-container">${optsHtml}</div>
                <div class="quiz-explanation" id="expl-${idx}">
                    <strong>Kunci: ${q.answer}</strong><br>
                    ${penHtml}
                </div>
            </div>
        `;
    });
    
    container.classList.add("active");
}
