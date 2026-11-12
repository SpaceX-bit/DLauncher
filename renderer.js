const $ = (id) => document.getElementById(id);
const api = window.api;

const NAMES = { vanilla: 'Vanilla', fabric: 'Fabric', forge: 'Forge', neoforge: 'NeoForge', quilt: 'Quilt' };
const KIND_LABEL = { mod: 'Моды', modpack: 'Сборки', resourcepack: 'Ресурспаки', shader: 'Шейдеры' };
const TYPE_LABEL = { release: 'релиз', snapshot: 'снапшот', old_beta: 'бета', old_alpha: 'альфа' };

let manifest = null;
let profiles = [];
let currentId = null;
let modSource = 'modrinth';
let modKind = 'mod';

const esc = (s) =>
  String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const cur = () => profiles.find((p) => p.id === currentId) || null;
const fmtDate = (t) => (t ? new Date(t).toLocaleDateString(I18N.locale()) : '—');
const fmtSize = (b) => (b > 1048576 ? (b / 1048576).toFixed(1) + ' МБ' : Math.max(1, Math.round(b / 1024)) + ' КБ');
const profileLabel = (p) => `${p.name} · ${p.version} · ${NAMES[p.loader] || p.loader}`;

// ---------- Тема ----------

// ---------- Окно ----------
$('btn-min').onclick = () => api.invoke('win:minimize');
$('btn-close').onclick = () => api.invoke('win:close');

// ---------- Навигация ----------
function showView(name) {
  document.querySelectorAll('.nav-btn').forEach((x) => x.classList.toggle('active', x.dataset.view === name));
  document.querySelectorAll('.view').forEach((v) => v.classList.toggle('active', v.id === 'view-' + name));
  if (name === 'mods') {
    refreshModsInfo();
    if (!$('mods-list').children.length) searchMods();
  }
  if (name === 'installed') loadInstalled();
  if (name === 'settings') refreshMsStatus();
}
document.querySelectorAll('.nav-btn').forEach((b) => { b.onclick = () => showView(b.dataset.view); });

// Секрет: 5 нажатий подряд (пауза не дольше 3 секунд) на «О разработчике»
function secretButton(id, image, onClick) {
  let clicks = 0;
  let timer = null;
  $(id).addEventListener('click', () => {
    if (onClick) onClick();
    clicks++;
    clearTimeout(timer);
    timer = setTimeout(() => { clicks = 0; }, 3000);
    if (clicks >= 5) {
      clicks = 0;
      showSecret(image);
    }
  });
}
secretButton('btn-about', 'secret.png', () => showView('about'));

// «Тестировщик»: один клик показывает карточку с именем и кнопкой TikTok
$('btn-tester').onclick = () => $('tester-modal').classList.remove('hidden');
$('tester-close').onclick = () => $('tester-modal').classList.add('hidden');
$('tester-modal').onclick = (e) => { if (e.target === $('tester-modal')) $('tester-modal').classList.add('hidden'); };
$('tester-tiktok').onclick = () => api.invoke('link:open', 'tiktok'); // адрес хранится в главном процессе

// Картинка сама исчезает через 3 секунды
let secretTimer = null;
function showSecret(image) {
  clearTimeout(secretTimer);
  $('secret-img').src = image;
  $('secret-modal').classList.remove('hidden');
  secretTimer = setTimeout(hideSecret, 3000);
}
function hideSecret() {
  clearTimeout(secretTimer);
  $('secret-modal').classList.add('hidden');
}
$('secret-modal').onclick = hideSecret;
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    hideSecret();
    $('tester-modal').classList.add('hidden');
    $('opt-modal').classList.add('hidden');
    $('pf-modal').classList.add('hidden');
    $('pe-modal').classList.add('hidden');
    closeServers();
    $('imp-modal').classList.add('hidden');
  }
});

// ---------- Профили ----------
async function loadProfiles() {
  const r = await api.invoke('profiles:list');
  profiles = r.profiles;
  currentId = r.current;
  renderProfileSelect();
  renderProfilesView();
  updateHero();
  refreshModsInfo();
}

function renderProfileSelect() {
  const sel = $('profile-select');
  if (!profiles.length) {
    sel.innerHTML = '<option value="">Нет профилей</option>';
  } else {
    sel.innerHTML = profiles.map((p) => `<option value="${esc(p.id)}">${esc(p.name)}</option>`).join('');
    sel.value = currentId || '';
  }
}

function updateHero() {
  const p = cur();
  $('hero-profile').textContent = p ? profileLabel(p) : 'Создай первый профиль, чтобы начать игру';
  const q = $('btn-quick');
  if (p && p.lastServer) {
    q.textContent = 'На сервер: ' + p.lastServer.host;
    q.title = `Зайти на ${p.lastServer.host}:${p.lastServer.port}`;
    q.classList.remove('hidden');
  } else {
    q.classList.add('hidden');
  }
}

async function selectProfile(id) {
  await api.invoke('profiles:select', id);
  currentId = id;
  renderProfileSelect();
  renderProfilesView();
  updateHero();
  refreshModsInfo();
  $('mods-list').innerHTML = '';
  if ($('view-installed').classList.contains('active')) loadInstalled();
  if ($('view-mods').classList.contains('active')) searchMods();
}

$('profile-select').onchange = () => { if ($('profile-select').value) selectProfile($('profile-select').value); };

function renderProfilesView() {
  const box = $('profiles-list');
  if (!profiles.length) {
    box.innerHTML = '<p class="muted">Профилей пока нет. Нажми «Новый профиль» или установи готовую сборку во вкладке «Моды» → «Сборки».</p>';
    return;
  }
  box.innerHTML = '';
  profiles.forEach((p) => {
    const card = document.createElement('div');
    card.className = 'pf-card' + (p.id === currentId ? ' current' : '');
    const server = p.lastServer ? `<span>Сервер: ${esc(p.lastServer.host)}</span>` : '';
    const extra = [
      p.ram ? `<span>Память: ${p.ram} ГБ</span>` : '',
      p.fullscreen ? '<span>Окно: весь экран</span>' : p.width && p.height ? `<span>Окно: ${p.width}×${p.height}</span>` : '',
      (p.servers || []).length ? `<span>Серверов: ${p.servers.length}</span>` : '',
    ].join('');
    const pack = p.pack ? `<span class="badge">Сборка${p.pack.version ? ' ' + esc(p.pack.version) : ''}</span>` : '';
    card.innerHTML = `
      <div class="pf-head">
        <div class="pf-name">${esc(p.name)}</div>
        ${p.id === currentId ? '<span class="badge on">Выбран</span>' : ''}
      </div>
      <div class="pf-meta">
        <span>Minecraft ${esc(p.version)}</span>
        <span>${esc(NAMES[p.loader] || p.loader)}${p.loaderVersion ? ' ' + esc(p.loaderVersion) : ''}</span>
        <span>Модов: ${p.modsCount}</span>
        <span>Запуск: ${fmtDate(p.lastPlayed)}</span>
        ${server}${extra}${pack}
      </div>
      <div class="pf-actions">
        <button class="btn" data-act="play">Играть</button>
        <button class="btn ghost" data-act="select">Выбрать</button>
        <button class="btn ghost" data-act="mods">Моды</button>
        <button class="btn ghost" data-act="servers">Серверы</button>
        <button class="btn ghost" data-act="edit">Настроить</button>
        <button class="btn ghost" data-act="folder">Папка</button>
        <button class="btn ghost danger" data-act="delete">Удалить</button>
      </div>`;
    card.querySelectorAll('button').forEach((b) => {
      b.onclick = async () => {
        const act = b.dataset.act;
        if (act === 'select') return selectProfile(p.id);
        if (act === 'play') {
          await selectProfile(p.id);
          showView('play');
          return launch(false);
        }
        if (act === 'mods') {
          await selectProfile(p.id);
          return showView('installed');
        }
        if (act === 'servers') return openServers(p.id);
        if (act === 'edit') return openProfileEdit(p);
        if (act === 'folder') return api.invoke('folder:open', { which: 'profile', profileId: p.id });
        if (act === 'delete') {
          if (b.dataset.sure !== '1') {
            b.dataset.sure = '1';
            b.textContent = 'Точно удалить?';
            setTimeout(() => { b.dataset.sure = ''; b.textContent = 'Удалить'; }, 3000);
            return;
          }
          const r = await api.invoke('profiles:delete', { id: p.id, deleteFiles: true });
          if (!r.ok) alert(r.error);
          await loadProfiles();
        }
      };
    });
    box.appendChild(card);
  });
}

