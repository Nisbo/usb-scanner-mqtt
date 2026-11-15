'use strict';
const {t, language: uiLanguage} = window.scannerI18n;
let token = '', state = null, busy = false, savedWeb = null, disableConfirmed = false, detectedSettings = null, calibrationLanguages = {};
const layoutLabels = {us: 'Englisch (US)', de: 'Deutsch', gb: 'Englisch (britisch)', fr: 'Französisch (AZERTY)', es: 'Spanisch'};
const $ = id => document.getElementById(id);
function setText(id, value) {
  // Keep existing text nodes (and the user's selection) across unchanged polls.
  const node = $(id);
  if (node.textContent !== value) node.textContent = value;
}
let authenticated = false, authEnabled = false, autoLogout = false, lastActivity = 0;
let dark = false;
try { dark = (localStorage.getItem('scanner-theme') || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')) === 'dark'; } catch (_) {}
function applyTheme() {
  document.documentElement.dataset.theme = dark ? 'dark' : 'light';
  const label = dark ? t('Hellmodus einschalten') : t('Dunkelmodus einschalten');
  $('theme-toggle').textContent = dark ? '☀' : '☾';
  $('theme-toggle').title = label; $('theme-toggle').setAttribute('aria-label', label);
  $('theme-toggle').setAttribute('aria-pressed', String(dark));
}
$('theme-toggle').onclick = () => { dark = !dark; applyTheme(); try { localStorage.setItem('scanner-theme', dark ? 'dark' : 'light'); } catch (_) {} };
applyTheme();
function showLogin() {
  scanSignature = '';
  $('access-status').hidden = true;
  authenticated = false; state = null; detectedSettings = null;
  $('app-main').hidden = true; $('login-panel').hidden = false; $('logout').hidden = true;
  $('settings').reset(); $('auth-settings').reset(); $('scan-list').replaceChildren();
  for (const id of ['raw', 'scan-text', 'exact-comparison', 'scan-diagnostics']) setText(id, '');
}
const tabs = [...document.querySelectorAll('[role="tab"]')];
function selectTab(name, focus = false) {
  if (state?.setup_pending) name = 'setup';
  if (name === 'calibration') name = 'test';
  if (!tabs.some(tab => tab.dataset.tab === name)) name = 'status';
  for (const tab of tabs) {
    const selected = tab.dataset.tab === name;
    tab.setAttribute('aria-selected', String(selected)); tab.tabIndex = selected ? 0 : -1;
    $(tab.getAttribute('aria-controls')).hidden = !selected;
    if (selected && focus) tab.focus();
  }
  history.replaceState(null, '', '#' + name);
}
for (const [index, tab] of tabs.entries()) {
  tab.onclick = () => selectTab(tab.dataset.tab);
  tab.onkeydown = event => {
    let next;
    if (event.key === 'ArrowRight') next = (index + 1) % tabs.length;
    if (event.key === 'ArrowLeft') next = (index + tabs.length - 1) % tabs.length;
    if (event.key === 'Home') next = 0;
    if (event.key === 'End') next = tabs.length - 1;
    if (next !== undefined) { event.preventDefault(); selectTab(tabs[next].dataset.tab, true); }
  };
}
selectTab(location.hash.slice(1));
window.addEventListener('hashchange', () => selectTab(location.hash.slice(1)));
async function api(path, body) {
  const response = await fetch(path, body === undefined ? {cache: 'no-store'} : {
    method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRF-Token': token}, body: JSON.stringify(body)
  });
  const data = await response.json();
  if (response.status === 401 && path !== '/api/auth/login') showLogin();
  if (!response.ok) throw new Error(t(data.error || t('Anfrage fehlgeschlagen')));
  return data;
}
function confirmAccess(title, text) {
  return new Promise(resolve => {
    const dialog = $('access-dialog');
    $('access-title').textContent = title; $('access-description').textContent = text;
    dialog.returnValue = 'cancel';
    $('access-cancel').onclick = () => dialog.close('cancel');
    $('access-confirm').onclick = () => dialog.close('confirm');
    dialog.onclose = () => resolve(dialog.returnValue === 'confirm');
    dialog.showModal(); $('access-cancel').focus();
  });
}
$('web-enabled').onchange = async event => {
  if (event.target.checked) { disableConfirmed = false; return; }
  disableConfirmed = await confirmAccess(t('Weboberfläche ausschalten?'),
    t('Nach dem Speichern ist diese Oberfläche nicht mehr erreichbar. Einschalten kannst du sie nur per Shell mit: myscanner set gui true. Jetzt lediglich die Auswahl ändern?'));
  if (!disableConfirmed) event.target.checked = true;
};
const keyRows = [
 [[41,'`','^'],[2,'1','1'],[3,'2','2'],[4,'3','3'],[5,'4','4'],[6,'5','5'],[7,'6','6'],[8,'7','7'],[9,'8','8'],[10,'9','9'],[11,'0','0'],[12,'-','ß'],[13,'=','´'],[14,'⌫','⌫']],
 [[15,'Tab','Tab'],[16,'Q','Q'],[17,'W','W'],[18,'E','E'],[19,'R','R'],[20,'T','T'],[21,'Y','Z'],[22,'U','U'],[23,'I','I'],[24,'O','O'],[25,'P','P'],[26,'[','Ü'],[27,']','+'],[43,'\\','#']],
 [[58,'Caps','Caps'],[30,'A','A'],[31,'S','S'],[32,'D','D'],[33,'F','F'],[34,'G','G'],[35,'H','H'],[36,'J','J'],[37,'K','K'],[38,'L','L'],[39,';','Ö'],[40,"'",'Ä'],[28,'Enter','Enter']],
 [[42,'Shift','Shift'],[86,'< >','< >'],[44,'Z','Y'],[45,'X','X'],[46,'C','C'],[47,'V','V'],[48,'B','B'],[49,'N','N'],[50,'M','M'],[51,',',','],[52,'.','.'],[53,'/','-'],[54,'Shift','Shift']],
 [[29,'Ctrl',t('Strg')],[56,'Alt','Alt'],[57,t('Leertaste'),t('Leertaste')],[100,t('Alt rechts'),'AltGr'],[97,'Ctrl',t('Strg')]],
 [[69,'Num','Num'],[71,'7','7'],[72,'8','8'],[73,'9','9'],[75,'4','4'],[76,'5','5'],[77,'6','6'],[79,'1','1'],[80,'2','2'],[81,'3','3'],[82,'0','0'],[83,'.',','],[96,'KP Enter','KP Enter'],[98,'/','/'],[55,'*','*'],[74,'-','-'],[78,'+','+']]
];
let keyboardSignature = '';
function keyboard(events) {
  const pressed = new Set(events.filter(event => event[1] === 1).map(event => event[0]));
  const layout = $('test-layout').value;
  const signature = layout + ':' + [...pressed].sort((a,b) => a-b).join(',');
  if (signature === keyboardSignature) return;
  keyboardSignature = signature; $('keyboard').replaceChildren();
  const known = new Set();
  for (const [rowIndex, row] of keyRows.entries()) {
    const node = document.createElement('div'); node.className = 'key-row';
    if (rowIndex === 5) node.classList.add('keypad');
    for (const [code, us, de] of row) {
      known.add(code);
      const key = document.createElement('span');
      key.className = 'key' + (pressed.has(code) ? ' recognized' : '') + (code === 57 ? ' space' : '');
      key.textContent = t(state?.keyboard_labels?.[layout]?.[code] || (layout === 'de' ? de : us));
      key.title = t`Linux-Code ${code}${pressed.has(code) ? t(' – erkannt') : ''}`;
      key.setAttribute('aria-label', t`${key.textContent}, Linux-Code ${code}${pressed.has(code) ? t(', erkannt') : ''}`);
      node.append(key);
    }
    $('keyboard').append(node);
  }
  const other = [...pressed].filter(code => !known.has(code));
  $('other-keys').textContent = other.length ? t('Weitere erkannte Codes:') + ' ' + other.join(', ') : t('Hervorgehobene Tasten wurden im Test erkannt; die Anzeige zeigt keine aktuell gedrückt gehaltenen Tasten.');
}
function comparison() {
  const result = state?.test, layout = $('test-layout').value;
  const text = result?.layouts[layout];
  setText('scan-text', result ? t`${text === null ? t('Mit diesem Layout nicht decodierbar') : text}\nZeichen: ${text === null ? 0 : [...text].length} · Abschluss: ${{28:'Enter',96:t('Nummernblock-Enter'),15:'Tab','packed-13':t('CR im Alt-Bytepaar'),'packed-10':t('LF im Alt-Bytepaar'),'packed-9':t('Tab im Alt-Bytepaar')}[result.terminator] || result.terminator}` : t('Noch kein Testscan.'));
  const diagnostics = result?.diagnostics;
  const lines = [];
  const error = diagnostics?.first_error?.[layout];
  if (error) {
    lines.push(t`Erste nicht unterstützte Eingabe: Linux-Code ${error.keycode}, Modifier: ${error.modifiers.length ? error.modifiers.join(', ') : t('keine')}.`);
    if (error.prefix) lines.push(t`Decodierter Anfang vor diesem Fehler (kein gültiger Gesamtscan): ${JSON.stringify(error.prefix)}`);
  }
  for (const [index, sequence] of (diagnostics?.alt_sequences || []).entries()) {
    lines.push(t`Alt-Sequenz ${index + 1}: linke Alt-Taste + Nummernblock-Ziffern ${JSON.stringify(sequence.digits)}; ${sequence.complete ? t('Alt losgelassen') : t('Alt nicht losgelassen')}.`);
    if (sequence.other_keys.length) lines.push(t`Weitere Tastencodes innerhalb der Alt-Sequenz: ${sequence.other_keys.join(', ')}.`);
  }
  if (diagnostics?.alt_sequences?.length) lines.push(result.output_profile === 'alt-pair-latin1' ? t('Aktives Profil: Alt-Zahl als zwei ISO-8859-1-Bytes. Die Kalibrierung prüft diese Interpretation anhand des Testtexts.') : t('Alt-Zahlencodes werden im Standardprofil nicht in Zeichen umgewandelt. Die Ziffernfolge allein legt keine Zeichenkodierung fest; ein anderes Tastaturlayout ändert diese Eingabeart nicht.'));
  if (result && text === null && !error && !lines.length) lines.push(t('Kein gültiger Text erfasst, beispielsweise nur ein Abschlusszeichen. Daraus lässt sich die Ursache nicht eindeutig bestimmen.'));
  setText('scan-diagnostics', lines.join('\n'));
  $('scan-diagnostics').hidden = !lines.length;
  const expected = typeof result?.expected === 'string' ? result.expected : $('expected').value;
  const staleLanguage = result?.language && result.language !== $('calibration-language').value;
  const detected = staleLanguage ? [] : (result?.comparison?.matches || []);
  detectedSettings = detected.length === 1 ? detected[0] : null;
  $('apply-detected').disabled = !detectedSettings || busy;
  setText('auto-calibration', !result ? t('Nach dem Scan werden passende Einstellungen vorgeschlagen.') : staleLanguage ? t('Die Sprache wurde geändert. Starte einen neuen Test für diese Sprache; das vorige Ergebnis wird nicht übernommen.') : !expected ? t('Für die Erkennung wird ein bekannter Testtext benötigt. Starte die Kalibrierung.') : detectedSettings ?
    t`Test erfolgreich: Alle ${[...expected].length} Zeichen stimmen genau überein. Du kannst die passenden Empfangseinstellungen jetzt übernehmen.` : detected.length > 1 ?
    t('Dieser Test ist nicht eindeutig. Mehrere Einstellungen passen. Starte die Kalibrierung mit dem vollständigen Testtext einschließlich Y/Z und Umlauten; es wird nichts automatisch gespeichert.') :
    t('Keine unterstützte Kombination passt vollständig. Öffne die weiteren Optionen und vergleiche die QR-Kodierungen oder die Rohdaten. Es wurde nichts verändert.'));
  const difference = result?.comparison?.difference;
  const displayChar = char => char === '' ? t('Textende') : `${JSON.stringify(char)} (U+${char.codePointAt(0).toString(16).toUpperCase().padStart(4, '0')})`;
  setText('exact-comparison', result && !staleLanguage && expected ? detectedSettings ?
    t`Erwartet: ${expected}\nEmpfangen: ${detectedSettings.text}` : difference ?
    t`Erste Abweichung beim ähnlichsten Ergebnis an Zeichen ${difference.position}:\nErwartet: ${displayChar(difference.expected)}\nEmpfangen: ${displayChar(difference.received)}\nDieses Ergebnis wird nicht übernommen.` : t`Erwartet: ${expected}` : '');
  $('exact-comparison').hidden = !result || !!staleLanguage || !expected;
  const matches = result && expected ? Object.keys(result.layouts).filter(key => result.layouts[key] === expected) : [];
  setText('calibration', !result ? t('Nach dem Scan erscheint hier der Vergleich.') : !expected ? t('Kein Solltext angegeben. Du kannst den Scan mit allen unterstützten Layouts ansehen.') :
    matches.length > 1 ? t('Mehrere Layouts stimmen exakt mit dem Solltext überein. Für eine eindeutige Auswahl Y/Z und Sonderzeichen verwenden.') :
    matches.length === 1 ? t`Exakte Übereinstimmung mit ${t(layoutLabels[matches[0]])}. ${text === expected ? t('Das gewählte Layout passt.') : t('Wechsle die Interpretation zum passenden Layout.')}` :
    t('Keines der unterstützten Layouts stimmt exakt überein. Prüfe den Solltext, die Scannerprogrammierung und mögliche nicht unterstützte Zeichen.'));
  $('apply-layout').disabled = !result || busy;
  setText('apply-layout', t`Layout ${t(layoutLabels[layout])} speichern`);
  const events = result ? result.events : state?.test_events || [];
  setText('raw', events.length ? JSON.stringify(events) : '');
  $('copy-raw').disabled = !events.length;
  keyboard(events);
}
async function poll() {
  if (!authenticated) return;
  try {
    const latest = await api('/api/state');
    if (!authenticated) return;
    state = latest;
    $('setup-notice').hidden = !state.setup_pending;
    for (const tab of tabs) tab.disabled = !!state.setup_pending && tab.dataset.tab !== 'setup';
    if (state.setup_pending) selectTab('setup');
    $('access-status').hidden = state.auth_enabled;
    $('logout').hidden = !state.auth_enabled;
    $('preview-note').hidden = !state.preview;
    setText('header-version', `Version ${state.version}`);
    setText('status', t`Version ${state.version} · Scanner ${state.scanner_connected ? t('verbunden') : t('nicht verbunden')} · MQTT ${state.mqtt_connected ? t('verbunden') : t('getrennt')} · Wartend: ${state.queued} · Letzter Scan: ${state.last_scan || '—'}`);
    setText('mode', state.capture_active ? t('Lokale Aufnahme läuft – Übertragung von Scans vorübergehend pausiert') : state.sending ? t('Scans werden an MQTT gesendet') : t('Übertragung ausgeschaltet – neue Scans werden verworfen'));
    $('mode').className = state.sending ? '' : 'paused';
    setText('send-toggle', state.send_enabled ? t('Übertragung ausschalten') : t('Übertragung einschalten'));
    $('send-toggle').disabled = busy || state.setup_pending || state.capture_active;
    for (const id of ['qr-start','calibrate-start']) $(id).disabled = busy || state.setup_pending || state.capture_active || (id === 'calibrate-start' && !Object.keys(calibrationLanguages).length);
    $('qr-generate').disabled = state.capture_active;
    $('qr-encoding').disabled = state.capture_active;
    $('calibration-language').disabled = state.capture_active || !Object.keys(calibrationLanguages).length;
    $('expected').readOnly = state.capture_active;
    $('test-stop').disabled = busy || (!state.test_active && !state.test);
    setText('test-state', state.test_active ? t`Warte auf einen Scan … noch ${state.test_remaining} Sekunden. Nur die Übertragung von Scans ist pausiert.` : state.test ? t('Scan empfangen. Test beendet; vorheriger Übertragungszustand wiederhergestellt.') : t('Bereit. Ein Test startet die Übertragungspause automatisch.'));
    comparison();
    renderScans();
  } catch (error) { $('status').textContent = t('Dienst nicht erreichbar. Adresse, Port und Dienststatus prüfen.'); }
}
async function action(fn) {
  if (busy) return;
  busy = true; $('message').textContent = '';
  try { await fn(); } catch (error) { $('message').textContent = error.message; }
  finally { busy = false; await poll(); }
}
async function save(patch, calibration = null) {
  if (calibration) await api('/api/calibration/apply', calibration);
  else await api('/api/config', patch);
  $('message').textContent = t('Gespeichert. Dienst wird neu geladen. Bei geänderter Web-Adresse die neue Adresse aufrufen.');
  const web = patch.web;
  if (web && (!web.enabled || (web.port && web.port !== Number(location.port || 80)) ||
      (web.host && !['0.0.0.0', location.hostname].includes(web.host)))) return;
  const previous = token;
  for (let attempt = 0; attempt < 50; attempt++) {
    await new Promise(resolve => setTimeout(resolve, 300));
    try {
      const access = await api('/api/auth');
      if (access.token !== previous) { disableConfirmed = false; await init(); return; }
    } catch (_) { /* Listener is closed briefly while reloading. */ }
  }
  throw new Error(t('Gespeichert; Wiederverbindung noch nicht möglich. Dienststatus prüfen und Seite neu laden.'));
}
async function devices() {
  const choice = $('device-choice');
  choice.replaceChildren();
  const paths = await api('/api/devices');
  const placeholder = document.createElement('option'); placeholder.value = '';
  placeholder.textContent = paths.length ? t('Gerät auswählen oder Pfad unten eingeben') : t('Keine Geräte erkannt – Pfad unten frei eingeben');
  choice.append(placeholder);
  for (const path of paths) { const option = document.createElement('option'); option.value = path; option.textContent = path; choice.append(option); }
  choice.value = paths.includes($('scanner-device').value) ? $('scanner-device').value : '';
}
$('device-choice').onchange = event => { if (event.target.value) $('scanner-device').value = event.target.value; };
$('scanner-device').oninput = () => { $('device-choice').value = ''; };
$('refresh-devices').onclick = () => action(devices);
$('generate-topic').onclick = () => {
  const id = $('scanner-id').value;
  if (!/^[a-zA-Z0-9_-]{1,64}$/.test(id)) { $('message').textContent = t('Für das Topic zuerst eine gültige Scannerkennung eintragen.'); return; }
  $('scanner-topic').value = `usb-scanner-mqtt/${id}/scan`;
};
function generateQR() {
  $('qr').hidden = true; $('qr-note').textContent = '';
  const text = $('expected').value;
  if (!text) throw new Error(t('Für einen QR-Code zuerst einen Testtext eingeben.'));
  const encoding = $('qr-encoding').value;
  let bytes;
  if (encoding === 'latin1') {
    bytes = [...text].map(char => char.codePointAt(0));
    if (bytes.some(code => code > 255)) throw new Error(t('Dieser Text enthält Zeichen außerhalb von ISO-8859-1 (z. B. € oder Emojis). Bitte UTF-8 wählen oder den Text anpassen.'));
  } else {
    bytes = [...new TextEncoder().encode(text)];
  }
  let qr;
  try {
    const segments = encoding === 'utf8' ? [qrcodegen.QrSegment.makeEci(26)] : [];
    segments.push(qrcodegen.QrSegment.makeBytes(bytes));
    qr = qrcodegen.QrCode.encodeSegments(segments, qrcodegen.QrCode.Ecc.MEDIUM);
  } catch (_) { throw new Error(t('Der Text ist zu groß für einen QR-Code. Bitte einen kürzeren Testtext verwenden.')); }
  const canvas = $('qr'), scale = 6, border = 4;
  canvas.width = canvas.height = (qr.size + border * 2) * scale;
  const context = canvas.getContext('2d');
  context.fillStyle = '#fff'; context.fillRect(0, 0, canvas.width, canvas.height);
  context.fillStyle = '#000';
  for (let y = 0; y < qr.size; y++) for (let x = 0; x < qr.size; x++) {
    if (qr.getModule(x,y)) context.fillRect((x+border)*scale, (y+border)*scale, scale, scale);
  }
  canvas.hidden = false;
  $('qr-note').textContent = t`QR-Code bereit: ${$('qr-encoding').selectedOptions[0].textContent}, ${bytes.length} Bytes. Ausschließlich lokal im Browser erzeugt.`;
}
$('calibrate-start').onclick = () => action(async () => {
  const language = $('calibration-language').value;
  const test = calibrationLanguages[language];
  if (!test) throw new Error(t('Bitte eine unterstützte Testsprache wählen.'));
  $('expected').value = test.text;
  $('qr-encoding').value = test.encoding;
  invalidateQR(); generateQR();
  setText('qr-note', t('Testcode bereit. Scanne ihn jetzt mit deinem Scanner.'));
  await api('/api/test/start', {language});
});
$('apply-detected').onclick = () => action(async () => {
  if (!detectedSettings) return;
  const {layout, output_profile} = detectedSettings;
  await save({scanner: {layout, output_profile}}, {test_id: state.test.test_id, language: state.test.language});
  $('scanner-layout').value = layout;
  $('scanner-output_profile').value = output_profile;
  $('test-layout').value = layout;
});
$('qr-generate').onclick = () => action(async () => generateQR());
$('qr-start').onclick = () => action(async () => { generateQR(); await api('/api/test/start', {expected: $('expected').value}); });
$('test-stop').onclick = () => action(() => api('/api/test/stop', {}));
function invalidateQR() { $('qr').hidden = true; $('qr-note').textContent = ''; comparison(); }
$('expected').oninput = invalidateQR;
$('qr-encoding').onchange = invalidateQR;
$('test-layout').onchange = comparison;
function selectLanguage() {
  const test = calibrationLanguages[$('calibration-language').value];
  if (!test) return;
  setText('language-coverage', t(test.coverage));
  setText('language-sample', test.text);
  $('qr').hidden = true; setText('qr-note', '');
  comparison();
}
$('calibration-language').onchange = () => {
  try { sessionStorage.setItem('scanner-test-language', $('calibration-language').value); } catch (_) {}
  selectLanguage();
};
$('send-toggle').onclick = () => action(() => save({scan_send_enabled: !state.send_enabled}));
$('apply-layout').onclick = () => action(async () => {
  const layout = $('test-layout').value;
  await save({scanner: {layout}}); $('scanner-layout').value = layout;
});
$('settings').onsubmit = event => {
  event.preventDefault();
  action(async () => {
    const patch = {};
    for (const field of event.target.elements) {
      if (!field.name) continue;
      const [section,key] = field.name.split('.');
      (patch[section] ||= {})[key] = field.type === 'checkbox' ? field.checked : field.type === 'number' ? Number(field.value) : field.value;
    }
    if (savedWeb?.enabled && !patch.web.enabled && !disableConfirmed && !await confirmAccess(t('Weboberfläche ausschalten?'), t('Nach dem Speichern ist die Oberfläche nicht mehr erreichbar. Zum Einschalten ist die Shell mit myscanner set gui true nötig.'))) return;
    if (savedWeb && patch.web.enabled && (savedWeb.host !== patch.web.host || savedWeb.port !== patch.web.port)) {
      const localOnly = ['127.0.0.1','localhost','::1'].includes(patch.web.host);
      const text = localOnly ? t('Die neue Adresse erlaubt nur Zugriff direkt auf dem Linux-System. Von einem anderen Rechner verlierst du den Webzugriff. Rückgängig per Shell: myscanner set web-host 0.0.0.0.') : t('Die Web-Adresse oder der Port wird geändert. Die aktuelle Verbindung kann abbrechen. Öffne anschließend die neue Adresse. Bei einer falschen Bind-Adresse ist die Korrektur per Shell nötig.');
      if (!await confirmAccess(localOnly ? t('Zugriff auf das Linux-System beschränken?') : t('Web-Adresse ändern?'), text)) return;
    }
    await save(patch); $('mqtt-password').value = '';
  });
};
async function init() {
  try {
    const access = await api('/api/auth'); token = access.token; authEnabled = access.enabled; autoLogout = access.auto_logout;
    $('access-status').hidden = authEnabled;
    $('auth-auto-logout').checked = autoLogout;
    lastActivity = 0;
    setText('header-version', `Version ${access.version}`);
    if (!access.authenticated) { showLogin(); return; }
    authenticated = true; $('login-panel').hidden = true; $('app-main').hidden = false;
    $('logout').hidden = !authEnabled;
    $('auth-enabled').checked = authEnabled;
    updateAuthFields();
    const data = await api('/api/config'); token = data.token; savedWeb = data.config.web;
    if (data.config.setup_pending) { state = {...state, setup_pending: true}; selectTab('setup'); }
    for (const field of document.forms.settings.elements) {
      if (!field.name) continue;
      const [section,key] = field.name.split('.');
      if (field.type === 'checkbox') field.checked = data.config[section][key]; else field.value = data.config[section][key];
    }
    $('test-layout').value = data.config.scanner.layout;
    setText('profile-state', t('Gespeichertes Ausgabeprofil:') + ' ' + (data.config.scanner.output_profile === 'alt-pair-latin1' ? t('Alt-Zahl als zwei ISO-8859-1-Bytes (experimentell)') : t('Standard – direkte Tasteneingabe')) + t('. Ändern unter Einrichtung; danach speichern.'));
    calibrationLanguages = await api('/api/calibration');
    $('calibration-language').replaceChildren();
    for (const [id, language] of Object.entries(calibrationLanguages)) {
      const option = document.createElement('option'); option.value = id; option.textContent = t(language.label);
      $('calibration-language').append(option);
    }
    let testLanguage = uiLanguage;
    try { const saved = sessionStorage.getItem('scanner-test-language'); if (Object.hasOwn(calibrationLanguages, saved)) testLanguage = saved; } catch (_) {}
    $('calibration-language').value = testLanguage; selectLanguage();
    await devices(); await poll();
  } catch (error) { $('message').textContent = error.message; }
}
function updateAuthFields() {
  $('auth-current-field').hidden = !authEnabled;
  $('auth-current').required = authEnabled;
  const enabled = $('auth-enabled').checked;
  for (const field of document.querySelectorAll('.auth-new-field')) field.hidden = !enabled;
  $('auth-new').required = enabled && !authEnabled; $('auth-confirm').required = enabled && !authEnabled;
  $('auth-auto-logout').disabled = !enabled;
}
$('auth-enabled').onchange = updateAuthFields;
$('login-form').onsubmit = async event => {
  event.preventDefault(); const button = event.target.querySelector('button'); button.disabled = true;
  try { await api('/api/auth/login', {password: $('login-password').value}); $('login-password').value = ''; setText('login-message', ''); await init(); }
  catch (error) { setText('login-message', error.message); }
  finally { button.disabled = false; }
};
$('logout').onclick = async () => { try { await api('/api/auth/logout', {}); location.reload(); } catch (_) { showLogin(); } };
$('auth-settings').onsubmit = async event => {
  event.preventDefault();
  if ($('auth-enabled').checked && $('auth-new').value !== $('auth-confirm').value) { setText('auth-message', t('Die neuen Passwörter stimmen nicht überein.')); return; }
  const button = event.target.querySelector('button'); button.disabled = true;
  try {
    await api('/api/auth/settings', {enabled: $('auth-enabled').checked, auto_logout: $('auth-auto-logout').checked, current_password: $('auth-current').value, new_password: $('auth-new').value});
    event.target.reset(); await init();
    setText(authEnabled ? 'login-message' : 'auth-message', authEnabled ? t('Passwortschutz gespeichert. Bitte anmelden.') : t('Passwortschutz ausgeschaltet und Passwort entfernt.'));
  } catch (error) { setText('auth-message', error.message); }
  finally { button.disabled = false; }
};
for (const name of ['pointerdown', 'keydown', 'wheel']) document.addEventListener(name, () => {
  if (!authenticated || !authEnabled || !autoLogout || Date.now() - lastActivity < 60000) return;
  lastActivity = Date.now(); api('/api/auth/activity', {}).catch(() => {});
}, {passive:true});
init(); setInterval(poll, 500);

async function copyText(text, node, statusId) {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
    } else {
      const buffer = document.createElement('textarea');
      buffer.className = 'copy-buffer'; buffer.value = text; buffer.readOnly = true;
      document.body.append(buffer);
      const previousFocus = document.activeElement;
      try { buffer.select(); if (!document.execCommand('copy')) throw new Error('Copy unavailable'); }
      finally { buffer.remove(); previousFocus?.focus(); }
    }
    setText(statusId, t('Kopiert.'));
  } catch (_) {
    const range = document.createRange(); range.selectNodeContents(node);
    const selection = window.getSelection(); selection.removeAllRanges(); selection.addRange(range);
    setText(statusId, t('Automatisches Kopieren nicht möglich. Text ist markiert – mit Strg+C bzw. ⌘C kopieren.'));
  }
}
$('copy-raw').onclick = () => {
  const text = $('raw').textContent;
  if (text) return copyText(text, $('raw'), 'copy-state');
};
let scanSignature = '';
function renderScans() {
  $('scan-start').disabled = busy || state.setup_pending || state.capture_active;
  $('scan-stop').disabled = busy || !state.scan_active;
  const items = state.scan_items || [];
  $('scan-clear').disabled = busy || !items.length;
  setText('scan-session-state', state.scan_active ?
    t`Scannen aktiv – Scans an MQTT pausiert. Noch ${state.scan_remaining} Sekunden; jeder abgeschlossene Scan startet den Timer neu.` :
    state.capture_active ? t('Die Kalibrierung läuft. Beende sie dort, bevor du hier scannst.') :
    state.capture_mode !== 'scan' ? t('Bereit zum lokalen Scannen. Beim Start wird die Übertragung von Scans automatisch pausiert.') : state.send_enabled ? t('Lokales Scannen beendet. Normale Übertragung an MQTT ist wieder freigegeben.') :
    t('Lokales Scannen beendet. Die zuvor dauerhaft ausgeschaltete Übertragung bleibt aus.'));
  $('scan-empty').hidden = items.length > 0;
  const signature = items.map(item => item.id).join(',');
  if (signature === scanSignature) return;
  scanSignature = signature;
  const keep = new Set(items.map(item => item.id));
  for (const card of [...$('scan-list').children]) if (!keep.has(card.dataset.scanId)) card.remove();
  for (const item of items) {
    if ([...$('scan-list').children].some(card => card.dataset.scanId === item.id)) continue;
    const card = document.createElement('article'); card.className = 'scan-entry'; card.dataset.scanId = item.id;
    const meta = document.createElement('p'); meta.className = 'scan-meta';
    meta.textContent = t`${item.timestamp} · ${item.length} Zeichen`;
    const text = document.createElement('pre');
    text.textContent = item.text === null ? t('Mit den gespeicherten Einstellungen nicht decodierbar. Prüfe die Kalibrierung.') : item.text;
    const copy = document.createElement('button'); copy.type = 'button'; copy.className = 'secondary'; copy.textContent = t('Kopieren'); copy.disabled = item.text === null;
    copy.onclick = () => copyText(item.text, text, 'scan-copy-state');
    card.append(meta, text, copy); $('scan-list').prepend(card);
  }
}
$('scan-start').onclick = () => action(() => api('/api/scan/start', {}));
$('scan-stop').onclick = () => action(() => api('/api/scan/stop', {}));
$('scan-clear').onclick = () => action(async () => { await api('/api/scan/clear', {}); setText('scan-copy-state', ''); });
