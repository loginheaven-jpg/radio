import { useState, useEffect, useRef, useCallback } from "react";

// ─── Confetti Particle System ───────────────────────────────────
function ConfettiCanvas({ active }) {
  const canvasRef = useRef(null);
  const particlesRef = useRef([]);
  const animRef = useRef(null);

  useEffect(() => {
    if (!active) return;
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    const W = (canvas.width = canvas.offsetWidth * 2);
    const H = (canvas.height = canvas.offsetHeight * 2);
    ctx.scale(1, 1);

    const goldPalette = [
      "#d4a45c", "#f0d490", "#c9983f", "#e8c868", "#b8862a",
      "#fff8e0", "#f5dfa0", "#a07830", "#dfc070", "#ffe8a0",
    ];

    // shapes: rect, circle, star, cross
    function createParticle() {
      return {
        x: Math.random() * W,
        y: -20 - Math.random() * H * 0.3,
        w: 4 + Math.random() * 8,
        h: 6 + Math.random() * 10,
        color: goldPalette[Math.floor(Math.random() * goldPalette.length)],
        rotation: Math.random() * Math.PI * 2,
        rotSpeed: (Math.random() - 0.5) * 0.15,
        vx: (Math.random() - 0.5) * 3,
        vy: 2 + Math.random() * 4,
        shape: Math.floor(Math.random() * 4),
        opacity: 0.6 + Math.random() * 0.4,
        wobble: Math.random() * Math.PI * 2,
        wobbleSpeed: 0.02 + Math.random() * 0.04,
      };
    }

    // Burst: create many particles at once
    for (let i = 0; i < 150; i++) {
      particlesRef.current.push(createParticle());
    }

    // Second wave after 600ms
    const wave2 = setTimeout(() => {
      for (let i = 0; i < 80; i++) {
        particlesRef.current.push(createParticle());
      }
    }, 600);

    function drawParticle(ctx, p) {
      ctx.save();
      ctx.translate(p.x, p.y);
      ctx.rotate(p.rotation);
      ctx.globalAlpha = p.opacity;
      ctx.fillStyle = p.color;

      switch (p.shape) {
        case 0: // rect
          ctx.fillRect(-p.w / 2, -p.h / 2, p.w, p.h);
          break;
        case 1: // circle
          ctx.beginPath();
          ctx.arc(0, 0, p.w / 2, 0, Math.PI * 2);
          ctx.fill();
          break;
        case 2: // star (4-point)
          ctx.beginPath();
          for (let i = 0; i < 8; i++) {
            const r = i % 2 === 0 ? p.w / 2 : p.w / 5;
            const a = (i * Math.PI) / 4;
            ctx.lineTo(Math.cos(a) * r, Math.sin(a) * r);
          }
          ctx.closePath();
          ctx.fill();
          break;
        case 3: // thin strip
          ctx.fillRect(-p.w / 2, -1, p.w, 2.5);
          break;
      }
      ctx.restore();
    }

    function animate() {
      ctx.clearRect(0, 0, W, H);
      const ps = particlesRef.current;
      for (let i = ps.length - 1; i >= 0; i--) {
        const p = ps[i];
        p.x += p.vx + Math.sin(p.wobble) * 0.8;
        p.y += p.vy;
        p.rotation += p.rotSpeed;
        p.wobble += p.wobbleSpeed;
        p.vy += 0.04; // gravity
        p.opacity -= 0.002;
        if (p.y > H + 20 || p.opacity <= 0) {
          ps.splice(i, 1);
          continue;
        }
        drawParticle(ctx, p);
      }
      animRef.current = requestAnimationFrame(animate);
    }
    animate();

    return () => {
      clearTimeout(wave2);
      cancelAnimationFrame(animRef.current);
      particlesRef.current = [];
    };
  }, [active]);

  return (
    <canvas
      ref={canvasRef}
      style={{
        position: "absolute",
        inset: 0,
        width: "100%",
        height: "100%",
        pointerEvents: "none",
        zIndex: 2,
      }}
    />
  );
}

