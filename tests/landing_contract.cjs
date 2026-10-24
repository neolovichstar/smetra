/* Guard against accidentally redeploying the retired minimal landing. */
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const web=path.join(__dirname,'../apps/web');
const html=fs.readFileSync(path.join(web,'index.html'),'utf8');
const landing=fs.readFileSync(path.join(web,'landing.js'),'utf8');
assert.match(html,/class="site-page landing-page dark"/);
assert.match(html,/<h1 id="hero-title"[\s\S]*?Смета, которую клиент понимает/);
assert.match(html,/data-flow/,'Interactive workflow must be present');
assert.match(html,/id="plans"/);
assert.match(html,/id="public-quote"/,'Public quote route must remain available');
assert.match(html,/\/ui\/site\.css\?v=/);
assert.match(html,/\/landing\.js\?v=/);
assert.doesNotMatch(html,/<body class="dark black-landing"/,'Retired landing accidentally restored');
for(const href of [...html.matchAll(/(?:src|href)="(\/(?:ui\/[^"?]+|landing\.js)[^"]*)"/g)].map(m=>m[1])){
 const target=path.join(web,href.split('?')[0].slice(1));
 assert.ok(fs.existsSync(target),'Missing landing asset: '+href);
}
assert.match(landing,/\/api\/billing\/catalog/,'Four plans must come from public server catalog');
assert.match(landing,/publicToken/,'Public client link bootstrapping must remain available');
vm.runInNewContext(fs.readFileSync(path.join(web,'ui/plans.js'),'utf8'),{window:{}});
new Function(landing);
const backend=fs.readFileSync(path.join(__dirname,'../backend/app.py'),'utf8');
assert.match(backend,/path == "\/api\/billing\/catalog"/);
console.log('PASS: modern motion landing, complete assets, client page and accurate catalog API');
