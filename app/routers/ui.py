from fastapi import APIRouter
from fastapi.responses import HTMLResponse


router = APIRouter(prefix="/ui", tags=["ui"])


@router.get("/overlay", response_class=HTMLResponse)
def overlay_page() -> str:
    """Simple web UI for selecting a folder/video and applying text overlay."""
    return """
<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8" />
  <title>FABRIC — Текст на видео</title>
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <style>
    :root {
      color-scheme: dark;
      --bg: #050816;
      --card-bg: #0f172a;
      --accent: #38bdf8;
      --accent-soft: rgba(56, 189, 248, 0.15);
      --border: #1e293b;
      --text: #e5e7eb;
      --muted: #9ca3af;
      --danger: #f97373;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "SF Pro Text", sans-serif;
      background: radial-gradient(circle at top, #1e293b 0, var(--bg) 40%);
      color: var(--text);
      min-height: 100vh;
      display: flex;
      align-items: stretch;
      justify-content: center;
    }
    .page {
      max-width: 1200px;
      padding: 24px 16px 40px;
      margin: 0 auto;
      width: 100%;
      display: grid;
      grid-template-columns: minmax(0, 3fr) minmax(0, 2fr);
      gap: 24px;
    }
    @media (max-width: 900px) {
      .page {
        grid-template-columns: minmax(0, 1fr);
      }
    }
    .card {
      background: linear-gradient(135deg, rgba(15,23,42,0.98), rgba(15,23,42,0.96));
      border-radius: 18px;
      border: 1px solid rgba(148, 163, 184, 0.2);
      box-shadow: 0 18px 45px rgba(15, 23, 42, 0.85);
      padding: 20px 20px 22px;
      backdrop-filter: blur(24px);
    }
    .header {
      grid-column: 1 / -1;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 4px;
    }
    .title {
      font-size: 20px;
      font-weight: 650;
      letter-spacing: 0.03em;
      display: flex;
      align-items: baseline;
      gap: 8px;
    }
    .title span.badge {
      font-size: 11px;
      text-transform: uppercase;
      padding: 2px 8px;
      border-radius: 999px;
      background: linear-gradient(135deg, rgba(56,189,248,0.15), rgba(59,130,246,0.1));
      border: 1px solid rgba(56,189,248,0.4);
      color: var(--accent);
      letter-spacing: 0.12em;
    }
    .subtitle {
      font-size: 13px;
      color: var(--muted);
    }
    label {
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--muted);
      display: block;
      margin-bottom: 4px;
    }
    select, input[type="text"], input[type="number"], textarea, input[type="color"] {
      width: 100%;
      border-radius: 10px;
      border: 1px solid var(--border);
      background: rgba(15,23,42,0.9);
      color: var(--text);
      font-size: 13px;
      padding: 8px 10px;
      outline: none;
      transition: border-color 0.15s ease, box-shadow 0.15s ease, background 0.15s ease;
    }
    select:focus, input:focus, textarea:focus {
      border-color: var(--accent);
      box-shadow: 0 0 0 1px rgba(56, 189, 248, 0.35);
      background: rgba(15,23,42,0.98);
    }
    textarea {
      min-height: 120px;
      resize: vertical;
      line-height: 1.5;
    }
    .row {
      display: flex;
      gap: 10px;
      margin-bottom: 10px;
    }
    .row > div {
      flex: 1;
      min-width: 0;
    }
    .section-title {
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.1em;
      color: var(--muted);
      margin: 10px 0 6px;
    }
    .pill-group {
      display: inline-flex;
      border-radius: 999px;
      padding: 2px;
      background: rgba(15,23,42,0.9);
      border: 1px solid var(--border);
    }
    .pill-btn {
      border: none;
      background: transparent;
      color: var(--muted);
      padding: 5px 12px;
      font-size: 12px;
      border-radius: 999px;
      cursor: pointer;
      transition: background 0.15s ease, color 0.15s ease;
    }
    .pill-btn.active {
      background: linear-gradient(135deg, #38bdf8, #6366f1);
      color: white;
    }
    .slider-row {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 11px;
      color: var(--muted);
    }
    input[type="range"] {
      flex: 1;
    }
    .btn {
      border-radius: 999px;
      border: none;
      padding: 9px 16px;
      font-size: 13px;
      font-weight: 550;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 8px;
      background: linear-gradient(135deg, #38bdf8, #6366f1);
      color: white;
      box-shadow: 0 10px 25px rgba(56,189,248,0.35);
      margin-top: 4px;
    }
    .btn:disabled {
      opacity: 0.5;
      cursor: default;
      box-shadow: none;
    }
    .btn-secondary {
      background: rgba(15,23,42,0.9);
      color: var(--muted);
      box-shadow: none;
      border: 1px solid var(--border);
    }
    .status {
      font-size: 12px;
      margin-top: 8px;
      color: var(--muted);
      min-height: 18px;
    }
    .status--error {
      color: var(--danger);
    }
    .badge-small {
      font-size: 11px;
      padding: 2px 8px;
      border-radius: 999px;
      background: var(--accent-soft);
      color: var(--accent);
      text-transform: uppercase;
      letter-spacing: 0.12em;
    }
    .pill-group {
      display: inline-flex;
      border-radius: 999px;
      padding: 2px;
      background: rgba(15,23,42,0.9);
      border: 1px solid var(--border);
    }
    .pill-btn {
      border: none;
      background: transparent;
      color: var(--muted);
      padding: 5px 12px;
      font-size: 12px;
      border-radius: 999px;
      cursor: pointer;
      transition: background 0.15s ease, color 0.15s ease;
    }
    .pill-btn.active {
      background: linear-gradient(135deg, #38bdf8, #6366f1);
      color: white;
    }
    video {
      width: 100%;
      border-radius: 14px;
      border: 1px solid rgba(148,163,184,0.3);
      background: black;
    }
    .output-meta {
      font-size: 12px;
      color: var(--muted);
      margin-top: 8px;
    }
    a.download-link {
      color: var(--accent);
      text-decoration: none;
      font-size: 13px;
    }
    a.download-link:hover {
      text-decoration: underline;
    }
  </style>
</head>
<body>
  <div class="page">
    <div class="header">
      <div>
        <div class="title">
          FABRIC Overlay
          <span class="badge">text on video</span>
        </div>
        <div class="subtitle">Выбери папку и ролик, настрой текст и получи готовое видео с титрами.</div>
      </div>
      <div class="subtitle" id="apiBaseInfo"></div>
    </div>

    <div class="card">
      <div class="section-title">Исходное видео</div>
      <div class="row">
        <div>
          <label>Источник</label>
          <div class="pill-group" id="sourceGroup">
            <button type="button" class="pill-btn active" data-value="upload">Загрузить (file picker)</button>
            <button type="button" class="pill-btn" data-value="server">Серверная папка</button>
          </div>
        </div>
      </div>

      <div id="uploadBlock">
        <div class="row">
          <div style="flex:2;">
            <label for="videoUpload">Видео файл (mp4)</label>
            <input id="videoUpload" type="file" accept="video/mp4,video/*" />
          </div>
          <div style="flex:1;display:flex;align-items:flex-end;gap:8px;">
            <span class="badge-small" id="uploadBadge" style="display:none;">готово</span>
          </div>
        </div>
        <div class="output-meta" id="uploadVideoInfo" style="margin-top:-2px;"></div>
      </div>

      <div id="serverBlock" style="display:none;">
      <div class="row">
        <div style="flex:2;">
          <label for="pathInput">Папка в файловой системе</label>
          <input id="pathInput" type="text" placeholder="/app/data или /home/..." />
        </div>
        <div style="flex:1;display:flex;align-items:flex-end;gap:8px;">
          <button type="button" class="btn btn-secondary" id="loadBtn" style="margin-top:0;">Загрузить</button>
          <button type="button" class="btn btn-secondary" id="upBtn" style="margin-top:0;">⬆︎</button>
        </div>
      </div>
      <div class="row">
        <div>
          <label for="fileSelect">Видео / папки</label>
          <select id="fileSelect"></select>
        </div>
      </div>
      <div class="output-meta" id="videoInfo" style="margin-top:-2px;"></div>
      </div>

      <div class="section-title">Текст</div>
      <div>
        <label for="textInput">Текст для наложения</label>
        <textarea id="textInput" placeholder="Напишите текст, который будет поверх видео..."></textarea>
      </div>

      <div class="section-title">Оформление</div>
      <div class="row">
        <div>
          <label for="fontSize">Размер шрифта</label>
          <input id="fontSize" type="number" min="8" max="200" value="48" />
        </div>
        <div>
          <label for="maxWords">Слов в строке</label>
          <input id="maxWords" type="number" min="1" max="50" value="7" />
        </div>
      </div>
      <div class="row">
        <div>
          <label>Выравнивание</label>
          <div class="pill-group" id="alignGroup">
            <button type="button" class="pill-btn" data-value="left">Слева</button>
            <button type="button" class="pill-btn active" data-value="center">По центру</button>
            <button type="button" class="pill-btn" data-value="right">Справа</button>
          </div>
        </div>
        <div>
          <label for="outlineWidth">Обводка</label>
          <input id="outlineWidth" type="number" min="0" max="20" value="2" />
        </div>
      </div>
      <div class="row">
        <div>
          <label for="fontColor">Цвет текста</label>
          <input id="fontColor" type="color" value="#ffffff" />
        </div>
        <div>
          <label for="outlineColor">Цвет обводки</label>
          <input id="outlineColor" type="color" value="#000000" />
        </div>
      </div>
      <div class="row">
        <div>
          <label>Позиция по X / Y</label>
          <div class="slider-row">
            X&nbsp;<input id="centerX" type="range" min="0" max="100" value="50" /><span id="centerXVal">50%</span>
          </div>
          <div class="slider-row" style="margin-top:4px;">
            Y (верхняя грань)&nbsp;<input id="centerY" type="range" min="0" max="100" value="80" /><span id="centerYVal">80%</span>
          </div>
        </div>
        <div>
          <label for="lineSpacing">Межстрочный интервал</label>
          <input id="lineSpacing" type="number" min="0" max="100" value="4" />
        </div>
      </div>

      <button class="btn" id="applyBtn">
        <span>Наложить текст</span>
      </button>
      <div class="status" id="statusText"></div>
      <div class="row" style="margin-top:12px;">
        <label class="section-title" style="margin-bottom:6px;">Функции</label>
        <div style="flex:1;">
          <input type="checkbox" id="autoFitToggle" />
          <label for="autoFitToggle" style="display:inline-block;margin-left:6px;font-size:12px;">Авто-подбор текста</label>
        </div>
      </div>
      <div id="autoFitBlock" style="display:none;">
        <div class="row">
          <div>
            <label for="paddingPct">Паддинг (%)</label>
            <input id="paddingPct" type="number" min="0" max="30" value="5" />
          </div>
          <div>
            <label for="baseFontSize">Базовый размер</label>
            <input id="baseFontSize" type="number" min="20" max="400" value="120" />
          </div>
        </div>
        <div class="row">
          <div>
            <label for="coverageMinPct">Покрытие текста (мин, %)</label>
            <input id="coverageMinPct" type="number" min="0" max="100" step="0.1" value="8" />
          </div>
          <div>
            <label for="coverageMaxPct">Покрытие текста (макс, %)</label>
            <input id="coverageMaxPct" type="number" min="0" max="100" step="0.1" value="18" />
          </div>
        </div>
        <div class="row">
          <div>
            <label for="autoFitMinWords">Мин. слов в строке</label>
            <input id="autoFitMinWords" type="number" min="1" max="50" value="3" />
          </div>
          <div>
            <label for="autoFitMaxWords">Макс. слов в строке</label>
            <input id="autoFitMaxWords" type="number" min="1" max="50" value="14" />
          </div>
        </div>
        <div class="row">
          <div>
            <label for="minFontSize">Мин. размер</label>
            <input id="minFontSize" type="number" min="6" max="200" value="14" />
          </div>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="section-title">Результат</div>
      <div id="resultBadge" class="badge-small" style="display:none;margin-bottom:8px;"></div>
      <video id="previewVideo" controls style="display:none;" playsinline></video>
      <div class="output-meta" id="outputMeta"></div>
      <div style="margin-top:10px;">
        <a id="downloadLink" class="download-link" href="#" style="display:none;" download>Скачать видео</a>
      </div>
    </div>
  </div>

  <script>
    const fileSelect = document.getElementById('fileSelect');
    const sourceGroup = document.getElementById('sourceGroup');
    const uploadBlock = document.getElementById('uploadBlock');
    const serverBlock = document.getElementById('serverBlock');
    const videoUpload = document.getElementById('videoUpload');
    const uploadBadge = document.getElementById('uploadBadge');
    const uploadVideoInfo = document.getElementById('uploadVideoInfo');
    const pathInput = document.getElementById('pathInput');
    const loadBtn = document.getElementById('loadBtn');
    const upBtn = document.getElementById('upBtn');
    const videoInfo = document.getElementById('videoInfo');
    const textInput = document.getElementById('textInput');
    const fontSizeInput = document.getElementById('fontSize');
    const maxWordsInput = document.getElementById('maxWords');
    const outlineWidthInput = document.getElementById('outlineWidth');
    const fontColorInput = document.getElementById('fontColor');
    const outlineColorInput = document.getElementById('outlineColor');
    const centerXInput = document.getElementById('centerX');
    const centerYInput = document.getElementById('centerY');
    const centerXVal = document.getElementById('centerXVal');
    const centerYVal = document.getElementById('centerYVal');
    const lineSpacingInput = document.getElementById('lineSpacing');
    const alignGroup = document.getElementById('alignGroup');
    const autoFitToggle = document.getElementById('autoFitToggle');
    const autoFitBlock = document.getElementById('autoFitBlock');
    const paddingPctInput = document.getElementById('paddingPct');
    const baseFontSizeInput = document.getElementById('baseFontSize');
    const coverageMinInput = document.getElementById('coverageMinPct');
    const coverageMaxInput = document.getElementById('coverageMaxPct');
    const autoFitMinWordsInput = document.getElementById('autoFitMinWords');
    const autoFitMaxWordsInput = document.getElementById('autoFitMaxWords');
    const minFontSizeInput = document.getElementById('minFontSize');
    const applyBtn = document.getElementById('applyBtn');
    const statusText = document.getElementById('statusText');
    const previewVideo = document.getElementById('previewVideo');
    const downloadLink = document.getElementById('downloadLink');
    const outputMeta = document.getElementById('outputMeta');
    const resultBadge = document.getElementById('resultBadge');
    const apiBaseInfo = document.getElementById('apiBaseInfo');

    function setStatus(text, isError = false) {
      statusText.textContent = text || '';
      statusText.classList.toggle('status--error', !!isError);
    }

    function getAlignValue() {
      const active = alignGroup.querySelector('.pill-btn.active');
      return active ? active.dataset.value : 'center';
    }

    function getSourceMode() {
      const active = sourceGroup.querySelector('.pill-btn.active');
      return active ? active.dataset.value : 'upload';
    }

    alignGroup.addEventListener('click', (e) => {
      const btn = e.target.closest('.pill-btn');
      if (!btn) return;
      alignGroup.querySelectorAll('.pill-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
    });

    sourceGroup.addEventListener('click', async (e) => {
      const btn = e.target.closest('.pill-btn');
      if (!btn) return;
      sourceGroup.querySelectorAll('.pill-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      const mode = getSourceMode();
      uploadBlock.style.display = (mode === 'upload') ? 'block' : 'none';
      serverBlock.style.display = (mode === 'server') ? 'block' : 'none';
      if (mode === 'server') {
        await loadFs(pathInput.value);
      }
      setStatus('');
    });

    videoUpload.addEventListener('change', async () => {
      uploadBadge.style.display = 'none';
      uploadVideoInfo.textContent = '';
      const file = videoUpload.files && videoUpload.files[0];
      if (!file) return;
      uploadBadge.style.display = 'inline-block';
      uploadBadge.textContent = file.name;

      // Client-side metadata (resolution, duration) for uploaded file
      try {
        const url = URL.createObjectURL(file);
        const v = document.createElement('video');
        v.preload = 'metadata';
        v.src = url;
        v.muted = true;
        v.playsInline = true;
        v.addEventListener('loadedmetadata', () => {
          const wh = (v.videoWidth && v.videoHeight) ? (v.videoWidth + '×' + v.videoHeight) : '—';
          const dur = (v.duration && isFinite(v.duration)) ? (v.duration.toFixed(1) + 's') : '—';
          const sizeMb = (file.size != null) ? (file.size / (1024 * 1024)).toFixed(2) + ' MB' : '—';
          uploadVideoInfo.textContent = 'Файл: ' + file.name + ' · Размер: ' + sizeMb + ' · Разрешение: ' + wh + ' · Длительность: ' + dur;
          URL.revokeObjectURL(url);
        }, { once: true });
      } catch (e) {
        // ignore
      }
    });

    autoFitToggle.addEventListener('change', () => {
      autoFitBlock.style.display = autoFitToggle.checked ? 'block' : 'none';
    });

    centerXInput.addEventListener('input', () => {
      centerXVal.textContent = centerXInput.value + '%';
    });
    centerYInput.addEventListener('input', () => {
      centerYVal.textContent = centerYInput.value + '%';
    });

    async function loadFs(path) {
      fileSelect.innerHTML = '';
      videoInfo.textContent = '';
      if (!path) return;
      try {
        const res = await fetch('/content/fs_ls?path=' + encodeURIComponent(path));
        if (!res.ok) throw new Error(await res.text());
        const data = await res.json();
        pathInput.value = data.path;

        const entries = [];
        if (data.dirs) {
          for (const d of data.dirs) entries.push({ kind: 'dir', name: d });
        }
        if (data.files) {
          for (const f of data.files) entries.push({ kind: 'file', name: f });
        }
        if (!entries.length) {
          const opt = document.createElement('option');
          opt.value = '';
          opt.textContent = 'Папка пустая';
          fileSelect.appendChild(opt);
          return;
        }
        for (const e of entries) {
          const opt = document.createElement('option');
          opt.value = e.name;
          opt.textContent = (e.kind === 'dir' ? '📁 ' : '🎬 ') + e.name;
          opt.dataset.kind = e.kind;
          fileSelect.appendChild(opt);
        }
      } catch (e) {
        setStatus('Ошибка чтения папки: ' + e, true);
      }
    }

    async function loadVideoInfo(absPath) {
      videoInfo.textContent = '';
      try {
        const res = await fetch('/content/video_info?path=' + encodeURIComponent(absPath));
        if (!res.ok) throw new Error(await res.text());
        const info = await res.json();
        const wh = (info.width && info.height) ? (info.width + '×' + info.height) : '—';
        const dur = (info.duration_sec != null) ? (info.duration_sec.toFixed(1) + 's') : '—';
        const fps = (info.fps != null) ? (info.fps.toFixed(2) + ' fps') : '—';
        const codec = info.codec || '—';
        const sizeMb = (info.size_bytes != null) ? (info.size_bytes / (1024 * 1024)).toFixed(2) + ' MB' : '—';
        const br = (info.bit_rate != null) ? Math.round(info.bit_rate / 1000) + ' kbps' : '—';
        videoInfo.textContent =
          'Разрешение: ' + wh +
          ' · Длительность: ' + dur +
          ' · FPS: ' + fps +
          ' · Codec: ' + codec +
          ' · Размер: ' + sizeMb +
          ' · Bitrate: ' + br;
      } catch (e) {
        videoInfo.textContent = 'Не удалось получить информацию о видео';
      }
    }

    loadBtn.addEventListener('click', () => {
      loadFs(pathInput.value.trim());
    });
    upBtn.addEventListener('click', async () => {
      const p = pathInput.value.trim();
      if (!p) return;
      // rely on server to tell parent; simplest: strip last segment client-side
      const idx = p.replace(/\/+$/, '').lastIndexOf('/');
      if (idx <= 0) return;
      const parent = p.slice(0, idx) || '/';
      await loadFs(parent);
    });

    fileSelect.addEventListener('change', async () => {
      const opt = fileSelect.selectedOptions[0];
      if (!opt) return;
      const kind = opt.dataset.kind;
      const name = opt.value;
      if (!kind || !name) return;
      const base = pathInput.value.trim().replace(/\/+$/, '');
      const abs = base + '/' + name;
      if (kind === 'dir') {
        await loadFs(abs);
      } else {
        await loadVideoInfo(abs);
      }
    });

    applyBtn.addEventListener('click', async () => {
      const mode = getSourceMode();
      const text = textInput.value.trim();
      if (!text) {
        setStatus('Введите текст для наложения', true);
        return;
      }

      const autoFitEnabled = autoFitToggle.checked;
      const cfg = {
        text: text,
        font_size: parseInt(fontSizeInput.value || '48', 10),
        max_words_per_line: parseInt(maxWordsInput.value || '7', 10),
        align: getAlignValue(),
        center_x: parseFloat(centerXInput.value) / 100.0,
        center_y: parseFloat(centerYInput.value) / 100.0,
        font_color: fontColorInput.value,
        outline_color: outlineColorInput.value,
        outline_width: parseInt(outlineWidthInput.value || '2', 10),
        line_spacing: parseInt(lineSpacingInput.value || '4', 10)
      };
      if (autoFitEnabled) {
        cfg.auto_fit = true;
        cfg.padding_pct = parseFloat(paddingPctInput.value || '5');
        cfg.auto_fit_base_font_size = parseInt(baseFontSizeInput.value || '120', 10);
        cfg.max_text_coverage_pct = parseFloat(coverageMaxInput.value || '18');
        cfg.min_text_coverage_pct = parseFloat(coverageMinInput.value || '8');
        cfg.auto_fit_min_words_per_line = parseInt(autoFitMinWordsInput.value || '3', 10);
        cfg.auto_fit_max_words_per_line = parseInt(autoFitMaxWordsInput.value || '14', 10);
        cfg.auto_fit_min_font_size = parseInt(minFontSizeInput.value || '14', 10);
      }

      setStatus('Обработка видео… Это может занять время.');
      applyBtn.disabled = true;
      resultBadge.style.display = 'none';
      previewVideo.style.display = 'none';
      downloadLink.style.display = 'none';
      outputMeta.textContent = '';

      try {
        let res;
        if (mode === 'upload') {
          const file = videoUpload.files && videoUpload.files[0];
          if (!file) {
            throw new Error('Выберите видеофайл для загрузки');
          }
          const form = new FormData();
          form.append('video', file);
          form.append('text', cfg.text);
          form.append('font_size', String(cfg.font_size));
          form.append('max_words_per_line', String(cfg.max_words_per_line));
          form.append('align', cfg.align);
          form.append('center_x', String(cfg.center_x));
          form.append('center_y', String(cfg.center_y));
          form.append('font_color', cfg.font_color);
          form.append('outline_color', cfg.outline_color);
          form.append('outline_width', String(cfg.outline_width));
          form.append('line_spacing', String(cfg.line_spacing));
          if (autoFitEnabled) {
            form.append('auto_fit', 'true');
            form.append('padding_pct', String(cfg.padding_pct));
            form.append('auto_fit_base_font_size', String(cfg.auto_fit_base_font_size));
            form.append('max_text_coverage_pct', String(cfg.max_text_coverage_pct));
            form.append('min_text_coverage_pct', String(cfg.min_text_coverage_pct));
            form.append('auto_fit_min_words_per_line', String(cfg.auto_fit_min_words_per_line));
            form.append('auto_fit_max_words_per_line', String(cfg.auto_fit_max_words_per_line));
            form.append('auto_fit_min_font_size', String(cfg.auto_fit_min_font_size));
          }
          res = await fetch('/content/overlay_text_upload', { method: 'POST', body: form });
        } else {
          const opt = fileSelect.selectedOptions[0];
          const base = pathInput.value.trim().replace(/\/+$/, '');
          const selected = (opt && opt.dataset.kind === 'file') ? opt.value : null;
          const absPath = selected ? (base + '/' + selected) : null;
          if (!absPath) throw new Error('Выберите видеофайл (mp4)');
          const payload = { path: absPath, config: cfg };
          res = await fetch('/content/overlay_text', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
          });
        }
        if (!res.ok) {
          const text = await res.text();
          throw new Error(text || ('HTTP ' + res.status));
        }
        const data = await res.json();
        setStatus('Готово');
        resultBadge.style.display = 'inline-block';
        resultBadge.textContent = 'Видео с текстом сгенерировано';

        if (data.download_url) {
          const url = data.download_url;
          downloadLink.href = url;
          downloadLink.style.display = 'inline-block';
          downloadLink.textContent = 'Скачать ' + (data.output || 'видео');

          previewVideo.src = url;
          previewVideo.style.display = 'block';
        }
        outputMeta.textContent = (data.source ? ('Источник: ' + data.source + ' · ') : '') +
          (data.output ? ('Результат: ' + data.output) : '');
      } catch (e) {
        setStatus('Ошибка: ' + e, true);
      } finally {
        applyBtn.disabled = false;
      }
    });

    // Init
    apiBaseInfo.textContent = window.location.origin;
    // default path: /app/data (docker) or ./data (local)
    pathInput.value = '/app/data';
    loadFs(pathInput.value);
  </script>
</body>
</html>
    """


