'use strict';
let token = '', state = null, busy = false, savedWeb = null, disableConfirmed = false;
const $ = id => document.getElementById(id);
const tabs = [...document.querySelectorAll('[role="tab"]')];
function selectTab(name, focus = false) {
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
  if (!response.ok) throw new Error(data.error || 'Anfrage fehlgeschlagen');
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
  disableConfirmed = await confirmAccess('Weboberfläche ausschalten?',
    'Nach dem Speichern ist diese Oberfläche nicht mehr erreichbar. Einschalten kannst du sie nur per Shell mit: myscanner set gui true. Jetzt lediglich die Auswahl ändern?');
  if (!disableConfirmed) event.target.checked = true;
};
const keyRows = [
 [[41,'`','^'],[2,'1','1'],[3,'2','2'],[4,'3','3'],[5,'4','4'],[6,'5','5'],[7,'6','6'],[8,'7','7'],[9,'8','8'],[10,'9','9'],[11,'0','0'],[12,'-','ß'],[13,'=','´'],[14,'⌫','⌫']],
 [[15,'Tab','Tab'],[16,'Q','Q'],[17,'W','W'],[18,'E','E'],[19,'R','R'],[20,'T','T'],[21,'Y','Z'],[22,'U','U'],[23,'I','I'],[24,'O','O'],[25,'P','P'],[26,'[','Ü'],[27,']','+'],[43,'\\','#']],
 [[58,'Caps','Caps'],[30,'A','A'],[31,'S','S'],[32,'D','D'],[33,'F','F'],[34,'G','G'],[35,'H','H'],[36,'J','J'],[37,'K','K'],[38,'L','L'],[39,';','Ö'],[40,"'",'Ä'],[28,'Enter','Enter']],
 [[42,'Shift','Shift'],[86,'< >','< >'],[44,'Z','Y'],[45,'X','X'],[46,'C','C'],[47,'V','V'],[48,'B','B'],[49,'N','N'],[50,'M','M'],[51,',',','],[52,'.','.'],[53,'/','-'],[54,'Shift','Shift']],
 [[29,'Ctrl','Strg'],[56,'Alt','Alt'],[57,'Leertaste','Leertaste'],[100,'Alt rechts','AltGr'],[97,'Ctrl','Strg']],
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
      key.textContent = layout === 'de' ? de : us;
      key.title = `Linux-Code ${code}${pressed.has(code) ? ' – erkannt' : ''}`;
      key.setAttribute('aria-label', `${key.textContent}, Linux-Code ${code}${pressed.has(code) ? ', erkannt' : ''}`);
      node.append(key);
    }
    $('keyboard').append(node);
  }
  const other = [...pressed].filter(code => !known.has(code));
  $('other-keys').textContent = other.length ? 'Weitere erkannte Codes: ' + other.join(', ') : 'Hervorgehobene Tasten wurden im Test erkannt; die Anzeige zeigt keine aktuell gedrückt gehaltenen Tasten.';
}
function comparison() {
  const result = state?.test, layout = $('test-layout').value;
  const text = result?.layouts[layout];
  $('scan-text').textContent = result ? `${text === null ? 'Mit diesem Layout nicht decodierbar' : text}\nZeichen: ${text === null ? 0 : [...text].length} · Abschluss: ${{28:'Enter',96:'Nummernblock-Enter',15:'Tab'}[result.terminator] || result.terminator}` : 'Noch kein Testscan.';
  const expected = $('expected').value;
  const matches = result && expected ? Object.keys(result.layouts).filter(key => result.layouts[key] === expected) : [];
  $('calibration').textContent = !result ? 'Nach dem Scan erscheint hier der Vergleich.' : !expected ? 'Kein Solltext angegeben. Du kannst den Scan mit beiden Layouts ansehen.' :
    matches.length === 2 ? 'Beide Layouts stimmen exakt mit dem Solltext überein. Für eine eindeutige Auswahl Y/Z und Sonderzeichen verwenden.' :
    matches.length === 1 ? `Exakte Übereinstimmung mit ${matches[0] === 'de' ? 'Deutsch' : 'US'}. ${text === expected ? 'Das gewählte Layout passt.' : 'Wechsle die Interpretation zum passenden Layout.'}` :
    'Keines der beiden Layouts stimmt exakt überein. Prüfe den Solltext, die Scannerprogrammierung und mögliche nicht unterstützte Zeichen.';
  $('apply-layout').disabled = !result || busy;
  $('apply-layout').textContent = `${layout === 'de' ? 'Deutsches Layout' : 'US-Layout'} speichern`;
  const events = result ? result.events : state?.test_events || [];
  $('raw').textContent = events.length ? JSON.stringify(events) : '';
  keyboard(events);
}
async function poll() {
  try {
    state = await api('/api/state');
    $('preview-note').hidden = !state.preview;
    $('status').textContent = `Version ${state.version} · Scanner ${state.scanner_connected ? 'verbunden' : 'nicht verbunden'} · MQTT ${state.mqtt_connected ? 'verbunden' : 'getrennt'} · Wartend: ${state.queued} · Letzter Scan: ${state.last_scan || '—'}`;
    $('mode').textContent = state.test_active ? 'Test läuft – Übertragung von Scans vorübergehend pausiert' : state.sending ? 'Scans werden an MQTT gesendet' : 'Übertragung ausgeschaltet – neue Scans werden verworfen';
    $('mode').className = state.sending ? '' : 'paused';
    $('send-toggle').textContent = state.send_enabled ? 'Übertragung ausschalten' : 'Übertragung einschalten';
    $('send-toggle').disabled = busy || state.test_active;
    for (const id of ['test-start','qr-start']) $(id).disabled = busy || state.test_active;
    $('qr-generate').disabled = state.test_active;
    $('expected').readOnly = state.test_active;
    $('test-stop').disabled = busy || (!state.test_active && !state.test);
    $('test-state').textContent = state.test_active ? `Warte auf einen Scan … noch ${state.test_remaining} Sekunden. Nur die Übertragung von Scans ist pausiert.` : state.test ? 'Scan empfangen. Test beendet; vorheriger Übertragungszustand wiederhergestellt.' : 'Bereit. Ein Test startet die Übertragungspause automatisch.';
    comparison();
  } catch (error) { $('status').textContent = 'Dienst nicht erreichbar. Adresse, Port und Dienststatus prüfen.'; }
}
async function action(fn) {
  if (busy) return;
  busy = true; $('message').textContent = '';
  try { await fn(); } catch (error) { $('message').textContent = error.message; }
  finally { busy = false; await poll(); }
}
async function save(patch) {
  await api('/api/config', patch);
  $('message').textContent = 'Gespeichert. Dienst wird neu geladen. Bei geänderter Web-Adresse die neue Adresse aufrufen.';
  const web = patch.web;
  if (web && (!web.enabled || (web.port && web.port !== Number(location.port || 80)) ||
      (web.host && !['0.0.0.0', location.hostname].includes(web.host)))) return;
  const previous = token;
  for (let attempt = 0; attempt < 50; attempt++) {
    await new Promise(resolve => setTimeout(resolve, 300));
    try {
      const data = await api('/api/config');
      if (data.token !== previous) { token = data.token; savedWeb = data.config.web; disableConfirmed = false; return; }
    } catch (_) { /* Listener is closed briefly while reloading. */ }
  }
  throw new Error('Gespeichert; Wiederverbindung noch nicht möglich. Dienststatus prüfen und Seite neu laden.');
}
async function devices() {
  const choice = $('device-choice');
  choice.replaceChildren();
  const paths = await api('/api/devices');
  const placeholder = document.createElement('option'); placeholder.value = '';
  placeholder.textContent = paths.length ? 'Gerät auswählen oder Pfad unten eingeben' : 'Keine Geräte erkannt – Pfad unten frei eingeben';
  choice.append(placeholder);
  for (const path of paths) { const option = document.createElement('option'); option.value = path; option.textContent = path; choice.append(option); }
  choice.value = paths.includes($('scanner-device').value) ? $('scanner-device').value : '';
}
$('device-choice').onchange = event => { if (event.target.value) $('scanner-device').value = event.target.value; };
$('scanner-device').oninput = () => { $('device-choice').value = ''; };
$('refresh-devices').onclick = () => action(devices);
$('generate-topic').onclick = () => {
  const id = $('scanner-id').value;
  if (!/^[a-zA-Z0-9_-]{1,64}$/.test(id)) { $('message').textContent = 'Für das Topic zuerst eine gültige Scannerkennung eintragen.'; return; }
  $('scanner-topic').value = `usb-scanner-mqtt/${id}/scan`;
};
function generateQR() {
  const text = $('expected').value;
  if (!text) throw new Error('Für einen QR-Code zuerst einen Testtext eingeben.');
  let qr;
  try {
    const segments = [qrcodegen.QrSegment.makeEci(26), qrcodegen.QrSegment.makeBytes([...new TextEncoder().encode(text)])];
    qr = qrcodegen.QrCode.encodeSegments(segments, qrcodegen.QrCode.Ecc.MEDIUM);
  } catch (_) { throw new Error('Der Text ist zu groß für einen QR-Code. Bitte einen kürzeren Testtext verwenden.'); }
  const canvas = $('qr'), scale = 6, border = 4;
  canvas.width = canvas.height = (qr.size + border * 2) * scale;
  const context = canvas.getContext('2d');
  context.fillStyle = '#fff'; context.fillRect(0, 0, canvas.width, canvas.height);
  context.fillStyle = '#000';
  for (let y = 0; y < qr.size; y++) for (let x = 0; x < qr.size; x++) {
    if (qr.getModule(x,y)) context.fillRect((x+border)*scale, (y+border)*scale, scale, scale);
  }
  canvas.hidden = false;
  $('qr-note').textContent = 'QR-Code bereit. Er wird ausschließlich lokal im Browser erzeugt.';
}
$('qr-generate').onclick = () => action(async () => generateQR());
$('qr-start').onclick = () => action(async () => { generateQR(); await api('/api/test/start', {}); });
$('test-start').onclick = () => action(() => api('/api/test/start', {}));
$('test-stop').onclick = () => action(() => api('/api/test/stop', {}));
$('expected').oninput = () => { $('qr').hidden = true; $('qr-note').textContent = ''; comparison(); };
$('test-layout').onchange = comparison;
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
    if (savedWeb?.enabled && !patch.web.enabled && !disableConfirmed && !await confirmAccess('Weboberfläche ausschalten?', 'Nach dem Speichern ist die Oberfläche nicht mehr erreichbar. Zum Einschalten ist die Shell mit myscanner set gui true nötig.')) return;
    if (savedWeb && patch.web.enabled && (savedWeb.host !== patch.web.host || savedWeb.port !== patch.web.port)) {
      const localOnly = ['127.0.0.1','localhost','::1'].includes(patch.web.host);
      const text = localOnly ? 'Die neue Adresse erlaubt nur Zugriff direkt auf dem Linux-System. Von einem anderen Rechner verlierst du den Webzugriff. Rückgängig per Shell: myscanner set web-host 0.0.0.0.' : 'Die Web-Adresse oder der Port wird geändert. Die aktuelle Verbindung kann abbrechen. Öffne anschließend die neue Adresse. Bei einer falschen Bind-Adresse ist die Korrektur per Shell nötig.';
      if (!await confirmAccess(localOnly ? 'Zugriff auf das Linux-System beschränken?' : 'Web-Adresse ändern?', text)) return;
    }
    await save(patch); $('mqtt-password').value = '';
  });
};
async function init() {
  try {
    const data = await api('/api/config'); token = data.token; savedWeb = data.config.web;
    for (const field of document.forms.settings.elements) {
      if (!field.name) continue;
      const [section,key] = field.name.split('.');
      if (field.type === 'checkbox') field.checked = data.config[section][key]; else field.value = data.config[section][key];
    }
    $('test-layout').value = data.config.scanner.layout;
    await devices(); await poll();
  } catch (error) { $('message').textContent = error.message; }
}
init(); setInterval(poll, 500);
