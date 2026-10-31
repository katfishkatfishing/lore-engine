// app.js

// Scroll-driven Animation & Nav Logo Animation
window.addEventListener('scroll', function() {
    const scrollY = window.scrollY;
    console.log("Current Scroll Y:", scrollY); // Check your F12 browser console!

    const heroContent = document.getElementById('hero-content');
    const navLogo = document.getElementById('nav-logo');
    const maxScroll = 400;
    const progress = Math.min(scrollY / maxScroll, 1);

    if (heroContent && navLogo) {
        if (scrollY <= maxScroll) {
            heroContent.style.transform = `translateY(${scrollY * 0.4}px) scale(${1 - progress * 0.15})`;
            heroContent.style.opacity = 1 - progress * 1.5;
            navLogo.style.opacity = progress;
        } else {
            heroContent.style.opacity = 0;
            navLogo.style.opacity = 1;
        }
    }
});

// Fetch LIVELORE Terminal Feed from Backend
async function loadLiveLore() {
    try {
        const response = await fetch('http://localhost:8000/api/quotes?limit=3&shuffle=true');
        if (!response.ok) throw new Error('API offline');

        const quotes = await response.json();
        const terminal = document.getElementById('live-lore-terminal');
        if (!terminal) return;

        terminal.innerHTML = `
            <div class="flex justify-between border-b border-green-900 pb-3 mb-4 text-sm text-green-600">
                <span>LORE-ENGINE TERMINAL v1.0</span>
                <span>STATUS: ONLINE</span>
            </div>
        `;

        quotes.forEach(q => {
            const author = q.authors && q.authors.length > 0 ? q.authors[0] : 'Unknown';
            const text = q.text || q.content || 'Lost content';
            const p = document.createElement('p');
            p.className = 'text-xl mb-2 text-green-400 font-mono truncate';
            p.textContent = `> [${author}]: "${text}"`;
            terminal.appendChild(p);
        });
    } catch (error) {
        const terminal = document.getElementById('live-lore-terminal');
        if (terminal) {
            terminal.innerHTML = `
                <div class="flex justify-between border-b border-red-900 pb-3 mb-4 text-sm text-red-600">
                    <span>LORE-ENGINE TERMINAL v1.0</span>
                    <span>STATUS: OFFLINE</span>
                </div>
                <p class="text-xl mb-2 text-red-400 font-mono">> The backend is disconnected, please pair your Bluetooth device.</p>
            `;
        }
    }
}

// Memory Lane Gallery Cards
async function loadMemoryLane() {
    try {
        const response = await fetch('http://localhost:8000/api/quotes?limit=6&shuffle=true');
        if (!response.ok) throw new Error('API offline');

        const quotes = await response.json();
        const grid = document.getElementById('memory-lane-grid');
        if (!grid) return;

        grid.innerHTML = '';
        quotes.forEach(q => {
            const authors = q.authors ? q.authors.join(', ') : 'Unknown';
            const channel = q.channel ? `#${q.channel}` : '#general';
            const text = q.text || q.content || 'Lost Memory';
            const card = document.createElement('div');
            card.className = 'bg-slate-950 border-2 border-slate-800 p-6 rounded hover:border-cyan-400 transition-colors flex flex-col justify-between';
            card.innerHTML = `
                <div>
                    <div class="flex justify-between items-center text-xs text-cyan-400 font-mono mb-3">
                        <span>${channel}</span>
                        <span class="text-slate-500">${q.timestamp || ''}</span>
                    </div>
                    <p class="text-lg text-slate-200 mb-4 leading-snug">"${text}"</p>
                </div>
                <div class="text-xs text-pink-400 font-mono mt-2 pt-3 border-t border-slate-900">
                    — ${authors}
                </div>
            `;
            grid.appendChild(card);
        });
    } catch (error) {
        const grid = document.getElementById('memory-lane-grid');
        if (grid) {
            grid.innerHTML = `<p class="text-slate-500 font-mono col-span-3 text-center">// Error connecting.</p>`;
        }
    }
}