// ---------- Окно «Новый профиль» ----------
let pfLoaders = [];

async function ensureManifest() {
  if (manifest) return true;
  try {
    manifest = await api.invoke('versions:list');
    return true;
  } catch {
    return false;
  }
}

function pfRenderVersions() {
  const filter = $('pf-type').value;
  const list = manifest.versions.filter((v) => filter === 'all' || v.type === filter);
  const prev = $('pf-version').value;
  $('pf-version').innerHTML = list
    .map((v) => `<option value="${v.id}" data-type="${v.type}">${v.id}${filter === 'all' ? ' · ' + TYPE_LABEL[v.type] : ''}</option>`)
    .join('');
  if (list.some((v) => v.id === prev)) $('pf-version').value = prev;
  else if (filter === 'release' && manifest.latest) $('pf-version').value = manifest.latest.release;
  pfLoadLoaders();
}

async function pfLoadLoaders() {
  const mc = $('pf-version').value;
  if (!mc) return;
  $('pf-loader').innerHTML = '<option>Загрузка...</option>';
  $('pf-create').disabled = true;
  let res;
  try {
    res = await api.invoke('loaders:list', mc);
  } catch {
    res = [{ loader: 'vanilla', versions: ['—'] }];
  }
  if ($('pf-version').value !== mc) return; // пользователь уже выбрал другую версию
  pfLoaders = res;
  $('pf-loader').innerHTML = pfLoaders.map((l) => `<option value="${l.loader}">${NAMES[l.loader] || l.loader}</option>`).join('');
  pfRenderLoaderVersions();
  $('pf-create').disabled = false;
}

function pfRenderLoaderVersions() {
  const c = pfLoaders.find((l) => l.loader === $('pf-loader').value);
  const wrap = $('pf-lv-wrap');
  if (!c || c.loader === 'vanilla') {
    wrap.classList.add('hidden');
    $('pf-loader-version').innerHTML = '';
  } else {
    wrap.classList.remove('hidden');
    $('pf-loader-version').innerHTML = c.versions.map((v) => `<option>${esc(v)}</option>`).join('');
  }
}

async function openProfileModal() {
  $('pf-modal').classList.remove('hidden');
  $('pf-msg').textContent = '';
  $('pf-name').value = '';
  if (!(await ensureManifest())) {
    $('pf-msg').textContent = 'Не удалось загрузить список версий: проверь интернет';
    return;
  }
  pfRenderVersions();
}

$('pf-type').onchange = () => manifest && pfRenderVersions();
$('pf-version').onchange = pfLoadLoaders;
$('pf-loader').onchange = pfRenderLoaderVersions;
$('pf-cancel').onclick = () => $('pf-modal').classList.add('hidden');
$('pf-modal').onclick = (e) => { if (e.target === $('pf-modal')) $('pf-modal').classList.add('hidden'); };
$('pf-new').onclick = openProfileModal;

$('pf-create').onclick = async () => {
  const opt = $('pf-version').selectedOptions[0];
  if (!opt) return;
  const loader = $('pf-loader').value;
  const name = $('pf-name').value.trim() || `${opt.value}${loader !== 'vanilla' ? ' ' + (NAMES[loader] || loader) : ''}`;
  $('pf-create').disabled = true;
  const r = await api.invoke('profiles:create', {
    name,
    version: opt.value,
    versionType: opt.dataset.type,
    loader,
    loaderVersion: $('pf-loader-version').value,
  });
  $('pf-create').disabled = false;
  if (!r.ok) {
    $('pf-msg').textContent = r.error;
    return;
  }
  $('pf-modal').classList.add('hidden');
  await loadProfiles();
};

// ---------- Запуск ----------
async function launch(quick, server, profileId) {
  if (profileId && profileId !== currentId) await selectProfile(profileId);
  const p = cur();
  if (!p) {
    showView('profiles');
    return openProfileModal();
  }
  $('btn-play').disabled = true;
  $('btn-quick').disabled = true;
  $('status').textContent = 'Запуск...';
  const res = await api.invoke('game:launch', { profileId: p.id, quickJoin: !!quick, server: server || undefined });
  if (!res.ok) {
    $('status').textContent = 'Ошибка: ' + res.error;
    $('progress').classList.add('hidden');
    $('btn-play').disabled = false;
    $('btn-quick').disabled = false;
  } else {
    bgGame(true); // видео-фон на паузу, пока идёт игра
    loadProfiles(); // обновится «Запуск: дата»
  }
}
$('btn-play').onclick = () => launch(false);
$('btn-quick').onclick = () => launch(true);

api.on('game:status', (t) => { $('status').textContent = t; });
api.on('game:progress', (p) => {
  $('progress').classList.remove('hidden');
  const pct = p.total ? Math.min(100, Math.round((p.task / p.total) * 100)) : 0;
  $('progress-bar').style.width = pct + '%';
  $('status').textContent = `${p.label || 'Загрузка'}: ${pct}%`;
});
api.on('game:closed', (code) => {
  bgGame(false);
  $('status').textContent = code === 0 ? 'Игра закрыта' : `Игра завершилась с кодом ${code}`;
  $('progress').classList.add('hidden');
  $('btn-play').disabled = false;
  $('btn-quick').disabled = false;
});
api.on('game:log', (m) => {
  if (m.includes('Launching with arguments') || m.includes('Setting user')) {
    $('status').textContent = 'Игра запущена';
    $('progress').classList.add('hidden');
  }
});
api.on('server:last', ({ profileId, lastServer }) => {
  const p = profiles.find((x) => x.id === profileId);
  if (p) {
    p.lastServer = lastServer;
    updateHero();
    renderProfilesView();
    if (srvPid === profileId && !$('srv-modal').classList.contains('hidden')) renderServers(false);
  }
});

