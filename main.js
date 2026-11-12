const { app, BrowserWindow, ipcMain, shell, dialog } = require('electron');
const { pathToFileURL } = require('url');
const path = require('path');
const fs = require('fs');
const os = require('os');
const crypto = require('crypto');
const { spawn } = require('child_process');
const { Client, Authenticator } = require('minecraft-launcher-core');

const { UA, getJSON, getText, download, run, loadersFor } = require('./lib/util');
const modsManager = require('./lib/modsmgr');
const msAuth = require('./lib/msauth');
const modpacks = require('./lib/modpacks');
const updater = require('./lib/updater');
const servers = require('./lib/servers');
const importer = require('./lib/importer');
const discord = require('./lib/discord');

const MANIFEST_URL = 'https://launchermeta.mojang.com/mc/game/version_manifest_v2.json';
let win;
let manifestCache = null;

// ---------- Настройки ----------
const settingsFile = () => path.join(app.getPath('userData'), 'settings.json');
const defaults = {
  nickname: 'Player',
  ram: 4,
  rootDir: path.join(os.homedir(), '.dlauncher'),
  curseforgeKey: '',
  javaPath: '', // пусто = Java скачивается автоматически
  accountMode: 'offline', // offline | microsoft
  msClientId: '',
  updateUrl: '',
  glass: true, // Liquid Glass
  glassStrength: 60,
  lang: 'ru', // ru | en
  bgFile: '', // свой фон: файл в userData/backgrounds (меняется только через bg:*)
  bgType: '', // image | video
  bgName: '', // исходное имя файла — для показа в настройках
  bgDim: 0, // затемнение фона, 0–80 %
  discordRpc: false, // статус в Discord (Rich Presence)
  discordClientId: '', // Application ID с discord.com/developers
  profiles: [],
  currentProfile: null,
};
// Эти поля интерфейс может менять через settings:set (профили — только через profiles:*)
const PUBLIC_KEYS = ['nickname', 'ram', 'rootDir', 'curseforgeKey', 'javaPath', 'accountMode', 'msClientId', 'updateUrl', 'glass', 'glassStrength', 'lang', 'discordRpc', 'discordClientId', 'bgDim'];
let settings = { ...defaults };

function loadSettings() {
  try {
    settings = { ...defaults, ...JSON.parse(fs.readFileSync(settingsFile(), 'utf8')) };
  } catch {
    settings = { ...defaults };
  }
  if (!Array.isArray(settings.profiles)) settings.profiles = [];
  if (!settings.profiles.some((p) => p.id === settings.currentProfile)) {
    settings.currentProfile = settings.profiles[0] ? settings.profiles[0].id : null;
  }
}
function saveSettings() {
  fs.mkdirSync(path.dirname(settingsFile()), { recursive: true });
  fs.writeFileSync(settingsFile(), JSON.stringify(settings, null, 2));
}
const systemRamGb = () => Math.max(2, Math.floor(os.totalmem() / 1024 ** 3));
// ---------- Свой фон ----------
const BG_IMAGE = ['.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp', '.avif'];
const BG_VIDEO = ['.mp4', '.webm', '.m4v', '.ogv', '.mov'];
const BG_LIMIT = { image: 100 * 1024 ** 2, video: 1024 ** 3 };
const bgDir = () => path.join(app.getPath('userData'), 'backgrounds');
const bgPath = () => (/^bg-\d+\.[a-z0-9]+$/.test(settings.bgFile || '') ? path.join(bgDir(), settings.bgFile) : null);

const publicSettings = () => {
  const { profiles, bgFile, ...rest } = settings;
  const bp = bgPath();
  const has = !!(bp && fs.existsSync(bp));
  return {
    ...rest,
    bgUrl: has ? pathToFileURL(bp).href : '',
    bgType: has ? settings.bgType : '',
    systemRamGb: systemRamGb(),
    appVersion: app.getVersion(),
  };
};

function send(channel, payload) {
  if (win && !win.isDestroyed()) win.webContents.send(channel, payload);
}

// ---------- Профили: у каждого своя папка instances/<id> (моды, миры, настройки) ----------
const SUBDIRS = ['mods', 'resourcepacks', 'shaderpacks', 'saves'];
const LOADERS = ['vanilla', 'fabric', 'forge', 'neoforge', 'quilt'];

const findProfile = (id) => settings.profiles.find((p) => p.id === id) || null;
const instanceDir = (id) => path.join(settings.rootDir, 'instances', id);

function ensureInstance(id) {
  const dir = instanceDir(id);
  for (const sub of SUBDIRS) fs.mkdirSync(path.join(dir, sub), { recursive: true });
  return dir;
}

