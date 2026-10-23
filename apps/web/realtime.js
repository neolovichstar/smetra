'use strict';
window.SmetraRealtime = (() => {
  let baseUrl='',apiKey='',socket=null,heartbeat=null,reconnectTimer=null,reconnectAttempts=0,seq=0,manuallyStopped=false;
  const channels=new Map(),nextRef=()=>String(++seq);
  const wsUrl=()=>{const url=new URL(baseUrl.replace(/\/$/,'')+'/realtime/v1/websocket');url.protocol=url.protocol==='https:'?'wss:':'ws:';url.searchParams.set('apikey',apiKey);url.searchParams.set('vsn','2.0.0');return url.toString();};
  function send(frame){if(!socket||socket.readyState!==1)return false;try{socket.send(JSON.stringify(frame));return true;}catch{return false;}}
  function join(topic,item){if(!socket||socket.readyState!==1||item.joined)return;item.joinRef=nextRef();item.joined=true;send([item.joinRef,nextRef(),'realtime:'+topic,'phx_join',{config:{broadcast:{ack:false,self:false},presence:{enabled:false,key:''},postgres_changes:[],private:false}}]);}
  function clearTimers(){if(heartbeat!==null)clearInterval(heartbeat);if(reconnectTimer!==null)clearTimeout(reconnectTimer);heartbeat=reconnectTimer=null;}
  function scheduleReconnect(){if(manuallyStopped||!channels.size||reconnectTimer!==null||!apiKey||!baseUrl)return;const delay=Math.min(30000,500*(2**Math.min(reconnectAttempts++,6)));reconnectTimer=setTimeout(()=>{reconnectTimer=null;connect();},delay);}
  function connect(){
    if(manuallyStopped||!channels.size||!apiKey||!baseUrl)return;if(socket&&(socket.readyState===0||socket.readyState===1))return;
    let ws;try{ws=new WebSocket(wsUrl());}catch{scheduleReconnect();return;}socket=ws;
    ws.onopen=()=>{if(socket!==ws)return;reconnectAttempts=0;for(const [topic,item] of channels){item.joined=false;join(topic,item);}if(heartbeat!==null)clearInterval(heartbeat);heartbeat=setInterval(()=>send([null,nextRef(),'phoenix','heartbeat',{}]),25000);channels.forEach(item=>item.listeners.forEach(fn=>{try{fn('realtime_connected',{});}catch{}}));};
    ws.onmessage=event=>{
      let frame;try{frame=JSON.parse(event.data);}catch{return;}if(!Array.isArray(frame)||frame.length<5)return;
      const topicName=String(frame[2]||''),eventName=String(frame[3]||''),payload=frame[4]&&typeof frame[4]==='object'?frame[4]:{};
      if(eventName==='phx_reply'&&payload.status==='error'){const topic=topicName.startsWith('realtime:')?topicName.slice(9):'',item=channels.get(topic);if(item){item.joined=false;item.listeners.forEach(fn=>{try{fn('realtime_unavailable',{});}catch{}});}return;}
      if(eventName!=='broadcast')return;const topic=topicName.startsWith('realtime:')?topicName.slice(9):'',item=channels.get(topic);if(!item)return;
      const actualEvent=typeof payload.event==='string'?payload.event:'';
      item.listeners.forEach(fn=>{try{fn(actualEvent,{});}catch{}});
    };
    ws.onerror=()=>{};ws.onclose=()=>{if(socket!==ws)return;socket=null;clearTimers();for(const item of channels.values())item.joined=false;scheduleReconnect();};
  }
  function configure(url,key){
    if(typeof url!=='string'||!url.startsWith('https://')||typeof key!=='string'||!key.trim())return false;
    let parsed;try{parsed=new URL(url);}catch{return false;}if(parsed.protocol!=='https:'||!parsed.hostname)return false;
    const normalized=parsed.origin;if(normalized===baseUrl&&key===apiKey){connect();return true;}
    baseUrl=normalized;apiKey=key.trim();manuallyStopped=false;if(socket){try{socket.close();}catch{}socket=null;}clearTimers();for(const item of channels.values())item.joined=false;connect();return true;
  }
  function subscribe(topic,listener){
    if(typeof topic!=='string'||topic.length<20||topic.length>180||typeof listener!=='function')return ()=>{};
    let item=channels.get(topic);if(!item){item={listeners:new Set(),joined:false,joinRef:null};channels.set(topic,item);}item.listeners.add(listener);if(!socket||socket.readyState>1)connect();else join(topic,item);
    let closed=false;return ()=>{if(closed)return;closed=true;const current=channels.get(topic);if(!current)return;current.listeners.delete(listener);if(!current.listeners.size){if(current.joined)send([current.joinRef,nextRef(),'realtime:'+topic,'phx_leave',{}]);channels.delete(topic);}if(!channels.size){manuallyStopped=true;clearTimers();const existing=socket;socket=null;if(existing)try{existing.close();}catch{}manuallyStopped=false;}};
  }
  function close(){manuallyStopped=true;channels.clear();clearTimers();const existing=socket;socket=null;if(existing)try{existing.close();}catch{}}
  return {configure,subscribe,close,isConnected:()=>!!socket&&socket.readyState===1,isSubscribed:topic=>!!channels.get(topic)?.joined,topicCount:()=>channels.size};
})();
