import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {readFile, writeFile} from 'node:fs/promises';
import {resolve, extname, sep} from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';
import {execFileSync} from 'node:child_process';

const root = resolve(fileURLToPath(new URL('../../', import.meta.url)));
const cases = JSON.parse(execFileSync(process.env.PYTHON || 'python', [resolve(root, 'testcode/202609150503/vectors.py')], {encoding:'utf8'}));
const {default:puppeteer} = await import(process.env.PUPPETEER_MODULE ? pathToFileURL(process.env.PUPPETEER_MODULE).href : 'puppeteer');
const server = createServer(async (req, res) => {
  try {
    const pathname = decodeURIComponent(new URL(req.url, 'http://localhost').pathname);
    const path = resolve(root, '.' + (pathname.endsWith('/') ? pathname + 'index.html' : pathname));
    if (!path.startsWith(root + sep)) throw new Error('outside root');
    res.setHeader('Content-Type', {'.html':'text/html', '.js':'text/javascript', '.json':'application/json'}[extname(path)] || 'text/plain');
    res.end(await readFile(path));
  } catch { res.writeHead(404); res.end(); }
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
let browser;
const results = {pass:false, cases:[], errors:[], viewport:{width:430,height:900,deviceScaleFactor:1}, physicalPhone:false};
try {
  browser = await puppeteer.launch({headless:true, executablePath:process.env.CHROME_PATH || undefined, args:['--no-sandbox']});
  const page = await browser.newPage();
  await page.setViewport(results.viewport);
  page.on('pageerror', error => results.errors.push(error.message));
  const url = `http://127.0.0.1:${server.address().port}/create/`;
  await page.goto(url, {waitUntil:'networkidle0'});
  results.browser = await browser.version();
  for (const vector of cases) {
    const direct = await page.evaluate(async observations => {
      const {observationBytes, prepareDefinition} = await import('./contract.js');
      return {bytes:observationBytes(observations), seed:(await prepareDefinition({sources:[{}], observations})).seed.value};
    }, vector.star.observations);
    assert.equal(direct.bytes, vector.bytes, vector.name + ' bytes');
    assert.equal(direct.seed, vector.star.seed.value, vector.name + ' seed');
    await page.$eval('#editor', (editor, value) => {editor.value=JSON.stringify(value)}, vector.star);
    await page.click('#prepare');
    await page.waitForFunction(() => document.querySelector('#status').textContent.startsWith('Prepared.'));
    const prepared = await page.$eval('#editor', editor => JSON.parse(editor.value));
    assert.deepEqual(prepared.seed, vector.star.seed, vector.name + ' actual UI');
    assert.deepEqual(JSON.parse(new URL(page.url()).searchParams.get('star')), prepared);
    await page.reload({waitUntil:'networkidle0'});
    assert.deepEqual(await page.$eval('#editor', editor => JSON.parse(editor.value)), prepared);
    results.cases.push(vector.name);
  }
  const rejected = await page.evaluate(async () => {
    const {canonical, prepareDefinition} = await import('./contract.js');
    const values = [Infinity, NaN, 2**53, -(2**53), '\ud800', {['\ud800']:1}, undefined];
    return Promise.all(values.map(async value => {
      try { canonical(value); return false; } catch { return true; }
    }));
  });
  assert(rejected.every(Boolean), 'invalid domain must fail closed');
  const changed = structuredClone(cases[0].star);
  changed.observations[0].value += 10;
  const changedSeed = await page.evaluate(async star => (await (await import('./contract.js')).prepareDefinition(star)).seed.value, changed);
  assert.notEqual(changedSeed, cases[0].star.seed.value);
  await page.$eval('#editor', editor => {editor.value='{"sources":[],"observations":[]}'});
  const previous = page.url();
  await page.click('#copy');
  await page.waitForFunction(() => document.querySelector('#status').textContent.startsWith('Not prepared:'));
  assert.equal(page.url(), previous, 'failed preparation does not replace URL');
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), '430px overflow');
  for (const box of await page.$$eval('button,a.button', nodes => nodes.map(node => ({height:node.getBoundingClientRect().height})))) assert(box.height >= 48);
  assert.deepEqual(results.errors, []);
  results.invalidVectors = rejected.length;
  results.changedMeasurementChangesSeed = true;
  results.urlReload = true;
  results.pass = true;
} finally {
  await browser?.close();
  await new Promise(resolve => server.close(resolve));
  if (process.env.PROOF_OUTPUT) await writeFile(process.env.PROOF_OUTPUT, JSON.stringify(results,null,2)+'\n');
  console.log(JSON.stringify(results,null,2));
}