const slug = (s) =>
  String(s || '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 24) || 'profile';

function countMods(id) {
  try {
    return fs.readdirSync(path.join(instanceDir(id), 'mods')).filter((f) => /\.jar$/i.test(f)).length;
  } catch {
    return 0;
  }
}

async function versionTypeOf(version) {
  try {
    const m = await getManifest();
    const v = m.versions.find((x) => x.id === version);
    return v ? v.type : 'release';
  } catch {
    return 'release';
  }
}

async function createProfile(data) {
  const version = String((data && data.version) || '').trim();
  if (!version) throw new Error('Не выбрана версия Minecraft');
  const loader = LOADERS.includes(data.loader) ? data.loader : 'vanilla';
  const name = String(data.name || '').trim().slice(0, 40) || `Minecraft ${version}`;
  const profile = {
    id: `${slug(name)}-${crypto.randomBytes(3).toString('hex')}`,
    name,
    version,
    versionType: data.versionType || (await versionTypeOf(version)),
    loader,
    loaderVersion: loader === 'vanilla' ? '' : String(data.loaderVersion || ''),
    pack: data.pack || null,
    ram: null, // null = общая память из настроек
    jvmArgs: '',
    width: null,
    height: null,
    fullscreen: false,
    javaPath: '',
    servers: [],
    lastServer: null,
    lastPlayed: null,
    createdAt: Date.now(),
  };
  settings.profiles.push(profile);
  settings.currentProfile = profile.id;
  saveSettings();
  ensureInstance(profile.id);
  return profile;
}

const ctx = {
  get settings() { return settings; },
  saveSettings,
  send,
  userData: () => app.getPath('userData'),
  instanceDir,
  findProfile,
  createProfile,
};

// ---------- Окно ----------
function createWindow() {
  win = new BrowserWindow({
    width: 1280,
    height: 720,
    minWidth: 1100,
    minHeight: 620,
    frame: false,
    backgroundColor: '#0b0b14',
    icon: path.join(__dirname, 'icon.png'),
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  win.setMenuBarVisibility(false);
  win.loadFile('index.html');
}

// Открываем во внешнем браузере только страницы входа Microsoft
const openExternal = async (url) => {
  const u = new URL(url);
  if (u.protocol === 'https:' && /(^|\.)(microsoft\.com|microsoftonline\.com|live\.com)$/.test(u.hostname)) {
    await shell.openExternal(url);
  }
};

// Внешние ссылки: только из этого списка, адрес из интерфейса не принимается
const LINKS = { tiktok: 'https://www.tiktok.com/@udinaxui067' };
ipcMain.handle('link:open', async (_e, key) => {
  const url = Object.prototype.hasOwnProperty.call(LINKS, key) ? LINKS[key] : null;
  if (!url) return { ok: false };
  await shell.openExternal(url);
  return { ok: true };
});

const ms = msAuth.register(ipcMain, ctx, { openExternal });
modsManager.register(ipcMain, ctx);
servers.register(ipcMain, ctx);
importer.register(ipcMain, ctx);
modpacks.register(ipcMain, ctx);
const upd = updater.register(ipcMain, ctx, { isPackaged: !!app.isPackaged });
const presence = discord.createPresence({ getSettings: () => settings, onStatus: (s) => send('discord:status', s) });
discord.register(ipcMain, presence);

app.whenReady().then(() => {
  loadSettings();
  fs.mkdirSync(settings.rootDir, { recursive: true });
  createWindow();
  presence.configure();
  setTimeout(() => upd.checkSilently(), 5000); // тихая проверка обновлений
});
app.on('window-all-closed', () => app.quit());
app.on('will-quit', () => presence.stop());

ipcMain.handle('win:minimize', () => win.minimize());
ipcMain.handle('win:close', () => win.close());

// ---------- Настройки ----------
ipcMain.handle('settings:get', () => publicSettings());
ipcMain.handle('settings:set', (_e, patch) => {
  const next = { ...settings };
  for (const k of PUBLIC_KEYS) if (patch && k in patch) next[k] = patch[k];
  next.ram = Math.min(Math.max(Number(next.ram) || 4, 1), systemRamGb());
  next.accountMode = next.accountMode === 'microsoft' ? 'microsoft' : 'offline';
  next.glass = next.glass !== false;
  next.glassStrength = Math.min(Math.max(Number(next.glassStrength), 0), 100);
  if (!Number.isFinite(next.glassStrength)) next.glassStrength = 60;
  next.lang = next.lang === 'en' ? 'en' : 'ru';
  next.bgDim = Math.min(Math.max(Math.round(Number(next.bgDim) || 0), 0), 80);
  next.discordRpc = next.discordRpc === true;
  next.discordClientId = String(next.discordClientId || '').trim().slice(0, 32);
  settings = next;
  saveSettings();
  fs.mkdirSync(settings.rootDir, { recursive: true });
  presence.configure(); // включить/выключить статус или сменить ID и язык
  return publicSettings();
});

// Выбор и сброс фона. Путь выбирает сам пользователь в системном окне, из интерфейса путь не принимается.
let bgBusy = false;
const removeBgFile = () => {
  const old = bgPath();
  if (old) fs.rmSync(old, { force: true });
};
ipcMain.handle('bg:choose', async () => {
  if (bgBusy) return { ok: false, error: 'Файл уже копируется' };
  bgBusy = true;
  try {
    const en = settings.lang === 'en';
    const r = await dialog.showOpenDialog(win, {
      title: en ? 'Choose a background image or video' : 'Выбери картинку или видео для фона',
      properties: ['openFile'],
      filters: [
        { name: en ? 'Images and videos' : 'Картинки и видео', extensions: [...BG_IMAGE, ...BG_VIDEO].map((e) => e.slice(1)) },
        { name: en ? 'Images' : 'Картинки', extensions: BG_IMAGE.map((e) => e.slice(1)) },
        { name: en ? 'Videos' : 'Видео', extensions: BG_VIDEO.map((e) => e.slice(1)) },
      ],
    });
    if (r.canceled || !r.filePaths || !r.filePaths[0]) return { ok: false, canceled: true };
    const src = r.filePaths[0];
    const ext = path.extname(src).toLowerCase();
    const type = BG_IMAGE.includes(ext) ? 'image' : BG_VIDEO.includes(ext) ? 'video' : null;
    if (!type) return { ok: false, error: 'Этот формат не поддерживается. Подходят: PNG, JPG, WEBP, GIF, BMP, AVIF, MP4, WEBM, M4V, OGV, MOV.' };
    const st = fs.statSync(src);
    if (!st.isFile()) return { ok: false, error: 'Это не файл' };
    if (st.size > BG_LIMIT[type]) return { ok: false, error: 'Файл слишком большой: картинки до 100 МБ, видео до 1 ГБ.' };

    fs.mkdirSync(bgDir(), { recursive: true });
    const name = `bg-${Date.now()}${ext}`;
    const dest = path.join(bgDir(), name);
    try {
      await fs.promises.copyFile(src, dest + '.part');
      fs.renameSync(dest + '.part', dest);
    } catch (err) {
      fs.rmSync(dest + '.part', { force: true });
      return { ok: false, error: 'Не удалось скопировать файл: ' + err.message };
    }
    removeBgFile(); // прежний фон больше не нужен
    settings.bgFile = name;
    settings.bgType = type;
    settings.bgName = path.basename(src).slice(0, 80);
    saveSettings();
    return { ok: true, settings: publicSettings() };
  } catch (err) {
    return { ok: false, error: err.message };
  } finally {
    bgBusy = false;
  }
});
ipcMain.handle('bg:reset', () => {
  removeBgFile();
  settings.bgFile = '';
  settings.bgType = '';
  settings.bgName = '';
  saveSettings();
  return { ok: true, settings: publicSettings() };
});

// ---------- Профили ----------
ipcMain.handle('profiles:list', () => ({
  current: settings.currentProfile,
  profiles: settings.profiles.map((p) => ({ ...p, modsCount: countMods(p.id) })),
}));

ipcMain.handle('profiles:create', async (_e, data) => {
  try {
    return { ok: true, profile: await createProfile(data || {}) };
  } catch (err) {
    return { ok: false, error: err.message };
  }
});

ipcMain.handle('profiles:select', (_e, id) => {
  if (!findProfile(id)) return { ok: false, error: 'Профиль не найден' };
  settings.currentProfile = id;
  saveSettings();
  return { ok: true };
});

// Аргументы Java: разбиваем по пробелам (кавычки поддерживаются). Память задаётся отдельно.
function parseJvmArgs(text) {
  const out = [];
  const re = /"([^"]*)"|'([^']*)'|(\S+)/g;
  let m;
  while ((m = re.exec(String(text || '')))) out.push(m[1] ?? m[2] ?? m[3]);
  for (const a of out) {
    if (!a.startsWith('-')) throw new Error(`Аргумент «${a}» должен начинаться с «-»`);
    if (/^-Xm[sx]/i.test(a)) throw new Error('Память задаётся ползунком выше, а не в аргументах (-Xmx/-Xms)');
  }
  return out;
}

const dimension = (v, label) => {
  if (v === null || v === undefined || v === '') return null;
  const n = Math.round(Number(v));
  if (!Number.isFinite(n) || n < 320 || n > 7680) throw new Error(`${label}: число от 320 до 7680`);
  return n;
};

ipcMain.handle('profiles:update', (_e, { id, patch } = {}) => {
  const p = findProfile(id);
  if (!p) return { ok: false, error: 'Профиль не найден' };
  try {
    const q = patch || {};
    const next = {};
    if ('name' in q) {
      next.name = String(q.name).trim().slice(0, 40);
      if (!next.name) throw new Error('Название не может быть пустым');
    }
    if ('ram' in q) {
      if (q.ram === null || q.ram === '') next.ram = null;
      else {
        const n = Number(q.ram);
        if (!Number.isFinite(n)) throw new Error('Память: нужно число');
        next.ram = Math.min(Math.max(n, 1), systemRamGb());
      }
    }
    if ('jvmArgs' in q) {
      parseJvmArgs(q.jvmArgs);
      next.jvmArgs = String(q.jvmArgs || '').trim().slice(0, 600);
    }
    if ('width' in q || 'height' in q) {
      const w = dimension('width' in q ? q.width : p.width, 'Ширина');
      const h = dimension('height' in q ? q.height : p.height, 'Высота');
      if ((w === null) !== (h === null)) throw new Error('Укажи ширину и высоту вместе (или оставь оба поля пустыми)');
      next.width = w;
      next.height = h;
    }
    if ('fullscreen' in q) next.fullscreen = !!q.fullscreen;
    if ('javaPath' in q) next.javaPath = String(q.javaPath || '').trim().slice(0, 260);
    Object.assign(p, next);
    saveSettings();
    return { ok: true, profile: { ...p, modsCount: countMods(p.id) } };
  } catch (err) {
    return { ok: false, error: err.message };
  }
});

ipcMain.handle('profiles:delete', (_e, { id, deleteFiles = true } = {}) => {
  const p = findProfile(id);
  if (!p) return { ok: false, error: 'Профиль не найден' };
  if (launching) return { ok: false, error: 'Нельзя удалять профиль, пока запускается игра' };
  try {
    if (deleteFiles) fs.rmSync(instanceDir(id), { recursive: true, force: true });
    settings.profiles = settings.profiles.filter((x) => x.id !== id);
    if (settings.currentProfile === id) {
      settings.currentProfile = settings.profiles[0] ? settings.profiles[0].id : null;
    }
    saveSettings();
    return { ok: true, current: settings.currentProfile };
  } catch (err) {
    return { ok: false, error: err.message };
  }
});

// ---------- Папки ----------
const FOLDERS = {
  mods: 'mods',
  resourcepacks: 'resourcepacks',
  shaderpacks: 'shaderpacks',
  saves: 'saves',
  screenshots: 'screenshots',
};
ipcMain.handle('folder:open', async (_e, arg) => {
  const which = typeof arg === 'string' ? arg : arg && arg.which;
  const profile = findProfile((arg && arg.profileId) || settings.currentProfile);
  let dir = settings.rootDir;
  if (which !== 'root' && profile) {
    dir = ensureInstance(profile.id);
    if (Object.prototype.hasOwnProperty.call(FOLDERS, which)) dir = path.join(dir, FOLDERS[which]);
  }
  fs.mkdirSync(dir, { recursive: true });
  await shell.openPath(dir);
});

// ---------- Версии Minecraft (релизы, снапшоты, бета, альфа) ----------
async function getManifest() {
  if (!manifestCache) manifestCache = await getJSON(MANIFEST_URL);
  return manifestCache;
}

ipcMain.handle('versions:list', async () => {
  const m = await getManifest();
  return {
    latest: m.latest,
    versions: m.versions.map((v) => ({ id: v.id, type: v.type, releaseTime: v.releaseTime })),
  };
});

// ---------- Загрузчики для выбранной версии ----------
let neoCache = null;
async function neoforgeVersions(mc) {
  const m = /^1\.(\d+)(?:\.(\d+))?$/.exec(mc);
  if (!m) return [];
  const major = Number(m[1]);
  const minor = Number(m[2] || 0);
  if (major < 20 || (major === 20 && minor < 2)) return []; // NeoForge начинается с 1.20.2
  if (!neoCache) {
    const xml = await getText('https://maven.neoforged.net/releases/net/neoforged/neoforge/maven-metadata.xml');
    neoCache = [...xml.matchAll(/<version>([^<]+)<\/version>/g)].map((x) => x[1]);
  }
  const prefix = `${major}.${minor}.`;
  const nums = (v) => v.replace(/-.*/, '').split('.').map(Number);
  const cmp = (a, b) => {
    const x = nums(a);
    const y = nums(b);
    for (let i = 0; i < Math.max(x.length, y.length); i++) {
      if ((y[i] || 0) !== (x[i] || 0)) return (y[i] || 0) - (x[i] || 0);
    }
    return 0;
  };
  const all = neoCache.filter((v) => v.startsWith(prefix)).sort(cmp);
  return [...all.filter((v) => !v.includes('-')), ...all.filter((v) => v.includes('-'))];
}

ipcMain.handle('loaders:list', async (_e, mc) => {
  const result = [{ loader: 'vanilla', versions: ['—'] }];

  const [fabric, quilt, forge, neo] = await Promise.allSettled([
    getJSON(`https://meta.fabricmc.net/v2/versions/loader/${encodeURIComponent(mc)}`),
    getJSON(`https://meta.quiltmc.org/v3/versions/loader/${encodeURIComponent(mc)}`),
    getJSON('https://files.minecraftforge.net/net/minecraftforge/forge/promotions_slim.json'),
    neoforgeVersions(mc),
  ]);

  if (fabric.status === 'fulfilled' && Array.isArray(fabric.value) && fabric.value.length) {
    result.push({ loader: 'fabric', versions: fabric.value.map((x) => x.loader.version) });
  }
  if (quilt.status === 'fulfilled' && Array.isArray(quilt.value) && quilt.value.length) {
    result.push({ loader: 'quilt', versions: quilt.value.map((x) => x.loader.version) });
  }
  if (forge.status === 'fulfilled') {
    const promos = forge.value.promos || {};
    const list = [];
    if (promos[`${mc}-recommended`]) list.push(promos[`${mc}-recommended`]);
    if (promos[`${mc}-latest`] && !list.includes(promos[`${mc}-latest`])) list.push(promos[`${mc}-latest`]);
    if (list.length) result.push({ loader: 'forge', versions: list });
  }
  if (neo.status === 'fulfilled' && neo.value.length) {
    result.push({ loader: 'neoforge', versions: neo.value });
  }
  return result;
});

// ---------- Java: автоматическая загрузка (Eclipse Temurin / Adoptium) ----------
async function requiredJava(version) {
  try {
    const m = await getManifest();
    const entry = m.versions.find((v) => v.id === version);
    if (!entry) return 17;
    const meta = await getJSON(entry.url);
    const major = (meta.javaVersion && meta.javaVersion.majorVersion) || 8;
    if (major <= 8) return 8;
    if (major <= 17) return 17; // 16 у Adoptium уже нет, 17 подходит
    if (major <= 21) return 21;
    return major;
  } catch {
    return 17;
  }
}

function findJavaBin(dir, depth = 0) {
  if (depth > 6 || !fs.existsSync(dir)) return null;
  const exe = process.platform === 'win32' ? 'java.exe' : 'java';
  let entries;
  try {
    entries = fs.readdirSync(dir, { withFileTypes: true });
  } catch {
    return null;
  }
  if (path.basename(dir) === 'bin' && entries.some((e) => e.isFile() && e.name === exe)) {
    return path.join(dir, exe);
  }
  for (const e of entries) {
    if (e.isDirectory()) {
      const found = findJavaBin(path.join(dir, e.name), depth + 1);
      if (found) return found;
    }
  }
  return null;
}

async function extractArchive(archive, dir) {
  try {
    await run('tar', ['-xf', archive, '-C', dir]); // Linux/macOS и Windows 10+ (bsdtar понимает zip)
  } catch (err) {
    if (process.platform !== 'win32') throw err;
    await run('powershell', [
      '-NoProfile', '-Command',
      `Expand-Archive -Force -LiteralPath '${archive}' -DestinationPath '${dir}'`,
    ]);
  }
}

async function ensureJava(major) {
  const dir = path.join(settings.rootDir, 'runtime', `java${major}`);
  const existing = findJavaBin(dir);
  if (existing) return existing;

  const osName = { win32: 'windows', linux: 'linux', darwin: 'mac' }[process.platform];
  const arch = { x64: 'x64', arm64: 'aarch64', ia32: 'x86' }[process.arch];
  if (!osName || !arch) throw new Error('Эта система не поддерживается для автоматической загрузки Java');

  const url = `https://api.adoptium.net/v3/binary/latest/${major}/ga/${osName}/${arch}/jre/hotspot/normal/eclipse`;
  const archive = path.join(settings.rootDir, 'runtime', `java${major}.${osName === 'windows' ? 'zip' : 'tar.gz'}`);

  send('game:status', `Скачивание Java ${major}...`);
  await download(url, archive, (p) =>
    send('game:progress', { task: p, total: 100, label: `Java ${major}` })
  );

  send('game:status', `Распаковка Java ${major}...`);
  fs.rmSync(dir, { recursive: true, force: true });
  fs.mkdirSync(dir, { recursive: true });
  try {
    await extractArchive(archive, dir);
  } catch (err) {
    fs.rmSync(dir, { recursive: true, force: true });
    throw new Error('Не удалось распаковать Java: ' + err.message);
  } finally {
    fs.rmSync(archive, { force: true });
  }

  const bin = findJavaBin(dir);
  if (!bin) {
    fs.rmSync(dir, { recursive: true, force: true });
    throw new Error('Java скачана, но java не найдена в архиве');
  }
  if (process.platform !== 'win32') fs.chmodSync(bin, 0o755);
  return bin;
}

// ---------- NeoForge: ставим установщиком в режиме --installClient ----------
function runInstaller(javaPath, jar, root) {
  return new Promise((resolve, reject) => {
    const p = spawn(javaPath, ['-jar', jar, '--installClient', root], { cwd: root });
    let tail = '';
    const onData = (d) => {
      const t = String(d);
      tail = (tail + t).slice(-2000);
      const line = t.trim().split(/\r?\n/).pop();
      if (line) send('game:status', 'NeoForge: ' + line.slice(0, 80));
    };
    p.stdout.on('data', onData);
    p.stderr.on('data', onData);
    p.on('error', reject);
    p.on('close', (code) =>
      code === 0
        ? resolve()
        : reject(new Error(`Установщик NeoForge завершился с ошибкой (${code}). ${tail.trim().split(/\r?\n/).slice(-3).join(' ')}`))
    );
  });
}

async function ensureNeoForge(loaderVersion, javaPath) {
  const root = settings.rootDir;
  const versionsDir = path.join(root, 'versions');
  const find = () => {
    const exact = `neoforge-${loaderVersion}`;
    const has = (id) => fs.existsSync(path.join(versionsDir, id, `${id}.json`));
    if (has(exact)) return exact;
    try {
      return fs.readdirSync(versionsDir).find((d) => d.startsWith('neoforge-') && d.includes(loaderVersion) && has(d)) || null;
    } catch {
      return null;
    }
  };
  const ready = find();
  if (ready) return ready;

  const jar = path.join(root, 'neoforge', `neoforge-${loaderVersion}-installer.jar`);
  if (!fs.existsSync(jar)) {
    send('game:status', 'Скачивание NeoForge...');
    await download(
      `https://maven.neoforged.net/releases/net/neoforged/neoforge/${loaderVersion}/neoforge-${loaderVersion}-installer.jar`,
      jar
    );
  }
  const lp = path.join(root, 'launcher_profiles.json'); // установщик требует этот файл
  if (!fs.existsSync(lp)) fs.writeFileSync(lp, JSON.stringify({ profiles: {}, version: 3 }));

  send('game:status', 'Установка NeoForge (это займёт несколько минут)...');
  await runInstaller(javaPath, jar, root);
  const id = find();
  if (!id) throw new Error('NeoForge установлен, но версия не найдена в папке versions.');
  return id;
}

// ---------- Быстрый вход на сервер ----------
function supportsQuickPlay(v) {
  let m = /^1\.(\d+)/.exec(v);
  if (m) return Number(m[1]) >= 20;
  m = /^(\d\d)w(\d\d)/.exec(v);
  if (m) return Number(m[1]) > 23 || (Number(m[1]) === 23 && Number(m[2]) >= 14);
  return false;
}

// Игра пишет в лог «Connecting to host, port» — так запоминаем последний сервер профиля
function trackServer(profile, text) {
  const all = [...String(text).matchAll(/Connecting to ([^\s,]+), (\d{2,5})/g)];
  if (!all.length) return;
  const [, host, port] = all[all.length - 1];
  const last = profile.lastServer;
  if (last && last.host === host && String(last.port) === port) return;
  profile.lastServer = { host, port: Number(port), at: Date.now() };
  saveSettings();
  send('server:last', { profileId: profile.id, lastServer: profile.lastServer });
}

// ---------- Запуск игры ----------
let launching = false;

ipcMain.handle('game:launch', async (_e, { profileId, quickJoin, server } = {}) => {
  if (launching) return { ok: false, error: 'Игра уже запускается' };
  const profile = findProfile(profileId || settings.currentProfile);
  if (!profile) return { ok: false, error: 'Сначала создай профиль (вкладка «Профили»).' };
  launching = true;
  presence.setLaunching(profile);
  try {
    const root = settings.rootDir;
    fs.mkdirSync(root, { recursive: true });
    const gameDir = ensureInstance(profile.id);

    // Аккаунт: Microsoft или офлайн
    const authorization =
      settings.accountMode === 'microsoft'
        ? await ms.getLaunchAuth()
        : Authenticator.getAuth(settings.nickname || 'Player');

    const ramMb = Math.round(Number(profile.ram || settings.ram || 4) * 1024);
    const opts = {
      authorization,
      root,
      version: { number: profile.version, type: profile.versionType || 'release' },
      memory: { max: `${ramMb}M`, min: `${Math.min(ramMb, 1024)}M` },
      // у каждого профиля своя папка игры: моды, миры, настройки
      overrides: { gameDirectory: gameDir, cwd: gameDir },
    };
    // свои настройки профиля: аргументы Java и окно
    const jvm = parseJvmArgs(profile.jvmArgs);
    if (jvm.length) opts.customArgs = jvm;
    if (profile.fullscreen) opts.window = { fullscreen: true };
    else if (profile.width && profile.height) opts.window = { width: String(profile.width), height: String(profile.height) };

    // Java: своя из настроек или автоматическая
    let javaPath = (profile.javaPath || settings.javaPath || '').trim();
    if (!javaPath) {
      const major = await requiredJava(profile.version);
      javaPath = await ensureJava(major);
    }
    opts.javaPath = javaPath;

    const { loader, loaderVersion, version } = profile;
    if (loader === 'fabric' || loader === 'quilt') {
      send('game:status', `Подготовка ${loader}...`);
      const base =
        loader === 'fabric'
          ? 'https://meta.fabricmc.net/v2/versions/loader'
          : 'https://meta.quiltmc.org/v3/versions/loader';
      const prof = await getJSON(`${base}/${version}/${loaderVersion}/profile/json`);
      const id = prof.id;
      const file = path.join(root, 'versions', id, `${id}.json`);
      fs.mkdirSync(path.dirname(file), { recursive: true });
      fs.writeFileSync(file, JSON.stringify(prof));
      opts.version.custom = id;
    } else if (loader === 'forge') {
      send('game:status', 'Скачивание Forge...');
      const full = `${version}-${loaderVersion}`;
      const jar = path.join(root, 'forge', `forge-${full}-installer.jar`);
      if (!fs.existsSync(jar)) {
        await download(
          `https://maven.minecraftforge.net/net/minecraftforge/forge/${full}/forge-${full}-installer.jar`,
          jar
        );
      }
      opts.forge = jar;
    } else if (loader === 'neoforge') {
      opts.version.custom = await ensureNeoForge(loaderVersion, javaPath);
    }

    // Быстрый вход: на выбранный сервер из списка или на последний
    const target = quickJoin ? (server ? servers.checkServer(server.host, server.port) : profile.lastServer) : null;
    if (quickJoin && !target) throw new Error('Неверный адрес сервера');
    if (target) {
      const { host, port } = target;
      opts.customLaunchArgs = supportsQuickPlay(version)
        ? ['--quickPlayMultiplayer', `${host}:${port}`]
        : ['--server', host, '--port', String(port)];
    }

    profile.lastPlayed = Date.now();
    saveSettings();

    const launcher = new Client();
    launcher.on('progress', (p) =>
      send('game:progress', { task: p.task, total: p.total, type: p.type })
    );
    launcher.on('debug', (m) => send('game:log', String(m)));
    launcher.on('data', (m) => {
      send('game:log', String(m));
      trackServer(profile, m);
    });
    launcher.on('close', (code) => {
      launching = false;
      presence.setIdle();
      send('game:closed', code);
    });

    send('game:status', 'Загрузка файлов игры...');
    const proc = await launcher.launch(opts);
    if (!proc) {
      launching = false;
      presence.setIdle();
      return { ok: false, error: 'Не удалось запустить игру. Проверь путь к Java в настройках.' };
    }
    presence.setPlaying(profile);
    send('game:status', 'Игра запущена');
    return { ok: true };
  } catch (err) {
    launching = false;
    presence.setIdle();
    return { ok: false, error: err.message };
  }
});

// ---------- Моды / ресурспаки / шейдеры / сборки: Modrinth + CurseForge ----------
const CF_LOADER = { forge: 1, fabric: 4, quilt: 5, neoforge: 6 };
const CF_CLASS = { mod: 6, resourcepack: 12, shader: 6552, modpack: 4471 };
const KIND_DIR = { mod: 'mods', resourcepack: 'resourcepacks', shader: 'shaderpacks' };
const CF_BASE = 'https://api.curseforge.com/v1';
const cfHeaders = () => ({ 'x-api-key': settings.curseforgeKey, Accept: 'application/json' });
const enc = (x) => encodeURIComponent(JSON.stringify(x));

// Скачивает проект Modrinth + его обязательные зависимости (например, Fabric API)
async function installModrinth(idOrSlug, mc, loaders, dir, seen = new Set()) {
  if (seen.has(idOrSlug)) return [];
  seen.add(idOrSlug);

  let url = `https://api.modrinth.com/v2/project/${encodeURIComponent(idOrSlug)}/version?game_versions=${enc([mc])}`;
  if (loaders && loaders.length) url += `&loaders=${enc(loaders)}`;
  const versions = await getJSON(url);
  if (!versions.length) {
    const err = new Error(`Нет версии для ${mc}`);
    err.code = 'NO_VERSION';
    throw err;
  }
  const v = versions.find((x) => x.version_type === 'release') || versions[0];
  const file = v.files.find((f) => f.primary) || v.files[0];
  const dest = path.join(dir, file.filename);
  if (!fs.existsSync(dest)) await download(file.url, dest);

  const done = [file.filename];
  for (const d of v.dependencies || []) {
    if (d.dependency_type === 'required' && d.project_id) {
      try {
        done.push(...(await installModrinth(d.project_id, mc, loaders, dir, seen)));
      } catch {
        /* зависимость не нашлась — пропускаем */
      }
    }
  }
  return done;
}

// Скачивает файл CurseForge + обязательные зависимости
async function installCurseForge(modId, mc, loader, dir, seen = new Set()) {
  if (seen.has(modId)) return [];
  seen.add(modId);

  let q = `gameVersion=${encodeURIComponent(mc)}&pageSize=10`;
  const lt = CF_LOADER[loader === 'quilt' ? 'fabric' : loader];
  if (lt) q += `&modLoaderType=${lt}`;
  const res = await getJSON(`${CF_BASE}/mods/${modId}/files?${q}`, cfHeaders());
  if (!res.data || !res.data.length) {
    const err = new Error(`Нет файла для ${mc}`);
    err.code = 'NO_VERSION';
    throw err;
  }
  const f = res.data.find((x) => x.releaseType === 1) || res.data[0];
  const dest = path.join(dir, f.fileName);
  if (!fs.existsSync(dest)) {
    const dl = f.downloadUrl || `https://www.curseforge.com/api/v1/mods/${modId}/files/${f.id}/download`;
    await download(dl, dest);
  }
  const done = [f.fileName];
  for (const d of f.dependencies || []) {
    if (d.relationType === 3) {
      try {
        done.push(...(await installCurseForge(d.modId, mc, loader, dir, seen)));
      } catch {
        /* зависимость не нашлась — пропускаем */
      }
    }
  }
  return done;
}

// Ищет мод на CurseForge по названию (только точное совпадение, чтобы не поставить чужое)
async function cfFindMod(name, slugName, mc, loader) {
  const lt = CF_LOADER[loader === 'quilt' ? 'fabric' : loader];
  let url =
    `${CF_BASE}/mods/search?gameId=432&classId=6&pageSize=10&sortField=2&sortOrder=desc` +
    `&searchFilter=${encodeURIComponent(name)}&gameVersion=${encodeURIComponent(mc)}`;
  if (lt) url += `&modLoaderType=${lt}`;
  const data = await getJSON(url, cfHeaders());
  const norm = (s) => String(s || '').toLowerCase().replace(/[^a-z0-9]/g, '');
  return (data.data || []).find((m) => norm(m.name) === norm(name) || norm(m.slug) === norm(slugName)) || null;
}

// ---------- Иконки: грузим сами и кэшируем на диске ----------
const ICON_HOSTS = [/(^|\.)modrinth\.com$/, /(^|\.)forgecdn\.net$/, /(^|\.)curseforge\.com$/];
const iconCacheDir = () => path.join(app.getPath('userData'), 'icon-cache');

async function fetchIconBytes(url) {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), 8000);
  try {
    const res = await fetch(url, { headers: { 'User-Agent': UA }, signal: ctl.signal, redirect: 'follow' });
    if (!res.ok) throw new Error(String(res.status));
    const type = res.headers.get('content-type') || 'image/png';
    if (!type.startsWith('image/')) throw new Error('не картинка');
    const buf = Buffer.from(await res.arrayBuffer());
    if (buf.length > 2 * 1024 * 1024) throw new Error('слишком большая');
    return { type, buf };
  } finally {
    clearTimeout(timer);
  }
}

