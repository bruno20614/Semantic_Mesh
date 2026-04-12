/* Semantic Mesh — animated graph background */
(function () {
    const canvas = document.createElement('canvas');
    canvas.id = 'sm-graph-bg';
    canvas.style.cssText = [
        'position:fixed', 'top:0', 'left:0', 'width:100%', 'height:100%',
        'z-index:0', 'pointer-events:none',
    ].join(';');
    document.body.prepend(canvas);

    const ctx = canvas.getContext('2d');
    let W, H;

    const COLORS = ['#7c3aed', '#2563eb', '#0891b2', '#16a34a', '#d97706', '#9333ea', '#db2777'];
    const NODE_COUNT = 38;
    const MAX_DIST = 160;
    const OPACITY = 0.28;

    let nodes = [];

    function resize() {
        W = canvas.width = window.innerWidth;
        H = canvas.height = window.innerHeight;
    }

    function initNodes() {
        nodes = Array.from({ length: NODE_COUNT }, () => ({
            x: Math.random() * W,
            y: Math.random() * H,
            vx: (Math.random() - 0.5) * 0.45,
            vy: (Math.random() - 0.5) * 0.45,
            r: 2.5 + Math.random() * 3.5,
            color: COLORS[Math.floor(Math.random() * COLORS.length)],
            pulse: Math.random() * Math.PI * 2,
        }));
    }

    function hexToRgb(hex) {
        const r = parseInt(hex.slice(1, 3), 16);
        const g = parseInt(hex.slice(3, 5), 16);
        const b = parseInt(hex.slice(5, 7), 16);
        return `${r},${g},${b}`;
    }

    function animate() {
        ctx.clearRect(0, 0, W, H);

        for (const n of nodes) {
            n.x += n.vx;
            n.y += n.vy;
            n.pulse += 0.03;
            if (n.x < 0 || n.x > W) n.vx *= -1;
            if (n.y < 0 || n.y > H) n.vy *= -1;
        }

        // Edges
        for (let i = 0; i < nodes.length; i++) {
            for (let j = i + 1; j < nodes.length; j++) {
                const dx = nodes[i].x - nodes[j].x;
                const dy = nodes[i].y - nodes[j].y;
                const d = Math.sqrt(dx * dx + dy * dy);
                if (d < MAX_DIST) {
                    const alpha = (OPACITY * 0.7) * (1 - d / MAX_DIST);
                    ctx.beginPath();
                    ctx.moveTo(nodes[i].x, nodes[i].y);
                    ctx.lineTo(nodes[j].x, nodes[j].y);
                    ctx.strokeStyle = `rgba(124,58,237,${alpha.toFixed(3)})`;
                    ctx.lineWidth = 0.8;
                    ctx.stroke();
                }
            }
        }

        // Nodes
        for (const n of nodes) {
            const glow = 1 + 0.3 * Math.sin(n.pulse);
            const r = n.r * glow;
            const rgb = hexToRgb(n.color);

            // Soft halo
            const grad = ctx.createRadialGradient(n.x, n.y, 0, n.x, n.y, r * 3);
            grad.addColorStop(0, `rgba(${rgb},${(OPACITY * 0.9).toFixed(2)})`);
            grad.addColorStop(1, `rgba(${rgb},0)`);
            ctx.beginPath();
            ctx.arc(n.x, n.y, r * 3, 0, Math.PI * 2);
            ctx.fillStyle = grad;
            ctx.fill();

            // Core dot
            ctx.beginPath();
            ctx.arc(n.x, n.y, r, 0, Math.PI * 2);
            ctx.fillStyle = `rgba(${rgb},${(OPACITY * 1.4).toFixed(2)})`;
            ctx.fill();
        }

        requestAnimationFrame(animate);
    }

    resize();
    initNodes();
    animate();
    window.addEventListener('resize', () => { resize(); });
})();
