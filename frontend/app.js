// app.js

// Background Effect
const canvas = document.getElementById('bg-canvas');
if (canvas) {
    const ctx = canvas.getContext('2d');

    let width = canvas.width = window.innerWidth;
    let height = canvas.height = window.innerHeight;

    window.addEventListener('resize', () => {
        width = canvas.width = window.innerWidth;
        height = canvas.height = window.innerHeight;

        particles.forEach(p => {
            p.x = Math.random() * width;
            p.y = Math.random() * height;
            p.trail = [];
        });
    });

    // Colours and the spots
    const pastelColors = [
        'rgba(255, 0, 0, ',
        'rgba(255, 0, 154, ',
        'rgba(255, 162, 0, ',
        'rgba(137, 255, 0, ',
        'rgba(0, 255, 0, ',
        'rgba(0, 137, 255, ',
        'rgba(0, 255, 239, ',
        'rgba(0, 0, 255, ',
        'rgba(213, 0, 255, ',
        'rgba(137, 0, 255, '
    ];

    const particleCount = 45
    const particles = [];

    for (let i = 0; i < particleCount; i++) {
        particles.push({
            x: Math.random() * width,
            y: Math.random() * height,
            size: Math.random() * 2.5 + 1,
            speedY: Math.random() * 0.3 + 0.1,
            colorBase: pastelColors[Math.floor(Math.random() * pastelColors.length)],
            targetAlpha: Math.random() * 0.4 + 0.2,
            alpha: Math.random() * 0.4 + 0.2,
            trail: []
        });
    }

    const boomSpot = [];
    const boomSpotColors = [
        'rgba(255, 30, 173, ',
        'rgba(245, 0, 0, ',
        'rgba(188, 28, 255, ',
        'rgba(0, 6, 176, ',
        'rgba(0, 255, 213, ',
        'rgba(255, 172, 77, ',
        'rgba(255, 111, 0, '
    ];

    function spawnBoomSpot() {
        if(document.hidden) return;
        boomSpot.push({
            x: Math.random() * width,
            y: Math.random() * height,
            radius: 15,
            maxRadius: Math.random() * 250 + 180,
            color: boomSpotColors[Math.floor(Math.random() * boomSpotColors.length)],
            alpha: 0,
            peakAlpha: Math.random() * 0.35 + 0.2,
            life: 0,
            maxLife: Math.random() * 250 + 200
        });
    }

    let boomSpotInterval = setInterval(spawnBoomSpot, 1500);

    document.addEventListener("visibilitychange", () => {
        if (document.hidden) {
            clearInterval(boomSpotInterval);
        } else {
            boomSpot.length = 0;
            boomSpotInterval = setInterval(spawnBoomSpot, 1500);
        }
    });

    let lastScrollY = window.scrollY;
    let scrollVelocity = 0;

    window.addEventListener('scroll', () => {
        const currentScrollY = window.scrollY;
        scrollVelocity = (currentScrollY - lastScrollY) * 0.3;
        lastScrollY = currentScrollY;
    });

    function animateBackground() {
        if (!document.hidden) {
            ctx.clearRect(0, 0, width, height);

            boomSpot.forEach((sn, index) => {
                sn.life++;

                const progress = sn.life / sn.maxLife;
                if (progress < 0.3) {
                    sn.alpha = (progress / 0.3) * sn.peakAlpha;
                } else {
                    sn.alpha = (1 - (progress - 0.3) / 0.7) * sn.peakAlpha;
                }

                sn.radius += 0.2;

                const gradient = ctx.createRadialGradient(sn.x, sn.y, 0, sn.x, sn.y, sn.radius);
                gradient.addColorStop(0, sn.color + sn.alpha + ')');
                gradient.addColorStop(1, sn.color + '0)');

                ctx.beginPath();
                ctx.arc(sn.x, sn.y, sn.radius, 0, Math.PI * 2);
                ctx.fillStyle = gradient;
                ctx.fill();

                if (sn.life >= sn.maxLife) {
                    boomSpot.splice(index, 1);
                }
            });

            particles.forEach(p => {
                p.y += p.speedY + (scrollVelocity * 0.1);

                if (p.alpha < p.targetAlpha) {
                    p.alpha += 0.005;
                }
                if (p.y > height) {
                    p.y = 0;
                    p.x = Math.random() * width;
                    p.alpha = 0;
                    p.trail = [];
                }
                if (p.y < 0) {
                    p.y = height;
                    p.x = Math.random() * width;
                    p.alpha = 0;
                    p.trail = [];
                }

                p.trail.unshift({ x: p.x, y: p.y });
                if (p.trail.length > 12) {
                    p.trail.pop();
                }

                p.trail.forEach((point, index) => {
                    const trailAlpha = (p.alpha * (1 - index / p.trail.length)) * 0.5;
                    const trailSize = p.size * (1 - index / p.trail.length);

                    ctx.beginPath();
                    ctx.arc(point.x, point.y, trailSize, 0, Math.PI * 2);
                    ctx.fillStyle = p.colorBase + trailAlpha + ')';
                    ctx.fill();
                });

                ctx.beginPath();
                ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
                ctx.fillStyle = p.colorBase + p.alpha + ')';
                ctx.shadowBlur = 10;
                ctx.shadowColor = p.colorBase + '0.6)';
                ctx.fill();
            });

            scrollVelocity *= 0.9;
        }

        requestAnimationFrame(animateBackground);
    }

    animateBackground();
}

// Scroll-driven Animation & Nav Logo Animation
window.addEventListener('scroll', function() {
    const scrollY = window.scrollY;
    const heroContent = document.getElementById('hero-content');
    const navLogo = document.getElementById('nav-logo');
    const chatBubbles = document.querySelectorAll('.discord-bubble');
    const maxScroll = 400;
    const progress = Math.min(scrollY / maxScroll, 1);

    if (heroContent && navLogo) {
        if (scrollY <= maxScroll) {
            heroContent.style.transform = `translateY(${scrollY * 0.4}px) scale(${1 - progress * 0.15})`;
            heroContent.style.opacity = 1 - progress * 1.5;
            navLogo.style.opacity = progress;

            chatBubbles.forEach(bubble => {
                bubble.style.opacity = 0.65 - (progress * 0.65);
            });
        } else {
            heroContent.style.opacity = 0;
            navLogo.style.opacity = 1;

            chatBubbles.forEach(bubble => {
                bubble.style.opacity = 0
            });
        }
    }
});

// Fetch LIVELORE Terminal Feed from Backend
async function loadLiveLore() {
    const terminalBox = document.getElementById('terminal-box');
    const terminal = document.getElementById('live-lore-terminal');
    if (!terminal || !terminalBox) return;

    try {
        const response = await fetch('http://localhost:8000/api/quotes?limit=3&shuffle=true');
        if (!response.ok) throw new Error('API offline');

        const quotes = await response.json();

        terminalBox.className = "relative bg-black border-2 border-green-500/80 p-8 font-mono text-green-400 text-lg neon-glow-green pixel-box overflow-hidden transition-colors duration-300";

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
        terminalBox.className = "relative bg-black border-2 border-red-500/80 p-8 font-mono text-red-400 text-lg neon-glow-magenta pixel-box overflow-hidden transition-colors duration-300";

        terminal.innerHTML = `
            <div class="flex justify-between border-b border-red-900 pb-3 mb-4 text-sm text-red-600">
                <span>LORE-ENGINE TERMINAL v1.0</span>
                <span>STATUS: OFFLINE</span>
            </div>
            <p class="text-xl mb-2 text-red-400 font-mono">> The backend is disconnected, please pair your Bluetooth device.</p>
        `;
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