ipcMain.handle('icon:get', async (_e, url) => {
  try {
    const u = new URL(url);
    if (u.protocol !== 'https:' || !ICON_HOSTS.some((re) => re.test(u.hostname))) return null;

    const key = crypto.createHash('sha1').update(url).digest('hex');
    const file = path.join(iconCacheDir(), key);
    if (fs.existsSync(file + '.json') && fs.existsSync(file)) {
      const meta = JSON.parse(fs.readFileSync(file + '.json', 'utf8'));
      return `data:${meta.type};base64,${fs.readFileSync(file).toString('base64')}`;
    }

    // 1) напрямую, 2) через публичный прокси картинок wsrv.nl (если CDN недоступен)
    const routes = [url, `https://wsrv.nl/?url=${encodeURIComponent(url)}&w=128&h=128&fit=cover`];
    for (const route of routes) {
      try {
        const { type, buf } = await fetchIconBytes(route);
        fs.mkdirSync(iconCacheDir(), { recursive: true });
        fs.writeFileSync(file, buf);
        fs.writeFileSync(file + '.json', JSON.stringify({ type }));
        return `data:${type};base64,${buf.toString('base64')}`;
      } catch {
        /* пробуем следующий путь */
      }
    }
    return null;
  } catch {
    return null;
  }
});