// ---------- Папки ----------
$('btn-root').onclick = () => api.invoke('folder:open', 'root');
$('btn-modsdir').onclick = () => api.invoke('folder:open', 'mods');

// ---------- Моды / ресурспаки / шейдеры / сборки ----------
function refreshModsInfo() {
  const p = cur();
  let text;
  if (modKind === 'modpack') {
    text = 'Сборка ставится как новый профиль: игра, загрузчик, моды и настройки скачаются сами.';
  } else if (!p) {
    text = 'Сначала создай профиль во вкладке «Профили» — моды ставятся в выбранный профиль.';
  } else if (modKind === 'mod') {
    text =
      p.loader === 'vanilla'
        ? `Профиль «${p.name}» — Vanilla. Для модов создай профиль с Fabric / Forge / NeoForge / Quilt.`
        : `Моды для профиля «${p.name}»: Minecraft ${p.version} · ${NAMES[p.loader] || p.loader}`;
  } else if (modKind === 'shader') {
    text = `Шейдеры для профиля «${p.name}» (Minecraft ${p.version}). Нужен мод Iris (Fabric/Quilt) или Oculus (Forge) — найди его во вкладке «Моды».`;
  } else {
    text = `Ресурспаки для профиля «${p.name}» (Minecraft ${p.version})`;
  }
  $('mods-info').textContent = text;
}

function setKind(kind) {
  modKind = kind;
  document.querySelectorAll('#kind-seg .seg-btn').forEach((x) => x.classList.toggle('active', x.dataset.kind === kind));
  $('mod-query').placeholder = `Поиск: ${KIND_LABEL[kind].toLowerCase()}...`;
  refreshModsInfo();
  searchMods();
}

document.querySelectorAll('#kind-seg .seg-btn').forEach((b) => { b.onclick = () => setKind(b.dataset.kind); });
document.querySelectorAll('#source-seg .seg-btn').forEach((b) => {
  b.onclick = () => {
    modSource = b.dataset.source;
    document.querySelectorAll('#source-seg .seg-btn').forEach((x) => x.classList.toggle('active', x === b));
    searchMods();
  };
});
$('mod-search').onclick = () => searchMods();
$('mod-query').onkeydown = (e) => { if (e.key === 'Enter') searchMods(); };

// Иконки грузит сам лаунчер (кэш на диске, запасной путь) — ВПН не нужен
const iconQueue = [];
let iconActive = 0;
function loadIcon(url, el) {
  iconQueue.push({ url, el });
  pumpIcons();
}
function pumpIcons() {
  while (iconActive < 6 && iconQueue.length) {
    const { url, el } = iconQueue.shift();
    iconActive++;
    api.invoke('icon:get', url)
      .then((data) => {
        if (data && el.isConnected) {
          const img = document.createElement('img');
          img.alt = '';
          img.src = data;
          el.replaceWith(img);
        }
      })
      .catch(() => {})
      .finally(() => { iconActive--; pumpIcons(); });
  }
}

let modOffset = 0;
let searchSeq = 0;

async function installPack(m, btn) {
  btn.disabled = true;
  $('pack-modal').classList.remove('hidden');
  $('pack-title').textContent = `Установка: ${m.title}`;
  $('pack-text').textContent = 'Подготовка...';
  $('pack-bar').style.width = '0%';
  $('pack-result').textContent = '';
  $('pack-close').classList.add('hidden');

  const r = await api.invoke('pack:install', { source: modSource, id: m.id, title: m.title });
  btn.disabled = false;
  $('pack-close').classList.remove('hidden');
  if (!r.ok) {
    $('pack-text').textContent = 'Не удалось установить сборку';
    $('pack-result').textContent = r.error;
    return;
  }
  $('pack-bar').style.width = '100%';
  $('pack-text').textContent = `Готово: создан профиль «${r.profile.name}»`;
  $('pack-result').textContent = r.missing.length
    ? `Не скачалось файлов: ${r.missing.length} (${r.missing.slice(0, 3).join(', ')}${r.missing.length > 3 ? '…' : ''}). Часть модов можно докачать вручную.`
    : 'Все файлы сборки скачаны. Выбери профиль и нажми «ИГРАТЬ» — загрузчик установится при первом запуске.';
  btn.textContent = 'Установлено';
  await loadProfiles();
}
$('pack-close').onclick = () => $('pack-modal').classList.add('hidden');
api.on('pack:progress', ({ text, done, total }) => {
  $('pack-text').textContent = text;
  if (total) $('pack-bar').style.width = Math.min(100, Math.round((done / total) * 100)) + '%';
});

async function searchMods(append = false) {
  const list = $('mods-list');
  const seq = ++searchSeq;
  if (!append) {
    iconQueue.length = 0;
    modOffset = 0;
    list.innerHTML = '<p class="muted">Ищу...</p>';
  } else if ($('mods-more')) {
    $('mods-more').disabled = true;
    $('mods-more').textContent = 'Загрузка...';
  }

  const p = cur();
  const filtered = modKind !== 'modpack' && p; // сборки ищем по всем версиям
  const res = await api.invoke('mods:search', {
    source: modSource,
    query: $('mod-query').value.trim(),
    mc: filtered ? p.version : '',
    loader: filtered ? p.loader : '',
    kind: modKind,
    offset: modOffset,
  });
  if (seq !== searchSeq) return; // пришёл устаревший ответ
  if ($('mods-more')) $('mods-more').remove();

  if (!res.ok) {
    if (append) $('mods-info').textContent = res.error;
    else list.innerHTML = `<p class="muted">${esc(res.error)}</p>`;
    return;
  }
  if (!append) list.innerHTML = '';
  if (!res.items.length && !append) { list.innerHTML = '<p class="muted">Ничего не найдено</p>'; return; }

  res.items.forEach((m) => {
    const card = document.createElement('div');
    card.className = 'mod-card';
    card.innerHTML = `
      <div class="ph">${esc((m.title || '?').trim().charAt(0).toUpperCase())}</div>
      <div class="info">
        <div class="name">${esc(m.title)}</div>
        <div class="desc">${esc(m.description)}</div>
        <div class="meta">${esc(m.author || '')} · ⬇ ${Number(m.downloads || 0).toLocaleString(I18N.locale())}</div>
      </div>
      <button class="btn">${modKind === 'modpack' ? 'Установить' : 'Скачать'}</button>`;
    if (m.icon) loadIcon(m.icon, card.querySelector('.ph'));
    const btn = card.querySelector('button');
    btn.onclick = async () => {
      if (modKind === 'modpack') return installPack(m, btn);
      btn.disabled = true;
      btn.textContent = '...';
      const r = await api.invoke('mods:install', {
        source: modSource,
        id: m.id,
        kind: modKind,
        profileId: currentId,
      });
      btn.textContent = r.ok ? 'Готово' : 'Ошибка';
      if (!r.ok) {
        $('mods-info').textContent = r.error;
        btn.disabled = false;
      } else {
        $('mods-info').textContent =
          `Установлено: ${r.filename}` + (r.extra ? ` (+${r.extra} необходимых зависимостей)` : '');
        loadProfiles();
      }
    };
    list.appendChild(card);
  });

  modOffset += res.items.length;
  if (res.total && modOffset < res.total) {
    const more = document.createElement('button');
    more.id = 'mods-more';
    more.className = 'btn ghost mods-more';
    more.textContent = `Показать ещё (осталось ${(res.total - modOffset).toLocaleString(I18N.locale())})`;
    more.onclick = () => searchMods(true);
    list.appendChild(more);
  }
}

