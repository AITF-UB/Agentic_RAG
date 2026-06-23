const form = document.getElementById('generateForm');
const jobsContainer = document.getElementById('jobsContainer');
const template = document.getElementById('jobCardTemplate');

const API_BASE_URL = 'http://localhost:8001';

// Trik UX: Pesan progress palsu
const PROGRESS_STAGES = [
    { p: 10, text: "Memasukkan ke antrian Celery..." },
    { p: 30, text: "Menganalisa referensi vektor RAG..." },
    { p: 60, text: "LLM sedang merancang konten..." },
    { p: 85, text: "Menyusun struktur & finalisasi..." },
    { p: 95, text: "Sedikit lagi selesai..." }
];

// Dictionary interval polling untuk setiap job (jobId -> intervalId)
const activePollings = {};

let currentJobIndex = 0; // State untuk pagination/carousel jobs

// Update tampilan pagination carousel jobs
function updateJobsPagination() {
    const cards = document.querySelectorAll('#jobsContainer .job-card');
    const total = cards.length;
    const pagination = document.getElementById('jobsPagination');
    const counter = document.getElementById('jobsCounter');
    
    if (total <= 1) {
        pagination.style.display = 'none';
        if (total === 1) cards[0].style.display = 'block';
        return;
    }
    
    pagination.style.display = 'flex';
    
    if (currentJobIndex >= total) currentJobIndex = total - 1;
    if (currentJobIndex < 0) currentJobIndex = 0;
    
    counter.innerText = `${currentJobIndex + 1} / ${total}`;
    
    cards.forEach((card, index) => {
        if (index === currentJobIndex) {
            card.style.display = 'block';
        } else {
            card.style.display = 'none';
        }
    });
}

// Navigasi carousel jobs
window.navJobs = function(dir) {
    const total = document.querySelectorAll('#jobsContainer .job-card').length;
    if (total === 0) return;
    
    currentJobIndex += dir;
    if (currentJobIndex < 0) currentJobIndex = total - 1;
    if (currentJobIndex >= total) currentJobIndex = 0;
    updateJobsPagination();
}

function addLog(card, message, isJson = false) {
    const logContainer = card.querySelector('.log-container');
    const time = new Date().toLocaleTimeString();
    let content = message;
    if (isJson) {
        content = JSON.stringify(message, null, 2);
    }
    
    if(isJson) {
        logContainer.innerHTML += `\n[${time}] DATA JSON:\n<pre><code class="language-json">${content}</code></pre>\n`;
        // Apply syntax highlight to new block
        const blocks = logContainer.querySelectorAll('pre code');
        hljs.highlightElement(blocks[blocks.length - 1]);
    } else {
        logContainer.innerHTML += `[${time}] ${content}\n`;
    }
    logContainer.scrollTop = logContainer.scrollHeight;
}

function updateCardStatus(card, status) {
    card.classList.remove('status-running', 'status-success', 'status-failed', 'status-cancelled');
    card.classList.add(`status-${status}`);
    
    const badge = card.querySelector('.badge');
    badge.className = `badge ${status}`;
    badge.innerText = status.toUpperCase();

    const btnCancel = card.querySelector('.btn-cancel');
    if (status !== 'pending' && status !== 'running') {
        btnCancel.style.display = 'none'; // Sembunyikan cancel jika udah selesai/gagal
    }
}

function simulateProgress(card) {
    const bar = card.querySelector('.progress-bar');
    const text = card.querySelector('.progress-text');
    let currentStage = 0;
    
    const progInterval = setInterval(() => {
        if(card.classList.contains('status-success') || 
           card.classList.contains('status-failed') || 
           card.classList.contains('status-cancelled')) {
            clearInterval(progInterval);
            if(card.classList.contains('status-success')) {
                text.innerText = "Selesai!";
                bar.innerHTML = ''; // Hapus style progress buatan agar CSS 100% bisa masuk
            }
            return;
        }

        if(currentStage < PROGRESS_STAGES.length) {
            const stage = PROGRESS_STAGES[currentStage];
            bar.innerHTML = `<style>.job-card[data-card-id="${card.dataset.cardId}"] .progress-bar::after { width: ${stage.p}% !important; }</style>`;
            text.innerText = stage.text;
            currentStage++;
        }
    }, 4000); // Ganti stage tiap 4 detik
}