ipcMain.handle('mods:search', async (_e, { source, query, mc, loader, kind = 'mod', offset = 0 }) => {
  try {
    if (source === 'modrinth') {
      const facets = [[`project_type:${kind}`]];
      if (mc) facets.push([`versions:${mc}`]);
      if (kind === 'mod' && loader && loader !== 'vanilla') facets.push([`categories:${loader}`]);
      const url =
        `https://api.modrinth.com/v2/search?limit=40&offset=${Number(offset) || 0}&index=${query ? 'relevance' : 'downloads'}` +
        `&query=${encodeURIComponent(query || '')}&facets=${encodeURIComponent(JSON.stringify(facets))}`;
      const data = await getJSON(url);
      return {
        ok: true,
        total: data.total_hits,
        items: data.hits.map((h) => ({
          id: h.project_id,
          title: h.title,
          description: h.description,
          icon: h.icon_url,
          downloads: h.downloads,
          author: h.author,
        })),
      };
    }

    if (!settings.curseforgeKey) {
      return { ok: false, error: 'Для CurseForge нужен API-ключ: вставь его в Настройках (console.curseforge.com).' };
    }
    let url =
      `${CF_BASE}/mods/search?gameId=432&classId=${CF_CLASS[kind] || 6}&pageSize=40&index=${Number(offset) || 0}` +
      `&sortField=${query ? 2 : 6}&sortOrder=desc&searchFilter=${encodeURIComponent(query || '')}`;
    if (mc) url += `&gameVersion=${encodeURIComponent(mc)}`;
    if (kind === 'mod' && CF_LOADER[loader]) url += `&modLoaderType=${CF_LOADER[loader]}`;
    const data = await getJSON(url, cfHeaders());
    return {
      ok: true,
      total: data.pagination && data.pagination.totalCount,
      items: data.data.map((m) => ({
        id: m.id,
        title: m.name,
        description: m.summary,
        icon: m.logo && m.logo.thumbnailUrl,
        downloads: m.downloadCount,
        author: m.authors && m.authors[0] && m.authors[0].name,
      })),
    };
  } catch (err) {
    return { ok: false, error: err.message };
  }
});