// ---------- Установленные моды ----------
let instSeq = 0;
let instItems = [];

function renderInstalled(res) {
  const box = $('inst-list');
  instItems = res.items;
  const withUpd = instItems.filter((i) => i.update);
  $('inst-updall').classList.toggle('hidden', !withUpd.length);
  $('inst-updall').textContent = `Обновить все (${withUpd.length})`;

  if (!instItems.length) {
    box.innerHTML = '<p class="muted">В папке модов этого профиля пока пусто. Скачай моды во вкладке «Моды».</p>';
    return;
  }
  box.innerHTML = '';
  instItems.forEach((it) => {
    const row = document.createElement('div');
    row.className = 'inst-row' + (it.enabled ? '' : ' off');
    const sub = [it.version ? 'v' + it.version : null, it.file, fmtSize(it.size)].filter(Boolean).join(' · ');
    row.innerHTML = `
      <div class="ph">${esc((it.title || it.file).trim().charAt(0).toUpperCase())}</div>
      <div class="info">
        <div class="name">${esc(it.title || it.file.replace(/\.jar(\.disabled)?$/i, ''))}${it.enabled ? '' : ' <span class="badge">выключен</span>'}</div>
        <div class="meta">${esc(sub)}</div>
      </div>
      ${it.update ? `<button class="btn" data-act="update">Обновить до ${esc(it.update.version)}</button>` : ''}
      <button class="btn ghost" data-act="toggle">${it.enabled ? 'Выключить' : 'Включить'}</button>
      <button class="btn ghost danger" data-act="delete">Удалить</button>`;
    if (it.icon) loadIcon(it.icon, row.querySelector('.ph'));
    row.querySelectorAll('button').forEach((b) => {
      b.onclick = async () => {
        const act = b.dataset.act;
        const args = { profileId: currentId, file: it.file };
        if (act === 'delete' && b.dataset.sure !== '1') {
          b.dataset.sure = '1';
          b.textContent = 'Точно?';
          setTimeout(() => { b.dataset.sure = ''; b.textContent = 'Удалить'; }, 3000);
          return;
        }
        b.disabled = true;
        let r;
        if (act === 'toggle') r = await api.invoke('installed:toggle', args);
        else if (act === 'delete') r = await api.invoke('installed:delete', args);
        else r = await api.invoke('installed:update', { ...args, url: it.update.url, filename: it.update.filename });
        if (!r.ok) {
          $('inst-info').textContent = r.error;
          b.disabled = false;
          return;
        }
        loadProfiles();
        await loadInstalled(true, false); // без быстрого прохода: старый список остаётся на экране
      };
    });
    box.appendChild(row);
  });
}

async function loadInstalled(check = true, fast = true) {
  const p = cur();
  const seq = ++instSeq;
  if (!p) {
    $('inst-info').textContent = '';
    $('inst-updall').classList.add('hidden');
    $('inst-list').innerHTML = '<p class="muted">Сначала создай профиль во вкладке «Профили».</p>';
    return;
  }
  $('inst-info').textContent = `${profileLabel(p)}${check ? ' · проверяю обновления...' : ''}`;
  iconQueue.length = 0;

  // Сначала быстро показываем файлы, затем подтягиваем названия и обновления из Modrinth
  if (fast || !check) {
    const quick = await api.invoke('installed:list', { profileId: p.id, check: false });
    if (seq !== instSeq) return;
    if (!quick.ok) { $('inst-list').innerHTML = `<p class="muted">${esc(quick.error)}</p>`; return; }
    renderInstalled(quick);
    if (!check) { $('inst-info').textContent = profileLabel(p); return; }
  }

  const full = await api.invoke('installed:list', { profileId: p.id, check: true });
  if (seq !== instSeq) return;
  if (!full.ok) return;
  renderInstalled(full);
  const n = full.items.filter((i) => i.update).length;
  $('inst-info').textContent =
    `${profileLabel(p)} · ` +
    (full.checked ? (n ? `доступно обновлений: ${n}` : 'все моды актуальны') : 'нет связи с Modrinth — показаны только файлы');
}

$('inst-refresh').onclick = () => loadInstalled(true);
$('inst-folder').onclick = () => api.invoke('folder:open', 'mods');
$('inst-updall').onclick = async () => {
  const todo = instItems.filter((i) => i.update);
  $('inst-updall').disabled = true;
  let ok = 0;
  for (const it of todo) {
    $('inst-info').textContent = `Обновляю ${ok + 1}/${todo.length}: ${it.title || it.file}`;
    const r = await api.invoke('installed:update', {
      profileId: currentId, file: it.file, url: it.update.url, filename: it.update.filename,
    });
    if (r.ok) ok++;
  }
  $('inst-updall').disabled = false;
  await loadInstalled(true, false);
  $('inst-info').textContent = `Обновлено модов: ${ok} из ${todo.length}`;
};

// ---------- Импорт из других лаунчеров ----------
let impList = [];

function impCountText(c) {
  return [
    `Minecraft ${c.version}`,
    c.loader === 'vanilla' ? 'без модов' : `${NAMES[c.loader] || c.loader}${c.loaderVersion ? ' ' + c.loaderVersion : ''}`,
    `Модов: ${c.modsCount}`,
    `Миров: ${c.worldsCount}`,
  ].join(' · ');
}

