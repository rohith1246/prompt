/* ============================================================
   PromptVault — main.js
   Handles: like, favorite, copy, mobile nav, password toggle
   ============================================================ */

"use strict";

// ── Mobile Nav Toggle ─────────────────────────────────────────
const navToggle = document.getElementById("navToggle");
const mobileMenu = document.getElementById("mobileMenu");

if (navToggle && mobileMenu) {
  navToggle.addEventListener("click", () => {
    mobileMenu.classList.toggle("open");
    const spans = navToggle.querySelectorAll("span");
    const isOpen = mobileMenu.classList.contains("open");
    spans[0].style.transform = isOpen ? "rotate(45deg) translate(4px, 4px)" : "";
    spans[1].style.opacity   = isOpen ? "0" : "1";
    spans[2].style.transform = isOpen ? "rotate(-45deg) translate(4px, -4px)" : "";
  });
}

// ── Auto-dismiss flash messages ───────────────────────────────
document.querySelectorAll(".flash").forEach((el) => {
  setTimeout(() => {
    el.style.opacity = "0";
    el.style.transform = "translateX(120%)";
    el.style.transition = "all .4s ease";
    setTimeout(() => el.remove(), 400);
  }, 4500);
});

// ── Like Prompt (grid card) ───────────────────────────────────
function likePrompt(promptId, btn) {
  if (btn.classList.contains("liked")) return;

  fetch(`/api/like/${promptId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  })
    .then((res) => {
      if (res.status === 401) {
        window.location.href = "/login";
        return null;
      }
      return res.json();
    })
    .then((data) => {
      if (!data) return;
      btn.querySelector(".like-count").textContent = data.likes;
      btn.classList.add("liked");
      // Pulse animation
      btn.style.transform = "scale(1.15)";
      setTimeout(() => (btn.style.transform = ""), 200);
    })
    .catch(console.error);
}

// ── Like Prompt (detail page) ─────────────────────────────────
function likePromptDetail(promptId, btn) {
  if (btn.classList.contains("liked")) return;

  fetch(`/api/like/${promptId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  })
    .then((res) => {
      if (res.status === 401) { window.location.href = "/login"; return null; }
      return res.json();
    })
    .then((data) => {
      if (!data) return;
      document.getElementById("likeCount").textContent = data.likes;
      btn.classList.add("liked");
      btn.style.color = "var(--gold)";
      btn.style.borderColor = "var(--gold)";
    })
    .catch(console.error);
}

// ── Toggle Favorite (grid card) ───────────────────────────────
function toggleFavorite(promptId, btn) {
  fetch(`/api/favorite/${promptId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  })
    .then((res) => {
      if (res.status === 401) { window.location.href = "/login"; return null; }
      return res.json();
    })
    .then((data) => {
      if (!data) return;
      if (data.status === "added") {
        btn.classList.add("active");
        btn.textContent = "♥";
        btn.title = "Remove from favorites";
      } else {
        btn.classList.remove("active");
        btn.textContent = "♡";
        btn.title = "Save to favorites";
        // If on favorites page, remove the card
        if (window.location.pathname === "/favorites") {
          const card = btn.closest(".prompt-card");
          if (card) {
            card.style.opacity = "0";
            card.style.transform = "scale(0.95)";
            card.style.transition = "all .3s";
            setTimeout(() => {
              card.remove();
              checkEmptyFavorites();
            }, 300);
          }
        }
      }
    })
    .catch(console.error);
}

function checkEmptyFavorites() {
  const grid = document.querySelector(".prompts-grid");
  if (grid && grid.children.length === 0) {
    window.location.reload();
  }
}

// ── Toggle Favorite (detail page) ────────────────────────────
function toggleFavDetail(promptId, btn) {
  fetch(`/api/favorite/${promptId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  })
    .then((res) => {
      if (res.status === 401) { window.location.href = "/login"; return null; }
      return res.json();
    })
    .then((data) => {
      if (!data) return;
      if (data.status === "added") {
        btn.classList.add("active");
        btn.textContent = "♥ Saved";
      } else {
        btn.classList.remove("active");
        btn.textContent = "♡ Save";
      }
    })
    .catch(console.error);
}

// ── Copy Prompt (grid card) ───────────────────────────────────
function copyPrompt(promptId, content, btn) {
  // Unescape newlines
  const text = content.replace(/\\n/g, "\n");

  navigator.clipboard
    .writeText(text)
    .then(() => {
      const original = btn.innerHTML;
      btn.innerHTML = "✅ Copied!";
      btn.classList.add("copied");
      setTimeout(() => {
        btn.innerHTML = original;
        btn.classList.remove("copied");
      }, 2200);
    })
    .catch(() => {
      // Fallback for older browsers
      const ta = document.createElement("textarea");
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
      btn.innerHTML = "✅ Copied!";
      setTimeout(() => (btn.innerHTML = "📋 Copy"), 2200);
    });
}

// ── Copy Prompt (detail page) ─────────────────────────────────
function copyDetailPrompt(btn) {
  const promptText = document.getElementById("promptContent").textContent;
  navigator.clipboard
    .writeText(promptText)
    .then(() => {
      const original = btn.textContent;
      btn.textContent = "✅ Copied!";
      btn.classList.add("copied");
      setTimeout(() => {
        btn.textContent = original;
        btn.classList.remove("copied");
      }, 2500);
    })
    .catch(() => {
      const ta = document.createElement("textarea");
      ta.value = promptText;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
      btn.textContent = "✅ Copied!";
      setTimeout(() => (btn.textContent = "📋 Copy Prompt"), 2500);
    });
}

// ── Password Toggle ───────────────────────────────────────────
function togglePassword(fieldId, btn) {
  const field = document.getElementById(fieldId);
  if (!field) return;
  if (field.type === "password") {
    field.type = "text";
    btn.textContent = "🙈";
  } else {
    field.type = "password";
    btn.textContent = "👁";
  }
}

// ── Smooth scroll for hero CTA ────────────────────────────────
document.querySelectorAll('a[href^="#"]').forEach((anchor) => {
  anchor.addEventListener("click", function (e) {
    const target = document.querySelector(this.getAttribute("href"));
    if (target) {
      e.preventDefault();
      target.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  });
});

// ── Card entrance animation ───────────────────────────────────
const observer = new IntersectionObserver(
  (entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        entry.target.style.opacity = "1";
        entry.target.style.transform = "translateY(0)";
        observer.unobserve(entry.target);
      }
    });
  },
  { threshold: 0.08 }
);

document.querySelectorAll(".prompt-card").forEach((card, i) => {
  card.style.opacity = "0";
  card.style.transform = "translateY(20px)";
  card.style.transition = `opacity .45s ease ${i * 0.06}s, transform .45s ease ${i * 0.06}s`;
  observer.observe(card);
});
