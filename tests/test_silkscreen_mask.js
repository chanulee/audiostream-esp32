// Run with node tests/test_silkscreen_mask.js; no browser dependency.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync(require('node:path').join(__dirname, '../tools/silkscreen-editor/editor.js'), 'utf8');
const implementation = source.slice(source.indexOf('function maskRectangles('), source.indexOf('function cleanSVG('));
const context = vm.createContext({});
vm.runInContext(implementation, context);
const mask = ['11111', '10001', '10101', '10001', '11111'];
const pixels = new Uint8ClampedArray(5 * 5 * 4);
mask.forEach((row, y) => [...row].forEach((v, x) => {pixels[(y * 5 + x) * 4 + 3] = v === '1' ? 255 : 0;}));
const rectangles = context.maskRectangles(pixels, 5, 5, false);
const reconstructed = Array.from({length: 5}, () => Array(5).fill(0));
for (const [x,y,w,h] of rectangles) {
  for(let py=Math.round(y*5);py<Math.round((y+h)*5);py++) {
    for(let px=Math.round(x*5);px<Math.round((x+w)*5);px++) reconstructed[py][px]++;
  }
}
assert.deepEqual(reconstructed.map(row=>row.join('')),mask, 'holes and disjoint islands must survive conversion');
assert.equal(context.maskRectangles(new Uint8ClampedArray(100).fill(255),5,5,false).length,1,'solid area should merge into one rectangle');
assert.equal(context.maskRectangles(new Uint8ClampedArray(100).fill(255),5,5,true).length,0,'white background removal');
console.log('Silkscreen stencil conversion tests passed');
