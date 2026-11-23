(function () {
  "use strict";

  const REPO = "danny19862025/prism-monitor";

  /* --------------------------------------------------------------------------
     1. Mobile Navigation Drawer
     -------------------------------------------------------------------------- */
  const navToggle = document.getElementById("nav-toggle");
  const mobileMenu = document.getElementById("mobile-menu");

  if (navToggle && mobileMenu) {
    navToggle.addEventListener("click", () => {
      const expanded = navToggle.getAttribute("aria-expanded") === "true";
      navToggle.setAttribute("aria-expanded", String(!expanded));
      mobileMenu.hidden = expanded;
    });

    mobileMenu.querySelectorAll("a").forEach((link) => {
      link.addEventListener("click", () => {
        navToggle.setAttribute("aria-expanded", "false");
        mobileMenu.hidden = true;
      });
    });
  }

  /* --------------------------------------------------------------------------
     2. Interactive Live Widget Simulator
     -------------------------------------------------------------------------- */
  const stage = document.getElementById("wallpaper-stage");
  const posterView = document.getElementById("poster-view");
  const cardView = document.getElementById("card-view");
  const panelControlGroup = document.getElementById("panel-control-group");

  const simEls = {
    verticalCaption: document.getElementById("sim-vertical-caption"),
    heroLabel: document.getElementById("sim-hero-label"),
    heroSubline: document.getElementById("sim-hero-subline"),
    bigNum: document.getElementById("sim-big-num"),
    bigUnit: document.getElementById("sim-big-unit"),
    cpuRow: document.getElementById("sim-cpu-row"),
    cpuVal: document.getElementById("sim-cpu-val"),
    gpuVal: document.getElementById("sim-gpu-val"),
    memVal: document.getElementById("sim-mem-val"),
    fan1Val: document.getElementById("sim-fan1-val"),
    fan2Val: document.getElementById("sim-fan2-val"),
    cardModePill: document.getElementById("card-mode-pill"),
    cardCpuVal: document.getElementById("card-cpu-val"),
    cardGpuVal: document.getElementById("card-gpu-val"),
    cardThirdLabel: document.getElementById("card-third-label"),
    cardThirdVal: document.getElementById("card-third-val"),
    cardFansVal: document.getElementById("card-fans-val"),
    sparkCpu: document.getElementById("spark-cpu"),
    sparkGpu: document.getElementById("spark-gpu"),
    sparkThird: document.getElementById("spark-third"),
  };

  const simState = {
    mode: "monitor", // "monitor" | "gaming"
    look: "poster", // "poster" | "card"
    panel: "off", // "off" | "45"
    accent: "ice",
    cpuTemp: 63,
    cpuLoad: 35,
    gpuTemp: 70,
    gpuLoad: 92,
    memGb: 9.4,
    fan1: 1411,
    fan2: 980,
    fps: 142,
    cpuHistory: [31, 33, 36, 34, 38, 35, 37, 34, 35],
    gpuHistory: [88, 90, 89, 92, 93, 91, 94, 91, 92],
    fpsHistory: [138, 141, 140, 143, 144, 141, 145, 142, 142],
    memHistory: [9.2, 9.2, 9.3, 9.3, 9.4, 9.4, 9.4, 9.4, 9.4],
  };

  function clamp(val, min, max) {
    return Math.min(max, Math.max(min, val));
  }

  function stepValue(current, delta, min, max) {
    const jitter = Math.round((Math.random() - 0.5) * 2 * delta);
    return clamp(current + jitter, min, max);
  }

  function toSparkPoints(series, min, max) {
    const width = 120;
    const height = 26;
    const pad = 3;
    const span = Math.max(1, max - min);
    return series
      .map((val, idx) => {
        const x = ((idx / (series.length - 1)) * width).toFixed(1);
        const norm = clamp((val - min) / span, 0, 1);
        const y = (height - pad - norm * (height - pad * 2)).toFixed(1);
        return `${x},${y}`;
      })
      .join(" ");
  }

  function renderWidget() {
    if (!stage) return;

    stage.dataset.mode = simState.mode;
    stage.dataset.look = simState.look;
    stage.dataset.panel = simState.panel;
    stage.dataset.accent = simState.accent;

    const isPoster = simState.look === "poster";
    const isGaming = simState.mode === "gaming";

    if (posterView) posterView.hidden = !isPoster;
    if (cardView) cardView.hidden = isPoster;
    if (panelControlGroup) {
      panelControlGroup.classList.toggle("is-disabled", !isPoster);
    }

    const frameMs = (1000 / simState.fps).toFixed(1);
    const memText = `${simState.memGb.toFixed(1)} / 32 GB`;

    if (simEls.verticalCaption) {
      simEls.verticalCaption.textContent = isGaming ? "GAMING" : "MONITOR";
    }
    if (simEls.heroLabel) {
      simEls.heroLabel.textContent = isGaming ? "FPS" : "CPU";
    }
    if (simEls.heroSubline) {
      simEls.heroSubline.textContent = isGaming
        ? `CYBERPUNK2077 \u00b7 ${frameMs} MS`
        : `${simState.cpuLoad}% LOAD`;
    }
    if (simEls.bigNum) {
      simEls.bigNum.textContent = isGaming ? String(simState.fps) : String(simState.cpuTemp);
    }
    if (simEls.bigUnit) {
      simEls.bigUnit.hidden = isGaming;
    }
    if (simEls.cpuRow) {
      simEls.cpuRow.hidden = !isGaming;
    }

    if (simEls.cpuVal) simEls.cpuVal.textContent = `${simState.cpuLoad}% \u00b7 ${simState.cpuTemp}\u00b0C`;
    if (simEls.gpuVal) simEls.gpuVal.textContent = `${simState.gpuLoad}% \u00b7 ${simState.gpuTemp}\u00b0C`;
    if (simEls.memVal) simEls.memVal.textContent = memText;
    if (simEls.fan1Val) simEls.fan1Val.textContent = `${simState.fan1} RPM`;
    if (simEls.fan2Val) simEls.fan2Val.textContent = `${simState.fan2} RPM`;

    // Card view synchronization
    if (simEls.cardModePill) {
      simEls.cardModePill.textContent = isGaming ? "GAMING \u00b7 1.0s" : "MONITOR \u00b7 1.0s";
    }
    if (simEls.cardCpuVal) {
      simEls.cardCpuVal.textContent = `${simState.cpuTemp}\u00b0C \u00b7 ${simState.cpuLoad}%`;
    }
    if (simEls.cardGpuVal) {
      simEls.cardGpuVal.textContent = `${simState.gpuTemp}\u00b0C \u00b7 ${simState.gpuLoad}%`;
    }
    if (simEls.cardThirdLabel) {
      simEls.cardThirdLabel.textContent = isGaming ? "FPS \u00b7 CYBERPUNK2077" : "MEMORY";
    }
    if (simEls.cardThirdVal) {
      simEls.cardThirdVal.textContent = isGaming ? `${simState.fps} FPS \u00b7 ${frameMs} ms` : memText;
    }
    if (simEls.cardFansVal) {
      simEls.cardFansVal.textContent = `CPU ${simState.fan1} RPM \u00b7 CASE ${simState.fan2} RPM`;
    }

    if (simEls.sparkCpu) {
      simEls.sparkCpu.setAttribute("points", toSparkPoints(simState.cpuHistory, 15, 75));
    }
    if (simEls.sparkGpu) {
      simEls.sparkGpu.setAttribute("points", toSparkPoints(simState.gpuHistory, 65, 100));
    }
    if (simEls.sparkThird) {
      simEls.sparkThird.setAttribute(
        "points",
        isGaming
          ? toSparkPoints(simState.fpsHistory, 120, 160)
          : toSparkPoints(simState.memHistory, 6, 16)
      );
    }
  }

  function tickTelemetry() {
    const isGaming = simState.mode === "gaming";
    simState.cpuLoad = stepValue(simState.cpuLoad, 3, isGaming ? 30 : 18, isGaming ? 52 : 46);
    simState.cpuTemp = stepValue(simState.cpuTemp, 1, 58, 69);
    simState.gpuLoad = stepValue(simState.gpuLoad, 2, isGaming ? 86 : 12, isGaming ? 98 : 96);
    simState.gpuTemp = stepValue(simState.gpuTemp, 1, 64, 74);
    simState.fps = stepValue(simState.fps, 3, 134, 151);
    simState.fan1 = stepValue(simState.fan1, 14, 1360, 1490);
    simState.fan2 = stepValue(simState.fan2, 8, 950, 1020);
    simState.memGb = clamp(Number((simState.memGb + (Math.random() - 0.5) * 0.1).toFixed(1)), 9.1, 9.9);

    simState.cpuHistory.push(simState.cpuLoad);
    simState.cpuHistory.shift();
    simState.gpuHistory.push(simState.gpuLoad);
    simState.gpuHistory.shift();
    simState.fpsHistory.push(simState.fps);
    simState.fpsHistory.shift();
    simState.memHistory.push(simState.memGb);
    simState.memHistory.shift();

    renderWidget();
  }

  function bindGroupButtons(selector, key, attr) {
    const buttons = document.querySelectorAll(selector);
    buttons.forEach((btn) => {
      btn.addEventListener("click", () => {
        buttons.forEach((b) => b.classList.remove("is-active"));
        btn.classList.add("is-active");
        simState[key] = btn.getAttribute(attr);
        renderWidget();
      });
    });
  }

  bindGroupButtons("[data-sim-mode]", "mode", "data-sim-mode");
  bindGroupButtons("[data-sim-look]", "look", "data-sim-look");
  bindGroupButtons("[data-sim-panel]", "panel", "data-sim-panel");
  bindGroupButtons("[data-accent]", "accent", "data-accent");

  renderWidget();
  window.setInterval(tickTelemetry, 1000);

  /* --------------------------------------------------------------------------
     3. Install Platform Tabs & Distro Switcher
     -------------------------------------------------------------------------- */
  const osTabs = document.querySelectorAll(".os-tab");
  const osPanels = document.querySelectorAll(".os-panel");

  function activateTab(tabName) {
    osTabs.forEach((tab) => {
      const active = tab.dataset.tab === tabName;
      tab.classList.toggle("is-active", active);
      tab.setAttribute("aria-selected", String(active));
    });
    osPanels.forEach((panel) => {
      const active = panel.id === `panel-${tabName}`;
      panel.classList.toggle("is-active", active);
      panel.hidden = !active;
    });
  }

  osTabs.forEach((tab) => {
    tab.addEventListener("click", () => activateTab(tab.dataset.tab));
  });

  document.querySelectorAll("[data-jump-tab]").forEach((el) => {
    el.addEventListener("click", () => {
      activateTab(el.dataset.jumpTab);
    });
  });

  const DISTRO_DATA = {
    arch: {
      cmd: "sudo pacman -S --needed git python gcc vulkan-icd-loader vulkan-tools",
      note: 'For game FPS, ensure your GPU Vulkan driver is installed: <code>vulkan-radeon</code> (AMD), <code>vulkan-intel</code> (Intel), or <code>nvidia-utils</code> (NVIDIA).',
    },
    debian: {
      cmd: "sudo apt install git python3 python3-venv gcc libvulkan1 vulkan-tools",
      note: 'For game FPS, add <code>mesa-vulkan-drivers</code> for AMD/Intel or the NVIDIA Vulkan ICD for GeForce GPUs.',
    },
    fedora: {
      cmd: "sudo dnf install git python3 gcc vulkan-loader vulkan-tools",
      note: 'For game FPS, add <code>mesa-vulkan-drivers</code> (AMD/Intel) or <code>xorg-x11-drv-nvidia</code> (NVIDIA).',
    },
    opensuse: {
      cmd: "sudo zypper install git python3 gcc libvulkan1 vulkan-tools",
      note: 'For game FPS, ensure your Mesa or NVIDIA Vulkan ICD package is installed. See the <a href="https://github.com/danny19862025/prism-monitor/blob/main/docs/GUIDE.md#installing-what-fps-needs" target="_blank" rel="noopener noreferrer">per-GPU guide</a>.',
    },
  };

  const distroPills = document.querySelectorAll(".distro-pill");
  const linuxDepsCmd = document.getElementById("linux-deps-cmd");
  const linuxGpuNote = document.getElementById("linux-gpu-note");

  distroPills.forEach((pill) => {
    pill.addEventListener("click", () => {
      const key = pill.dataset.distro;
      const entry = DISTRO_DATA[key];
      if (!entry) return;

      distroPills.forEach((p) => p.classList.remove("is-active"));
      pill.classList.add("is-active");

      if (linuxDepsCmd) linuxDepsCmd.textContent = entry.cmd;
      if (linuxGpuNote) linuxGpuNote.innerHTML = entry.note;
    });
  });

  /* --------------------------------------------------------------------------
     4. Copy-to-Clipboard Controls
     -------------------------------------------------------------------------- */
  async function copyText(text) {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return;
    }
    const helper = document.createElement("textarea");
    helper.value = text;
    helper.setAttribute("readonly", "");
    helper.style.position = "fixed";
    helper.style.opacity = "0";
    document.body.appendChild(helper);
    helper.select();
    document.execCommand("copy");
    document.body.removeChild(helper);
  }

  document.querySelectorAll(".copy-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const directValue = btn.getAttribute("data-copy");
      const targetId = btn.getAttribute("data-copy-target");
      const text = directValue || (targetId && document.getElementById(targetId)?.textContent) || "";
      if (!text) return;

      const originalLabel = btn.textContent;
      try {
        await copyText(text.trim());
        btn.textContent = "Copied!";
        btn.classList.add("is-copied");
        window.setTimeout(() => {
          btn.textContent = originalLabel;
          btn.classList.remove("is-copied");
        }, 1600);
      } catch {
        btn.textContent = "Failed";
        window.setTimeout(() => {
          btn.textContent = originalLabel;
        }, 1600);
      }
    });
  });

  /* --------------------------------------------------------------------------
     5. Progressive Scroll Reveal
     -------------------------------------------------------------------------- */
  const revealEls = document.querySelectorAll(".reveal");
  if ("IntersectionObserver" in window && revealEls.length > 0) {
    document.documentElement.classList.add("js-reveal");
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("is-visible");
            observer.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.12, rootMargin: "0px 0px -24px 0px" }
    );
    revealEls.forEach((el) => observer.observe(el));
  }

  /* --------------------------------------------------------------------------
     6. Optional Live GitHub Latest Release Metadata Refresh
     -------------------------------------------------------------------------- */
  function formatMegabytes(bytes) {
    if (!Number.isFinite(bytes) || bytes <= 0) return null;
    return `${(bytes / 1000000).toFixed(1)} MB`;
  }

  async function syncLatestRelease() {
    try {
      const response = await fetch(`https://api.github.com/repos/${REPO}/releases/latest`, {
        headers: { Accept: "application/vnd.github+json" },
      });
      if (!response.ok) return;

      const release = await response.json();
      const tag = release?.tag_name;
      const assets = Array.isArray(release?.assets) ? release.assets : [];
      if (!tag || assets.length === 0) return;

      const exeAsset = assets.find((a) => /^PrismMonitor-Setup-.*\.exe$/i.test(a.name));
      const zipAsset = assets.find((a) => /^PrismMonitor-windows\.zip$/i.test(a.name));

      const heroBadge = document.getElementById("hero-release-badge");
      if (heroBadge) heroBadge.textContent = `${tag} \u00b7 Windows 10/11 & Linux \u00b7 GPL-3.0`;

      const versionLabel = document.getElementById("install-version-label");
      if (versionLabel) versionLabel.textContent = tag;

      if (exeAsset) {
        const heroWin = document.getElementById("hero-win-download");
        const winInstallerLink = document.getElementById("win-installer-link");
        const exeSize = document.getElementById("exe-size");
        const exeSha = document.getElementById("exe-sha");
        const exeFilename = document.querySelector(".dl-card.is-recommended .dl-filename");

        if (heroWin) heroWin.href = exeAsset.browser_download_url;
        if (winInstallerLink) winInstallerLink.href = exeAsset.browser_download_url;
        if (exeFilename) exeFilename.textContent = exeAsset.name;
        const sizeLabel = formatMegabytes(exeAsset.size);
        if (exeSize && sizeLabel) exeSize.textContent = sizeLabel;

        const sha = typeof exeAsset.digest === "string" && exeAsset.digest.startsWith("sha256:")
          ? exeAsset.digest.slice(7)
          : null;
        if (sha && exeSha) {
          exeSha.textContent = sha;
          const copyBtn = exeSha.parentElement?.querySelector(".copy-btn");
          if (copyBtn) copyBtn.setAttribute("data-copy", sha);
        }
      }

      if (zipAsset) {
        const winZipLink = document.getElementById("win-zip-link");
        const zipSize = document.getElementById("zip-size");
        const zipSha = document.getElementById("zip-sha");

        if (winZipLink) winZipLink.href = zipAsset.browser_download_url;
        const sizeLabel = formatMegabytes(zipAsset.size);
        if (zipSize && sizeLabel) zipSize.textContent = sizeLabel;

        const sha = typeof zipAsset.digest === "string" && zipAsset.digest.startsWith("sha256:")
          ? zipAsset.digest.slice(7)
          : null;
        if (sha && zipSha) {
          zipSha.textContent = sha;
          const copyBtn = zipSha.parentElement?.querySelector(".copy-btn");
          if (copyBtn) copyBtn.setAttribute("data-copy", sha);
        }
      }
    } catch {
      // Offline or GitHub API rate-limited: fallback v1.1.0 values remain intact.
    }
  }

  syncLatestRelease();
})();