// ─── Floating Gold Particles (Background) ───────────────────────
function FloatingParticle({ delay, x, char, size, opacity }) {
  return (
    <div
      style={{
        position: "absolute",
        bottom: "-20px",
        left: `${x}%`,
        fontSize: `${size}px`,
        opacity,
        animation: `floatUp ${14 + Math.random() * 6}s ${delay}s linear infinite`,
        pointerEvents: "none",
      }}
    >
      {char}
    </div>
  );
}

// ─── Celebration Splash (1안) ───────────────────────────────────
function CelebrationSplash({ onEnter }) {
  const [phase, setPhase] = useState("enter"); // enter → visible → exit
  const [visible, setVisible] = useState(true);

  useEffect(() => {
    const t1 = setTimeout(() => setPhase("visible"), 100);
    // Auto-dismiss after 8s if user doesn't tap
    const t2 = setTimeout(() => handleExit(), 8000);
    return () => {
      clearTimeout(t1);
      clearTimeout(t2);
    };
  }, []);

  const handleExit = useCallback(() => {
    setPhase("exit");
    setTimeout(() => {
      setVisible(false);
      onEnter?.();
    }, 800);
  }, [onEnter]);

  if (!visible) return null;

  const isVisible = phase === "visible";

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 9999,
        background: "#0D0B1A",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        opacity: phase === "exit" ? 0 : 1,
        transition: "opacity 0.8s ease",
        overflow: "hidden",
      }}
    >
      {/* Confetti */}
      <ConfettiCanvas active={true} />

      {/* Radial glow behind 40 */}
      <div
        style={{
          position: "absolute",
          top: "38%",
          left: "50%",
          transform: "translate(-50%, -50%)",
          width: "340px",
          height: "340px",
          borderRadius: "50%",
          background:
            "radial-gradient(circle, rgba(212,164,92,0.18) 0%, rgba(212,164,92,0.05) 40%, transparent 70%)",
          filter: "blur(30px)",
          pointerEvents: "none",
          opacity: isVisible ? 1 : 0,
          transition: "opacity 1.5s ease 0.3s",
        }}
      />

      {/* Content */}
      <div
        style={{
          position: "relative",
          zIndex: 3,
          textAlign: "center",
          padding: "0 32px",
        }}
      >
        {/* Cross symbol */}
        <div
          style={{
            fontSize: "18px",
            color: "#d4a45c",
            opacity: isVisible ? 0.5 : 0,
            transform: isVisible ? "translateY(0)" : "translateY(10px)",
            transition: "all 1s ease 0.2s",
            marginBottom: "16px",
            letterSpacing: "8px",
          }}
        >
          ✦ ✝ ✦
        </div>

        {/* The Big 40 */}
        <div
          style={{
            fontFamily: "'Space Grotesk', monospace",
            fontSize: "120px",
            fontWeight: 700,
            lineHeight: 1,
            background: "linear-gradient(135deg, #c9983f 0%, #f0d490 40%, #d4a45c 60%, #e8c868 100%)",
            WebkitBackgroundClip: "text",
            WebkitTextFillColor: "transparent",
            backgroundClip: "text",
            opacity: isVisible ? 1 : 0,
            transform: isVisible ? "scale(1)" : "scale(0.8)",
            transition: "all 1s cubic-bezier(0.34, 1.56, 0.64, 1) 0.3s",
            filter: "drop-shadow(0 4px 30px rgba(212,164,92,0.3))",
            letterSpacing: "-4px",
          }}
        >
          40
        </div>

        {/* th Anniversary */}
        <div
          style={{
            fontFamily: "'Space Grotesk', monospace",
            fontSize: "13px",
            fontWeight: 500,
            color: "#d4a45c",
            letterSpacing: "6px",
            textTransform: "uppercase",
            marginTop: "4px",
            opacity: isVisible ? 0.7 : 0,
            transform: isVisible ? "translateY(0)" : "translateY(8px)",
            transition: "all 0.8s ease 0.6s",
          }}
        >
          ANNIVERSARY
        </div>

        {/* Divider */}
        <div
          style={{
            width: "60px",
            height: "1px",
            background: "linear-gradient(90deg, transparent, #d4a45c, transparent)",
            margin: "24px auto",
            opacity: isVisible ? 0.5 : 0,
            transition: "opacity 1s ease 0.8s",
          }}
        />

        {/* Church name */}
        <div
          style={{
            fontFamily: "'Pretendard Variable', sans-serif",
            fontSize: "22px",
            fontWeight: 700,
            color: "#ece4d8",
            opacity: isVisible ? 1 : 0,
            transform: isVisible ? "translateY(0)" : "translateY(10px)",
            transition: "all 0.8s ease 0.9s",
          }}
        >
          예봄교회 40주년을 축하합니다
        </div>

        {/* Year range */}
        <div
          style={{
            fontFamily: "'Space Grotesk', monospace",
            fontSize: "13px",
            color: "#9a9494",
            marginTop: "8px",
            letterSpacing: "3px",
            opacity: isVisible ? 0.5 : 0,
            transition: "opacity 1s ease 1.1s",
          }}
        >
          1986 — 2026
        </div>

        {/* Scripture */}
        <div
          style={{
            fontFamily: "'Pretendard Variable', sans-serif",
            fontSize: "13px",
            lineHeight: 1.8,
            color: "#c9b896",
            marginTop: "28px",
            opacity: isVisible ? 0.6 : 0,
            transform: isVisible ? "translateY(0)" : "translateY(8px)",
            transition: "all 0.8s ease 1.3s",
            maxWidth: "300px",
            marginLeft: "auto",
            marginRight: "auto",
          }}
        >
          "여호와 우리 하나님의 은총을 우리에게 임하게 하사
          <br />
          우리의 손이 행한 일을 우리에게 견고하게 하소서"
          <br />
          <span style={{ fontSize: "11px", opacity: 0.6, marginTop: "4px", display: "inline-block" }}>
            — 시편 90:17
          </span>
        </div>

        {/* Enter button */}
        <button
          onClick={handleExit}
          style={{
            marginTop: "36px",
            padding: "14px 48px",
            borderRadius: "30px",
            border: "1px solid rgba(212,164,92,0.4)",
            background: "linear-gradient(135deg, rgba(212,164,92,0.15), rgba(212,164,92,0.05))",
            color: "#f0d490",
            fontSize: "14px",
            fontWeight: 600,
            fontFamily: "'Pretendard Variable', sans-serif",
            cursor: "pointer",
            letterSpacing: "2px",
            opacity: isVisible ? 1 : 0,
            transform: isVisible ? "translateY(0)" : "translateY(15px)",
            transition: "all 0.8s ease 1.6s, background 0.3s ease, border-color 0.3s ease",
            backdropFilter: "blur(8px)",
          }}
          onMouseEnter={(e) => {
            e.target.style.background = "linear-gradient(135deg, rgba(212,164,92,0.3), rgba(212,164,92,0.1))";
            e.target.style.borderColor = "rgba(212,164,92,0.7)";
          }}
          onMouseLeave={(e) => {
            e.target.style.background = "linear-gradient(135deg, rgba(212,164,92,0.15), rgba(212,164,92,0.05))";
            e.target.style.borderColor = "rgba(212,164,92,0.4)";
          }}
        >
          라디오 시작하기
        </button>
      </div>
    </div>
  );
}