ipcMain.handle('mods:install', async (_e, { source, id, kind = 'mod', profileId }) => {
  try {
    const profile = findProfile(profileId || settings.currentProfile);
    if (!profile) return { ok: false, error: 'Сначала создай профиль (вкладка «Профили»).' };
    const { version: mc, loader } = profile;
    if (kind === 'mod' && loader === 'vanilla') {
      return { ok: false, error: 'В профиле выбран Vanilla — моды ставятся только на Fabric, Forge, NeoForge или Quilt. Создай профиль с загрузчиком.' };
    }
    const dir = path.join(ensureInstance(profile.id), KIND_DIR[kind] || 'mods');

    if (source === 'modrinth') {
      const files = await installModrinth(id, mc, kind === 'mod' ? loadersFor(loader) : null, dir);
      return { ok: true, filename: files[0], extra: files.length - 1 };
    }

    if (!settings.curseforgeKey) {
      return { ok: false, error: 'Для CurseForge нужен API-ключ: вставь его в Настройках (console.curseforge.com).' };
    }
    const files = await installCurseForge(id, mc, kind === 'mod' ? loader : null, dir);
    return { ok: true, filename: files[0], extra: files.length - 1 };
  } catch (err) {
    return { ok: false, error: err.message };
  }
});

// ---------- Оптимизация: набор модов (Modrinth, затем CurseForge) ----------
// [slug на Modrinth, название, описание]
const OPT_FABRIC = [
  ['sodium', 'Sodium', 'Новый движок отрисовки — главный буст FPS'],
  ['lithium', 'Lithium', 'Оптимизация игровой логики и сервера'],
  ['ferrite-core', 'FerriteCore', 'Меньше потребление памяти'],
  ['entityculling', 'Entity Culling', 'Не рисует мобов, которых не видно'],
  ['immediatelyfast', 'ImmediatelyFast', 'Быстрее интерфейс и текст'],
  ['modernfix', 'ModernFix', 'Быстрый запуск и меньше памяти'],
  ['krypton', 'Krypton', 'Оптимизация сети'],
  ['dynamic-fps', 'Dynamic FPS', 'Снижает нагрузку, когда окно не в фокусе'],
  ['sodium-extra', 'Sodium Extra', 'Доп. настройки Sodium: облака, анимации, частицы'],
  ['moreculling', 'More Culling', 'Ещё больше отсечения невидимых объектов'],
  ['scalablelux', 'ScalableLux', 'Быстрое освещение мира'],
  ['noisium', 'Noisium', 'Быстрее генерация новых территорий'],
  ['memoryleakfix', 'Memory Leak Fix', 'Исправляет утечки памяти'],
];
const OPT_FORGE = [
  ['embeddium', 'Embeddium', 'Движок отрисовки (аналог Sodium) — буст FPS'],
  ['ferrite-core', 'FerriteCore', 'Меньше потребление памяти'],
  ['modernfix', 'ModernFix', 'Быстрый запуск и меньше памяти'],
  ['entityculling', 'Entity Culling', 'Не рисует мобов, которых не видно'],
  ['immediatelyfast', 'ImmediatelyFast', 'Быстрее интерфейс и текст'],
  ['dynamic-fps', 'Dynamic FPS', 'Снижает нагрузку, когда окно не в фокусе'],
  ['moreculling', 'More Culling', 'Ещё больше отсечения невидимых объектов'],
  ['memoryleakfix', 'Memory Leak Fix', 'Исправляет утечки памяти'],
];
const optList = (loader) =>
  loader === 'forge' || loader === 'neoforge' ? OPT_FORGE : loader === 'fabric' || loader === 'quilt' ? OPT_FABRIC : [];

