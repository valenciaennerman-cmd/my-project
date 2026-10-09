let currentSquad = [];
const history = [];
let latestSwapResults = [];
const $ = id => document.getElementById(id);
const settings = () => ({
    mode: $('sbc-mode').value,
    target_score: Number($('sbc-target-score').value) || 0,
    min_rating: Number($('sbc-min-rating').value) || 0,
    min_chem: Number($('sbc-min-chem').value) || 0,
    protect_expensive: $('protect-expensive').checked,
    prefer_untradeable: $('prefer-untradeable').checked,
    completion_count: Number($('completion-count').value) || 1
});
async function request(path, payload) {
    const response = await fetch(`/api/sbc/${path}`, {
        method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
    return data;
}
function showVerification(v) {
    $('sbc-validity').textContent = v.valid ? 'VALID' : 'INVALID';
    $('sbc-validity').dataset.valid = String(v.valid);
    $('sbc-status').textContent = v.valid ? 'Kadro doğrulandı' : v.errors.join('; ');
    $('res-rating').textContent = v.team_rating == null ? '' : `Reyting: ${v.team_rating}`;
    $('res-chem').textContent = v.team_chemistry == null ? '' : `Kimya: ${v.team_chemistry}`;
    $('res-score').textContent = v.total_score == null ? '' : `Item Score: ${v.total_score} / ${v.required_score}`;
    $('sbc-total-cost').textContent = `${Number(v.estimated_cost || 0).toLocaleString('tr-TR')} 🪙`;
}
function invalidate() {
    $('sbc-validity').textContent = 'VERIFYING';
    $('sbc-validity').dataset.valid = 'pending';
    $('sbc-status').textContent = 'Kadro doğrulanıyor...';
}
async function verifyCurrent() {
    invalidate();
    const snapshot = JSON.stringify(currentSquad);
    try {
        const data = await request('verify', {squad: currentSquad, ...settings()});
        if (snapshot === JSON.stringify(currentSquad)) showVerification(data.verification);
    } catch (error) {
        $('sbc-validity').textContent = 'INVALID';
        $('sbc-validity').dataset.valid = 'false';
        $('sbc-status').textContent = error.message;
    }
}
function saveHistory() {
    history.push(structuredClone(currentSquad));
    $('undo-btn').disabled = false;
}
function renderSquad() {
    const container = $('sbc-results-container');
    container.replaceChildren();
    currentSquad.forEach(player => {
        const row = document.createElement('div');
        row.className = 'sol-card';
        row.dataset.instanceId = player.instance_id;
        const label = document.createElement('span');
        label.textContent = `${player.rating} ${player.name}${player.locked ? ' [Kilitli]' : ''}`;
        const lock = document.createElement('button');
        lock.textContent = player.locked ? 'Unlock' : 'Lock';
        lock.addEventListener('click', () => {
            saveHistory(); player.locked = !player.locked; renderSquad(); verifyCurrent();
        });
        const swap = document.createElement('button');
        swap.textContent = 'Swap';
        swap.addEventListener('click', () => openSwap(player.instance_id));
        row.append(label, lock, swap);
        container.appendChild(row);
    });
}
async function openSwap(instanceId) {
    $('swap-modal').hidden = false;
    $('swap-candidates').textContent = 'Adaylar aranıyor...';
    latestSwapResults = [];
    try {
        const data = await request('swap', {current_squad: currentSquad, original_instance_id: instanceId, ...settings()});
        latestSwapResults = data.results || [];
        $('swap-candidates').replaceChildren();
        if (!latestSwapResults.length) $('swap-candidates').textContent =
            data.solver_status === 'INFEASIBLE' ? 'Aynı reytingde alternatif yok.' : 'Arama sınırına ulaşıldı; uygun alternatif kanıtlanamadı.';
        latestSwapResults.forEach((result, index) => {
            const button = document.createElement('button');
            button.textContent = `${result.candidate.rating} ${result.candidate.name} (${result.candidate.instance_id})`;
            button.dataset.instanceId = result.candidate.instance_id;
            button.addEventListener('click', async () => {
                saveHistory(); currentSquad = structuredClone(latestSwapResults[index].repaired_squad);
                $('swap-modal').hidden = true; renderSquad(); await verifyCurrent();
            });
            $('swap-candidates').appendChild(button);
        });
    } catch (error) { $('swap-candidates').textContent = error.message; }
}
$('sbc-solve-btn').addEventListener('click', async () => {
    const button = $('sbc-solve-btn'); button.disabled = true; invalidate();
    try {
        const data = await request('solve', {
            ...settings(), locked_players: currentSquad.filter(p => p.locked).map(p => ({instance_id: p.instance_id}))
        });
        if (data.status !== 'success' && data.status !== 'partial') {
            $('sbc-validity').textContent = data.solver_status;
            $('sbc-solver-status').textContent = data.solver_status;
            $('sbc-status').textContent = data.metadata?.diagnostic || data.solver_status;
            return;
        }
        if (currentSquad.length) saveHistory();
        $('sbc-solver-status').textContent = data.solver_status;
        currentSquad = data.squad; renderSquad(); await verifyCurrent();
        $('res-completions').textContent = `Çözüm: ${data.completion_count} / ${settings().completion_count}`;
    } catch (error) {
        $('sbc-validity').textContent = 'ERROR'; $('sbc-status').textContent = error.message;
    } finally { button.disabled = false; }
});
$('undo-btn').addEventListener('click', async () => {
    if (!history.length) return;
    currentSquad = history.pop(); $('undo-btn').disabled = !history.length;
    renderSquad(); await verifyCurrent();
});
$('swap-close').addEventListener('click', () => { $('swap-modal').hidden = true; });
$('sbc-mode').addEventListener('change', () => {
    $('rating-controls').hidden = $('sbc-mode').value === 'STREAMLINED';
    $('score-controls').hidden = $('sbc-mode').value !== 'STREAMLINED';
    if (currentSquad.length) verifyCurrent();
});
['sbc-min-rating', 'sbc-target-score', 'sbc-min-chem'].forEach(id => $(id).addEventListener('change', () => {
    if (currentSquad.length) verifyCurrent();
}));
