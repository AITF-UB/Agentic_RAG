function renderMindmap(content) {
    document.getElementById("view-mindmap").classList.add("active");
    const container = d3.select("#mindmap-svg-container");
    container.selectAll("*").remove(); // clear previous

    const width = container.node().getBoundingClientRect().width || 1000;
    const height = container.node().getBoundingClientRect().height || 800;

    const svg = container.append("svg")
        .attr("width", width)
        .attr("height", height)
        .call(d3.zoom().on("zoom", (e) => g.attr("transform", e.transform)));
    
    const g = svg.append("g").attr("transform", `translate(${width/2}, 50)`);

    // Konversi flat nodes -> hierarchical
    const nodeMap = {};
    content.nodes.forEach(n => nodeMap[n.id] = { ...n, children: [] });
    
    let root = null;
    content.nodes.forEach(n => {
        if (!n.parent_id) {
            if (!root) root = nodeMap[n.id];
        } else {
            if (nodeMap[n.parent_id]) {
                nodeMap[n.parent_id].children.push(nodeMap[n.id]);
            }
        }
    });
    if(!root) root = nodeMap[content.nodes[0].id]; // fallback

    const rootHierarchy = d3.hierarchy(root);
    
    // Layout
    const treeLayout = d3.tree().nodeSize([250, 180]);
    treeLayout(rootHierarchy);

    // Gambar Links (Garis)
    g.selectAll(".link")
        .data(rootHierarchy.links())
        .enter().append("path")
        .attr("class", "link")
        .attr("d", d3.linkVertical()
            .x(d => d.x)
            .y(d => d.y)
        );

    // Gambar Nodes
    const nodes = g.selectAll(".node")
        .data(rootHierarchy.descendants())
        .enter().append("g")
        .attr("class", "node")
        .attr("transform", d => `translate(${d.x},${d.y})`);

    const boxWidth = 220;
    
    // Gambar Kotak
    nodes.append("rect")
        .attr("x", -boxWidth/2)
        .attr("y", -15)
        .attr("width", boxWidth)
        .attr("height", d => {
            const textLen = (d.data.penjelasan || "").length;
            return textLen > 60 ? 120 : (textLen > 30 ? 95 : 75); 
        })
        .attr("rx", 8)
        .attr("ry", 8)
        .attr("fill", d => d.depth === 0 ? "#2563eb" : (d.depth === 1 ? "#059669" : "#374151"))
        .attr("stroke", "#475569")
        .attr("stroke-width", 2);

    // Gambar Teks Label Utama
    nodes.append("text")
        .attr("class", "label")
        .attr("dy", 8)
        .attr("text-anchor", "middle")
        .text(d => d.data.label)
        .call(wrapText, boxWidth - 20);

    // Gambar Teks Penjelasan (tepat di bawah label)
    nodes.append("text")
        .attr("class", "desc")
        .attr("dy", 35)
        .attr("text-anchor", "middle")
        .text(d => d.data.penjelasan || "")
        .call(wrapText, boxWidth - 20);
}

// Fungsi bantu untuk membungkus teks SVG agar tidak meluber dari kotak
function wrapText(text, width) {
    text.each(function () {
        var text = d3.select(this),
            words = text.text().split(/\s+/).reverse(),
            word,
            line = [],
            lineNumber = 0,
            lineHeight = 1.2, 
            y = text.attr("y"),
            dy = parseFloat(text.attr("dy")),
            tspan = text.text(null).append("tspan").attr("x", 0).attr("y", y).attr("dy", dy + "px");
            
        while (word = words.pop()) {
            line.push(word);
            tspan.text(line.join(" "));
            if (tspan.node().getComputedTextLength() > width) {
                line.pop();
                tspan.text(line.join(" "));
                line = [word];
                tspan = text.append("tspan").attr("x", 0).attr("y", y).attr("dy", ++lineNumber * lineHeight + dy + "px").text(word);
            }
        }
    });
}
