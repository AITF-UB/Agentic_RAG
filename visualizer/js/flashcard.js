// Global state lokal untuk flashcard
let currentFlashcards = [];
let fcIndex = 0;

function renderFlashcard(content) {
    currentFlashcards = content.cards;
    fcIndex = 0;
    updateFCDOM();
    document.getElementById("view-flashcard").classList.add("active");
}

function updateFCDOM() {
    if(!currentFlashcards.length) return;
    const c = currentFlashcards[fcIndex];
    document.getElementById("fc-front").innerHTML = c.front;
    document.getElementById("fc-back").innerHTML = c.back;
    document.getElementById("fc-counter").innerText = `${fcIndex+1}/${currentFlashcards.length}`;
    document.getElementById("fc-card").classList.remove("is-flipped");
}

function fcNext() { 
    if(fcIndex < currentFlashcards.length - 1) { 
        fcIndex++; 
        updateFCDOM(); 
    } 
}

function fcPrev() { 
    if(fcIndex > 0) { 
        fcIndex--; 
        updateFCDOM(); 
    } 
}
