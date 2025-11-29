//fireworks.js

// ===================================================================
// FIREWORKS CANVAS ANIMATION LOGIC (Refactored)
// ===================================================================

(function() {
    // -------------------------------------------------------------------
    // 1. CONFIGURATION & STATE
    // -------------------------------------------------------------------

    // DOM Elements
    const canvas = document.getElementById('fireworksCanvas');
    const ctx = canvas?.getContext('2d');
    const body = document.body;
    const toggleColorButton = document.getElementById('toggleColorButton');
    const gravityToggleButton = document.getElementById('gravityToggleButton');
    const toggleFireworksButton = document.getElementById('toggleFireworksButton');
    const messageBox = document.getElementById('message-box');

    // Constants
    const MAX_PARTICLES = 500;
    const NUM_STARS = 400;
    const GROUND_HEIGHT = 50;
    const GRAVITY_BASE = 0.05;
    const CELESTIAL_SPEED = 0.00008;
    const HUE_TRANSITION_RATE = 0.1;
    const MIN_AUTO_DELAY = 2000;
    const MAX_AUTO_DELAY = 7000;
    const COLOR_HUE_MAP = {
        '#FFC300': 45, '#FF5733': 14, '#C70039': 344, '#900C3F': 329, '#581845': 316,
        '#33FFBD': 164, '#337AFF': 218, '#B833FF': 280, '#FFFFFF': 0, '#4DFF5E': 125,
        '#FF33CC': 320, '#33D7FF': 193, '#C0C0C0': 0, '#FF8A00': 31, '#AAFF33': 85,
        '#33AFFF': 200,
    };
    const COLOR_HEXES = Object.keys(COLOR_HUE_MAP);
    const GRAVITY_STATES = [
        { factor: 0.5, name: 'Low', class: 'gravity-low' },
        { factor: 1.0, name: 'Normal', class: 'gravity-normal' },
        { factor: 1.5, name: 'High', class: 'gravity-high' }
    ];

    // Dynamic State
    let rockets = [];
    let particles = [];
    let stars = [];
    let groundPoints = [];
    let flare = { active: false, x: 0, y: 0, hue: 0, life: 0, maxLife: 30 };
    let autoLaunchTimer = null;
    let celestialPosition = 0;
    let currentGravityIndex = 1;
    let currentBgHue = 240;
    let targetBgHue = 240;

    // Persistence Initialization
    const savedTheme = localStorage.getItem('themePreference');
    let isDarkMode = savedTheme === 'light' ? false : (savedTheme === 'dark' ? true : window.matchMedia('(prefers-color-scheme: dark)').matches);
    const savedAnimationState = localStorage.getItem('fireworksAnimation');
    let isAnimating = savedAnimationState !== 'false';


    // -------------------------------------------------------------------
    // 2. UTILITY FUNCTIONS
    // -------------------------------------------------------------------

    function showMessage(text, duration = 3000) {
        if (!messageBox) return;
        messageBox.textContent = text;
        messageBox.style.opacity = 1;
        messageBox.style.pointerEvents = 'auto';
        setTimeout(() => {
            messageBox.style.opacity = 0;
            messageBox.style.pointerEvents = 'none';
        }, duration);
    }

    function randomColor() {
        const hex = COLOR_HEXES[Math.floor(Math.random() * COLOR_HEXES.length)];
        return { hex, hue: COLOR_HUE_MAP[hex] };
    }

    // Helper function for distance calculation
    function distance(x1, y1, x2, y2) {
        return Math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2);
    }

    // -------------------------------------------------------------------
    // 3. UI CONTROLS & STATE MANAGEMENT
    // -------------------------------------------------------------------

    function updateGravityButton() {
        if (!gravityToggleButton) return;
        const currentState = GRAVITY_STATES[currentGravityIndex];
        const nextIndex = (currentGravityIndex + 1) % GRAVITY_STATES.length;
        const label = `Gravity: ${currentState.name}. Click to switch to ${GRAVITY_STATES[nextIndex].name}`;
        gravityToggleButton.setAttribute('aria-label', `Gravity: ${currentState.name}. Click to switch to ${GRAVITY_STATES[nextIndex].name}`);
        gravityToggleButton.setAttribute('title', label)
    }

    function toggleGravity() {
        currentGravityIndex = (currentGravityIndex + 1) % GRAVITY_STATES.length;
        showMessage(`Gravity set to ${GRAVITY_STATES[currentGravityIndex].name}`, 2000);
        updateGravityButton();
    }

    function updateFireworksButton() {
        if (!toggleFireworksButton) return;

        if (isAnimating) {
            const label = 'Turn off fireworks animation';
            toggleFireworksButton.setAttribute('aria-label', label);
            toggleFireworksButton.setAttribute('title', label); // ADDED: Sets the hover text
            toggleFireworksButton.querySelector('span').textContent = '🎆';
        } else {
            const label = 'Turn on fireworks animation';
            toggleFireworksButton.setAttribute('aria-label', label);
            toggleFireworksButton.setAttribute('title', label); // ADDED: Sets the hover text
            toggleFireworksButton.querySelector('span').textContent = '🚫';
        }
    }

    function toggleFireworks() {
        isAnimating = !isAnimating;
        localStorage.setItem('fireworksAnimation', isAnimating);
        updateFireworksButton();

        if (isAnimating) {
            showMessage('Fireworks ON! 🎉');
            startAutoLaunch();
            requestAnimationFrame(animate); // Restart loop if needed
        } else {
            showMessage('Fireworks OFF. 😴');
            stopAutoLaunch();
            // Clear dynamic elements and redraw static sky
            if (ctx && canvas) {
                ctx.clearRect(0, 0, canvas.width, canvas.height);
                updateBackgroundColor();
                drawStars();
                drawSun();
                drawMoon();
                drawGround();
            }
        }
    }

    function updateToggleText() {
        if (!toggleColorButton) return;
        const modeText = isDarkMode ? 'Light Mode' : 'Dark Mode';
        const label = 'Switch to ${modeText}';
        toggleColorButton.setAttribute('aria-label', `Switch to ${modeText}`);
        toggleColorButton.setAttribute('title', label);
        toggleColorButton.querySelector('span').textContent = isDarkMode ? '🔦' : '☀️';
    }

    function toggleMode() {
        isDarkMode = !isDarkMode;
        body.classList.toggle('light-mode', !isDarkMode);
        currentBgHue = 240;
        targetBgHue = 240;
        updateToggleText();
        localStorage.setItem('themePreference', isDarkMode ? 'dark' : 'light');
    }

    function updateBackgroundColor() {
        const diff = targetBgHue - currentBgHue;
        // Smooth hue transition logic
        currentBgHue += (diff > 180 ? (diff - 360) : diff < -180 ? (diff + 360) : diff) * HUE_TRANSITION_RATE;
        currentBgHue = (currentBgHue % 360 + 360) % 360; // Normalize hue

        body.style.backgroundColor = `hsl(${currentBgHue}, ${isDarkMode ? 70 : 40}%, ${isDarkMode ? 8 : 85}%)`;
    }

    // -------------------------------------------------------------------
    // 4. CANVAS DRAWING HELPERS
    // -------------------------------------------------------------------

    function resizeCanvas() {
        if (!canvas) return;
        canvas.width = window.innerWidth;
        canvas.height = window.innerHeight;
        initStars();
        initGround();
    }

    function initStars() {
        stars = [];
        if (!canvas) return;
        for (let i = 0; i < NUM_STARS; i++) {
            stars.push({
                x: Math.random() * canvas.width,
                y: Math.random() * canvas.height * 0.7,
                radius: Math.random() * 1.5 + 0.5,
                opacity: Math.random(),
                blinkRate: (Math.random() * 0.05 + 0.01) * (Math.random() < 0.5 ? 1 : -1)
            });
        }
    }

    function drawStars() {
        if (!ctx || !isDarkMode) return;
        ctx.fillStyle = 'white';
        stars.forEach(star => {
            star.opacity += star.blinkRate;
            if (star.opacity > 1 || star.opacity < 0.2) star.blinkRate *= -1;
            ctx.save();
            ctx.globalAlpha = star.opacity;
            ctx.beginPath();
            ctx.arc(star.x, star.y, star.radius, 0, Math.PI * 2);
            ctx.fill();
            ctx.restore();
        });
    }

    function drawSun() {
        if (!ctx || isDarkMode) return;
        const sunX = canvas.width * (0.1 + 0.8 * celestialPosition);
        const sunY = canvas.height * 0.05;
        const diskRadius = canvas.width * 0.03;
        const radiusOuter = canvas.width * 0.7;
        ctx.save();

        // Sun Disk and Border
        ctx.fillStyle = 'rgba(255, 255, 220, 0.90)';
        ctx.strokeStyle = '#ffd900';
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.arc(sunX, sunY, diskRadius, 0, Math.PI * 2);
        ctx.fill();
        ctx.stroke();

        // Sun Glow
        const gradient = ctx.createRadialGradient(sunX, sunY, diskRadius * 0.5, sunX, sunY, radiusOuter);
        gradient.addColorStop(0, 'rgba(255, 255, 180, 0.9)');
        gradient.addColorStop(0.1, 'rgba(255, 255, 220, 0.5)');
        gradient.addColorStop(0.3, 'rgba(255, 255, 255, 0.2)');
        gradient.addColorStop(1, 'rgba(255, 255, 255, 0)');
        ctx.fillStyle = gradient;
        ctx.beginPath();
        ctx.arc(sunX, sunY, radiusOuter, 0, Math.PI * 2);
        ctx.fill();
        ctx.restore();
    }

    function drawMoon() {
        if (!ctx || !isDarkMode) return;
        const moonX = canvas.width * (0.9 - 0.8 * celestialPosition);
        const moonY = canvas.height * 0.1;
        const moonRadius = canvas.width * 0.03;
        ctx.save();

        // Full moon disk
        ctx.fillStyle = 'rgba(255, 255, 255, 0.95)';
        ctx.beginPath();
        ctx.arc(moonX, moonY, moonRadius, 0, Math.PI * 2);
        ctx.fill();

        // Shadow for crater effect
        ctx.fillStyle = 'rgba(0, 0, 0, 0.2)';
        [
            { r: 0.15, dx: -0.3, dy: -0.3 },
            { r: 0.2, dx: 0.2, dy: 0.4 },
            { r: 0.1, dx: 0.4, dy: -0.05 }
        ].forEach(crater => {
            ctx.beginPath();
            ctx.arc(moonX + moonRadius * crater.dx, moonY + moonRadius * crater.dy, moonRadius * crater.r, 0, Math.PI * 2);
            ctx.fill();
        });

        ctx.restore();
    }

    function initGround() {
        groundPoints = [];
        if (!canvas) return;
        const segments = 15;
        const segmentWidth = canvas.width / segments;
        for (let i = 0; i <= segments; i++) {
            const x = i * segmentWidth;
            // Add slight randomness for a natural look
            const y = canvas.height - GROUND_HEIGHT + (Math.random() * 20 - 10);
            groundPoints.push({ x, y });
        }
    }

    function drawGround() {
        if (!ctx || !groundPoints.length) return;
        ctx.save();
        ctx.fillStyle = isDarkMode ? 'rgba(0, 0, 0, 0.9)' : 'rgba(180, 180, 180, 0.9)';
        ctx.beginPath();
        ctx.moveTo(0, canvas.height);
        ctx.lineTo(groundPoints[0].x, groundPoints[0].y);

        // Use bezier curves for smooth ground texture
        for (let i = 1; i < groundPoints.length; i++) {
            const cpX = (groundPoints[i-1].x + groundPoints[i].x) / 2;
            const cpY = groundPoints[i-1].y;
            ctx.bezierCurveTo(cpX, cpY, cpX, groundPoints[i].y, groundPoints[i].x, groundPoints[i].y);
        }

        ctx.lineTo(canvas.width, canvas.height);
        ctx.closePath();
        ctx.fill();
        ctx.restore();
    }

    function drawFlare() {
        if (!ctx || !flare.active || flare.life <= 0) return;
        const alpha = (flare.life / flare.maxLife) * 0.5;
        const radius = 50 + (1 - flare.life / flare.maxLife) * 150;

        ctx.save();
        ctx.globalCompositeOperation = 'lighter';
        const gradient = ctx.createRadialGradient(flare.x, flare.y, 0, flare.x, flare.y, radius);
        gradient.addColorStop(0, `hsla(${flare.hue}, 100%, 90%, ${alpha * 0.8})`);
        gradient.addColorStop(0.3, `hsla(${flare.hue}, 80%, 70%, ${alpha * 0.4})`);
        gradient.addColorStop(1, `hsla(${flare.hue}, 0%, 0%, 0)`);
        ctx.fillStyle = gradient;
        ctx.beginPath();
        ctx.arc(flare.x, flare.y, radius, 0, Math.PI * 2);
        ctx.fill();
        ctx.restore();

        flare.life--;
        if (flare.life <= 0) flare.active = false;
    }


    // -------------------------------------------------------------------
    // 5. FIREWORK CLASSES
    // -------------------------------------------------------------------

    class Particle {
        constructor(x, y, vx, vy, color, lifeTime = 100) {
            this.x = x;
            this.y = y;
            // Randomized velocity for spread
            this.vx = vx * (Math.random() * 0.5 + 0.5);
            this.vy = vy * (Math.random() * 0.5 + 0.5);
            this.color = color;
            this.alpha = 1;
            this.life = lifeTime;
            this.friction = 0.98;
            this.size = Math.random() * 2 + 1;
        }

        update() {
            // Apply current gravity factor
            this.vy += GRAVITY_BASE * GRAVITY_STATES[currentGravityIndex].factor * 0.5;
            this.vx *= this.friction;
            this.x += this.vx;
            this.y += this.vy;
            this.alpha -= 0.01;
            this.life--;
        }

        draw() {
            if (!ctx) return;
            ctx.save();
            ctx.globalAlpha = this.alpha;

            // Draw with a radial gradient for a glow effect
            const gradient = ctx.createRadialGradient(this.x, this.y, 0, this.x, this.y, this.size);
            gradient.addColorStop(0, this.color);
            gradient.addColorStop(1, 'rgba(0, 0, 0, 0)');
            ctx.fillStyle = gradient;

            ctx.beginPath();
            ctx.arc(this.x, this.y, this.size, 0, Math.PI * 2);
            ctx.fill();
            ctx.restore();
        }
    }

    class Firework {
        constructor(startX, startY, endX, endY, type = 'standard') {
            const colorObj = randomColor();
            this.x = startX;
            this.y = startY;
            this.endX = endX;
            this.endY = endY;
            this.color = colorObj.hex;
            this.hue = colorObj.hue;
            this.exploded = false;
            this.trail = [];
            this.speed = 15;
            this.type = type;

            const dist = distance(startX, startY, endX, endY);
            this.vx = (endX - startX) / dist * this.speed;
            this.vy = (endY - startY) / dist * this.speed;
            this.targetY = Math.min(startY, endY);
        }

        createParticles(count, velocityBase, whiteInner = false, innerLife = 40) {
            const particlesToAdd = [];
            for (let i = 0; i < count; i++) {
                const angle = Math.random() * Math.PI * 2;
                let velocity = Math.random() * velocityBase + 1;
                let color = this.color;
                let life = 100;

                // Special handling for 'flower' type
                if (whiteInner && i < count * 0.4) { // Approximately 40% inner white particles
                    color = '#FFFFFF';
                    life = innerLife;
                    velocity = Math.random() * 2 + 0.5;
                } else if (whiteInner) {
                    velocity = Math.random() * 6 + 3;
                }

                particlesToAdd.push(new Particle(
                    this.x, this.y,
                    Math.cos(angle) * velocity,
                    Math.sin(angle) * velocity,
                    color,
                    life
                ));
            }
            particles.push(...particlesToAdd.slice(0, MAX_PARTICLES - particles.length));
        }

        explode() {
            this.exploded = true;
            targetBgHue = this.hue;

            flare.active = true; flare.x = this.x; flare.y = this.y; flare.hue = this.hue; flare.life = flare.maxLife;

            if (this.type === 'bomb') {
                const bombRockets = 5 + Math.floor(Math.random() * 5);
                for (let i = 0; i < bombRockets; i++) {
                    const angle = Math.random() * Math.PI * 2;
                    const velocity = 4;
                    // Create smaller, immediately exploding secondary rockets
                    const secondaryRocket = new Firework(this.x, this.y, this.x + Math.cos(angle) * velocity * 10, this.y + Math.sin(angle) * velocity * 10, 'standard');
                    secondaryRocket.color = this.color;
                    secondaryRocket.hue = this.hue;

                    secondaryRocket.explode = function() {
                        this.exploded = true;
                        this.createParticles(40, 3); // Override particle creation
                    };
                    rockets.push(secondaryRocket);
                    secondaryRocket.explode(); // Explode immediately
                }
                return;
            }

            if (this.type === 'flower') {
                this.createParticles(120, 5, true);
            } else { // 'standard' or other unknown types
                this.createParticles(70 + Math.floor(Math.random() * 50), 5);
            }
        }

        update() {
            if (this.exploded) return;

            // Check if passed target Y (or hit it and velocity changed direction)
            if (this.y <= this.targetY || (this.vy > 0 && this.y >= this.targetY)) {
                this.explode();
                return;
            }

            // Apply gravity
            this.vy += GRAVITY_BASE * GRAVITY_STATES[currentGravityIndex].factor;
            this.x += this.vx;
            this.y += this.vy;

            // Create trail particle
            if (Math.random() < 0.5) {
                particles.push(new Particle(
                    this.x, this.y,
                    this.vx * -0.1 + (Math.random() - 0.5) * 0.5,
                    this.vy * -0.1 + Math.random() * 0.5,
                    '#FFFFFF',
                    30
                ));
            }

            this.trail.push({ x: this.x, y: this.y, color: this.color });
            if (this.trail.length > 5) this.trail.shift();
        }

        draw() {
            if (!ctx || this.exploded) return;

            // Draw trail
            for (let i = 0; i < this.trail.length; i++) {
                ctx.save();
                ctx.globalAlpha = (i / this.trail.length) * 0.8;
                ctx.fillStyle = this.color;
                ctx.beginPath();
                ctx.arc(this.trail[i].x, this.trail[i].y, 1.5, 0, Math.PI * 2);
                ctx.fill();
                ctx.restore();
            }

            // Draw rocket head
            ctx.save();
            ctx.fillStyle = 'white';
            ctx.beginPath();
            ctx.arc(this.x, this.y, 2, 0, Math.PI * 2);
            ctx.fill();
            ctx.restore();
        }
    }


    // -------------------------------------------------------------------
    // 6. ANIMATION AND INPUT HANDLERS
    // -------------------------------------------------------------------

    function launchFireworkAt(x, y, type = 'standard') {
        if (!isAnimating || !canvas) return;

        // Randomly choose special types
        const launchRoll = Math.random();
        if (launchRoll < 0.20) type = 'bomb';
        else if (launchRoll < 0.40) type = 'flower';

        const startX = canvas.width / 2 + (Math.random() - 0.5) * canvas.width * 0.1;
        const startY = canvas.height;
        const minExplodeY = canvas.height * 0.2;

        rockets.push(new Firework(startX, startY, x, Math.min(y, minExplodeY), type));
    }

    function startAutoLaunch() {
        if (!isAnimating || autoLaunchTimer) return;
        const launch = () => {
            if (!isAnimating) {
                clearTimeout(autoLaunchTimer);
                autoLaunchTimer = null;
                return;
            }
            const targetX = Math.random() * canvas.width;
            const targetY = Math.random() * canvas.height * 0.8;
            launchFireworkAt(targetX, targetY);
            const nextDelay = Math.floor(Math.random() * (MAX_AUTO_DELAY - MIN_AUTO_DELAY + 1)) + MIN_AUTO_DELAY;
            autoLaunchTimer = setTimeout(launch, nextDelay);
        };
        launch();
    }

    function stopAutoLaunch() {
        if (autoLaunchTimer) {
            clearTimeout(autoLaunchTimer);
            autoLaunchTimer = null;
        }
    }

    function getCoordinates(e) {
        return e.touches?.length > 0 ? { x: e.touches[0].clientX, y: e.touches[0].clientY } : { x: e.clientX, y: e.clientY };
    }

    function handleImmediateLaunch(e) {
        // Prevent launch if animating is off or if clicking on a control element
        if (!isAnimating) return;
        if (e.target.closest('#app-header, #main-content-wrapper, #fireworks-controls, #mobile-nav-overlay, #crop-modal, #message-box')) return;

        const { x, y } = getCoordinates(e);
        launchFireworkAt(x, y);
    }

    function setupEventListeners() {
        if (!canvas) return;
        window.addEventListener('resize', resizeCanvas);
        document.addEventListener('click', handleImmediateLaunch);
        document.addEventListener('touchstart', handleImmediateLaunch);

        if (toggleColorButton) { toggleColorButton.addEventListener('click', toggleMode); }
        if (gravityToggleButton) { gravityToggleButton.addEventListener('click', toggleGravity); }
        if (toggleFireworksButton) { toggleFireworksButton.addEventListener('click', toggleFireworks); }

        document.addEventListener('visibilitychange', () => {
            if (!isAnimating) return;
            if (!document.hidden) startAutoLaunch();
            else stopAutoLaunch();
        });
    }


    // -------------------------------------------------------------------
    // 7. MAIN ANIMATION LOOP
    // -------------------------------------------------------------------

    function animate() {
        if (!canvas || !ctx) return;

        // Background update (always runs)
        celestialPosition = (celestialPosition + CELESTIAL_SPEED) % 1;
        updateBackgroundColor();

        // H1 shadow effect
        const pageH1 = document.querySelector('.content h1');
        if (pageH1) {
            const shadowColor = isDarkMode ? `hsl(${currentBgHue}, 100%, 85%)` : `transparent`;
            pageH1.style.textShadow = `0 0 5px ${shadowColor}, 0 0 10px ${shadowColor}`;
        }

        // Clear canvas
        const clearAlpha = isDarkMode ? 0.1 : 0.05;
        // Use full opacity clear when animation is off to ensure a clean, static background
        ctx.fillStyle = `hsla(${currentBgHue}, ${isDarkMode ? 70 : 40}%, ${isDarkMode ? 8 : 85}%, ${isAnimating ? clearAlpha : 1})`;
        ctx.fillRect(0, 0, canvas.width, canvas.height);

        // Draw static elements
        drawStars();
        drawSun();
        drawMoon();
        drawGround();

        // Draw dynamic elements (only if animating)
        if (isAnimating) {
            drawFlare();

            // Update and draw rockets
            rockets = rockets.filter(r => !r.exploded);
            rockets.forEach(r => { r.update(); r.draw(); });

            // Update and draw particles
            particles = particles.filter(p => p.life > 0 && p.alpha > 0).slice(-MAX_PARTICLES);
            particles.forEach(p => { p.update(); p.draw(); });
        }

        requestAnimationFrame(animate);
    }


    // -------------------------------------------------------------------
    // 8. INITIALIZATION
    // -------------------------------------------------------------------

    document.addEventListener('DOMContentLoaded', () => {
        if (!canvas || !ctx) {
            console.error('Fireworks Canvas or context not found');
            return;
        }

        if (!isDarkMode) body.classList.add('light-mode');

        resizeCanvas();
        updateToggleText();
        updateGravityButton();
        updateFireworksButton();
        setupEventListeners();

        // Start the main animation loop and auto-launch conditionally
        animate();
        if (isAnimating) {
            startAutoLaunch();
        }
    });
})();