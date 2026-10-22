const $ = id => document.getElementById(id);
const nomes = ['Passado', 'Presente', 'Futuro'];
const REDUZ = window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;
let escolhidas = [], tiragemId = null, estiloId = null;

function escrever(el, texto, vel = 13) {
  if (REDUZ) { el.textContent = texto; el.classList.add('pronto'); return Promise.resolve(); }
  el.textContent = '';
  return new Promise(fim => {
    let i = 0;
    const t = setInterval(() => {
      if (i >= texto.length) { clearInterval(t); el.classList.add('pronto'); fim(); return; }
      el.textContent += texto[i++];
    }, vel);
  });
}

async function api(path, data = {}) {
  const r = await fetch('/api/' + path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
  const j = await r.json();
  if (!r.ok) throw Error(j.erro || 'Erro inesperado');
  return j;
}

function erro(e) { $('erro').textContent = e.message || String(e); }

function instrucao() {
  $('instrucao').textContent = escolhidas.length < 3 ? 'Escolha a carta do ' + nomes[escolhidas.length] : 'Três cartas selecionadas';
  $('progresso').textContent = escolhidas.length + ' de 3 cartas escolhidas';
  $('revelar').disabled = escolhidas.length !== 3;
}

async function iniciar() {
  try {
    $('erro').textContent = '';
    const data = await api('iniciar', { pergunta: $('pergunta').value });
    escolhidas = [];
    $('baralho').replaceChildren();
    for (let i = 0; i < data.total; i++) {
      const b = document.createElement('button');
      b.className = 'carta';
      b.type = 'button';
      b.textContent = '✦';
      b.setAttribute('aria-label', 'Escolher carta ' + (i + 1));
      b.addEventListener('click', () => escolher(i, b));
      $('baralho').append(b);
    }
    $('intro').hidden = true;
    $('resultado').hidden = true;
    $('escolha').hidden = false;
    instrucao();
  } catch (e) { erro(e); }
}

async function escolher(i, b) {
  try {
    await api('escolher', { indice: i });
    escolhidas.push(i);
    b.disabled = true;
    b.textContent = '✓';
    instrucao();
  } catch (e) { erro(e); }
}

async function revelar() {
  try {
    const data = await api('revelar');
    $('cartasResultado').replaceChildren();
    data.cartas.forEach((c, i) => {
      const article = document.createElement('article');
      article.className = 'resultado-carta';
      const flip = document.createElement('div');
      flip.className = 'flip';
      const inner = document.createElement('div');
      inner.className = 'flip-inner';
      const verso = document.createElement('div');
      verso.className = 'flip-face flip-verso';
      verso.textContent = '✦';
      const frente = document.createElement('div');
      frente.className = 'flip-face flip-frente';
      frente.setAttribute('aria-hidden', 'true');
      const img = document.createElement('img');
      img.className = 'flip-img';
      img.src = '/static/cards/' + c.id + '.jpg';
      img.alt = c.nome;
      img.onerror = () => { frente.textContent = c.nome; };
      frente.append(img);
      inner.append(verso, frente);
      flip.append(inner);
      const info = document.createElement('div');
      info.className = 'info';
      const pos = document.createElement('small');
      pos.textContent = c.posicao;
      const title = document.createElement('h3');
      title.textContent = c.nome;
      const text = document.createElement('p');
      text.textContent = '';
      info.append(pos, title, text);
      article.append(flip, info);
      $('cartasResultado').append(article);
      const passo = REDUZ ? 0 : 600 + i * 1300;
      setTimeout(() => { flip.classList.add('aberta'); escrever(text, c.texto); }, passo);
    });
    $('sintese').textContent = '';
    $('escolha').hidden = true;
    $('resultado').hidden = false;
    await new Promise(r => setTimeout(r, REDUZ ? 100 : 600 + data.cartas.length * 1300 + 1100));
    escrever($('sintese'), data.sintese);
    tiragemId = data.tiragem;
    estiloId = data.estilo;
    const fb = $('feedback');
    fb.hidden = false;
    $('fbSim').disabled = false;
    $('fbNao').disabled = false;
    $('temasFb').hidden = true;
    $('fbAviso').textContent = '';
  } catch (e) { erro(e); }
}

function feedback(util) {
  api('feedback', { tiragem: tiragemId, util, estilo: estiloId }).catch(e => erro(e));
  $('fbSim').disabled = true;
  $('fbNao').disabled = true;
  if (util === 1) { $('temasFb').hidden = false; }
  $('fbAviso').textContent = 'Obrigado por ajudar o app a aprender.';
}

$('iniciar').addEventListener('click', iniciar);
$('revelar').addEventListener('click', revelar);

$('fbSim').addEventListener('click', () => feedback(1));
$('fbNao').addEventListener('click', () => feedback(0));

document.querySelectorAll('#temasFb .chip').forEach(b => {
  b.addEventListener('click', async () => {
    try {
      await api('feedback', { tiragem: tiragemId, tema: b.dataset.tema || null, estilo: estiloId });
      $('temasFb').hidden = true;
      $('fbAviso').textContent = b.dataset.tema ? 'Anotado, obrigado!' : 'Da próxima vez você me ensina.';
    } catch (e) { $('fbAviso').textContent = e.message || String(e); }
  });
});

$('reiniciar').addEventListener('click', () => {
  $('resultado').hidden = true;
  $('intro').hidden = false;
  $('pergunta').value = '';
  $('erro').textContent = '';
});