function impRender(res, auto) {
  impList = res.candidates;
  const box = $('imp-list');
  box.innerHTML = '';
  if (!impList.length) {
    box.innerHTML = '<p class="muted">Сборок в других лаунчерах не найдено. Поддерживаются Prism Launcher, PolyMC, MultiMC, приложение CurseForge, Modrinth App и официальный лаунчер Minecraft.</p>';
  }
  impList.forEach((c) => {
    const row = document.createElement('label');
    row.className = 'imp-row' + (c.imported ? ' done' : '');
    row.innerHTML = `
      <input type="checkbox" data-id="${esc(c.id)}" ${c.imported ? '' : 'checked'} />
      <div class="info">
        <div class="name">${esc(c.name)} <span class="badge">${esc(c.launcher)}</span>${c.imported ? ' <span class="badge on">уже импортирована</span>' : ''}</div>
        <div class="meta">${esc(impCountText(c))}</div>
        ${c.options && c.options.length > 1 && !c.imported ? `<label class="imp-pick">Версия для импорта:
          <select data-pick="${esc(c.id)}">${c.options.map((o) => `<option value="${esc(o.id)}"${o.id === c.defaultOption ? ' selected' : ''}>${esc(o.version)} · ${esc(o.loader === 'vanilla' ? 'без модов' : (NAMES[o.loader] || o.loader) + (o.loaderVersion ? ' ' + o.loaderVersion : ''))}</option>`).join('')}</select></label>` : ''}
        <div class="imp-state"></div>
      </div>`;
    // переключатель версии не должен ставить/снимать галочку строки
    row.querySelectorAll('select').forEach((sel) => {
      sel.onclick = (e) => e.stopPropagation();
      sel.onchange = () => {
        const o = c.options.find((x) => x.id === sel.value);
        row.querySelector('.meta').textContent = impCountText({ ...c, version: o.version, loader: o.loader, loaderVersion: o.loaderVersion });
        row.querySelector('.name').firstChild.textContent = `Minecraft ${o.version} `;
      };
    });
    box.appendChild(row);
  });
  const sk = res.skipped || [];
  $('imp-skipped').textContent = sk.length
    ? `Не удалось прочитать: ${sk.map((x) => `${x.name} (${x.launcher}: ${x.reason})`).join('; ')}`
    : '';
  $('imp-never').classList.toggle('hidden', !auto);
  $('imp-close').textContent = auto ? 'Позже' : 'Закрыть';
  $('imp-go').disabled = !impList.some((c) => !c.imported);
  $('imp-go').textContent = 'Импортировать';
  $('imp-msg').textContent = '';
  $('imp-modal').classList.remove('hidden');
}

async function openImport(auto) {
  const res = await api.invoke('import:scan', { auto });
  if (!res || !res.ok || !Array.isArray(res.candidates)) { if (!auto && res && res.error) alert(res.error); return; }
  if (auto && (!res.candidates.length || res.asked)) return; // при запуске тихо, если нечего предлагать
  impRender(res, auto);
}

$('pf-import').onclick = () => openImport(false);
$('imp-close').onclick = () => $('imp-modal').classList.add('hidden');
$('imp-never').onclick = async () => {
  await api.invoke('import:dismiss');
  $('imp-modal').classList.add('hidden');
};
$('imp-go').onclick = async () => {
  const ids = [...$('imp-list').querySelectorAll('input[type=checkbox]:checked')].map((x) => x.dataset.id);
  if (!ids.length) { $('imp-msg').textContent = 'Отметь хотя бы одну сборку'; return; }
  $('imp-go').disabled = true;
  $('imp-msg').textContent = 'Копирую...';
  const choices = {};
  $('imp-list').querySelectorAll('select[data-pick]').forEach((s) => { choices[s.dataset.pick] = s.value; });
  const r = await api.invoke('import:run', { ids, withWorlds: $('imp-worlds').checked, choices });
  if (!r.ok) { $('imp-msg').textContent = r.error; $('imp-go').disabled = false; return; }
  let okCount = 0;
  r.results.forEach((x) => {
    const st = $('imp-list').querySelector(`input[data-id="${x.id}"]`);
    const el = st && st.parentElement.querySelector('.imp-state');
    if (x.ok) okCount++;
    if (el) el.textContent = x.ok ? 'Готово: профиль создан' : 'Ошибка: ' + x.error;
    if (st && x.ok) { st.checked = false; st.disabled = true; }
  });
  $('imp-msg').textContent = `Импортировано сборок: ${okCount} из ${r.results.length}. Они появились во вкладке «Профили».`;
  $('imp-go').textContent = 'Импортировать ещё';
  $('imp-go').disabled = !$('imp-list').querySelector('input:not(:disabled)');
  await loadProfiles();
};
api.on('import:progress', ({ text }) => { if (!$('imp-modal').classList.contains('hidden')) $('imp-msg').textContent = text; });

// ---------- Настройки профиля ----------
let peId = null;
let globalRam = 4;

function peRamUi() {
  const def = $('pe-ram-def').checked;
  $('pe-ram').disabled = def;
  $('pe-ram-val').textContent = def ? globalRam : $('pe-ram').value;
}

function openProfileEdit(p) {
  peId = p.id;
  $('pe-title').textContent = `Настройки профиля: ${p.name}`;
  $('pe-name').value = p.name;
  $('pe-ram').max = ramMax;
  $('pe-ram').value = p.ram || globalRam;
  $('pe-ram-def').checked = !p.ram;
  $('pe-ram-global').textContent = globalRam;
  $('pe-jvm').value = p.jvmArgs || '';
  $('pe-w').value = p.width || '';
  $('pe-h').value = p.height || '';
  $('pe-full').checked = !!p.fullscreen;
  $('pe-java').value = p.javaPath || '';
  $('pe-msg').textContent = '';
  peRamUi();
  $('pe-modal').classList.remove('hidden');
}
$('pe-ram').oninput = peRamUi;
$('pe-ram-def').onchange = peRamUi;
$('pe-cancel').onclick = () => $('pe-modal').classList.add('hidden');
$('pe-modal').onclick = (e) => { if (e.target === $('pe-modal')) $('pe-modal').classList.add('hidden'); };
$('pe-save').onclick = async () => {
  const r = await api.invoke('profiles:update', {
    id: peId,
    patch: {
      name: $('pe-name').value,
      ram: $('pe-ram-def').checked ? null : Number($('pe-ram').value),
      jvmArgs: $('pe-jvm').value,
      width: $('pe-w').value,
      height: $('pe-h').value,
      fullscreen: $('pe-full').checked,
      javaPath: $('pe-java').value,
    },
  });
  if (!r.ok) { $('pe-msg').textContent = r.error; return; }
  $('pe-modal').classList.add('hidden');
  await loadProfiles();
};

// ---------- Серверы профиля ----------
let srvPid = null;
let srvSeq = 0;
const pingCache = {};
const srvKey = (s) => `${s.host}:${s.port}`;

function srvStatusHtml(r) {
  if (!r) return '<span class="dot load"></span><span class="muted">проверяю...</span>';
  if (!r.online) return `<span class="dot off"></span><span class="muted">недоступен${r.error ? ' (' + esc(r.error) + ')' : ''}</span>`;
  return `<span class="dot on"></span><span>${r.players.online}/${r.players.max}</span><span class="muted">· ${r.latency} мс${r.version ? ' · ' + esc(r.version) : ''}</span>`;
}

function paintServer(row, s, r) {
  row.querySelector('.srv-status').innerHTML = srvStatusHtml(r);
  row.querySelector('.srv-motd').textContent = r && r.online ? r.motd || '' : '';
  if (r && r.icon) {
    const ph = row.querySelector('.ph');
    if (ph) { const img = document.createElement('img'); img.alt = ''; img.src = r.icon; ph.replaceWith(img); }
  }
}