// ─── Mock Radio App (Simplified) ────────────────────────────────
function MockRadioApp() {
  const [currentCh, setCurrentCh] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [discAngle, setDiscAngle] = useState(0);

  const channels = [
    { name: "KBS 클래식FM", freq: "93.1", unit: "MHz", label: "클래식의 향연", accent: "#d4a45c", bg: "#1a150e" },
    { name: "극동방송", freq: "106.9", unit: "MHz", label: "복음의 빛", accent: "#c48a6a", bg: "#18100e" },
    { name: "말씀의 전당", freq: "CH.3", unit: "", label: "말씀으로 세워지는 삶", accent: "#6a8cb8", bg: "#0e1218" },
    { name: "찬양의 숲", freq: "CH.4", unit: "", label: "고요한 찬양의 쉼터", accent: "#6aaa60", bg: "#0e1610" },
    { name: "봄소리방송", freq: "LIVE", unit: "", label: "실시간 · LIVE", accent: "#c87890", bg: "#181014" },
  ];

  const ch = channels[currentCh];

  // Disc rotation
  useEffect(() => {
    if (!isPlaying) return;
    let raf;
    let angle = discAngle;
    function spin() {
      angle += 0.3;
      setDiscAngle(angle);
      raf = requestAnimationFrame(spin);
    }
    spin();
    return () => cancelAnimationFrame(raf);
  }, [isPlaying]);

  return (
    <div
      style={{
        width: "100%",
        maxWidth: "440px",
        minHeight: "100vh",
        margin: "0 auto",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        padding: "20px 16px 28px",
        fontFamily: "'Pretendard Variable', 'Apple SD Gothic Neo', sans-serif",
        color: "#ece4d8",
        position: "relative",
        background: ch.bg,
        transition: "background 0.8s ease",
      }}
    >
      {/* Ambient glow */}
      <div
        style={{
          position: "fixed",
          top: "12%",
          left: "50%",
          transform: "translateX(-50%)",
          width: "280px",
          height: "280px",
          borderRadius: "50%",
          filter: "blur(50px)",
          background: `${ch.accent}30`,
          transition: "background 0.8s ease",
          pointerEvents: "none",
          zIndex: 0,
        }}
      />

      {/* ═══ HEADER (2안-A: Logo Gold Pulse) ═══ */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          width: "100%",
          marginBottom: "10px",
          position: "relative",
          zIndex: 2,
        }}
      >
        {/* Clock */}
        <div>
          <span
            style={{
              fontFamily: "'Space Grotesk', monospace",
              fontSize: "2.2em",
              fontWeight: 700,
              letterSpacing: "-0.02em",
            }}
          >
            {new Date().getHours().toString().padStart(2, "0")}:
            {new Date().getMinutes().toString().padStart(2, "0")}
          </span>
          <span
            style={{
              fontFamily: "'Space Grotesk', monospace",
              fontSize: "0.9em",
              opacity: 0.4,
              marginLeft: "2px",
            }}
          >
            {new Date().getSeconds().toString().padStart(2, "0")}
          </span>
        </div>

        {/* Logo with gold pulse */}
        <div style={{ textAlign: "right" }}>
          <div
            style={{
              fontSize: "16px",
              fontWeight: 800,
              letterSpacing: "0.12em",
              color: ch.accent,
              transition: "color 0.6s",
              cursor: "pointer",
            }}
          >
            예봄{" "}
            <span
              style={{
                fontFamily: "'Space Grotesk', monospace",
                fontSize: "1.5em",
                fontWeight: 700,
                letterSpacing: "-0.02em",
                /* ★ 2안-A: Gold Pulse Animation */
                color: "#f0c060",
                animation: "goldPulse 3s ease-in-out infinite",
                display: "inline-block",
              }}
            >
              40'
            </span>
          </div>
          <div style={{ fontSize: "10px", opacity: 0.3, marginTop: "1px" }}>
            Yebom Radio 2.0
          </div>
        </div>
      </div>

      {/* Now Playing */}
      <div
        style={{
          fontSize: "12px",
          opacity: 0.5,
          marginBottom: "10px",
          textAlign: "center",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          gap: "6px",
          minHeight: "20px",
        }}
      >
        {ch.name}
      </div>

      {/* ═══ VINYL DISC (2안-B: Since 1986 Label) ═══ */}
      <div style={{ position: "relative", zIndex: 2, width: "100%", display: "flex", flexDirection: "column", alignItems: "center" }}>
        {/* Arrow buttons */}
        <button
          onClick={() => setCurrentCh((c) => (c - 1 + channels.length) % channels.length)}
          style={{
            position: "absolute",
            top: "20px",
            bottom: "20px",
            left: 0,
            width: "48px",
            background: "transparent",
            border: "none",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            cursor: "pointer",
            zIndex: 5,
          }}
        >
          <svg width="20" height="20" viewBox="0 0 14 14">
            <path d="M9 3 L5 7 L9 11" stroke={ch.accent} strokeWidth="1.5" fill="none" strokeLinecap="round" />
          </svg>
        </button>
        <button
          onClick={() => setCurrentCh((c) => (c + 1) % channels.length)}
          style={{
            position: "absolute",
            top: "20px",
            bottom: "20px",
            right: 0,
            width: "48px",
            background: "transparent",
            border: "none",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            cursor: "pointer",
            zIndex: 5,
          }}
        >
          <svg width="20" height="20" viewBox="0 0 14 14">
            <path d="M5 3 L9 7 L5 11" stroke={ch.accent} strokeWidth="1.5" fill="none" strokeLinecap="round" />
          </svg>
        </button>

        {/* The vinyl disc */}
        <div
          style={{
            width: "210px",
            height: "210px",
            borderRadius: "50%",
            position: "relative",
            transform: `rotate(${discAngle}deg)`,
            transition: isPlaying ? "none" : "transform 0.3s ease",
          }}
        >
          {/* Grooves */}
          <div
            style={{
              position: "absolute",
              inset: 0,
              borderRadius: "50%",
              background: `repeating-radial-gradient(circle at 50% 50%, transparent 0px, transparent 3px, rgba(255,255,255,0.025) 3px, rgba(255,255,255,0.025) 4px), radial-gradient(circle, #232030 0%, #1a1820 100%)`,
              boxShadow: "0 8px 40px rgba(0,0,0,0.5), inset 0 0 40px rgba(0,0,0,0.3)",
            }}
          />
          {/* Conic shimmer */}
          <div
            style={{
              position: "absolute",
              inset: 0,
              borderRadius: "50%",
              background:
                "conic-gradient(from 0deg at 50% 50%, transparent 0deg, rgba(255,255,255,0.06) 30deg, transparent 90deg, transparent 180deg, rgba(255,255,255,0.03) 210deg, transparent 270deg, transparent 360deg)",
            }}
          />
          {/* Rings */}
          <div
            style={{
              position: "absolute",
              inset: "15px",
              borderRadius: "50%",
              border: `1px solid ${ch.accent}25`,
            }}
          />
          <div
            style={{
              position: "absolute",
              inset: "35px",
              borderRadius: "50%",
              border: `1px solid ${ch.accent}20`,
            }}
          />

          {/* ★ 2안-B: Circular Text Path — LP 라벨 스타일 */}
          <svg
            viewBox="0 0 210 210"
            style={{
              position: "absolute",
              inset: 0,
              width: "210px",
              height: "210px",
              pointerEvents: "none",
              zIndex: 1,
            }}
          >
            <defs>
              <path
                id="circleTextTop"
                d="M 105,105 m -52,0 a 52,52 0 1,1 104,0 a 52,52 0 1,1 -104,0"
                fill="none"
              />
              <path
                id="circleTextBottom"
                d="M 105,105 m 52,0 a 52,52 0 1,1 -104,0 a 52,52 0 1,1 104,0"
                fill="none"
              />
            </defs>
            {/* Upper arc: Since 1986 */}
            <text
              fill={ch.accent}
              opacity="0.5"
              style={{
                fontFamily: "'Space Grotesk', monospace",
                fontSize: "8px",
                fontWeight: 500,
                letterSpacing: "3px",
              }}
            >
              <textPath href="#circleTextTop" startOffset="50%" textAnchor="middle">
                ✦ SINCE 1986 ✦
              </textPath>
            </text>
            {/* Lower arc: 40th Anniversary */}
            <text
              fill={ch.accent}
              opacity="0.4"
              style={{
                fontFamily: "'Space Grotesk', monospace",
                fontSize: "7.5px",
                fontWeight: 500,
                letterSpacing: "2.5px",
              }}
            >
              <textPath href="#circleTextBottom" startOffset="50%" textAnchor="middle">
                40TH ANNIVERSARY
              </textPath>
            </text>
          </svg>

          {/* ★ Center Label */}
          <div
            style={{
              position: "absolute",
              top: "50%",
              left: "50%",
              width: "80px",
              height: "80px",
              marginTop: "-40px",
              marginLeft: "-40px",
              borderRadius: "50%",
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              background: `${ch.accent}18`,
              border: `1px solid ${ch.accent}30`,
              backdropFilter: "blur(4px)",
              zIndex: 2,
              /* Counter-rotate to keep text upright */
              transform: `rotate(${-discAngle}deg)`,
              transition: isPlaying ? "none" : "transform 0.3s ease",
            }}
          >
            {/* Channel icon area */}
            <div style={{ fontSize: "20px", lineHeight: 1 }}>
              {currentCh === 0 ? "🎹" : currentCh === 1 ? "✝" : currentCh === 2 ? "📖" : currentCh === 3 ? "🌿" : "🌸"}
            </div>

            {/* Frequency */}
            <span
              style={{
                fontSize: "7px",
                fontWeight: 700,
                opacity: 0.7,
                marginTop: "3px",
                letterSpacing: "0.03em",
                color: ch.accent,
                fontFamily: "'Space Grotesk', monospace",
              }}
            >
              {ch.freq}
              {ch.unit && <span style={{ fontSize: "5px", marginLeft: "1px" }}>{ch.unit}</span>}
            </span>

          </div>
        </div>

        {/* Channel info */}
        <div style={{ textAlign: "center", marginTop: "12px", marginBottom: "6px" }}>
          <div style={{ fontSize: "21px", fontWeight: 700 }}>{ch.name}</div>
          <div style={{ fontSize: "11px", opacity: 0.35, marginTop: "3px" }}>{ch.label}</div>
        </div>

        {/* Dots */}
        <div style={{ display: "flex", gap: "6px", marginBottom: "4px", alignItems: "center", justifyContent: "center" }}>
          {channels.map((_, i) => (
            <button
              key={i}
              onClick={() => setCurrentCh(i)}
              style={{
                height: "8px",
                width: currentCh === i ? "24px" : "8px",
                borderRadius: "4px",
                border: "none",
                cursor: "pointer",
                padding: 0,
                background: currentCh === i ? ch.accent : "rgba(255,255,255,0.15)",
                transition: "all 0.4s cubic-bezier(0.4,0,0.2,1)",
              }}
            />
          ))}
        </div>
      </div>

      {/* Progress bar placeholder */}
      <div style={{ width: "100%", marginTop: "12px", position: "relative", zIndex: 2 }}>
        <div
          style={{
            height: "8px",
            borderRadius: "4px",
            background: "rgba(255,255,255,0.06)",
            overflow: "hidden",
          }}
        >
          <div
            style={{
              width: "35%",
              height: "100%",
              borderRadius: "4px",
              background: `linear-gradient(90deg, ${ch.accent}60, ${ch.accent})`,
              transition: "background 0.6s",
            }}
          />
        </div>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            fontSize: "10px",
            opacity: 0.3,
            marginTop: "5px",
            fontFamily: "'Space Grotesk', monospace",
          }}
        >
          <span>02:14</span>
          <span>06:38</span>
        </div>
      </div>

      {/* Play controls */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          gap: "20px",
          position: "relative",
          zIndex: 2,
          marginTop: "4px",
          marginBottom: "6px",
        }}
      >
        {/* Prev */}
        <button style={{ background: "none", border: "none", cursor: "pointer", opacity: 0.5, padding: "8px" }}>
          <svg width="24" height="24" viewBox="0 0 24 24">
            <path d="M19 20L9 12l10-8v16z" fill={ch.accent} opacity="0.5" />
            <line x1="5" y1="5" x2="5" y2="19" stroke={ch.accent} strokeWidth="2" opacity="0.5" />
          </svg>
        </button>

        {/* Play/Pause */}
        <button
          onClick={() => setIsPlaying(!isPlaying)}
          style={{
            width: "62px",
            height: "62px",
            borderRadius: "50%",
            border: "none",
            cursor: "pointer",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            background: `linear-gradient(135deg, ${ch.accent}, ${ch.accent}88)`,
            boxShadow: `0 4px 24px ${ch.accent}40`,
            transition: "all 0.3s",
          }}
        >
          {isPlaying ? (
            <svg width="24" height="24" viewBox="0 0 24 24">
              <rect x="6" y="4" width="4" height="16" rx="1" fill="#0D0B1A" />
              <rect x="14" y="4" width="4" height="16" rx="1" fill="#0D0B1A" />
            </svg>
          ) : (
            <svg width="24" height="24" viewBox="0 0 24 24">
              <path d="M8 5v14l11-7z" fill="#0D0B1A" />
            </svg>
          )}
        </button>

        {/* Next */}
        <button style={{ background: "none", border: "none", cursor: "pointer", opacity: 0.5, padding: "8px" }}>
          <svg width="24" height="24" viewBox="0 0 24 24">
            <path d="M5 4l10 8-10 8V4z" fill={ch.accent} opacity="0.5" />
            <line x1="19" y1="5" x2="19" y2="19" stroke={ch.accent} strokeWidth="2" opacity="0.5" />
          </svg>
        </button>
      </div>

      {/* Bottom panel */}
      <div
        style={{
          width: "100%",
          background: "rgba(255,255,255,0.03)",
          border: "1px solid rgba(255,255,255,0.05)",
          borderRadius: "16px",
          padding: "14px 20px",
          position: "relative",
          zIndex: 2,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
          <svg width="16" height="16" viewBox="0 0 24 24" style={{ opacity: 0.4 }}>
            <path d="M11 5L6 9H2v6h4l5 4V5z" fill="none" stroke="#ece4d8" strokeWidth="2" />
          </svg>
          <div
            style={{
              flex: 1,
              height: "4px",
              background: "rgba(255,255,255,0.08)",
              borderRadius: "2px",
              position: "relative",
            }}
          >
            <div
              style={{
                width: "72%",
                height: "100%",
                borderRadius: "2px",
                background: ch.accent,
                transition: "background 0.6s",
              }}
            />
          </div>
          <span
            style={{
              fontSize: "11px",
              opacity: 0.35,
              width: "26px",
              textAlign: "right",
              fontFamily: "'Space Grotesk', monospace",
            }}
          >
            72
          </span>
        </div>
      </div>

      {/* Footer */}
      <div style={{ fontSize: "10px", opacity: 0.2, marginTop: "12px", position: "relative", zIndex: 2 }}>
        v2.0 · ©2026 예봄교회
      </div>
    </div>
  );
}

