const $ = (id) => document.getElementById(id);
const fragment = new URLSearchParams(location.hash.slice(1));
history.replaceState(null, '', location.pathname);
const headers = {
  'X-AutoFgo-Session-Id': fragment.get('autofgoSession') || '',
  Authorization: `Bearer ${fragment.get('autofgoToken') || ''}`,
};
let catalog, layout, card = 0, size, candidate = 0, sourceUrl, candidateUrls = [], loadVersion = 0;
// API index 0 is the standard crop; display indices follow the crop's direction.
const candidateGrid = [
  [1, '左上'], [2, '上'], [3, '右上'],
  [4, '左'], [0, '標準'], [5, '右'],
  [6, '左下'], [7, '下'], [8, '右下'],
];
const show = (message, kind = '') => { $('status').textContent = message; $('status').className = kind; };
async function showStartupWarning() {
  try {
    const result = await (await api('/api/startup-warning')).json();
    if (result.companionWasRunning) {
      $('startupWarning').hidden = false;
      setTimeout(() => { $('startupWarning').hidden = true; }, 10000);
    }
  } catch { /* The sampler remains usable if the warning status is unavailable. */ }
}
async function api(path, options = {}) {
  const response = await fetch(path, { ...options, headers: { ...headers, ...options.headers } });
  if (!response.ok) {
    let detail;
    try { const body = await response.json(); detail = body.detail || body.error; } catch { /* empty response */ }
    throw new Error(typeof detail === 'string' ? detail : `HTTP ${response.status}`);
  }
  return response;
}
async function live() {
  while (true) {
    try {
      const response = await api('/api/events');
      const reader = response.body.getReader();
      while (!(await reader.read()).done) { /* heartbeat */ }
    } catch { show('接続を再試行しています', 'error'); }
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
}
function revokeCandidates() { candidateUrls.forEach(URL.revokeObjectURL); candidateUrls = []; }
function clearImage() {
  loadVersion++; layout = null; revokeCandidates();
  if (sourceUrl) URL.revokeObjectURL(sourceUrl);
  sourceUrl = null; $('source').removeAttribute('src'); $('overlay').replaceChildren();
  $('cards').replaceChildren(); $('sizes').replaceChildren(); $('candidates').replaceChildren();
  $('selected').replaceChildren(); $('confirmed').checked = false; updateSummary();
}
async function discard() {
  await api('/api/image', { method: 'DELETE' }); clearImage(); show('画像を破棄しました', 'success');
}
function characterData() {
  return catalog?.manifest.characters.find((item) => item.name === $('character').value);
}
function renderAppearances() {
  const character = characterData(); const select = $('appearance'); select.replaceChildren();
  const fresh = new Option('新しい衣装を作成', ''); select.add(fresh);
  for (const id of character?.appearances || []) select.add(new Option(`衣装 ${id}`, String(id)));
  $('displayName').textContent = catalog.characters.find((item) => item.name === $('character').value)?.displayName || '';
  renderReferences(); updateSummary();
}
async function renderReferences() {
  const target = $('references'); target.replaceChildren();
  const character = characterData();
  if (!character) { target.textContent = '参照画像はまだありません。'; return; }
  const entries = catalog.manifest.references.filter((item) => item.characterId === character.id);
  if (!entries.length) { target.textContent = '参照画像はまだありません。'; return; }
  for (const entry of entries) {
    const figure = document.createElement('figure'); const image = document.createElement('img');
    image.alt = `衣装 ${entry.appearanceId} サンプル ${entry.sampleNumber}`;
    const caption = document.createElement('figcaption'); caption.textContent = image.alt;
    figure.append(image, caption); target.append(figure);
    try { image.src = URL.createObjectURL(await (await api(`/api/references/${entry.id}/image`)).blob()); }
    catch { caption.textContent += '（読込失敗）'; }
  }
}
async function refreshCatalog() {
  catalog = await (await api('/api/catalog')).json();
  const previous = $('character').value; $('character').replaceChildren();
  for (const item of catalog.characters) $('character').add(new Option(item.name, item.name));
  if (catalog.characters.some((item) => item.name === previous)) $('character').value = previous;
  renderAppearances();
}
function updateOverlay() {
  if (!layout) return;
  const svg = $('overlay'); svg.setAttribute('viewBox', `0 0 ${layout.sourceSize[0]} ${layout.sourceSize[1]}`);
  const boxes = [layout.header, ...layout.cards];
  svg.innerHTML = boxes.map(([x,y,w,h], i) => `<rect x="${x}" y="${y}" width="${w}" height="${h}" fill="none" stroke="${i === card + 1 ? '#ffcc50' : '#69d6ff'}" stroke-width="5"/>`).join('');
}
function renderCards() {
  $('cards').replaceChildren();
  layout.cards.forEach((_, index) => {
    const button = document.createElement('button'); button.textContent = `カード ${index + 1}`;
    button.className = index === card ? 'active' : '';
    button.onclick = () => { card = index; candidate = 0; renderCards(); updateOverlay(); renderCandidates(); };
    $('cards').append(button);
  }); updateOverlay();
}
function renderSizes() {
  $('sizes').replaceChildren();
  layout.sizes.forEach(([width, height]) => {
    const label = document.createElement('label'); const radio = document.createElement('input');
    radio.type = 'radio'; radio.name = 'size'; radio.checked = width === size[0] && height === size[1];
    radio.onchange = () => { size = [width, height]; candidate = 0; renderCandidates(); };
    label.append(radio, ` ${width}×${height}`); $('sizes').append(label);
  });
}
async function renderCandidates() {
  const version = ++loadVersion; revokeCandidates(); $('candidates').replaceChildren(); $('selected').replaceChildren(); updateSummary();
  show('9候補を読み込み中');
  try {
    const results = await Promise.all(Array.from({ length: 9 }, async (_, index) => {
      const response = await api(`/api/candidates/${card}/${size[0]}/${size[1]}/${index}`);
      return { url: URL.createObjectURL(await response.blob()), crop: response.headers.get('X-Crop') };
    }));
    if (version !== loadVersion) { results.forEach((item) => URL.revokeObjectURL(item.url)); return; }
    candidateUrls = results.map((item) => item.url);
    candidateGrid.forEach(([index, direction]) => {
      const item = results[index];
      const button = document.createElement('button'); const image = document.createElement('img');
      image.src = item.url; image.alt = `${direction}にずらした候補`;
      button.append(image, `${direction} · ${item.crop}`);
      button.onclick = () => { candidate = index; selectCandidate(results); };
      $('candidates').append(button);
    }); selectCandidate(results); show('候補を比較してください');
  } catch (error) { show(`候補を生成できません: ${error.message}`, 'error'); }
}
function selectCandidate(results) {
  [...$('candidates').children].forEach((button, position) => button.classList.toggle('active', candidateGrid[position][0] === candidate));
  const chosen = results[candidate]; $('selected').replaceChildren();
  const image = document.createElement('img'); image.src = chosen.url; image.alt = '選択した切り出し';
  const details = document.createElement('p'); details.textContent = `候補 ${candidate + 1} / 元画像上の矩形: ${chosen.crop}`;
  $('selected').append(image, details); updateSummary();
}
function updateSummary() {
  const name = $('character').value; const appearance = $('appearance').value;
  $('summary').textContent = layout && candidateUrls.length ? `${name} / ${appearance ? `衣装 ${appearance} に追加` : '新しい衣装'} / カード ${card + 1} / ${size.join('×')} / 候補 ${candidate + 1}。保存後に元画像を破棄します。` : '画像と候補を選択してください。';
  $('save').disabled = !layout || candidateUrls.length !== 9 || !name || !$('confirmed').checked;
}
async function loadImage(file) {
  clearImage();
  try {
    await api('/api/image', { method: 'DELETE' });
    if (!file || file.type !== 'image/png') throw new Error('PNG画像を選択してください');
    const response = await api('/api/image', { method: 'POST', headers: { 'Content-Type': 'image/png' }, body: file });
    layout = await response.json(); card = 0; size = layout.sizes.find(([w,h]) => w === 105 && h === 100) || layout.sizes[0]; candidate = 0;
    sourceUrl = URL.createObjectURL(await (await api('/api/image')).blob()); $('source').src = sourceUrl;
    renderCards(); renderSizes(); await renderCandidates();
  } catch (error) { clearImage(); show(`画像を読み込めません: ${error.message}`, 'error'); }
}
$('character').onchange = renderAppearances;
$('appearance').onchange = () => { renderReferences(); updateSummary(); };
$('confirmed').onchange = updateSummary;
$('file').onchange = (event) => { loadImage(event.target.files[0]); event.target.value = ''; };
$('discard').onclick = () => discard().catch((error) => show(error.message, 'error'));
$('clipboard').onclick = async () => {
  try {
    const items = await navigator.clipboard.read();
    const item = items.find((entry) => entry.types.includes('image/png'));
    if (!item) throw new Error('PNG画像がありません');
    await loadImage(await item.getType('image/png'));
  } catch (error) { show(`クリップボードを読めません: ${error.message}`, 'error'); }
};
document.addEventListener('paste', (event) => {
  const file = [...(event.clipboardData?.items || [])].find((item) => item.type === 'image/png')?.getAsFile();
  if (file) { event.preventDefault(); loadImage(file); }
});
const drop = $('drop');
drop.ondragover = (event) => { event.preventDefault(); drop.classList.add('drag'); };
drop.ondragleave = () => drop.classList.remove('drag');
drop.ondrop = (event) => { event.preventDefault(); drop.classList.remove('drag'); loadImage(event.dataTransfer.files[0]); };
$('save').onclick = async () => {
  $('save').disabled = true;
  try {
    const payload = { characterName: $('character').value, appearanceId: $('appearance').value ? Number($('appearance').value) : null,
      cardIndex: card, size, candidateIndex: candidate, sourceId: layout.sourceId, confirmed: $('confirmed').checked };
    if ($('sourceUrl').value.trim()) payload.sourceUrl = $('sourceUrl').value.trim();
    const result = await (await api('/api/references', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })).json();
    clearImage(); $('sourceUrl').value = ''; await refreshCatalog(); show(`${result.saved} を保存しました`, 'success');
  } catch (error) { show(`保存できません: ${error.message}`, 'error'); updateSummary(); }
};
refreshCatalog().then(() => show('画像を読み込んでください')).catch((error) => show(`一覧を取得できません: ${error.message}`, 'error'));
showStartupWarning();
$('dismissStartupWarning').onclick = () => { $('startupWarning').hidden = true; };
live();
