/**
 * Jednorazowy skrypt do pobrania tokenu puter.com.
 * Uruchom: node get-token.mjs
 * Otworzy przeglądarkę → zaloguj się → token zapisze się do .env
 */
import { getAuthToken } from '@heyputer/puter.js/src/init.cjs';
import { writeFileSync } from 'fs';

console.log('Otwieranie przeglądarki puter.com...');
const token = await getAuthToken();
console.log('Token:', token.substring(0, 20) + '...');

// Zapisz do .env
writeFileSync('../.env', `PUTER_AUTH_TOKEN=${token}\n`, { flag: 'a' });
console.log('Zapisano do .env jako PUTER_AUTH_TOKEN');