async function pingAll(items, seq) {
  const queue = [...items];
  const worker = async () => {
    while (queue.length && seq === srvSeq) {
      const { s, row } = queue.shift();
      const r = await api.invoke('servers:ping', { host: s.host, port: s.port });
      pingCache[srvKey(s)] = r;
      if (seq === srvSeq && row.isConnected) paintServer(row, s, r);
    }
  };
  await Promise.all([worker(), worker(), worker(), worker()]);
}

async function renderServers(ping = true) {
  const seq = ++srvSeq;
  const res = await api.invoke('servers:list', { profileId: srvPid });
  if (seq !== srvSeq) return;
  const box = $('srv-list');
  if (!res.ok) { box.innerHTML = `<p class="muted">${esc(res.error)}</p>`; return; }
  const list = [...res.servers].sort((a, b) => Number(b.favorite) - Number(a.favorite) || a.name.localeCompare(b.name));
  box.innerHTML = '';

  if (res.last && !list.some((x) => srvKey(x) === srvKey(res.last))) {
    const hint = document.createElement('div');
    hint.className = 'srv-hint';
    hint.innerHTML = `<span class="grow">Последний сервер: <b>${esc(res.last.host)}${res.last.port !== 25565 ? ':' + res.last.port : ''}</b></span>
      <button class="btn ghost" data-act="join">Зайти</button><button class="btn ghost" data-act="keep">Добавить в список</button>`;
    hint.querySelector('[data-act=join]').onclick = () => joinServer(res.last);
    hint.querySelector('[data-act=keep]').onclick = async () => {
      await api.invoke('servers:add', { profileId: srvPid, name: res.last.host, address: srvKey(res.last) });
      renderServers(false);
    };
    box.appendChild(hint);
  }
  if (!list.length && !box.children.length) {
    box.innerHTML = '<p class="muted">Серверов пока нет. Добавь адрес выше или нажми «Импорт из игры» — подтянутся серверы, которые ты добавил в самой игре.</p>';
    return;
  }

  const toPing = [];
  list.forEach((s) => {
    const row = document.createElement('div');
    row.className = 'srv-row';
    row.innerHTML = `
      <div class="ph">${esc((s.name || '?').trim().charAt(0).toUpperCase())}</div>
      <div class="info">
        <div class="name">${esc(s.name)}${s.favorite ? ' <span class="badge on">избранное</span>' : ''}</div>
        <div class="meta">${esc(s.host)}${s.port !== 25565 ? ':' + s.port : ''}</div>
        <div class="srv-status"></div>
        <div class="srv-motd"></div>
      </div>
      <button class="btn" data-act="join">Зайти</button>
      <button class="btn ghost" data-act="fav">${s.favorite ? 'Убрать из избранного' : 'В избранное'}</button>
      <button class="btn ghost danger" data-act="del">Удалить</button>`;
    paintServer(row, s, pingCache[srvKey(s)]);
    row.querySelectorAll('button').forEach((b) => {
      b.onclick = async () => {
        const act = b.dataset.act;
        if (act === 'join') return joinServer(s);
        if (act === 'fav') {
          await api.invoke('servers:edit', { profileId: srvPid, id: s.id, favorite: !s.favorite });
          return renderServers(false);
        }
        if (b.dataset.sure !== '1') {
          b.dataset.sure = '1';
          b.textContent = 'Точно удалить?';
          setTimeout(() => { b.dataset.sure = ''; b.textContent = 'Удалить'; }, 3000);
          return;
        }
        await api.invoke('servers:remove', { profileId: srvPid, id: s.id });
        renderServers(false);
      };
    });
    box.appendChild(row);
    if (ping || !pingCache[srvKey(s)]) toPing.push({ s, row });
  });
  pingAll(toPing, seq);
}

function joinServer(s) {
  const pid = srvPid;
  closeServers();
  showView('play');
  launch(true, { host: s.host, port: s.port }, pid);
}

function openServers(pid) {
  const p = profiles.find((x) => x.id === pid);
  if (!p) return;
  srvPid = pid;
  $('srv-title').textContent = `Серверы · ${p.name}`;
  $('srv-msg').textContent = '';
  $('srv-name').value = '';
  $('srv-addr').value = '';
  $('srv-modal').classList.remove('hidden');
  renderServers(true);
}
function closeServers() {
  if (!$('srv-modal') || $('srv-modal').classList.contains('hidden')) return;
  $('srv-modal').classList.add('hidden');
  srvSeq++;
  loadProfiles();
}

$('btn-servers').onclick = () => (cur() ? openServers(currentId) : (showView('profiles'), openProfileModal()));
$('srv-close').onclick = closeServers;
$('srv-modal').onclick = (e) => { if (e.target === $('srv-modal')) closeServers(); };
$('srv-refresh').onclick = () => { Object.keys(pingCache).forEach((k) => delete pingCache[k]); renderServers(true); };
$('srv-add').onclick = async () => {
  const r = await api.invoke('servers:add', { profileId: srvPid, name: $('srv-name').value, address: $('srv-addr').value });
  if (!r.ok) { $('srv-msg').textContent = r.error; return; }
  $('srv-msg').textContent = '';
  $('srv-name').value = '';
  $('srv-addr').value = '';
  renderServers(false);
};
$('srv-addr').onkeydown = (e) => { if (e.key === 'Enter') $('srv-add').click(); };
$('srv-import').onclick = async () => {
  const r = await api.invoke('servers:import', { profileId: srvPid });
  $('srv-msg').textContent = r.ok ? `Найдено в игре: ${r.found}, добавлено новых: ${r.added}` : r.error;
  if (r.ok) renderServers(false);
};

// ---------- Оптимизация ----------
const OPT_ICON = { loading: '⏳', ok: '✅', skip: '➖', fail: '❌' };

async function openOpt() {
  const p = cur();
  $('opt-modal').classList.remove('hidden');
  $('opt-msg').textContent = '';
  $('opt-go').textContent = 'Установить всё';
  if (!p) {
    $('opt-sub').textContent = '';
    $('opt-list').innerHTML = '<p class="muted">Сначала создай профиль во вкладке «Профили».</p>';
    $('opt-go').disabled = true;
    return;
  }
  $('opt-sub').textContent = `Профиль «${p.name}» · Minecraft ${p.version} · ${NAMES[p.loader] || p.loader}`;

  const list = await api.invoke('opt:list', p.loader);
  if (!list.length) {
    $('opt-list').innerHTML =
      '<p class="muted">Для Vanilla оптимизация модами недоступна. Создай профиль с Fabric, Forge, NeoForge или Quilt.</p>';
    $('opt-go').disabled = true;
    return;
  }
  $('opt-list').innerHTML = list
    .map(
      (m) => `<div class="opt-row">
        <span class="opt-state" id="opt-${m.slug}">•</span>
        <div><b>${esc(m.name)}</b> <span class="src" id="optsrc-${m.slug}"></span><div class="muted">${esc(m.desc)}</div></div>
      </div>`
    )
    .join('');
  $('opt-go').disabled = false;
}

