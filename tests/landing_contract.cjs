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
// Search and link previews: canonical, Open Graph image on disk, FAQ markup equal to the visible FAQ.
assert.match(html,/<link rel="canonical" href="https:\/\/smetra\.online\/">/);
assert.match(html,/<meta property="og:image" content="https:\/\/smetra\.online\/assets\/og\/smetra-og\.jpg">/);
assert.ok(fs.existsSync(path.join(web,'assets/og/smetra-og.jpg')),'Open Graph image is missing');
const ld=JSON.parse(html.match(/<script type="application\/ld\+json">([\s\S]*?)<\/script>/)[1]);
const faq=ld['@graph'].find(node=>node['@type']==='FAQPage').mainEntity.map(q=>[q.name,q.acceptedAnswer.text]);
const visible=[...html.matchAll(/<details><summary>(.*?)<\/summary><p>(.*?)<\/p><\/details>/g)].map(m=>[m[1],m[2]].map(t=>t.replace(/<[^>]+>/g,'').replace(/&nbsp;/g,'\u00a0').replace(/&amp;/g,'&')));
assert.deepEqual(faq,visible,'FAQ structured data must match the visible FAQ — regenerate it after editing the questions');
const sitemap=fs.readFileSync(path.join(web,'sitemap.xml'),'utf8'),robots=fs.readFileSync(path.join(web,'robots.txt'),'utf8');
assert.doesNotMatch(sitemap,/vercel\.app/,'Sitemap must list the production domain');
assert.match(robots,/Sitemap: https:\/\/smetra\.online\/sitemap\.xml/);
assert.match(landing,/noindex/,'Client quote pages must stay out of search results');
console.log('PASS: modern motion landing, complete assets, client page and accurate catalog API');
