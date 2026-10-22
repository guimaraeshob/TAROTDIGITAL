import json
import math
import os
import random
import re
import secrets
import sqlite3
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib import request as urequest
from flask import Flask, jsonify, render_template, request, session

BASE = Path(__file__).resolve().parent
CARTAS = json.loads((BASE / "data" / "cartas.json").read_text(encoding="utf-8"))
DB = BASE / "tarot.db"

ENV = {}
if (BASE / ".env").exists():
    for linha in (BASE / ".env").read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if linha and not linha.startswith("#") and "=" in linha:
            k, v = linha.split("=", 1)
            ENV[k.strip()] = v.strip().strip('"').strip("'")

def env(k, d=None):
    import os
    return os.environ.get(k) or ENV.get(k) or d
app = Flask(__name__)
STANDARD_MODO = os.environ.get("SERVER_SOFTWARE", "").lower().startswith("gunicorn")
if not os.environ.get("SECRET_KEY"):
    print("AVISO: SECRET_KEY não definida — defina em variável de ambiente (ou .env) para publicar;")
    print("       sem ela, cada reinício invalida as sessões abertas (tiragem em andamento e feedback).")
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
DEBUG = env("FLASK_DEBUG") == "1"
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    # No deploy (gunicorn atrás de TLS do provedor) marca o cookie como Secure; local rota em http.
    SESSION_COOKIE_SECURE=env("HTTPS_ONLY", "1" if STANDARD_MODO else "0") == "1",
)

# A ordem do baralho em andamento fica só no servidor — o cookie nunca a expõe.
TIRAGENS_ATIVAS = {}

