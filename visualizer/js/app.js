let lastGeneratedData = null; // Menyimpan data terakhir yang digenerate untuk keperluan evaluasi essay

document.getElementById("inp-tipe").addEventListener("change", (e) => {
    const levelGroup = document.getElementById("group-level");
    // Sembunyikan pilihan level jika tipe = mindmap atau pretest
    levelGroup.style.display = (e.target.value === "mindmap" || e.target.value === "pretest") ? "none" : "block";
});

async function handleGenerate() {
    const btn = document.getElementById("btn-gen");
    const loading = document.getElementById("loading");
    
    // 1. Ambil data dari form
    const tipe = document.getElementById("inp-tipe").value;
    const payload = {
        mapel_id: document.getElementById("inp-mapel").value,
        elemen_id: document.getElementById("inp-elemen-id").value,
        elemen_label: document.getElementById("inp-elemen-label").value,
        materi: document.getElementById("inp-materi").value,
        atp: [document.getElementById("inp-atp").value],
        kelas_id: document.getElementById("inp-kelas").value,
        jenjang: document.getElementById("inp-jenjang").value,
        tipe: tipe
    };
    if (tipe !== "mindmap" && tipe !== "pretest") {
        payload.level = document.getElementById("inp-level").value;
    }

    // 2. Reset UI
    document.querySelectorAll(".view-container").forEach(el => el.classList.remove("active"));
    document.getElementById("debug-json").style.display = "none";
    const globalVisuals = document.getElementById("global-visuals");
    if (globalVisuals) {
        globalVisuals.style.display = "none";
        globalVisuals.innerHTML = "";
    }
    btn.disabled = true;
    loading.style.display = "flex";

    try {
        // 3. Panggil API Utama Beta Agentic
        const response = await fetch("http://localhost:8000/konten/generate", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        
        const json = await response.json();
        console.log("Raw Response:", json);
        
        if (json.error) {
            alert("Error: " + json.error.message);
            return;
        }

        const data = json.data;
        const content = data.content;
        lastGeneratedData = data;

        // 4. Tampilkan RAW JSON untuk keperluan debug
        document.getElementById("debug-json").textContent = JSON.stringify(data, null, 2);
        document.getElementById("debug-json").style.display = "block";

        // 5. Render Visuals (jika ada array visuals dari RAG base64)
        if (content.visuals && content.visuals.length > 0) {
            let imgHtml = "<div style='font-weight: 600; margin-bottom: 12px; color: #1e293b;'>🖼️ Referensi Gambar dari Materi:</div>";
            imgHtml += "<div style='display: flex; gap: 15px; overflow-x: auto; padding-bottom: 10px;'>";
            content.visuals.forEach((v, index) => {
                imgHtml += `<img src="${v}" alt="Gambar Referensi ${index+1}" style="max-height: 250px; border-radius: 6px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); border: 1px solid #cbd5e1; cursor: pointer;" onclick="window.open(this.src)" />`;
            });
            imgHtml += "</div>";
            const visualContainer = document.getElementById("global-visuals");
            visualContainer.innerHTML = imgHtml;
            visualContainer.style.display = "block";
        }

        // 6. Render konten menggunakan script modular spesifik
        if (content.error) {
            document.getElementById("view-bacaan").innerHTML = `
                <div style="padding: 20px; color: #ef4444; background: #fee2e2; border-radius: 8px; border: 1px solid #fca5a5;">
                    <h3 style="margin-top: 0;">Error dari LLM: ${content.error}</h3>
                    <p style="margin-bottom: 0;">LLM gagal menghasilkan format JSON yang valid. Hal ini biasanya terjadi karena teks terpotong akibat limit token dari model gratis Hugging Face, atau LLM salah format.</p>
                </div>
            `;
            document.getElementById("view-bacaan").classList.add("active");
        } else {
            if (tipe === "bacaan") renderBacaan(content, content.source);
            else if (tipe === "quiz_pg") renderQuizPG(content);
            else if (tipe === "quiz_essay") renderQuizEssay(content);
            else if (tipe === "flashcard") renderFlashcard(content);
            else if (tipe === "mindmap") renderMindmap(content);
            else if (tipe === "pretest") renderPretest(content);
        }

    } catch (err) {
        alert("Network error: " + err.message);
    } finally {
        btn.disabled = false;
        loading.style.display = "none";
    }
}
