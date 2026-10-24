/* Regression tests for free material calculators. Run: node tests/calculators.cjs */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.resolve(__dirname, '../apps/web/calculators.js'), 'utf8');
const sandbox = {window: {}, Intl};
vm.runInNewContext(source, sandbox, {filename: 'calculators.js'});
const {calculate, kinds} = sandbox.window.SmetraCalculators;
const approx = (actual, expected) => assert.ok(Math.abs(actual - expected) <= 1e-9,
  'Expected ' + expected + ', got ' + actual);
const tile = {length:'4',width:'3',openings:'0',waste:'10',pack:'1.44'};
const laminate = {length:'5',width:'4',waste:'8',pack:'2.2'};
const paint = {length:'5',height:'2.7',openings:'1.5',coats:'2',coverage:'10',waste:'10',pack:'2.5'};
const plaster = {length:'5',height:'2.7',openings:'1.5',thickness:'10',rate:'9',waste:'10',pack:'30'};
const concrete = {length:'5',width:'3',thickness:'10',waste:'5'};

assert.equal(kinds.length, 5);
approx(calculate('tile',tile).primary.value, 13.2);
assert.equal(calculate('tile',tile).secondary.value, 10);
approx(calculate('tile',{...tile,openings:'2'}).area, 10);
assert.equal(calculate('tile',{...tile,openings:'2'}).secondary.value, 8);
approx(calculate('laminate',laminate).primary.value,21.6);
assert.equal(calculate('laminate',laminate).secondary.value,10);
approx(calculate('paint',paint).primary.value,2.64);
assert.equal(calculate('paint',paint).secondary.value,2);
approx(calculate('plaster',plaster).primary.value,118.8);
assert.equal(calculate('plaster',plaster).secondary.value,4);
approx(calculate('concrete',concrete).primary.value,1.575);
approx(calculate('concrete',concrete).secondary.value,1.5);
approx(calculate('tile',{...tile,length:'1,5'}).area,4.5);
assert.equal(calculate('tile',{...tile,waste:'0',length:'1',width:'1',pack:'0.1'}).secondary.value,10);

for (const [type,values] of [
  ['tile',{...tile,pack:'0'}],
  ['tile',{...tile,length:'-1'}],
  ['tile',{...tile,openings:'12'}],
  ['tile',{...tile,openings:'13'}],
  ['tile',{...tile,waste:'101'}],
  ['tile',{...tile,length:'1e5'}],
  ['laminate',{...laminate,pack:'NaN'}],
  ['laminate',{...laminate,width:'Infinity'}],
  ['paint',{...paint,coats:'0'}],
  ['paint',{...paint,openings:'13.5'}],
  ['paint',{...paint,coverage:'0'}],
  ['plaster',{...plaster,rate:''}],
  ['plaster',{...plaster,thickness:'-10'}],
  ['concrete',{...concrete,thickness:'0'}]
]) assert.throws(()=>calculate(type,values), {name:'Error'}, 'Invalid value should fail in ' + type);
assert.throws(()=>calculate('unknown',{}),{name:'Error'});
assert.throws(()=>calculate('tile',{}),{name:'Error'});
console.log('PASS: 5 free material calculators, unit conversion, pack rounding and invalid-input guards');
