function renderBacaan(content, source) {
    // 1. Parsing Markdown menjadi HTML dan memperbaiki URL gambar
    let mdText = String(content.konten_markdown || content.text || "");
    mdText = mdText.replace(/!\[(.*?)\]\((?!http)(.*?)\)/g, "![$1](http://localhost:8000/extraction/$2)");
    let html = marked.parse(mdText);
    
    if (content.visuals && typeof content.visuals === 'string' && content.visuals.startsWith("data:image")) {
        html = `<img src="${content.visuals}" alt="Ilustrasi Materi" style="max-width: 100%; border-radius: 8px; margin-bottom: 1rem;" />\n` + html;
    } else if (content.image_path && typeof content.image_path === 'string' && content.image_path.trim() !== "") {
        html = `<img src="http://localhost:8000/extraction/${content.image_path}" alt="Ilustrasi Materi" style="max-width: 100%; border-radius: 8px; margin-bottom: 1rem;" />\n` + html;
    }
    
    document.getElementById("bacaan-html").innerHTML = html;
    
    // 2. Format Sumber Referensi (Array of Strings)
    let srcHtml = "<strong>Sumber Referensi:</strong><br>";
    if (source && source.length > 0) {
        source.forEach(s => { srcHtml += `- ${s}<br>`; });
    } else {
        srcHtml += "- (Generated without DB Source)";
    }
    
    document.getElementById("bacaan-source").innerHTML = srcHtml;
    
    // 3. Tampilkan kontainer
    document.getElementById("view-bacaan").classList.add("active");
}
