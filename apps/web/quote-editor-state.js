/* One writer per editor. Retries replay the captured request, never newer input. */
(() => {
  const clone=value=>structuredClone(value),equal=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
  class History {
    constructor(value){this.entries=[clone(value)];this.index=0;this.group=null;this.time=0}
    push(value,group=null){if(equal(this.entries[this.index],value))return;const now=Date.now();
      if(group&&group===this.group&&now-this.time<700&&this.index>0)this.entries[this.index]=clone(value);
      else{this.entries.splice(this.index+1);this.entries.push(clone(value));if(this.entries.length>60)this.entries.shift();this.index=this.entries.length-1}
      this.group=group;this.time=now;
    }
    undo(){this.group=null;if(this.index===0)return null;return clone(this.entries[--this.index])}
    redo(){this.group=null;if(this.index===this.entries.length-1)return null;return clone(this.entries[++this.index])}
    get canUndo(){return this.index>0}get canRedo(){return this.index<this.entries.length-1}
  }
  function writer(options){
    let quote=clone(options.quote||{}),saved=JSON.stringify(options.data()),pending=null,busy=null,timer,stopped=false,blocked=false,attempt=0;
    const active=()=>!stopped&&options.active();
    const persist=()=>{if(active())options.persist({quote:clone(quote),snapshot:options.snapshot(),pending:pending?clone(pending):null,savedAt:Date.now()})};
    const state=(kind,text)=>{if(active())options.state(kind,text)};
    const schedule=(delay=1800)=>{clearTimeout(timer);if(active()&&!blocked)timer=setTimeout(()=>save().catch(()=>{}),delay)};
    async function save(){
      clearTimeout(timer);if(!active())return null;if(busy)return busy;
      if(blocked){state('conflict','Смета изменилась на сервере. Ваши правки сохранены на устройстве.');return null}
      if(!pending){
        if(!options.valid()){persist();state('invalid','Заполните обязательные поля. Правки сохранены на устройстве.');return null}
        const data=clone(options.data()),fingerprint=JSON.stringify(data);
        if(quote.id&&fingerprint===saved){state('saved','Сохранено');return quote}
        pending={path:quote.id?'/quotes/'+quote.id+'/autosave':'/quotes',method:quote.id?'PATCH':'POST',body:{...data,...(quote.id?{revision:quote.revision}:{})},fingerprint,key:crypto.randomUUID()};persist();
      }
      const captured=clone(pending);state('saving','Сохраняем…');
      busy=(async()=>{
        try{
          const result=await options.request(captured.path,{method:captured.method,headers:{'Idempotency-Key':captured.key},body:JSON.stringify(captured.body)});
          if(!active())return null;
          const first=!quote.id;quote=result.quote;saved=captured.fingerprint;pending=null;attempt=0;
          if(first&&result.replayed&&quote.revision>1){options.accept(quote,true);quote={...quote,revision:1};blocked=true;state('conflict','Созданная смета уже изменена на другом устройстве. Правки не перезаписаны.');persist();return null}
          options.accept(quote,first);persist();
          if(JSON.stringify(options.data())!==saved){state('pending','Есть новые правки');schedule()}
          else state('saved','Сохранено');return quote;
        }catch(error){
          if(!active())return null;
          if(error.status===409){blocked=true;state('conflict','Смета изменилась на сервере. Правки не перезаписаны.')}
          else if(error.status===401||error.status===403||error.status===402){blocked=true;state('blocked',error.message)}
          else if(error.status===400){pending=null;state('invalid',error.message)}
          else{state('offline','Нет связи. Правки на устройстве; можно повторить сохранение.');if(attempt<3)schedule([4000,10000,30000][attempt++])}
          persist();return null;
        }finally{busy=null}
      })();return busy;
    }
    const online=()=>{if(active()){attempt=0;schedule(0)}};
    const beforeUnload=event=>{if(active()&&(pending||JSON.stringify(options.data())!==saved)){persist();event.preventDefault();event.returnValue=''}};
    window.addEventListener('online',online);window.addEventListener('beforeunload',beforeUnload);
    return {
      changed(){persist();if(!blocked){state('pending','Правки сохранены на устройстве');schedule()}},
      async flush(){let result;for(let n=0;n<4;n++){result=await save();if(!result||!active()||blocked)return null;if(!pending&&JSON.stringify(options.data())===saved)return result}schedule();return null},
      retry(){attempt=0;return save()},
      restore(value){if(value.pending)pending=clone(value.pending);persist();schedule(0)},
      conflict(base){if(base)quote=clone(base);blocked=true;pending=null;clearTimeout(timer);state('conflict','Смета изменилась на сервере. Правки не перезаписаны.');persist()},
      stop(keep=true){if(keep)persist();stopped=true;clearTimeout(timer);window.removeEventListener('online',online);window.removeEventListener('beforeunload',beforeUnload)},
      get quote(){return quote},get blocked(){return blocked}
    };
  }
  window.SmetraQuoteEditorState={History,writer};
})();
