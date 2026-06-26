function renderPretest(content) {
    const container = document.getElementById("view-pretest");
    container.innerHTML = "";

    content.soal.forEach((q, idx) => {
        const fixImgUrl = (text) => text.replace(/!\[(.*?)\]\((?!http)(.*?)\)/g, "![$1](http://localhost:8000/extraction/$2)");

        const soalStr = Array.isArray(q.question) ? q.question.join('\n') : String(q.question || "");
        const soalHtml = marked.parse(fixImgUrl(soalStr));
        const penHtml = marked.parse(fixImgUrl(String(q.explanation || "")));

        let optionsArr = Array.isArray(q.options) ? q.options : Object.values(q.options || {});
        let optsHtml = optionsArr.map((opt, i) => `
            <div class="quiz-opt" onclick="this.parentElement.querySelectorAll('.quiz-opt').forEach(el=>el.classList.remove('selected')); this.classList.add('selected'); document.getElementById('expl-pre-${idx}').style.display='block';">
                <strong>${String.fromCharCode(65 + i)}.</strong> ${opt}
            </div>
        `).join('');

        let badgeColor = q.level === 'high' ? 'var(--danger)' : (q.level === 'mid' ? '#eab308' : 'var(--success)');

        container.innerHTML += `
            <div class="quiz-card">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                    <div class="quiz-q" style="margin-bottom: 0;">${idx + 1}.</div>
                    <span style="background-color: ${badgeColor}; color: #fff; padding: 4px 8px; border-radius: 4px; font-size: 12px; font-weight: bold; text-transform: uppercase;">${q.level}</span>
                </div>
                <div style="margin-bottom: 16px;">${soalHtml}</div>
                <div class="opts-container">${optsHtml}</div>
                <div class="quiz-explanation" id="expl-pre-${idx}">
                    <strong>Kunci: ${q.answer}</strong><br>
                    ${penHtml}
                </div>
            </div>
        `;
    });

    container.classList.add("active");
}