ipcMain.handle('opt:list', (_e, loader) =>
  optList(loader).map(([slugName, name, desc]) => ({ slug: slugName, name, desc }))
);

ipcMain.handle('opt:install', async (_e, { profileId } = {}) => {
  const profile = findProfile(profileId || settings.currentProfile);
  if (!profile) return { ok: false, error: 'Сначала создай профиль (вкладка «Профили»).' };
  const { version: mc, loader } = profile;
  const list = optList(loader);
  if (!list.length) return { ok: false, error: 'Для Vanilla оптимизация модами недоступна — создай профиль с Fabric, Forge, NeoForge или Quilt.' };

  const dir = path.join(ensureInstance(profile.id), 'mods');
  const seenMr = new Set();
  const seenCf = new Set();
  const stats = { installed: 0, skipped: 0, failed: 0, needKey: 0, bySource: { modrinth: 0, curseforge: 0 } };

  for (const [slugName, name] of list) {
    send('opt:progress', { slug: slugName, status: 'loading' });
    let source = null;
    let file = null;
    let mrErr = null;
    let cfErr = null;

    // 1) Modrinth
    try {
      const files = await installModrinth(slugName, mc, loadersFor(loader), dir, seenMr);
      source = 'Modrinth';
      file = files[0];
    } catch (err) {
      mrErr = err;
    }

    // 2) CurseForge (если на Modrinth не нашлось и есть API-ключ)
    if (!source && settings.curseforgeKey) {
      try {
        const m = await cfFindMod(name, slugName, mc, loader);
        if (!m) {
          const e = new Error('не найден на CurseForge');
          e.code = 'NO_VERSION';
          throw e;
        }
        const files = await installCurseForge(m.id, mc, loader, dir, seenCf);
        source = 'CurseForge';
        file = files[0];
      } catch (err) {
        cfErr = err;
      }
    }

    if (source) {
      stats.installed++;
      stats.bySource[source === 'Modrinth' ? 'modrinth' : 'curseforge']++;
      send('opt:progress', { slug: slugName, status: 'ok', detail: file, source });
      continue;
    }

    if (!settings.curseforgeKey) stats.needKey++;
    const real = [mrErr, cfErr].find((e) => e && e.code !== 'NO_VERSION');
    if (real) {
      stats.failed++;
      send('opt:progress', { slug: slugName, status: 'fail', detail: real.message });
    } else {
      stats.skipped++;
      send('opt:progress', { slug: slugName, status: 'skip', detail: `Нет версии для ${mc}` });
    }
  }
  return { ok: true, ...stats };
});
