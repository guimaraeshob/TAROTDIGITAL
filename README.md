# Tarot Digital — MVP

Aplicação Flask com o baralho completo de 78 cartas Rider–Waite–Smith (22 Arcanos Maiores + 56 Menores), escolha manual de 3 cartas e interpretações simbólicas.

## Executar

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Abra http://127.0.0.1:5000. O banco `tarot.db` é criado na primeira leitura.

## Publicar no Render (grátis)

O repositório contém um blueprint (`render.yaml`) que faz o deploy reprodutível.

1. Crie um repositório **público no GitHub** e envie o projeto:

   ```bash
git init
git add .
git commit -m "Tarot Digital MVP"
git remote add origin https://github.com/SEU-USUARIO/tarot-digital.git
git push -u origin main
```

2. No [render.com](https://render.com), conecte a conta do GitHub e escolha **New → Blueprint** selecionando o repositório (ou **New → Web Service**; o `Procfile`/`render.yaml` fornecem build e start). O plano gratuito cumpre os requisitos deste MVP.
3. O blueprint gera `SECRET_KEY` automaticamente. **Não** configure `LLM_*` por enquanto — a leitura sai pelo motor de regras. Para ativar a IA mais tarde, adicione `LLM_API_KEY`, `LLM_BASE_URL` e `LLM_MODEL` nas variáveis de ambiente do serviço (e defina limite de gasto no provedor: a API fica aberta ao público).
4. Limites do plano gratuito do Render que você deve saber antes de compartilhar o link:
   - **Disco efêmero:** o `tarot.db` é zerado a cada redeploy/reinício — o painel Memória da casa recomeça do zero. As leituras em andamento de visitantes também se perdem se o serviço reiniciar.
   - **Hibernação:** após 15 min sem acesso, o serviço dorme; o primeiro acesso demora cerca de 1 minuto para acordar.
   - Sem criptografia das perguntas dos visitantes: elas ficam no banco do servidor (apenas em números agregados no painel `/memoria`) e desaparecem no próximo deploy.

No Windows local, `gunicorn` não é instalado (marcador em `requirements.txt`); use `python app.py` como sempre.

## Observações

- As imagens das cartas são scans do baralho Rider–Waite–Smith (1909), domínio público nos EUA, baixadas do repositório `searge/tarot` para `static/cards/`. Numa publicação nos EUA, o uso é livre; em alguns países europeus protectores de editor prevalecem — avalie antes de comercializar.
- O verso das cartas fechadas usa um padrão estilizado próprio, sem imagens de terceiros.
- O conteúdo das interpretações é um rascunho editorial e deve ser revisado antes da publicação.
- O histórico fica armazenado localmente no SQLite; a interface ainda não possui uma página para consultá-lo.
- Para produção, defina `SECRET_KEY` estável em variável de ambiente, use HTTPS e servidor WSGI apropriado, desative debug e implemente medidas de privacidade, exclusão de histórico e proteção contra CSRF.
- **Leitura com IA (opcional):** crie um arquivo `.env` na raiz com:

  ```
  LLM_API_KEY=sua-chave
  LLM_BASE_URL=https://api.seuprovedor/v1
  LLM_MODEL=nome-do-modelo
  ```

  Requer um provedor compatível com a API da OpenAI (ex.: Groq, Google AI Studio/Gemini, OpenRouter — todos com nível gratuito). Sem `.env`, a síntese usa o motor de regras embutido (naipes, Arcanos Majores, cortes e pergunta de aprofundamento). Se a chamada à IA falhar ou expirar (30 s), o motor de regras assume automaticamente.
- A ordem do baralho em andamento fica só no servidor (`TIRAGENS_ATIVAS`, em memória); o cookie da sessão não a expõe. O feedback só é aceito para a tiragem atual do próprio cliente.
