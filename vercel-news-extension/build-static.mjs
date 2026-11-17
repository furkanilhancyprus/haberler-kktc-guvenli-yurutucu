import { cpSync } from 'node:fs';
import { relative, resolve, sep } from 'node:path';

const source = resolve('public');
const dynamicIndexes = /^(?:index\.html|son-haberler\/index\.html|kategori\/(?:gundem|dunya|siyaset|spor|ekonomi|teknoloji|yasam|magazin)\/index\.html)$/;

// Vercel serves existing static output before rewrites. Keep the originals in
// public for the server renderer and omit only these entries from static output.
cpSync(source, resolve('site-output'), {
  recursive: true,
  filter: path => !dynamicIndexes.test(relative(source, path).split(sep).join('/')),
});
