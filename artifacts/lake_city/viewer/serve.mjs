import {createServer} from 'node:http';
import {readFile,stat} from 'node:fs/promises';
import path from 'node:path';
const root=path.resolve('dist');
const types={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.json':'application/json','.bin':'application/octet-stream','.png':'image/png','.svg':'image/svg+xml'};
const server=createServer(async(req,res)=>{
  try{
    const pathname=decodeURIComponent(new URL(req.url,'http://127.0.0.1').pathname);
    if(pathname==='/favicon.ico'){res.writeHead(204);res.end();return;}
    const file=path.resolve(root,'.'+(pathname==='/'?'/index.html':pathname));
    if(!file.startsWith(root+path.sep)){res.writeHead(403);res.end();return;}
    const data=await readFile(file);const info=await stat(file);
    res.writeHead(200,{'Content-Type':types[path.extname(file)]??'application/octet-stream','Content-Length':data.length,'Cache-Control':'no-cache','Last-Modified':info.mtime.toUTCString()});
    res.end(data);
  }catch{res.writeHead(404,{'Content-Type':'text/plain'});res.end('Not found');}
});
server.listen(4173,'127.0.0.1',()=>console.log('Lake City: http://127.0.0.1:4173/'));
