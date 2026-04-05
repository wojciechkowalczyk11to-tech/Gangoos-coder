/**
 * Puter.js bridge — HTTP server wywołujący puter.ai.chat()
 *
 * Setup:
 *   npm install @heyputer/puter.js
 *   node get-token.mjs  # jednorazowo — otworzy przeglądarkę
 *   PUTER_AUTH_TOKEN=xxx node index.js
 *
 * API:
 *   POST /opus  { prompt, system? }  →  { result: "..." }
 */
import http from 'http';
import { init } from '@heyputer/puter.js/src/init.cjs';

const TOKEN = process.env.PUTER_AUTH_TOKEN;
if (!TOKEN) {
  console.error('Brak PUTER_AUTH_TOKEN. Uruchom najpierw: node get-token.mjs');
  process.exit(1);
}

const puter = init(TOKEN);

async function callOpus(prompt, system = '') {
  const messages = system
    ? [{ role: 'system', content: system }, { role: 'user', content: prompt }]
    : [{ role: 'user', content: prompt }];

  const resp = await puter.ai.chat(messages, { model: 'claude-opus-4-6' });
  // puter.ai.chat zwraca string lub { message: { content: ... } }
  if (typeof resp === 'string') return resp;
  if (resp?.message?.content) return resp.message.content;
  return JSON.stringify(resp);
}

const server = http.createServer(async (req, res) => {
  if (req.method !== 'POST' || req.url !== '/opus') {
    res.writeHead(404); res.end(); return;
  }
  let body = '';
  req.on('data', c => { body += c; });
  req.on('end', async () => {
    try {
      const { prompt, system } = JSON.parse(body);
      const result = await callOpus(prompt, system || '');
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ result }));
    } catch (e) {
      res.writeHead(500, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: e.message }));
    }
  });
});

server.listen(3847, () => {
  console.log('Puter bridge :3847 — model: claude-opus-4-6');
});
