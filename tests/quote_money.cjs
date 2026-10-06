/* Compare browser previews against the authoritative Python Decimal calculator. */
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),{spawnSync}=require('node:child_process');
const context={window:{},document:{addEventListener(){},querySelector(){return null}},escapeHtml:String,Intl};vm.runInNewContext(fs.readFileSync('apps/web/workspace.js','utf8'),context);
const money=context.window.Workspace;
const row=(quantity,unit_price,extra={})=>({name:'QA',quantity,unit_price,unit:'m',...extra});
const rows=[row('1.005',100),row('0.29',50),row('0.1',5,{tax:'50'}),row('1e-4',10000),row('1',999,{optional:true,included:false}),row('1',999,{optional:false,included:false})];
for(let i=1;i<=150;i++)rows.push(row((i/100).toFixed(2),i*137,{coefficient:(.001+(i%90)/10).toFixed(3),markup:((i*13)%70/10).toFixed(4),discount:((i*17)%80/10).toFixed(4),tax:String(i%21)}));
const result=spawnSync(process.env.SMETRA_TEST_PYTHON||'python',['-c','import json,sys; from backend.business import calculate; print(json.dumps([calculate([row,{"name":"Base","unit_price":100}])[1]-100 for row in json.load(sys.stdin)]))'],{input:JSON.stringify(rows),encoding:'utf8',windowsHide:true});
assert.equal(result.status,0,result.stderr);const expected=JSON.parse(result.stdout);
assert.deepEqual(rows.map(item=>money.calculateLineTotal(item)),expected);assert.equal(expected[0],101);assert.equal(expected[1],15);
assert.equal(money.majorToKopecks('123456.78'),12345678);assert.equal(money.majorToKopecks('1e-2'),1);assert.throws(()=>money.majorToKopecks('1.001'));assert.throws(()=>money.majorToKopecks('-1'));
console.log('PASS: 156 browser money calculations match server Decimal; half-kopeck boundaries, taxes, optional items and scientific input');