form.addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const tipe = document.getElementById('tipe').value;
    const payload = {
        mapel_id: document.getElementById('mapel').value,
        elemen_id: "1",
        jenjang: "SMA",
        kelas_id: "10",
        tipe: tipe,
        elemen_label: document.getElementById('elemen_label').value,
        materi: document.getElementById('materi').value,
    };
    const level = document.getElementById('level').value;
    if (level) payload.level = level;

    // 1. Buat elemen UI baru untuk Job ini
    const jobsContainer = document.getElementById('jobsContainer');
    const template = document.getElementById('jobCardTemplate');
    const cardElement = template.content.cloneNode(true).firstElementChild;
    
    cardElement.dataset.tipe = tipe;
    cardElement.dataset.cardId = Date.now().toString() + Math.floor(Math.random()*1000); // ID unik untuk DOM UI
    cardElement.querySelector('.job-tipe').innerText = tipe;
    
    // Taruh di paling atas list
    jobsContainer.prepend(cardElement);
    currentJobIndex = 0; // Selalu fokus ke job terbaru
    updateJobsPagination();
    
    // 2. Mulai proses
    addLog(cardElement, `Memulai Request POST /konten/generate...`);
    updateCardStatus(cardElement, 'pending');
    simulateProgress(cardElement); // Mulai jalankan fake progress
    
    try {
        const response = await fetch(`${API_BASE_URL}/konten/generate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (!response.ok) throw new Error(JSON.stringify(await response.json()));
        
        const data = await response.json();
        const jobId = data.job_id;
        
        cardElement.dataset.jobId = jobId;
        cardElement.querySelector('.job-id-text span').innerText = jobId;
        addLog(cardElement, `Job diterima! ID: ${jobId}`);
        updateCardStatus(cardElement, 'running');
        
        // 3. Mulai Polling Independen
        startPolling(cardElement, jobId);

    } catch (error) {
        updateCardStatus(cardElement, 'failed');
        addLog(cardElement, `ERROR: ${error.message}`);
    }
});

function startPolling(card, jobId) {
    const intervalId = setInterval(async () => {
        try {
            const response = await fetch(`${API_BASE_URL}/job/${jobId}`);
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            
            const data = await response.json();
            
            // Jika tiba-tiba dibatalkan
            if(card.classList.contains('status-cancelled')) {
                clearInterval(intervalId);
                delete activePollings[jobId];
                return;
            }

            if (data.status === 'success') {
                clearInterval(intervalId);
                delete activePollings[jobId];
                updateCardStatus(card, 'success');
                addLog(card, '✅ GENERASI SELESAI!');
                addLog(card, data.result, true); // Tetap log raw JSON
                
                // RENDER UI DINAMIS
                renderResultUI(card, card.dataset.tipe, data.result);
            } 
            else if (data.status === 'failed') {
                clearInterval(intervalId);
                delete activePollings[jobId];
                updateCardStatus(card, 'failed');
                addLog(card, `❌ GENERASI GAGAL! Error: ${data.error}`);
            } else {
                addLog(card, `Polling status... [${data.status}]`);
            }
        } catch (err) {
            addLog(card, `WARNING polling: ${err.message}`);
        }
    }, 3000);
    
    activePollings[jobId] = intervalId;
}

// Fitur Pembatalan
async function cancelJob(btn) {
    const card = btn.closest('.job-card');
    const jobId = card.dataset.jobId;
    
    updateCardStatus(card, 'cancelled');
    addLog(card, `Membatalkan job...`);
    
    if(activePollings[jobId]) {
        clearInterval(activePollings[jobId]);
        delete activePollings[jobId];
    }
    
    if(jobId) {
        try {
            await fetch(`${API_BASE_URL}/job/${jobId}`, { method: 'DELETE' });
            addLog(card, `✅ Sinyal Kill dikirim ke Server.`);
        } catch(e) {
            addLog(card, `Gagal membatalkan di server: ${e.message}`);
        }
    }
}

// Fitur Rendering Dinamis
function renderResultUI(card, tipe, resultJson) {
    const container = card.querySelector('.result-container');
    container.style.display = 'block';
    
    let html = `<h4>✨ Hasil (Rendered UI)</h4>`;
    
    try {
        if (tipe === 'bacaan') {
            const mdContent = resultJson.konten_markdown || resultJson.bacaan || resultJson.content || '';
            const title = resultJson.judul_utama ? `<h2>${resultJson.judul_utama}</h2>\n` : '';
            html += `<div class="markdown-body">${marked.parse(title + mdContent)}</div>`;
        } 
        else if (tipe.includes('quiz') || tipe === 'pretest') {
            // Ambil array dari key 'soal' atau 'pertanyaan', kadang terbungkus di 'final_payload'
            let listSoal = resultJson.soal || resultJson.pertanyaan || [];
            if (listSoal.length === 0 && resultJson.final_payload && resultJson.final_payload.soal) {
                listSoal = resultJson.final_payload.soal;
            }
            
            listSoal.forEach((soal, index) => {
                const questionText = soal.pertanyaan || soal.question;
                if(!questionText) return;
                
                html += `<div class="quiz-question">`;
                
                // Render stimulus jika ada (biasanya markdown/teks panjang)
                if (soal.stimulus) {
                    html += `<div class="markdown-body" style="background:var(--bg-color); padding:0.75rem; border-radius:8px; margin-bottom:1rem; border-left:4px solid var(--primary); font-size:0.95rem;">${marked.parse(soal.stimulus)}</div>`;
                }
                
                // Label tingkat kesulitan (level)
                const levelBadge = soal.level ? `<span class="badge" style="background:var(--primary); color:white; margin-left:0.5rem; font-size:0.7rem;">${soal.level}</span>` : '';
                html += `<p style="font-weight:600; font-size:1.05rem;">Soal ${index + 1} ${levelBadge}</p>`;
                html += `<div class="markdown-body" style="margin-bottom:1rem;">${marked.parse(questionText)}</div>`;
                
                const optionsObj = soal.opsi || soal.options;
                if (optionsObj && typeof optionsObj === 'object') {
                    html += `<ul class="quiz-options">`;
                    for(const opKey in optionsObj) {
                        html += `<li><label><input type="radio" name="${card.dataset.cardId}_soal_${index}"> <strong>${opKey}.</strong>&nbsp; ${optionsObj[opKey]}</label></li>`;
                    }
                    html += `</ul>`;
                }
                
                // Tombol lihat jawaban
                const boxId = `${card.dataset.cardId}_ans_${index}`;
                const ansText = soal.jawaban_benar || soal.jawaban || soal.answer || '';
                const expText = soal.penjelasan || soal.explanation || '';
                
                html += `<button type="button" class="btn-nav" onclick="document.getElementById('${boxId}').style.display='block'" style="margin-top:1rem; max-width:200px;">Lihat Jawaban</button>`;
                html += `<div id="${boxId}" class="correct-answer-box">
                            <strong>Jawaban Benar: ${ansText}</strong>
                            <div class="markdown-body" style="margin-top:0.5rem; font-size:0.95rem;">${marked.parse(expText)}</div>
                         </div>`;
                html += `</div>`;
            });
        }
        else if (tipe === 'mindmap') {
            const rootNode = resultJson.root || (resultJson.final_payload && resultJson.final_payload.root);
            if (rootNode) {
                html += `<div class="mindmap-container" style="padding:1rem 0;">`;
                html += buildMindmapHTML(rootNode);
                html += `</div>`;
            } else {
                html += `<p><em>Format mindmap tidak dikenali atau JSON kosong.</em></p>`;
            }
        }
        else if (tipe === 'flashcard') {
            // resultJson = { cards: [ { front: "", back: "" }, ... ] }
            let cards = resultJson.cards || [];
            
            // Fallback backward compat jika array terstruktur beda
            if (!Array.isArray(cards)) {
                 cards = [];
                 for (const key in resultJson) {
                     if (resultJson[key].front || resultJson[key].muka) {
                         cards.push(resultJson[key]);
                     }
                 }
            }
            
            // Render Carousel
            if(cards.length > 0) {
                const carouselId = `fc_${card.dataset.cardId}`;
                window[carouselId] = { cards, current: 0 };
                
                const frontText = cards[0].front || cards[0].muka || "";
                const backText = cards[0].back || cards[0].belakang || "";
                
                html += `<div class="flashcard-carousel" id="${carouselId}_container">
                            <div class="flashcard-scene">
                                <div class="flashcard" onclick="this.classList.toggle('is-flipped')">
                                    <div class="flashcard-face flashcard-front" id="${carouselId}_front">${frontText}</div>
                                    <div class="flashcard-face flashcard-back" id="${carouselId}_back">${backText}</div>
                                </div>
                            </div>
                            <div class="carousel-controls">
                                <button class="btn-nav" onclick="navFlashcard('${carouselId}', -1)">⬅ Prev</button>
                                <span id="${carouselId}_counter">1 / ${cards.length}</span>
                                <button class="btn-nav" onclick="navFlashcard('${carouselId}', 1)">Next ➡</button>
                            </div>
                            <p class="progress-text" style="text-align:center; margin-top:0.5rem">Klik kartu untuk membalik</p>
                         </div>`;
            } else {
                html += `<p><em>Tidak ada flashcard valid yang ditemukan.</em></p>`;
            }
        }
        else {
            html += `<p><em>UI Renderer untuk tipe <strong>${tipe}</strong> belum didukung. Silakan lihat raw JSON di log terminal.</em></p>`;
        }
    } catch(e) {
        html += `<p style="color:red">Gagal merender UI: ${e.message}</p>`;
    }
    
    container.innerHTML = html;
    
    // Trigger MathJax untuk merender ulang LaTeX yang baru saja disisipkan
    if (window.MathJax) {
        window.MathJax.typesetPromise([container]).catch((err) => console.error('MathJax Error:', err));
    }
}

// Helper rekursif untuk merender Mindmap
function buildMindmapHTML(node, isRoot = true) {
    if (!node) return '';
    let html = `<div class="mindmap-node" style="margin-left: ${isRoot ? '0' : '1.5rem'}; ${!isRoot ? 'border-left: 2px solid var(--border); padding-left: 1rem;' : ''} margin-top: 0.5rem;">`;
    
    html += `<div style="background:var(--card-bg); border: 1px solid var(--border); padding: 0.75rem; border-radius: 6px; margin-bottom: 0.5rem; transition: all 0.2s ease;">`;
    html += `<h5 style="margin:0 0 0.25rem 0; color:var(--primary); font-size:1.05rem;">${node.name}</h5>`;
    if (node.description) {
        html += `<p style="margin:0; font-size:0.9rem; color:var(--text-muted);">${node.description}</p>`;
    }
    html += `</div>`;
    
    if (node.children && Array.isArray(node.children) && node.children.length > 0) {
        node.children.forEach(child => {
            html += buildMindmapHTML(child, false);
        });
    }
    html += `</div>`;
    return html;
}

// Helper untuk navigasi flashcard global
window.navFlashcard = function(carouselId, direction) {
    const state = window[carouselId];
    state.current += direction;
    if(state.current < 0) state.current = state.cards.length - 1;
    if(state.current >= state.cards.length) state.current = 0;
    
    const cardEl = document.querySelector(`#${carouselId}_container .flashcard`);
    cardEl.classList.remove('is-flipped'); // reset flip
    
    setTimeout(() => {
        const frontText = state.cards[state.current].front || state.cards[state.current].muka || "";
        const backText = state.cards[state.current].back || state.cards[state.current].belakang || "";
        
        const frontEl = document.getElementById(`${carouselId}_front`);
        const backEl = document.getElementById(`${carouselId}_back`);
        
        frontEl.innerHTML = frontText;
        backEl.innerHTML = backText;
        document.getElementById(`${carouselId}_counter`).innerText = `${state.current + 1} / ${state.cards.length}`;
        
        // Render MathJax di kartu yang baru
        if (window.MathJax) {
            window.MathJax.typesetPromise([frontEl, backEl]).catch((err) => console.error('MathJax Error:', err));
        }
    }, 150); // delay dikit biar animasi flip ke reset mulus
}

// ==========================================
// THEME SWITCHER (Light/Dark Mode)
// ==========================================
const toggleSwitch = document.querySelector('.theme-switch input[type="checkbox"]');
const currentTheme = localStorage.getItem('theme');

if (currentTheme) {
    document.body.classList.add(currentTheme);
    if (currentTheme === 'dark-mode') {
        toggleSwitch.checked = true;
    }
} else if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
    // Auto-detect system preference
    document.body.classList.add('dark-mode');
    toggleSwitch.checked = true;
}

toggleSwitch.addEventListener('change', function(e) {
    if (e.target.checked) {
        document.body.classList.add('dark-mode');
        localStorage.setItem('theme', 'dark-mode');
    } else {
        document.body.classList.remove('dark-mode');
        localStorage.setItem('theme', 'light-mode');
    }
});
