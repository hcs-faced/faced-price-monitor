# Procedura — Raccolta prezzi Sephora dal Chrome dell'ufficio

Sephora blocca le raccolte automatiche (server GitHub e runner del PC, anche con browser automatico: errore 403). Dal Chrome dell'ufficio (account aziendale, estensione Claude) le pagine si leggono normalmente. Questa procedura la esegue Claude, a mano o come attività programmata (lunedì e giovedì).

**Requisiti:** PC dell'ufficio acceso, Chrome aperto con l'estensione Claude collegata, login alla dashboard già fatto in Chrome (sessione salvata nel browser). Nessuna password o chiave va inserita.

## Passo 1 — Lettura in una scheda Sephora
Aprire `https://www.sephora.it/` in una nuova scheda di Chrome (strumenti Claude in Chrome) ed eseguire con javascript_tool lo script seguente. Gira in background (circa 2 minuti): controllare `window.__done` ogni 30–40 secondi.

Elenco pagine: `[id product_urls, codice Sephora, variante]` — sito Sephora `site_id = 5`. La pagina si apre come `/p/faced-<codice>.html`. Se si aggiungono pagine Sephora in "Gestione prodotti", aggiornare questo elenco (query: `product_urls` con `site_id=5`, attive, prodotto attivo).

```js
const T=[[62,"P2633002","Chiara"],[63,"P2633002","Scura"],[64,"P3516049","30 ml"],[65,"P3516049","50 ml"],[66,"P2632002","Light"],[67,"P2632002","Medium"],[68,"P2632002","Caramel"],[69,"P1000208055","Light"],[70,"P1000208055","Medium"],[71,"P1000208055","Caramel"],[72,"500724",""],[73,"836618",""],[74,"641250","4 fiale"],[75,"706340",""],[76,"469914",""],[292,"469915",""],[293,"356142",""],[294,"554750","400 ml"],[295,"610014",""],[296,"500725","Singola"],[297,"570207",""],[298,"559635",""],[299,"554754",""],[300,"341833",""],[301,"554751","30 ml"],[302,"355029",""],[303,"392323",""],[304,"610016",""],[305,"341832",""],[306,"341834",""],[307,"554752",""],[308,"530516","5 pezzi"],[309,"341827",""],[310,"469916","30 ml"],[311,"530517",""],[312,"836185",""],[313,"836741",""],[314,"836186",""],[315,"789896",""],[316,"774613",""],[317,"821366",""],[318,"836738",""],[319,"663474",""],[320,"836739",""],[321,"812928",""],[322,"818111",""],[323,"743030",""],[324,"659784",""],[325,"722878",""],[326,"706339",""],[327,"771819",""],[328,"706341",""],[329,"824204",""],[330,"838967",""],[331,"836740",""],[332,"735976",""],[333,"798306",""],[334,"770627",""],[335,"788293",""],[336,"821365",""],[337,"770465",""],[338,"836737",""],[339,"838954",""],[340,"818551",""],[341,"671033",""],[342,"730497",""],[343,"730498",""],[344,"771818",""],[345,"730499","SPF30"],[346,"730500","200 ml"],[348,"730501",""],[350,"770481","SPF50"]];
const WORDS={chiara:['light','chiara','clair'],scura:['dark','scura','fonc'],light:['light','clair','chiara'],medium:['medium'],caramel:['caramel']};
function parse(h,variant){ const u=h.replace(/\\"/g,'"'); const title=((h.match(/<title>([^<]*)<\/title>/)||[])[1]||'').split(' | ')[0].trim(); let price=+((h.match(/itemProp="price" content="([\d.]+)"/)||[])[1]||NaN); const avail=/itemProp="availability" (?:href|content)="[^"]*InStock/.test(h); const m=u.match(/"price":([\d.]+),"discountPercentage":(\d+),"originalPrice":([\d.]+)/); let list=m?+m[3]:null; let stock=avail; let vname='';
 const segs=u.split('{"id":"').slice(1).map(s=>{const n=(s.match(/^\d+","name":"([^"]+)"/)||[])[1]; const p=(s.match(/"price":([\d.]+)/)||[])[1]; const o=(s.match(/"originalPrice":([\d.]+)/)||[])[1]; const a=(s.match(/"isAvailable":(true|false)/)||[])[1]; return n&&p?{n,p:+p,o:o?+o:null,a:a==='true'}:null}).filter(Boolean);
 const uniq=[...new Map(segs.map(s=>[s.n,s])).values()];
 if(variant && uniq.length>1){ const v=variant.toLowerCase(); const ws=WORDS[v]||[v.replace(' ml','ml')]; const hit=uniq.find(s=>ws.some(w=>s.n.toLowerCase().replace(' ml','ml').includes(w.replace(' ml','ml')))); if(hit){price=hit.p; list=hit.o; stock=hit.a; vname=hit.n;} }
 return {title:(title+(vname?' – '+vname:'')).slice(0,200), price:isNaN(price)?null:price, list, stock, nv:uniq.length}; }
window.__R=[]; window.__done=false; (async()=>{ const cache={}; for(const [id,code,variant] of T){ try{ if(!cache[code]){ const r=await fetch('/p/faced-'+code+'.html',{credentials:'include'}); cache[code]={s:r.status,h:r.status===200?await r.text():''}; await new Promise(x=>setTimeout(x,1200)); } const c=cache[code]; if(c.s!==200){window.__R.push({id,err:'HTTP '+c.s}); continue;} const o=parse(c.h,variant); window.__R.push(Object.assign({id},o, o.price==null?{err:'prezzo non trovato'}:{})); }catch(e){window.__R.push({id,err:String(e).slice(0,80)});} } window.__done=true; })(); 'started'
```

Quando `window.__done` è true: `window.__C=JSON.stringify(window.__R.map(r=>[r.id,r.price,r.list,r.stock?1:0,r.err||'']))` e leggerlo a pezzi di ~900 caratteri (`window.__C.slice(0,900)`, poi `.slice(900)`, ...). Se molte righe hanno `HTTP 403`, fermarsi e avvisare (Sephora ha bloccato anche il Chrome).

## Passo 2 — Salvataggio dalla dashboard
Nella stessa scheda aprire `https://hcs-faced.github.io/faced-price-monitor/dashboard/` (login già fatto) ed eseguire, incollando in `C` l'array letto al passo 1:

```js
const C=[/* incollare qui */];
const {data:pu}=await sb.from('product_urls').select('id,url,product_id').in('id',C.map(c=>c[0]));
const map=Object.fromEntries(pu.map(p=>[p.id,p]));
const r=await sb.from('runs').insert({status:'running'}).select('id');
const run_id=r.data[0].id;
const rows=C.map(([id,price,list,st,err])=>({run_id, product_id:map[id].product_id, site_id:5, seller_id:'', url:map[id].url, price, list_price:list, in_stock:!!st, error:err||null}));
const ins=await sb.from('observations').insert(rows);
const ok=rows.filter(x=>x.price!=null).length;
await sb.from('runs').update({status:ins.error?'error':(ok<rows.length?'partial':'ok'), finished_at:new Date().toISOString(), summary:{source:'chrome-sephora', retailer_rows:rows.length, prices_found:ok, errors:rows.length-ok, log:['Sephora letta dal Chrome dell\'ufficio']}}).eq('id',run_id);
'run '+run_id+' '+(ins.error?ins.error.message:'ok '+ok+'/'+rows.length)
```

## Passo 3 — Esito
Chiudere le schede aperte e riferire: prezzi letti su 72, offerte Sephora oltre −20% rispetto a faced.com (vista `v_latest`, `site_id=5`, `deviation_pct <= -20`).