// Fetch Server Stats
async function loadServerStats() {
    try {
        const response = await fetch('http://localhost:8000/api/stats');
        if (!response.ok) throw new Error('Failed to fetch server stats');

        const stats = await response.json();
        
        const totalChunksEl = document.getElementById('stat-chunks');
        const totalMsgsEl = document.getElementById('stat-messages');
        const topAuthorsEl = document.getElementById('stat-top-authors');

        if(totalChunksEl) totalChunksEl.textContent = stats.total_chunks || 0;
        if (totalMsgsEl) totalMsgsEl.textContent = stats.total_messages || 0;

        if (topAuthorsEl && stats.top_authors) {
            topAuthorsEl.innerHTML = '';
            for (const [author, count] of Object.entries(stats.top_authors)) {
                const li = document.createElement('li');
                li.className = 'flex justify-between text-slate-300 font-mono text-sm py-1 border-b border-slate-800';
                li.innerHTML = `<span>${author}</span> <span class="text-cyan-400">${count} chunks</span>`;
                topAuthorsEl.appendChild(li);
            }
        }
    } catch (error) {
        console.log("Stats not found:", error);
    }
}

// The "Who Said It?" quizz
async function loadTriviaQuiz() {
    const container = document.getElementById('trivia-container');
    if (!container) return;

    container.innerHTML = `<p class="text-slate-400 font-mono text-center py-4">Generating question...</p>`;

    try {
        const response = await fetch('http://localhost:8000/api/game/who-said-it');
        if (!response.ok) throw new Error('Could not fetch quiz');

        const quiz = await response.json();

        container.innerHTML = `
            <div class="mb-4 text-xs font-mono text-cyan-400">${quiz.hint.channel} | ${quiz.hint.date}</div>
            <p class="text-xl md:text-2xl text-white mb-6 font-semibold">${quiz.question}</p>
            <div id="trivia-options" class="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-4"></div>
            <div id="trivia-feedback" class="text-lg font-mono mt-2"></div>
            <button onclick="loadTriviaQuiz()" class="mt-4 bg-slate-800 hover:bg-slate-700 text-cyan-300 px-4 py-2 text-xs font-mono border border-slate-600 transition-colors">
                NEXT QUESTION ➤
            </button>
        `;

        const optionsGrid = document.getElementById('trivia-options');
        quiz.options.forEach(option => {
            const btn = document.createElement('button');
            btn.className = 'bg-slate-950 border-2 border-slate-800 p-3 text-left text-slate-200 hover:border-cyan-400 hover:text-cyan-400 font-mono transition-colors rounded';
            btn.textContent = option;
            btn.onclick = () => {
                const allButtons = optionsGrid.querySelectorAll('button');
                allButtons.forEach(b => b.disabled = true);

                const feedback = document.getElementById('trivia-feedback');
                feedback.classList.remove('hidden');

                if (option === quiz.correct_answer) {
                    btn.classList.add('border-green-500', 'bg-green-950/40', 'text-green-400');
                    feedback.textContent = `Correct! ٩(◕‿◕｡)۶ Indeed it was ${quiz.correct_answer}.`;
                    feedback.className = "text-lg font-mono mt-2 text-green-400";
                } else {
                    btn.classList.add('border-red-500', 'bg-red-950/40', 'text-red-400');
                    feedback.textContent = `WRONG! ヾ( ￣O￣)ツ It was ${quiz.correct_answer}.`;
                    feedback.className = "text-lg font-mono mt-2 text-red-400";
                    allButtons.forEach(b => {
                        if (b.textContent === quiz.correct_answer) {
                            b.classList.add('border-green-500', 'bg-green-950/40', 'text-green-400');
                        }
                    });
                }
            };
            optionsGrid.appendChild(btn);
        });
    } catch (error) {
        container.innerHTML = `<p class="text-slate-500 font-mono text-center py-4">// Start FastAPI to play the quiz.</p>`;
    }
}

window.addEventListener('DOMContentLoaded', () => {
    loadLiveLore();
    loadMemoryLane();
    loadServerStats();
    loadTriviaQuiz();
});