// Global state to hold the current features from persona or manual input
let currentFeatures = [0, 0, 0, 0, 0.5, 1.0, 30, 0, 0, 0, 0, 0];

// Initialize personas
async function initPersonas() {
    const grid = document.getElementById('persona-grid');
    try {
        const response = await fetch('/static/personas.json');
        const personas = await response.json();

        personas.forEach((persona, index) => {
            const chip = document.createElement('div');
            // Add 'high' or 'low' class based on persona.risk
            chip.className = `persona-chip ${persona.risk || 'low'}`;
            chip.innerHTML = `
                <span class="persona-name">${persona.name}</span>
            `;
            chip.onclick = () => selectPersona(persona, chip);
            grid.appendChild(chip);
            
            // Auto-select first persona
            if (index === 0) selectPersona(persona, chip);
        });
    } catch (e) {
        console.error("Failed to load personas:", e);
    }
}

function selectPersona(persona, chipElement) {
    // Update active state
    document.querySelectorAll('.persona-chip').forEach(c => c.classList.remove('active'));
    chipElement.classList.add('active');

    // Update global state
    currentFeatures = [...persona.features];

    // Update UI Form
    document.getElementById('amount').value = currentFeatures[0];
    
    // Reverse select merchant category
    const categoryIndex = currentFeatures.slice(7, 12).indexOf(1);
    if (categoryIndex !== -1) {
        document.getElementById('merchant').value = categoryIndex + 1; // 1-indexed
    }

    // Update Intelligence Grid
    updateIntelligenceUI();
}

function updateIntelligenceUI() {
    document.getElementById('v-device-trust').innerText = currentFeatures[4].toFixed(2);
    document.getElementById('v-ip-risk').innerText = currentFeatures[5].toFixed(1);
    document.getElementById('v-location').innerText = currentFeatures[3] === 1 ? "Mismatch" : "Match";
}

document.getElementById('protect-btn').addEventListener('click', async () => {
    const btn = document.getElementById('protect-btn');
    const btnText = btn.querySelector('.btn-text');
    const loader = btn.querySelector('.loader');

    // Sync form values into currentFeatures just in case user edited them
    currentFeatures[0] = parseFloat(document.getElementById('amount').value) || 0;
    currentFeatures[1] = new Date().getHours() + (new Date().getMinutes() / 60); // Current time
    
    const merchant = parseFloat(document.getElementById('merchant').value);
    // Reset categories
    for (let i = 7; i < 12; i++) currentFeatures[i] = 0;
    const mIdx = Math.floor(merchant);
    if (mIdx >= 1 && mIdx <= 5) {
        currentFeatures[6 + mIdx] = 1;
    }

    // Show loading state
    btnText.classList.add('hidden');
    loader.classList.remove('hidden');
    btn.disabled = true;

    try {
        const response = await fetch('/shield', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ features: currentFeatures })
        });

        const data = await response.json();
        showResult(data, currentFeatures);

    } catch (error) {
        console.error('Error:', error);
        alert('Could not connect to Digital Shield Backend.');
    } finally {
        btnText.classList.remove('hidden');
        loader.classList.add('hidden');
        btn.disabled = false;
    }
});

async function showResult(data, features) {
    const overlay = document.getElementById('result-overlay');
    const statusIcon = document.getElementById('result-status-icon');
    const title = document.getElementById('result-title');
    const desc = document.getElementById('result-desc');
    const scoreFill = document.getElementById('score-fill');
    const scoreVal = document.getElementById('score-val');
    const guidanceBox = document.getElementById('ai-guidance-box');
    const guidanceText = document.getElementById('ai-guidance-text');
    const sourceTag = document.getElementById('prediction-source') || createSourceTag();

    guidanceBox.classList.add('hidden');
    guidanceText.innerText = "Analyzing risk patterns...";

    const scorePercent = (data.fraud_score * 100).toFixed(1);

    sourceTag.innerText = `Engine: ${data.prediction_source === 'vertex' ? 'Vertex AI' : 'Local Engine'}`;
    sourceTag.className = `source-tag ${data.prediction_source}`;

    if (data.transaction_status === 'Approved') {
        statusIcon.innerText = '✅';
        title.innerText = 'Transaction Approved';
        title.style.color = 'var(--success)';
        desc.innerText = 'Digital Shield verified this transaction as secure.';
        scoreFill.style.background = 'var(--success)';
    } else {
        statusIcon.innerText = '🚫';
        title.innerText = 'Transaction Rejected';
        title.style.color = 'var(--danger)';
        desc.innerText = 'Potential threat detected. Access has been restricted.';
        scoreFill.style.background = 'var(--danger)';
    }

    overlay.classList.remove('hidden');

    setTimeout(() => {
        scoreFill.style.width = scorePercent + '%';
        scoreVal.innerText = scorePercent + '%';
    }, 100);

    // Display AI Guidance from Gemini
    guidanceBox.classList.remove('hidden');
    guidanceText.innerText = data.explanation || "Analysis pending...";
}

function createSourceTag() {
    const tag = document.createElement('div');
    tag.id = 'prediction-source';
    document.querySelector('.score-container').prepend(tag);
    return tag;
}

document.getElementById('reset-btn').addEventListener('click', () => {
    document.getElementById('result-overlay').classList.add('hidden');
    document.getElementById('score-fill').style.width = '0%';
});

// Run init
initPersonas();