// ─── Main Component ─────────────────────────────────────────────
export default function Anniversary40thPrototype() {
  const [showSplash, setShowSplash] = useState(true);
  const [showReplayBtn, setShowReplayBtn] = useState(false);

  return (
    <div style={{ background: "#0D0B1A", minHeight: "100vh" }}>
      {/* Google Fonts */}
      <link
        href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;700&display=swap"
        rel="stylesheet"
      />

      {/* Keyframes */}
      <style>{`
        @keyframes goldPulse {
          0%, 100% { 
            text-shadow: 0 0 4px rgba(240,192,96,0.0); 
            color: #f0c060; 
          }
          50% { 
            text-shadow: 0 0 18px rgba(240,192,96,0.5), 0 0 40px rgba(212,164,92,0.2); 
            color: #ffe8a0; 
          }
        }
        @keyframes floatUp {
          0% { transform: translateY(0) rotate(0deg); opacity: var(--float-opacity, 0.06); }
          50% { opacity: calc(var(--float-opacity, 0.06) * 1.5); }
          100% { transform: translateY(-100vh) rotate(360deg); opacity: 0; }
        }
        @keyframes fadeInUp {
          from { opacity: 0; transform: translateY(8px); }
          to { opacity: 1; transform: translateY(0); }
        }
      `}</style>

      {/* Splash */}
      {showSplash && (
        <CelebrationSplash
          onEnter={() => {
            setShowSplash(false);
            setShowReplayBtn(true);
          }}
        />
      )}

      {/* Radio App */}
      <MockRadioApp />

      {/* Replay splash button (for demo only) */}
      {showReplayBtn && !showSplash && (
        <button
          onClick={() => {
            setShowSplash(true);
            setShowReplayBtn(false);
          }}
          style={{
            position: "fixed",
            bottom: "20px",
            right: "20px",
            padding: "10px 18px",
            borderRadius: "12px",
            border: "1px solid rgba(212,164,92,0.3)",
            background: "rgba(13,11,26,0.9)",
            color: "#d4a45c",
            fontSize: "12px",
            cursor: "pointer",
            zIndex: 100,
            fontFamily: "'Pretendard Variable', sans-serif",
            backdropFilter: "blur(10px)",
            animation: "fadeInUp 0.5s ease",
          }}
        >
          🎉 스플래시 다시보기
        </button>
      )}
    </div>
  );
}