def init_db():
    with sqlite3.connect(DB) as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS tiragens (
          id TEXT PRIMARY KEY, criada_em TEXT NOT NULL,
          pergunta TEXT NOT NULL, cartas_json TEXT NOT NULL
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS avaliacoes (
          tiragem_id TEXT PRIMARY KEY, util INTEGER, tema TEXT,
          estilo TEXT, criada_em TEXT NOT NULL
        )""")

@app.get("/")
def inicio():
    return render_template("index.html")

TEMAS = {
    "Paus": "energia, iniciativa e ação",
    "Copas": "emoção, vínculos e afeto",
    "Espadas": "mente, escolhas e verdade",
    "Ouros": "o concreto: trabalho, corpo e dinheiro",
}
PERGUNTAS_FUTURO = {
    "Paus": "Qual é o primeiro passo concreto que você pode dar hoje, sem esperar o sinal perfeito?",
    "Copas": "O que o seu coração já sabe — talvez desde sempre — sobre essa questão?",
    "Espadas": "Existe algo que você ainda prefere não nomear e que merece ser olhado de frente?",
    "Ouros": "Qual pequeno gesto prático, já ao seu alcance, pode começar a construir o que você quer?",
}
PERGUNTAS_MAIOR = "Se essa força maior tivesse um recado para você, qual seria — e qual parte dele você já reconhece?"
TEMAS_PESSOA = ("Amor", "Trabalho", "Saúde", "Espiritualidade")
CONVITES_TEMA = {
    "Amor": "Onde nessa relação você ainda age no automático — e o que faria escolhendo de olhos abertos?",
    "Trabalho": "Se ninguém estivesse avaliando, qual próximo passo você daria por conta própria?",
    "Saúde": "Qual pequeno cuidado com o corpo anda sendo adiado por algo menos importante?",
    "Espiritualidade": "Que silêncio anda faltando na sua rotina — e a que pergunta ele responderia?",
}
ESTILOS = ("narrativa", "direta", "poetica")

def _contada(pergunta, resultado, estilo="narrativa", tema=None, confianca=0.0):
    """Síntese construída por regras: naipes dominantes, presença de Maiores,
    cartas de corte, citação da pergunta e um convite de aprofundamento."""
    cartas = [CARTAS[c["id"]] for c in resultado]
    naipes = [c["naipe"] for c in cartas if c.get("naipe")]
    maiores = len(cartas) - len(naipes)
    tem_corte = any(c.get("naipe") and c.get("numero") in (11, 12, 13, 14) for c in cartas)
    frases = []
    p = (pergunta or "").strip()
    if p:
        resumo = p if len(p) <= 90 else p[:87].rstrip() + "…"
        frases.append(f'Você perguntou: "{resumo}". Agora deixe as cartas conversarem entre si.')
    else:
        frases.append("Sem pergunta escrita, a leitura fica mais aberta — e as cartas conversam igualmente.")
    if maiores == 3:
        frases.append("As três são do Arcano Maior: essa questão toca algo grande e estrutural na sua vida, não é um detalhe burocrático.")
    elif maiores == 2:
        frases.append("Dois Arcanos Maiores assumem a mesa: uma força grande atravessa o cotidiano — pertence a ela a cor principal da história.")
    elif maiores == 1:
        frases.append("Um Arcano Maior entre os menores: há uma força relevante em jogo, mas quem conduz o desenrolar são as suas escolhas do dia a dia.")
    else:
        frases.append("Vieram apenas cartas dos naipes: nada aqui é magia de marquês — a história é toda trabalhável por você.")
    contagem = Counter(naipes)
    if naipes:
        dominante, n = contagem.most_common(1)[0]
        if n >= 2:
            frases.append(f"A repetição do naipe {dominante} dá o fio condutor: o terreno é de {TEMAS[dominante]}.")
        else:
            temas = " e ".join(TEMAS[n] for n in dict.fromkeys(naipes))
            frases.append(f"Naipes variados ({temas}) mostram um tema que se desloca de plano — o que foi sentimento pode virar decisão.")
    if tem_corte:
        frases.append("As cartas de corte indicam pessoas reais na trama: procure uma figura na sua vida que combine com elas — aliada ou influência, ninguém fica neutro.")
    alvo = next((c for c in cartas[::-1] if c.get("naipe")), None)
    convite = PERGUNTAS_FUTURO[alvo["naipe"]] if alvo else PERGUNTAS_MAIOR
    tema_conf = tema if confianca >= 0.55 else None
    if tema_conf and tema_conf in CONVITES_TEMA:
        frases.insert(1, f"Pelo padrão das suas leituras anteriores, essa pergunta aponta para {tema_conf.lower()}.")
        convite = CONVITES_TEMA[tema_conf]
    if estilo == "direta":
        corpo = frases[:2] if len(frases) > 2 else frases
        fim = f"Próximo passo: {convite}"
    elif estilo == "poetica":
        corpo = ["Cada carta é um espelho em três quadros: passado, presente e porvir."] + frases
        fim = f"Deixe esta pergunta residir em você: {convite}"
    else:
        corpo = frases
        fim = f"Leve contigo: {convite}"
    return "\n\n".join(corpo + [fim])

def _escolher_estilo():
    """Bandit epsilon-greedy: escolhe o estilo de síntese com melhor nota
    média (👍=1/👎=0); explora aleatoriamente 25% das vezes."""
    try:
        with sqlite3.connect(DB) as conn:
            linhas = conn.execute(
                "SELECT estilo, AVG(util), COUNT(*) FROM avaliacoes WHERE util IS NOT NULL GROUP BY estilo"
            ).fetchall()
    except sqlite3.Error:
        linhas = []
    total = sum(r[2] for r in linhas)
    validos = [r for r in linhas if r[0] in ESTILOS]
    if validos and total >= 5 and random.random() > 0.25:
        return max(validos, key=lambda r: (r[1], r[2]))[0]
    return random.choice(ESTILOS)

def _tokens(texto):
    return re.findall(r"[a-zà-ú]{3,}", (texto or "").lower())

def _treinar_tema():
    """Par rotulado (pergunta, tema) = um exemplo de treino do classificador."""
    docs = []
    try:
        with sqlite3.connect(DB) as conn:
            for p, t in conn.execute(
                """SELECT t.pergunta, a.tema FROM avaliacoes a
                   JOIN tiragens t ON t.id = a.tiragem_id
                   WHERE a.tema IS NOT NULL AND TRIM(t.pergunta) <> ''"""
            ).fetchall():
                docs.append((t, _tokens(p)))
    except sqlite3.Error:
        pass
    return docs

def _tema_previsto(pergunta):
    """Naive Bayes multinomial próprio (sem dependências).
    Retorna (tema, probabilidade) ou (None, 0.0) se ainda não houver dados."""
    docs = _treinar_tema()
    if len(docs) < 6 or not (pergunta or "").strip():
        return None, 0.0
    vocab = set()
    palavras, ndocs = {}, Counter()
    for tema, toks in docs:
        palavras.setdefault(tema, Counter(toks))
        ndocs[tema] += 1
        vocab.update(toks)
    total_docs = len(docs)
    logits = {}
    toks = _tokens(pergunta)
    for tema, cont in palavras.items():
        tot = sum(cont.values())
        logit = math.log(ndocs[tema] / total_docs)
        for w in toks:
            logit += math.log((cont.get(w, 0) + 1) / (tot + len(vocab)))
        logits[tema] = logit
    if not logits:
        return None, 0.0
    m = max(logits.values())
    exps = {t: math.exp(v - m) for t, v in logits.items()}
    z = sum(exps.values())
    tema = max(exps, key=lambda t: exps[t] / z)
    return tema, exps[tema] / z

def _ia(pergunta, resultado):
    """Leitura narrativa por LLM compatível com OpenAI. Requer .env:
    LLM_API_KEY, LLM_BASE_URL e (opcional) LLM_MODEL. Falha=>None."""
    key, base = env("LLM_API_KEY"), env("LLM_BASE_URL")
    if not key or not base:
        return None
    url = base.rstrip("/") + "/chat/completions"
    sist = (
        "Você é uma tarologa experiente, acolhedora e direta. Escreva em português do Brasil. "
        "Use apenas as três cartas informadas, nas posições dadas. Conecte as cartas entre si "
        "(contrastes, continuidades, dominância de naipes), cite a pergunta do usuário quando houver, "
        "e nunca prometa ou preveja o futuro — a leitura é espelho, não oráculo. "
        "Escreva 2 a 4 parágrafos curtos; o último termina com uma pergunta de reflexão. Sem emojis."
    )
    resumo = "\n".join(
        f"- {c['posicao'].capitalize()}: {c['nome']} — {CARTAS[c['id']].get('naipe', 'Arcano Maior')} "
        f"— palavras-chave: {', '.join(CARTAS[c['id']]['palavras_chave'])}"
        for c in resultado
    )
    corpo = {
        "model": env("LLM_MODEL", "gpt-4o-mini"),
        "temperature": 0.8,
        "max_tokens": 600,
        "messages": [
            {"role": "system", "content": sist},
            {"role": "user", "content": f"Pergunta: {pergunta or '(em branco)'}\nTiragem:\n{resumo}"},
        ],
    }
    req = urequest.Request(
        url,
        data=json.dumps(corpo).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
    )
    try:
        with urequest.urlopen(req, timeout=30) as r:
            j = json.loads(r.read().decode("utf-8"))
            texto = (j["choices"][0]["message"]["content"] or "").strip()
            return texto or None
    except Exception:
        return None


@app.post("/api/iniciar")
def iniciar():
    body = request.get_json(silent=True) or {}
    pergunta = str(body.get("pergunta", ""))[:500]
    ordem = list(range(len(CARTAS)))
    secrets.SystemRandom().shuffle(ordem)
    tiragem_id = str(uuid.uuid4())
    TIRAGENS_ATIVAS[tiragem_id] = ordem
    if len(TIRAGENS_ATIVAS) > 500:  # dique: ordens abandonadas não ficam para sempre
        TIRAGENS_ATIVAS.pop(next(iter(TIRAGENS_ATIVAS)))
    session["tiragem"] = {"id": tiragem_id, "pergunta": pergunta, "escolhidas": [], "finalizada": False}
    return jsonify({"ok": True, "total": len(ordem)})

@app.post("/api/escolher")
def escolher():
    tiragem = session.get("tiragem")
    if not tiragem or tiragem["finalizada"]:
        return jsonify({"erro": "Inicie uma nova tiragem."}), 400
    ordem = TIRAGENS_ATIVAS.get(tiragem["id"])
    if not ordem:
        return jsonify({"erro": "Sessão expirada — comece uma nova tiragem."}), 400
    body = request.get_json(silent=True) or {}
    indice = body.get("indice")
    if type(indice) is not int or indice < 0 or indice >= len(ordem):
        return jsonify({"erro": "Posição inválida."}), 400
    if indice in tiragem["escolhidas"] or len(tiragem["escolhidas"]) >= 3:
        return jsonify({"erro": "Carta já escolhida ou limite atingido."}), 400
    tiragem["escolhidas"].append(indice)
    session["tiragem"] = tiragem
    return jsonify({"quantidade": len(tiragem["escolhidas"])})

@app.post("/api/revelar")
def revelar():
    tiragem = session.get("tiragem")
    if not tiragem or len(tiragem["escolhidas"]) != 3:
        return jsonify({"erro": "Escolha exatamente três cartas."}), 400
    posicoes = ("passado", "presente", "futuro")
    ordem = TIRAGENS_ATIVAS.get(tiragem["id"])
    resultado = None
    if tiragem["finalizada"]:
        # Já registrada: reconstitui as cartas pelo banco, sem depender da ordem em memória.
        with sqlite3.connect(DB) as conn:
            linha = conn.execute("SELECT cartas_json FROM tiragens WHERE id = ?", (tiragem["id"],)).fetchone()
        if linha:
            resultado = json.loads(linha[0])
    elif ordem:
        resultado = []
        for posicao, indice in zip(posicoes, tiragem["escolhidas"]):
            carta = CARTAS[ordem[indice]]
            resultado.append({"id": carta["id"], "nome": carta["nome"], "posicao": posicao, "texto": carta["significados"][posicao]})
    if resultado is None:
        return jsonify({"erro": "Sessão expirada — comece uma nova tiragem."}), 400
    estilo = tiragem.get("estilo")
    sintese = None
    if not tiragem["finalizada"]:
        # A IA é chamada uma única vez: o texto retornado já serve como decisão e síntese.
        sintese = _ia(tiragem["pergunta"], resultado)
        if sintese:
            estilo = "ia"
        else:
            estilo = _escolher_estilo()
        init_db()
        with sqlite3.connect(DB) as conn:
            conn.execute("INSERT OR IGNORE INTO tiragens VALUES (?, ?, ?, ?)",
                (tiragem["id"], datetime.now(timezone.utc).isoformat(), tiragem["pergunta"], json.dumps(resultado, ensure_ascii=False)))
        tiragem["finalizada"] = True
        tiragem["estilo"] = estilo
        TIRAGENS_ATIVAS.pop(tiragem["id"], None)  # registrada no banco, não precisa mais de memória
    elif estilo == "ia":
        sintese = _ia(tiragem["pergunta"], resultado)
    if not sintese:
        tema_prev, conf = _tema_previsto(tiragem["pergunta"])
        if estilo == "ia":
            # A IA falhou nesta revelagem: o estilo reportado precisa ser o do motor de regras usado.
            estilo = _escolher_estilo()
        sintese = _contada(tiragem["pergunta"], resultado, estilo=estilo, tema=tema_prev, confianca=conf)
    session["tiragem"] = tiragem
    return jsonify({"pergunta": tiragem["pergunta"], "cartas": resultado, "sintese": sintese,
                    "tiragem": tiragem["id"], "estilo": estilo})

@app.post("/api/feedback")
def feedback():
    body = request.get_json(silent=True) or {}
    tiragem_id = body.get("tiragem")
    util = body.get("util")
    tema = body.get("tema") or None
    estilo = body.get("estilo") or None
    sessao_id = (session.get("tiragem") or {}).get("id")
    if not tiragem_id or tiragem_id != sessao_id:
        return jsonify({"erro": "Avaliação fora de contexto."}), 400
    if util is None:
        with sqlite3.connect(DB) as conn:
            existe = conn.execute("SELECT 1 FROM avaliacoes WHERE tiragem_id = ?", (tiragem_id,)).fetchone()
        if not existe:
            return jsonify({"erro": "Avalie antes com 👍/👎."}), 400
    elif util not in (0, 1):
        return jsonify({"erro": "Voto inválido."}), 400
    if tema and tema not in TEMAS_PESSOA:
        tema = None
    if estilo and estilo not in ESTILOS:
        estilo = None
    init_db()
    with sqlite3.connect(DB) as conn:
        conn.execute("""INSERT INTO avaliacoes (tiragem_id, util, tema, estilo, criada_em)
                        VALUES (?, ?, ?, ?, ?)
                        ON CONFLICT(tiragem_id) DO UPDATE SET
                        util = COALESCE(?, util), tema = COALESCE(?, tema),
                        estilo = COALESCE(?, estilo), criada_em = ?""",
            (tiragem_id, util, tema, estilo, datetime.now(timezone.utc).isoformat(),
             body.get("util") if util is not None else None, tema, estilo,
             datetime.now(timezone.utc).isoformat()))
    return jsonify({"ok": True})

@app.get("/memoria")
def memoria():
    """Painel: o que o app já 'aprendeu' com suas leituras."""
    init_db()
    with sqlite3.connect(DB) as conn:
        total = conn.execute("SELECT COUNT(*) FROM tiragens").fetchone()[0]
        n_avaliadas, media_util = conn.execute(
            "SELECT COUNT(*), COALESCE(AVG(util), -1) FROM avaliacoes WHERE util IS NOT NULL").fetchone()
        temas_n = conn.execute(
            "SELECT tema, COUNT(*) FROM avaliacoes WHERE tema IS NOT NULL GROUP BY tema ORDER BY 2 DESC").fetchall()
        estilos_n = conn.execute(
            "SELECT estilo, COUNT(*), COALESCE(AVG(util), -1) FROM avaliacoes WHERE util IS NOT NULL GROUP BY estilo").fetchall()
    freq = Counter()
    for (brutas,) in sqlite3.connect(DB).execute("SELECT cartas_json FROM tiragens"):
        for c in json.loads(brutas):
            freq[c["id"]] += 1
    top_cartas = [{"id": i, "nome": CARTAS[i]["nome"], "naipe": CARTAS[i].get("naipe", "Arcano Maior"), "n": n}
                  for i, n in freq.most_common(12)]
    naipes_n = Counter()
    for i in freq:
        if CARTAS[i].get("naipe"):
            naipes_n[CARTAS[i]["naipe"]] += freq[i]
    docs = _treinar_tema()
    return render_template("memoria.html", total=total, avaliadas=n_avaliadas,
                           media_util=(media_util + 1) / 2 if media_util >= 0 else None,
                           top_cartas=top_cartas, naipes=dict(naipes_n.most_common()),
                           temas=temas_n, estilos=estilos_n,
                           exemplos=len(docs),
                           temas_exemplo=[{t: c} for t, c in Counter(t for t, _ in docs).most_common()])

if __name__ == "__main__":
    init_db()
    app.run(debug=DEBUG)