$('btn-opt').onclick = openOpt;
$('opt-close').onclick = () => $('opt-modal').classList.add('hidden');
$('opt-modal').onclick = (e) => { if (e.target === $('opt-modal')) $('opt-modal').classList.add('hidden'); };

$('opt-go').onclick = async () => {
  $('opt-go').disabled = true;
  $('opt-msg').textContent = 'Скачиваю...';
  const r = await api.invoke('opt:install', { profileId: currentId });
  if (!r.ok) {
    $('opt-msg').textContent = r.error;
  } else {
    $('opt-msg').textContent =
      `Готово: установлено ${r.installed} (Modrinth: ${r.bySource.modrinth}, CurseForge: ${r.bySource.curseforge})` +
      (r.skipped ? `, недоступно для этой версии: ${r.skipped}` : '') +
      (r.failed ? `, ошибок: ${r.failed}` : '') +
      (r.needKey && r.skipped ? '. Чтобы искать и на CurseForge, добавь API-ключ в Настройках.' : '');
    loadProfiles();
  }
  $('opt-go').textContent = 'Повторить';
  $('opt-go').disabled = false;
};

api.on('opt:progress', ({ slug, status, detail, source }) => {
  const el = $('opt-' + slug);
  if (!el) return;
  el.textContent = OPT_ICON[status] || '•';
  el.title = detail || '';
  const src = $('optsrc-' + slug);
  if (src) src.textContent = source ? '· ' + source : '';
});

// ---------- Microsoft ----------
function applyAccountMode() {
  const ms = $('set-account').value === 'microsoft';
  $('ms-block').classList.toggle('hidden', !ms);
  $('row-nick').classList.toggle('hidden', ms);
}
$('set-account').onchange = applyAccountMode;

async function refreshMsStatus() {
  const s = await api.invoke('ms:status');
  $('ms-state').textContent = s.loggedIn ? `Вход выполнен: ${s.name}` : 'Не выполнен вход';
  $('ms-login').classList.toggle('hidden', !!s.loggedIn);
  $('ms-logout').classList.toggle('hidden', !s.loggedIn);
}

$('ms-login').onclick = async () => {
  // Client ID нужен main-процессу — сохраняем перед входом
  await api.invoke('settings:set', { msClientId: $('set-msid').value.trim() });
  $('ms-login').disabled = true;
  $('ms-state').textContent = 'Жду подтверждения входа...';
  const r = await api.invoke('ms:login');
  $('ms-modal').classList.add('hidden');
  $('ms-login').disabled = false;
  if (!r.ok) $('ms-state').textContent = 'Ошибка: ' + r.error;
  else await refreshMsStatus();
};
$('ms-logout').onclick = async () => {
  await api.invoke('ms:logout');
  refreshMsStatus();
};
$('ms-cancel').onclick = () => {
  api.invoke('ms:cancel');
  $('ms-modal').classList.add('hidden');
};
$('ms-copy').onclick = () => {
  try { navigator.clipboard.writeText($('ms-code').textContent); $('ms-copy').textContent = 'Скопировано'; } catch { /* ignore */ }
  setTimeout(() => { $('ms-copy').textContent = 'Копировать код'; }, 1500);
};
api.on('ms:code', ({ code, url }) => {
  $('ms-code').textContent = code;
  $('ms-url').textContent = url;
  $('ms-modal').classList.remove('hidden');
});

// ---------- Обновление лаунчера ----------
let appVersion = '';
function updateText(s) {
  switch (s.state) {
    case 'checking': return 'Проверяю обновления...';
    case 'available': return `Найдена версия ${s.version || ''} — скачиваю...`;
    case 'downloading': return `Скачиваю обновление: ${s.percent || 0}%`;
    case 'ready': return `Обновление ${s.version || ''} готово — перезапусти лаунчер`;
    case 'none': return 'У тебя последняя версия';
    case 'error': return 'Ошибка обновления: ' + (s.message || '');
    default: return '';
  }
}
api.on('update:status', (s) => {
  const t = updateText(s);
  $('upd-state').textContent = t;
  const show = ['available', 'downloading', 'ready'].includes(s.state);
  $('update-toast').classList.toggle('hidden', !show);
  $('update-text').textContent = t;
  $('update-install').classList.toggle('hidden', s.state !== 'ready');
});
$('update-install').onclick = () => api.invoke('update:install');
$('upd-check').onclick = async () => {
  $('upd-state').textContent = 'Проверяю...';
  await api.invoke('settings:set', { updateUrl: $('set-update').value.trim() });
  const r = await api.invoke('update:check');
  if (!r.ok) $('upd-state').textContent = r.error;
};

// ---------- Liquid Glass ----------
function applyGlass(on, strength) {
  const root = document.documentElement;
  root.dataset.glass = on ? 'on' : 'off';
  const s = Math.min(Math.max(Number(strength) || 0, 0), 100);
  root.style.setProperty('--g-blur', `${(6 + s * 0.34).toFixed(1)}px`);
  root.style.setProperty('--g-sat', (1.2 + s * 0.008).toFixed(2));
  root.style.setProperty('--g-tint', (0.06 + s * 0.0014).toFixed(3));
  root.style.setProperty('--g-edge', (0.25 + s * 0.004).toFixed(2));
}
function glassUi() {
  const on = $('set-glass').checked;
  $('glass-row').classList.toggle('hidden', !on);
  $('glass-val').textContent = $('set-glass-strength').value;
  applyGlass(on, $('set-glass-strength').value);
}
$('set-glass').onchange = async () => {
  glassUi();
  await api.invoke('settings:set', { glass: $('set-glass').checked });
};
$('set-glass-strength').oninput = glassUi;
$('set-glass-strength').onchange = () => api.invoke('settings:set', { glassStrength: Number($('set-glass-strength').value) });