@router.get("/topics", response_class=HTMLResponse)
def topics_page() -> str:
    """UI: generate topics, pick video, batch overlay (title + description)."""
    return """
<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8" />
  <title>FABRIC — Темы → Текст на видео</title>
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <style>
    :root {
      color-scheme: dark;
      --bg: #050816;
      --card-bg: #0f172a;
      --accent: #38bdf8;
      --accent-soft: rgba(56, 189, 248, 0.15);
      --border: #1e293b;
      --text: #e5e7eb;
      --muted: #9ca3af;
      --danger: #f97373;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "SF Pro Text", sans-serif;
      background: radial-gradient(circle at top, #1e293b 0, var(--bg) 40%);
      color: var(--text);
      min-height: 100vh;
      display: flex;
      align-items: stretch;
      justify-content: center;
    }
    .page {
      max-width: 1200px;
      padding: 24px 16px 40px;
      margin: 0 auto;
      width: 100%;
      display: grid;
      grid-template-columns: minmax(0, 3fr) minmax(0, 2fr);
      gap: 24px;
    }
    @media (max-width: 900px) {
      .page { grid-template-columns: minmax(0, 1fr); }
    }
    .card {
      background: linear-gradient(135deg, rgba(15,23,42,0.98), rgba(15,23,42,0.96));
      border-radius: 18px;
      border: 1px solid rgba(148, 163, 184, 0.2);
      box-shadow: 0 18px 45px rgba(15, 23, 42, 0.85);
      padding: 20px 20px 22px;
      backdrop-filter: blur(24px);
    }
    .header {
      grid-column: 1 / -1;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 4px;
    }
    .title {
      font-size: 20px;
      font-weight: 650;
      letter-spacing: 0.03em;
      display: flex;
      align-items: baseline;
      gap: 8px;
    }
    .title span.badge {
      font-size: 11px;
      text-transform: uppercase;
      padding: 2px 8px;
      border-radius: 999px;
      background: linear-gradient(135deg, rgba(56,189,248,0.15), rgba(59,130,246,0.1));
      border: 1px solid rgba(56,189,248,0.4);
      color: var(--accent);
      letter-spacing: 0.12em;
    }
    .subtitle { font-size: 13px; color: var(--muted); }
    label {
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--muted);
      display: block;
      margin-bottom: 4px;
    }
    select, input[type="text"], input[type="number"], textarea {
      width: 100%;
      border-radius: 10px;
      border: 1px solid var(--border);
      background: rgba(15,23,42,0.9);
      color: var(--text);
      font-size: 13px;
      padding: 8px 10px;
      outline: none;
    }
    textarea { min-height: 70px; resize: vertical; line-height: 1.5; }
    .row { display: flex; gap: 10px; margin-bottom: 10px; }
    .row > div { flex: 1; min-width: 0; }
    .section-title {
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.1em;
      color: var(--muted);
      margin: 10px 0 6px;
    }
    .btn {
      border-radius: 999px;
      border: none;
      padding: 9px 16px;
      font-size: 13px;
      font-weight: 550;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 8px;
      background: linear-gradient(135deg, #38bdf8, #6366f1);
      color: white;
      box-shadow: 0 10px 25px rgba(56,189,248,0.35);
      margin-top: 4px;
    }
    .btn:disabled { opacity: 0.5; cursor: default; box-shadow: none; }
    .btn-secondary {
      background: rgba(15,23,42,0.9);
      color: var(--muted);
      box-shadow: none;
      border: 1px solid var(--border);
    }
    .status { font-size: 12px; margin-top: 8px; color: var(--muted); min-height: 18px; }
    .status--error { color: var(--danger); }
    .badge-small {
      font-size: 11px;
      padding: 2px 8px;
      border-radius: 999px;
      background: var(--accent-soft);
      color: var(--accent);
      text-transform: uppercase;
      letter-spacing: 0.12em;
    }
    .topic-list { display: grid; gap: 10px; margin-top: 8px; }
    .topic-item {
      border: 1px solid rgba(148,163,184,0.22);
      border-radius: 12px;
      padding: 10px 12px;
      display: flex;
      gap: 10px;
      align-items: flex-start;
      background: rgba(2, 6, 23, 0.35);
    }
    .topic-item strong { display: block; font-size: 13px; }
    .topic-item .desc { color: var(--muted); font-size: 12px; margin-top: 2px; }
    .output-meta { font-size: 12px; color: var(--muted); margin-top: 8px; }
    a.download-link { color: var(--accent); text-decoration: none; font-size: 13px; }
    a.download-link:hover { text-decoration: underline; }
    video { width: 100%; border-radius: 14px; border: 1px solid rgba(148,163,184,0.3); background: black; }
  </style>
</head>
<body>
  <div class="page">
    <div class="header">
      <div>
        <div class="title">FABRIC Topics <span class="badge">batch overlay</span></div>
        <div class="subtitle">Сгенерируй темы → выбери нужные → выбери видео → запусти пакетную генерацию.</div>
      </div>
      <div class="subtitle" id="apiBaseInfo"></div>
    </div>

    <div class="card">
      <div class="section-title">1) Генерация тем</div>
      <div class="row">
        <div>
          <label for="topicsN">Количество (N)</label>
          <input id="topicsN" type="number" min="1" max="50" value="8" />
        </div>
        <div style="display:flex;align-items:flex-end;gap:8px;">
          <button type="button" class="btn btn-secondary" id="genBtn" style="margin-top:0;">Сгенерировать темы</button>
        </div>
      </div>
      <div>
        <label for="topicsHint">Подсказка (опционально)</label>
        <textarea id="topicsHint" placeholder="Например: психология, спорт, отношения, бизнес..."></textarea>
      </div>
      <div class="row" style="margin-top:8px;">
        <div style="display:flex;gap:8px;align-items:center;">
          <span class="badge-small" id="topicsCount">0 выбрано</span>
          <button type="button" class="btn btn-secondary" id="selectAllBtn" style="margin-top:0;">Выбрать все</button>
          <button type="button" class="btn btn-secondary" id="clearBtn" style="margin-top:0;">Снять</button>
        </div>
      </div>
      <div class="status" id="topicsStatus"></div>
      <div class="topic-list" id="topicsList"></div>
    </div>

    <div class="card">
      <div class="section-title">2) Видео</div>
      <div class="row">
        <div>
          <label>Источник</label>
          <div class="pill-group" id="sourceGroup">
            <button type="button" class="pill-btn active" data-value="upload">Загрузить (file picker)</button>
            <button type="button" class="pill-btn" data-value="server">Серверная папка</button>
          </div>
        </div>
      </div>

      <div id="uploadBlock">
        <div class="row">
          <div style="flex:2;">
            <label for="videoUpload">Видео файл</label>
            <input id="videoUpload" type="file" accept="video/mp4,video/*" />
          </div>
          <div style="flex:1;display:flex;align-items:flex-end;gap:8px;">
            <span class="badge-small" id="uploadBadge" style="display:none;">готово</span>
          </div>
        </div>
        <div class="output-meta" id="uploadVideoInfo" style="margin-top:-2px;"></div>
      </div>

      <div id="serverBlock" style="display:none;">
        <div class="row">
          <div style="flex:2;">
            <label for="pathInput">Папка в файловой системе</label>
            <input id="pathInput" type="text" placeholder="/app/data или /home/..." />
          </div>
          <div style="flex:1;display:flex;align-items:flex-end;gap:8px;">
            <button type="button" class="btn btn-secondary" id="loadBtn" style="margin-top:0;">Загрузить</button>
            <button type="button" class="btn btn-secondary" id="upBtn" style="margin-top:0;">⬆︎</button>
          </div>
        </div>
        <div class="row">
          <div>
            <label for="fileSelect">Видео / папки</label>
            <select id="fileSelect"></select>
          </div>
        </div>
        <div class="output-meta" id="videoInfo" style="margin-top:-2px;"></div>
      </div>

      <div class="section-title">Параметры</div>
      <div class="row">
        <div>
          <label for="titleY">Y заголовка (верхняя грань, %)</label>
          <input id="titleY" type="number" min="0" max="100" value="12" />
        </div>
        <div>
          <label for="paddingPct">Паддинг (%)</label>
          <input id="paddingPct" type="number" min="0" max="30" value="5" />
        </div>
      </div>
      <div class="row">
        <div>
          <label for="coverageMinPct">Покрытие (мин, %)</label>
          <input id="coverageMinPct" type="number" min="0" max="100" step="0.1" value="8" />
        </div>
        <div>
          <label for="coverageMaxPct">Покрытие (макс, %)</label>
          <input id="coverageMaxPct" type="number" min="0" max="100" step="0.1" value="18" />
        </div>
      </div>
      <div class="row">
        <div>
          <label for="autoFitMinWords">Мин. слов в строке</label>
          <input id="autoFitMinWords" type="number" min="1" max="50" value="3" />
        </div>
        <div>
          <label for="autoFitMaxWords">Макс. слов в строке</label>
          <input id="autoFitMaxWords" type="number" min="1" max="50" value="14" />
        </div>
      </div>
      <div class="row">
        <div>
          <label for="minFontSize">Мин. размер текста</label>
          <input id="minFontSize" type="number" min="6" max="200" value="14" />
        </div>
        <div>
          <label for="baseFontSize">Базовый размер</label>
          <input id="baseFontSize" type="number" min="20" max="400" value="120" />
        </div>
      </div>

      <button class="btn" id="runBtn"><span>Запустить</span></button>
      <div class="status" id="runStatus"></div>
    </div>

    <div class="card" style="grid-column: 1 / -1;">
      <div class="section-title">Результат</div>
      <div id="resultsList" class="topic-list"></div>
      <div style="margin-top:12px;">
        <video id="previewVideo" controls style="display:none;" playsinline></video>
      </div>
    </div>
  </div>

  <script>
    const apiBaseInfo = document.getElementById('apiBaseInfo');
    apiBaseInfo.textContent = window.location.origin;

    const topicsN = document.getElementById('topicsN');
    const topicsHint = document.getElementById('topicsHint');
    const genBtn = document.getElementById('genBtn');
    const topicsStatus = document.getElementById('topicsStatus');
    const topicsList = document.getElementById('topicsList');
    const topicsCount = document.getElementById('topicsCount');
    const selectAllBtn = document.getElementById('selectAllBtn');
    const clearBtn = document.getElementById('clearBtn');

    const sourceGroup = document.getElementById('sourceGroup');
    const uploadBlock = document.getElementById('uploadBlock');
    const serverBlock = document.getElementById('serverBlock');
    const videoUpload = document.getElementById('videoUpload');
    const uploadBadge = document.getElementById('uploadBadge');
    const uploadVideoInfo = document.getElementById('uploadVideoInfo');

    const pathInput = document.getElementById('pathInput');
    const loadBtn = document.getElementById('loadBtn');
    const upBtn = document.getElementById('upBtn');
    const fileSelect = document.getElementById('fileSelect');
    const videoInfo = document.getElementById('videoInfo');

    const titleY = document.getElementById('titleY');
    const paddingPct = document.getElementById('paddingPct');
    const coverageMinPct = document.getElementById('coverageMinPct');
    const coverageMaxPct = document.getElementById('coverageMaxPct');
    const autoFitMinWords = document.getElementById('autoFitMinWords');
    const autoFitMaxWords = document.getElementById('autoFitMaxWords');
    const minFontSize = document.getElementById('minFontSize');
    const baseFontSize = document.getElementById('baseFontSize');

    const runBtn = document.getElementById('runBtn');
    const runStatus = document.getElementById('runStatus');
    const resultsList = document.getElementById('resultsList');
    const previewVideo = document.getElementById('previewVideo');

    let currentTopics = [];
    let selectedVideoPath = null;
    let selectedUploadFile = null;

    function getSourceMode() {
      const active = sourceGroup.querySelector('.pill-btn.active');
      return active ? active.dataset.value : 'upload';
    }

    sourceGroup.addEventListener('click', async (e) => {
      const btn = e.target.closest('.pill-btn');
      if (!btn) return;
      sourceGroup.querySelectorAll('.pill-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      const mode = getSourceMode();
      uploadBlock.style.display = (mode === 'upload') ? 'block' : 'none';
      serverBlock.style.display = (mode === 'server') ? 'block' : 'none';
      if (mode === 'server') {
        await loadFs(pathInput.value);
      }
    });

    videoUpload.addEventListener('change', async () => {
      uploadBadge.style.display = 'none';
      uploadVideoInfo.textContent = '';
      selectedUploadFile = null;
      const file = videoUpload.files && videoUpload.files[0];
      if (!file) return;
      selectedUploadFile = file;
      uploadBadge.style.display = 'inline-block';
      uploadBadge.textContent = file.name;

      // Client-side metadata (resolution, duration)
      try {
        const url = URL.createObjectURL(file);
        const v = document.createElement('video');
        v.preload = 'metadata';
        v.src = url;
        v.muted = true;
        v.playsInline = true;
        v.addEventListener('loadedmetadata', () => {
          const wh = (v.videoWidth && v.videoHeight) ? (v.videoWidth + '×' + v.videoHeight) : '—';
          const dur = (v.duration && isFinite(v.duration)) ? (v.duration.toFixed(1) + 's') : '—';
          const sizeMb = (file.size != null) ? (file.size / (1024 * 1024)).toFixed(2) + ' MB' : '—';
          uploadVideoInfo.textContent = 'Файл: ' + file.name + ' · Размер: ' + sizeMb + ' · Разрешение: ' + wh + ' · Длительность: ' + dur;
          URL.revokeObjectURL(url);
        }, { once: true });
      } catch (e) {}
    });

    function setStatus(el, text, isError=false) {
      el.textContent = text || '';
      el.classList.toggle('status--error', !!isError);
    }

    function updateSelectedCount() {
      const selected = currentTopics.filter(t => t.selected);
      topicsCount.textContent = selected.length + ' выбрано';
    }

    function renderTopics() {
      topicsList.innerHTML = '';
      for (const t of currentTopics) {
        const row = document.createElement('div');
        row.className = 'topic-item';

        const cb = document.createElement('input');
        cb.type = 'checkbox';
        cb.checked = !!t.selected;
        cb.addEventListener('change', () => {
          t.selected = cb.checked;
          updateSelectedCount();
        });

        const content = document.createElement('div');
        const title = document.createElement('strong');
        title.textContent = t.title;
        const desc = document.createElement('div');
        desc.className = 'desc';
        desc.textContent = t.description;
        content.appendChild(title);
        content.appendChild(desc);

        row.appendChild(cb);
        row.appendChild(content);
        topicsList.appendChild(row);
      }
      updateSelectedCount();
    }

    selectAllBtn.addEventListener('click', () => {
      currentTopics.forEach(t => t.selected = true);
      renderTopics();
    });
    clearBtn.addEventListener('click', () => {
      currentTopics.forEach(t => t.selected = false);
      renderTopics();
    });

    genBtn.addEventListener('click', async () => {
      setStatus(topicsStatus, 'Генерация тем…');
      genBtn.disabled = true;
      try {
        const payload = { n: parseInt(topicsN.value || '8', 10), hint: (topicsHint.value || '').trim() || null };
        const res = await fetch('/content/topics_generate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        if (!res.ok) throw new Error(await res.text());
        const data = await res.json();
        currentTopics = (data.topics || []).map(x => ({ title: x.title, description: x.description, selected: true }));
        renderTopics();
        setStatus(topicsStatus, 'Готово: темы сгенерированы');
      } catch (e) {
        setStatus(topicsStatus, 'Ошибка генерации: ' + e, true);
      } finally {
        genBtn.disabled = false;
      }
    });

    async function loadFs(path) {
      fileSelect.innerHTML = '';
      videoInfo.textContent = '';
      selectedVideoPath = null;
      if (!path) return;
      try {
        const res = await fetch('/content/fs_ls?path=' + encodeURIComponent(path));
        if (!res.ok) throw new Error(await res.text());
        const data = await res.json();
        pathInput.value = data.path;
        const entries = [];
        if (data.dirs) for (const d of data.dirs) entries.push({ kind: 'dir', name: d });
        if (data.files) for (const f of data.files) entries.push({ kind: 'file', name: f });
        if (!entries.length) {
          const opt = document.createElement('option');
          opt.value = '';
          opt.textContent = 'Папка пустая';
          fileSelect.appendChild(opt);
          return;
        }
        for (const e of entries) {
          const opt = document.createElement('option');
          opt.value = e.name;
          opt.textContent = (e.kind === 'dir' ? '📁 ' : '🎬 ') + e.name;
          opt.dataset.kind = e.kind;
          fileSelect.appendChild(opt);
        }
      } catch (e) {
        videoInfo.textContent = 'Ошибка чтения папки: ' + e;
      }
    }

    async function loadVideoInfo(absPath) {
      videoInfo.textContent = '';
      try {
        const res = await fetch('/content/video_info?path=' + encodeURIComponent(absPath));
        if (!res.ok) throw new Error(await res.text());
        const info = await res.json();
        const wh = (info.width && info.height) ? (info.width + '×' + info.height) : '—';
        const dur = (info.duration_sec != null) ? (info.duration_sec.toFixed(1) + 's') : '—';
        const fps = (info.fps != null) ? (info.fps.toFixed(2) + ' fps') : '—';
        videoInfo.textContent = 'Выбрано: ' + absPath + ' · ' + wh + ' · ' + dur + ' · ' + fps;
      } catch (e) {
        videoInfo.textContent = 'Не удалось получить информацию о видео';
      }
    }

    loadBtn.addEventListener('click', () => loadFs(pathInput.value.trim()));
    upBtn.addEventListener('click', async () => {
      const p = pathInput.value.trim();
      if (!p) return;
      const idx = p.replace(/\/+$/, '').lastIndexOf('/');
      if (idx <= 0) return;
      const parent = p.slice(0, idx) || '/';
      await loadFs(parent);
    });

    fileSelect.addEventListener('change', async () => {
      const opt = fileSelect.selectedOptions[0];
      if (!opt) return;
      const kind = opt.dataset.kind;
      const name = opt.value;
      if (!kind || !name) return;
      const base = pathInput.value.trim().replace(/\/+$/, '');
      const abs = base + '/' + name;
      if (kind === 'dir') {
        await loadFs(abs);
      } else {
        selectedVideoPath = abs;
        await loadVideoInfo(abs);
      }
    });

    runBtn.addEventListener('click', async () => {
      const selected = currentTopics.filter(t => t.selected).map(t => ({ title: t.title, description: t.description }));
      if (!selected.length) {
        setStatus(runStatus, 'Выберите хотя бы одну тему', true);
        return;
      }
      const mode = getSourceMode();
      if (mode === 'server') {
        if (!selectedVideoPath) {
          setStatus(runStatus, 'Выберите видео из файловой системы', true);
          return;
        }
      } else {
        if (!selectedUploadFile) {
          setStatus(runStatus, 'Выберите видеофайл (upload)', true);
          return;
        }
      }

      const params = {
        title_y: parseFloat(titleY.value || '12') / 100.0,
        padding_pct: parseFloat(paddingPct.value || '5'),
        coverage_min_pct: parseFloat(coverageMinPct.value || '8'),
        coverage_max_pct: parseFloat(coverageMaxPct.value || '18'),
        words_min: parseInt(autoFitMinWords.value || '3', 10),
        words_max: parseInt(autoFitMaxWords.value || '14', 10),
        min_font_size: parseInt(minFontSize.value || '14', 10),
        base_font_size: parseInt(baseFontSize.value || '120', 10),
      };

      setStatus(runStatus, 'Запуск… (будет создано видео: ' + selected.length + ')');
      runBtn.disabled = true;
      resultsList.innerHTML = '';
      previewVideo.style.display = 'none';

      try {
        let res;
        if (mode === 'upload') {
          const form = new FormData();
          form.append('video', selectedUploadFile);
          form.append('topics_json', JSON.stringify(selected));
          form.append('params_json', JSON.stringify(params));
          res = await fetch('/content/topics_overlay_batch_upload', { method: 'POST', body: form });
        } else {
          res = await fetch('/content/topics_overlay_batch', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path: selectedVideoPath, topics: selected, params })
          });
        }
        if (!res.ok) throw new Error(await res.text());
        const data = await res.json();
        const results = data.results || [];
        for (const r of results) {
          const item = document.createElement('div');
          item.className = 'topic-item';
          const content = document.createElement('div');
          const t = document.createElement('strong');
          t.textContent = r.title;
          const d = document.createElement('div');
          d.className = 'desc';
          d.textContent = r.description;
          const link = document.createElement('a');
          link.className = 'download-link';
          link.href = r.download_url;
          link.textContent = 'Скачать';
          link.target = '_blank';
          content.appendChild(t);
          content.appendChild(d);
          content.appendChild(link);
          item.appendChild(content);
          resultsList.appendChild(item);
        }
        if (results.length && results[0].download_url) {
          previewVideo.src = results[0].download_url;
          previewVideo.style.display = 'block';
        }
        setStatus(runStatus, 'Готово');
      } catch (e) {
        setStatus(runStatus, 'Ошибка: ' + e, true);
      } finally {
        runBtn.disabled = false;
      }
    });

    // Init
    if (pathInput) {
      pathInput.value = '/app/data';
    }
  </script>
</body>
</html>
    """




