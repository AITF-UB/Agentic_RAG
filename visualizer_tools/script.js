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
                bar.style.setProperty('--bar-width', '100%');
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

    // 1. Buat Job Card Baru dari Template
    const clone = template.content.cloneNode(true);
    const cardElement = clone.querySelector('.job-card');
    const cardId = 'card_' + Date.now();
    cardElement.dataset.cardId = cardId;
    cardElement.dataset.tipe = tipe;
    cardElement.querySelector('.job-tipe').innerText = tipe;
    
    // Taruh di paling atas list
    jobsContainer.prepend(cardElement);
    
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
            // Ambil array dari key 'soal' atau 'pertanyaan'
            const listSoal = resultJson.soal || resultJson.pertanyaan || [];
            
            listSoal.forEach((soal, index) => {
                if(!soal.pertanyaan) return;
                
                html += `<div class="quiz-question">`;
                html += `<p><strong>Soal ${index + 1}:</strong> ${soal.pertanyaan}</p>`;
                
                if (soal.opsi && typeof soal.opsi === 'object') {
                    html += `<ul class="quiz-options">`;
                    for(const opKey in soal.opsi) {
                        html += `<li><label><input type="radio" name="${card.dataset.cardId}_soal_${index}"> ${opKey}. ${soal.opsi[opKey]}</label></li>`;
                    }
                    html += `</ul>`;
                }
                
                // Tombol lihat jawaban
                const boxId = `${card.dataset.cardId}_ans_${index}`;
                html += `<button type="button" class="btn-nav" onclick="document.getElementById('${boxId}').style.display='block'">Lihat Jawaban</button>`;
                html += `<div id="${boxId}" class="correct-answer-box">
                            <strong>Jawaban:</strong> ${soal.jawaban_benar || soal.jawaban || ''} <br>
                            <em>${soal.penjelasan || ''}</em>
                         </div>`;
                html += `</div>`;
            });
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
