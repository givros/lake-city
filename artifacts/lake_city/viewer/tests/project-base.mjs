import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {readFile} from 'node:fs/promises';
import path from 'node:path';
import {chromium} from 'playwright';

const root=path.resolve(process.argv[2]??'dist-pages-check');
const base='/lake-city/';
const types={'.html':'text/html','.js':'text/javascript','.css':'text/css','.json':'application/json','.bin':'application/octet-stream','.glb':'model/gltf-binary'};
const server=createServer(async(req,res)=>{
  try{
    const pathname=decodeURIComponent(new URL(req.url,'http://127.0.0.1').pathname);
    if(pathname==='/favicon.ico'){res.writeHead(204);res.end();return;}
    if(!pathname.startsWith(base)){res.writeHead(404);res.end();return;}
    const file=path.resolve(root,pathname.slice(base.length)||'index.html');
    if(!file.startsWith(root+path.sep)){res.writeHead(403);res.end();return;}
    const data=await readFile(file);
    res.writeHead(200,{'Content-Type':types[path.extname(file)]??'application/octet-stream'});res.end(data);
  }catch{res.writeHead(404);res.end();}
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
let browser;
try{
  browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||undefined,headless:true,args:['--enable-unsafe-webgpu','--use-angle=d3d11']});
  const page=await browser.newPage({viewport:{width:1600,height:1000},deviceScaleFactor:1});
  const errors=[],responses=[];
  page.on('pageerror',e=>errors.push(e.message));
  page.on('response',r=>responses.push({url:new URL(r.url()).pathname,status:r.status()}));
  const url=`http://127.0.0.1:${server.address().port}${base}`;
  await page.goto(url,{waitUntil:'domcontentloaded'});
  await page.waitForFunction(()=>window.__cityTest?.ready||!document.getElementById('error').hidden,undefined,{timeout:180000});
  const state=await page.evaluate(()=>window.__cityTest?.ready?window.__cityTest.getState():null);
  assert.ok(state,await page.locator('#error-message').textContent());
  for(const resource of ['city.json','geometry.bin','traffic_network.json','characters/pedestrian.glb','characters/pedestrian.json']){
    assert.ok(responses.some(r=>r.url===`${base}assets/${resource}`&&r.status===200),`Missing project-base resource: ${resource}`);
  }
  assert.equal(responses.filter(r=>r.status>=400).length,0,'Resource requests failed');
  assert.equal(responses.filter(r=>r.url.startsWith('/assets/')).length,0,'A resource escaped the project base');
  assert.equal(state.life.vehicles,562);
  assert.equal(state.life.pedestrians.count,80);
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({status:'passed',base,vehicles:state.life.vehicles,pedestrians:state.life.pedestrians.count,resources:responses,backend:state.backend},null,2));
}finally{
  if(browser)await browser.close();
  await new Promise(resolve=>server.close(resolve));
}