// ---------- Свой фон (картинка или видео) ----------
let bgVideo = null;
let gameRunning = false;
const bgSafeUrl = (u) => (typeof u === 'string' && /^file:\/\/\//.test(u) && !/["\\\s]/.test(u) ? u : '');

function bgMessage(text, isErr) {
  const el = $('bg-msg');
  el.textContent = text || '';
  el.classList.toggle('err', !!isErr);
}
// Видео не крутим, пока окно свёрнуто или идёт игра: меньше нагрузки на ПК
function syncBgVideo() {
  if (!bgVideo) return;
  if (gameRunning || document.hidden) bgVideo.pause();
  else bgVideo.play().catch(() => {});
}
function bgGame(running) { gameRunning = running; syncBgVideo(); }
document.addEventListener('visibilitychange', syncBgVideo);

function resetBgLook() {
  if (bgVideo) { bgVideo.remove(); bgVideo = null; }
  document.documentElement.style.removeProperty('--bg-custom');
}
function applyBackground(s) {
  const root = document.documentElement;
  root.style.setProperty('--bg-dim', String((Number(s.bgDim) || 0) / 100));
  $('set-bg-dim').value = Number(s.bgDim) || 0;
  $('bg-dim-val').textContent = Number(s.bgDim) || 0;
  resetBgLook();
  const url = bgSafeUrl(s.bgUrl);
  $('bg-reset').classList.toggle('hidden', !url);
  $('bg-state').textContent = !url ? 'Сейчас: стандартный фон' : `Сейчас: ${s.bgName || (s.bgType === 'video' ? 'видео' : 'картинка')}`;
  if (!url) return;
  if (s.bgType === 'video') {
    const v = document.createElement('video');
    v.className = 'bg-video';
    v.muted = true; v.loop = true; v.autoplay = true; v.playsInline = true; v.disablePictureInPicture = true;
    v.setAttribute('muted', '');
    v.onerror = () => {
      if (bgVideo !== v) return;
      resetBgLook();
      bgMessage('Не удалось воспроизвести видео. Лучше всего подходят MP4 (H.264) и WEBM.', true);
    };
    v.src = url;
    document.body.insertBefore(v, document.querySelector('.bg-overlay'));
    bgVideo = v;
    syncBgVideo();
  } else {
    const img = new Image();
    img.onload = () => root.style.setProperty('--bg-custom', `url("${url}")`);
    img.onerror = () => bgMessage('Не удалось открыть картинку. Попробуй PNG, JPG или WEBP.', true);
    img.src = url;
  }
}
$('bg-choose').onclick = async () => {
  $('bg-choose').disabled = true;
  bgMessage('Копирую файл...');
  const r = await api.invoke('bg:choose');
  $('bg-choose').disabled = false;
  if (r.ok) { bgMessage(''); applyBackground(r.settings); }
  else if (r.canceled) bgMessage('');
  else bgMessage(r.error || 'Не удалось выбрать файл', true);
};
$('bg-reset').onclick = async () => {
  const r = await api.invoke('bg:reset');
  if (r.ok) { bgMessage(''); applyBackground(r.settings); }
};
$('set-bg-dim').oninput = () => {
  const v = Number($('set-bg-dim').value) || 0;
  $('bg-dim-val').textContent = v;
  document.documentElement.style.setProperty('--bg-dim', String(v / 100));
};
$('set-bg-dim').onchange = () => api.invoke('settings:set', { bgDim: Number($('set-bg-dim').value) || 0 });

// ---------- Язык ----------
// Меняем язык и перезагружаем окно: так весь интерфейс сразу перерисовывается на нужном языке
$('set-lang').onchange = async () => {
  const lang = $('set-lang').value === 'en' ? 'en' : 'ru';
  await api.invoke('settings:set', { lang });
  I18N.setLang(lang);
  location.reload();
};

// ---------- Discord Rich Presence ----------
function setDiscordState(s) {
  const el = $('dc-state');
  if (!s) { el.textContent = ''; return; }
  el.textContent = {
    off: 'Выключено',
    'no-id': 'Укажи Application ID',
    connecting: 'Жду запуска Discord...',
    'bad-id': 'Discord не принял Application ID',
  }[s.state] || (s.user ? `Подключено: ${s.user}` : 'Подключено');
}
api.on('discord:status', setDiscordState);
$('set-dc').onchange = async () => {
  $('dc-block').classList.toggle('hidden', !$('set-dc').checked);
  await api.invoke('settings:set', { discordRpc: $('set-dc').checked, discordClientId: $('set-dcid').value.trim() });
};
$('set-dcid').onchange = () => api.invoke('settings:set', { discordClientId: $('set-dcid').value.trim() });

// ---------- Настройки ----------
let ramMax = 16;

function setRamUi(value) {
  const v = Math.min(Math.max(Number(value) || 4, 1), ramMax);
  $('set-ram').value = v;
  $('ram-val').textContent = v;
  document.querySelectorAll('#ram-chips .chip').forEach((c) =>
    c.classList.toggle('active', Number(c.dataset.ram) === v)
  );
}

async function loadSettings() {
  const s = await api.invoke('settings:get');
  ramMax = s.systemRamGb || 16;
  $('set-ram').max = ramMax;
  $('ram-hint').textContent =
    `Всего в системе: ${ramMax} ГБ. Для Vanilla хватит 2–4 ГБ, для модов обычно 4–8 ГБ. ` +
    `Не выделяй больше, чем половину памяти компьютера.`;
  globalRam = s.ram;
  setRamUi(s.ram);
  $('set-nick').value = s.nickname;
  $('set-cf').value = s.curseforgeKey;
  $('set-root').value = s.rootDir;
  $('set-java').value = s.javaPath || '';
  $('set-account').value = s.accountMode || 'offline';
  $('set-msid').value = s.msClientId || '';
  $('set-update').value = s.updateUrl || '';
  appVersion = s.appVersion || '';
  $('app-version').textContent = appVersion || '—';
  $('upd-state').textContent = `Версия лаунчера: ${appVersion || '—'}`;
  $('set-glass').checked = s.glass !== false;
  $('set-glass-strength').value = s.glassStrength ?? 60;
  glassUi();
  applyAccountMode();
  $('set-lang').value = s.lang === 'en' ? 'en' : 'ru';
  applyBackground(s);
  $('set-dc').checked = !!s.discordRpc;
  $('set-dcid').value = s.discordClientId || '';
  $('dc-block').classList.toggle('hidden', !s.discordRpc);
  api.invoke('discord:status').then(setDiscordState);
  return s;
}

$('set-ram').oninput = () => setRamUi($('set-ram').value);
document.querySelectorAll('#ram-chips .chip').forEach((c) => {
  c.onclick = () => setRamUi(c.dataset.ram);
});

$('set-save').onclick = async () => {
  await api.invoke('settings:set', {
    nickname: $('set-nick').value.trim() || 'Player',
    ram: Number($('set-ram').value),
    curseforgeKey: $('set-cf').value.trim(),
    rootDir: $('set-root').value.trim(),
    javaPath: $('set-java').value.trim(),
    accountMode: $('set-account').value,
    msClientId: $('set-msid').value.trim(),
    updateUrl: $('set-update').value.trim(),
  });
  globalRam = Number($('set-ram').value);
  $('set-msg').textContent = 'Сохранено ✓';
  setTimeout(() => ($('set-msg').textContent = ''), 2000);
};

// «Предметы для Minecraft»: папки и переходы к скачиванию
document.querySelectorAll('[data-folder]').forEach((b) => {
  b.onclick = () => api.invoke('folder:open', b.dataset.folder);
});
document.querySelectorAll('[data-goto]').forEach((b) => {
  b.onclick = () => {
    showView('mods');
    setKind(b.dataset.goto);
  };
});

// ---------- Старт ----------
(async function init() {
  const s = await loadSettings();
  // язык в настройках важнее кэша окна: если они разошлись, перезагружаемся на нужном
  const want = s.lang === 'en' ? 'en' : 'ru';
  if (want !== I18N.lang) {
    I18N.setLang(want);
    location.reload();
    return;
  }
  await loadProfiles();
  if (!(await ensureManifest())) {
    $('status').textContent = 'Не удалось загрузить список версий: проверь интернет';
  }
  openImport(true); // при запуске предлагаем перенести сборки из других лаунчеров
})();
