'use strict';

/* Camera frames stay on the device. Only reviewed dimensions reach the API. */
window.SmetraARScan = (() => {
  let revision = 0, dispose = () => {};
  const fmt = value => Number(value).toLocaleString('ru-RU', {maximumFractionDigits: 2});
  const esc = value => escapeHtml(String(value ?? ''));
  const steps = ['Длина', 'Ширина', 'Высота'];

  async function render(parentActive = () => true) {
    dispose();
    const mine = ++revision, owner = user, workspace = sessionStorage.getItem('workspace_id');
    let closed = false, stream = null, xr = null, renderer = null, hitSource = null;
    let nativeBusy = false, cameraRequest = 0, rooms = [], objects = [], dimensions = [], points = [], hit = null;
    let xrSupported = false, objectCreated = '', saving = false;
    const active = () => !closed && parentActive() && revision === mine && user === owner && tab === 'ar-scan' && workspace === sessionStorage.getItem('workspace_id');
    view(`<section class="ar-page" aria-label="AR Скан">
      <div class="ar-stage">
        <video class="ar-video" autoplay muted playsinline aria-label="Камера помещения"></video>
        <canvas class="ar-canvas" hidden aria-label="Пространственный замер"></canvas>
        <header class="ar-top"><div><span class="ar-eyebrow">ОБМЕР ПОМЕЩЕНИЯ</span><h1>AR Скан</h1></div><button type="button" class="ar-icon" data-ar-exit aria-label="Закрыть сканер">×</button></header>
        <div class="ar-camera-state" role="status"><span class="ar-camera-symbol" aria-hidden="true">◉</span><p data-ar-state>Открываю камеру…</p></div>
        <div class="ar-target" hidden aria-hidden="true"></div>
        <div class="ar-bottom">
          <p class="ar-instruction" data-ar-instruction>Наведите камеру на помещение. Изображение остаётся на телефоне.</p>
          <div class="ar-readouts" aria-live="polite">${steps.map((name, index) => `<div><span>${name}</span><strong data-ar-dimension="${index}">Не измерена</strong></div>`).join('')}</div>
          <div class="ar-controls"><button type="button" class="ar-secondary" data-ar-undo hidden>Отменить точку</button><button type="button" class="ar-primary" data-ar-start hidden>Начать AR-замер</button><button type="button" class="ar-primary" data-ar-point hidden disabled>Поставить точку</button><button type="button" class="ar-primary" data-ar-finish hidden>Проверить замер</button></div>
          <button type="button" class="ar-text-button" data-ar-manual>Ввести размеры вручную</button>
        </div>
      </div>
      <section class="ar-review" hidden aria-label="Проверка замера"><header><div><span class="ar-eyebrow">ПЕРЕД СОХРАНЕНИЕМ</span><h2>Проверьте размеры</h2></div><button type="button" class="ar-icon" data-ar-review-close aria-label="Вернуться к камере">×</button></header>
        <p class="ar-review-note">Форма рассчитана на прямоугольные комнаты. Сверьте размеры рулеткой. Найденная плоскость может покрывать только часть стены.</p>
        <form data-ar-form><div data-ar-rooms></div><label class="ar-label">Объект<select data-ar-object required><option value="">Загружаю объекты…</option></select></label><label class="ar-label" data-ar-new-object hidden>Название нового объекта<input maxlength="200" data-ar-object-name autocomplete="off"></label>
          <label class="ar-confirm"><input type="checkbox" data-ar-confirm required><span>Я проверил размеры и хочу добавить помещения в объект</span></label>
          <p data-ar-save-status role="status"></p><button class="ar-primary" type="submit" data-ar-save>Добавить помещения</button><button class="ar-secondary" type="button" data-ar-open-object hidden>Открыть объект и проверить</button>
        </form>
      </section>
    </section>`);
    const root = document.querySelector('.ar-page'), video = root.querySelector('video'), canvas = root.querySelector('canvas');
    const $ = selector => root.querySelector(selector);
    const state = text => {if (active()) $('[data-ar-state]').textContent = text;};
    const instruction = text => {if (active()) $('[data-ar-instruction]').textContent = text;};
    const stopCamera = () => {cameraRequest++;stream?.getTracks().forEach(track => track.stop());stream = null;video.srcObject = null;};
    const endXR = async () => {const session = xr;xr = null;hitSource?.cancel();hitSource = null;renderer?.setAnimationLoop(null);if (session) await session.end().catch(() => {});renderer?.dispose();renderer = null;};
    const cleanup = () => {if (closed) return;closed = true;stopCamera();void endXR();document.body.classList.remove('ar-scanning');document.removeEventListener('smetra:before-view', cleanup);document.removeEventListener('visibilitychange', visibility);window.removeEventListener('pagehide', cleanup);};
    dispose = cleanup;
    document.addEventListener('smetra:before-view', cleanup, {once: true});
    window.addEventListener('pagehide', cleanup, {once: true});
    function visibility() {if (document.hidden) {stopCamera();void endXR();} else if (active() && !nativeBusy && !xr && $('.ar-review').hidden) void openCamera();}
    document.addEventListener('visibilitychange', visibility);
    $('[data-ar-exit]').onclick = () => window.SmetraNavigateTo('assistant');

    const cameraError = error => ({NotAllowedError: 'Разрешите доступ к камере в настройках браузера и повторите попытку.',NotFoundError: 'Камера не найдена. Размеры можно ввести вручную.',NotReadableError: 'Камера занята. Закройте другое приложение с камерой.',SecurityError: 'Браузер запретил камеру. Откройте Сметру по HTTPS.'}[error?.name] || 'Не удалось открыть камеру. Повторите попытку или введите размеры вручную.');
    async function openCamera() {
      if (!active() || document.hidden || nativeBusy || xr) return;
      stopCamera();const request = cameraRequest;
      $('[data-ar-start]').hidden = false;$('[data-ar-start]').textContent = 'Повторить запуск камеры';
      $('[data-ar-start]').onclick = () => openCamera();
      if (!navigator.mediaDevices?.getUserMedia) {state('Этот браузер не предоставляет доступ к камере.');return;}
      state('Открываю камеру…');
      try {
        const captured = await navigator.mediaDevices.getUserMedia({video: {facingMode: {ideal: 'environment'},width: {ideal: 1280},height: {ideal: 720}},audio: false});
        if (!active() || request !== cameraRequest || document.hidden) {captured.getTracks().forEach(track => track.stop());return;}
        stream = captured;video.srcObject = stream;await video.play();
        if (!active() || request !== cameraRequest) return;
        state('Камера включена');root.classList.add('has-camera');
        xrSupported = Boolean(navigator.xr && await navigator.xr.isSessionSupported('immersive-ar').catch(() => false));
        if (!active() || request !== cameraRequest) return;
        $('[data-ar-start]').hidden = !xrSupported;$('[data-ar-start]').textContent = 'Начать AR-замер';$('[data-ar-start]').onclick = startWebXR;
        instruction(xrSupported ? 'Для замера нажмите "Начать AR-замер" и медленно поводите телефоном вдоль пола и стен.' : 'На этом устройстве нет пространственного AR в браузере. Камера помогает осмотреть комнату, размеры нужно ввести вручную.');
      } catch (error) {if (active() && request === cameraRequest) state(cameraError(error));}
    }

    function updateDimensions() {
      root.querySelectorAll('[data-ar-dimension]').forEach((label, index) => label.textContent = dimensions[index] ? fmt(dimensions[index]) + ' м' : 'Не измерена');
      $('[data-ar-finish]').hidden = dimensions.length !== 3;$('[data-ar-point]').hidden = dimensions.length === 3;
      $('[data-ar-undo]').hidden = !points.length;
      if (dimensions.length < 3) instruction(`${steps[dimensions.length]}. Наведите метку на ${points.length % 2 ? 'конец' : 'начало'} отрезка и поставьте точку.${dimensions.length === 2 ? ' Измеряйте от пола до потолка.' : ' Держите обе точки на одной высоте.'}`);
      else instruction('Размеры получены. Откройте проверку перед сохранением.');
    }
    function placePoint() {
      if (!xr || !hit || dimensions.length === 3 || !active()) return;
      const point = {x: hit.x,y: hit.y,z: hit.z};
      if (points.length % 2) {
        const first = points[points.length - 1], index = dimensions.length;
        const horizontal = Math.hypot(point.x - first.x, point.z - first.z), vertical = Math.abs(point.y - first.y);
        const length = index === 2 ? vertical : horizontal;
        if (length < 0.5 || length > 100) {instruction('Отрезок должен быть от 0,5 до 100 м. Переставьте вторую точку.');return;}
        if (index < 2 && vertical > 0.2 || index === 2 && horizontal > 0.35) {instruction(index === 2 ? 'Верхняя точка должна быть над нижней.' : 'Поставьте вторую точку на той же высоте.');return;}
        dimensions.push(length);
      }
      points.push(point);updateDimensions();
    }
    $('[data-ar-point]').onclick = placePoint;
    $('[data-ar-undo]').onclick = () => {if (points.length % 2 === 0) dimensions.pop();points.pop();updateDimensions();};
    $('[data-ar-finish]').onclick = () => showReview([{name: 'Комната 1',unit: 'м',length: dimensions[0].toFixed(2),width: dimensions[1].toFixed(2),height: dimensions[2].toFixed(2),source: 'ar'}]);

    async function startWebXR() {
      if (!active() || xr) return;
      stopCamera();$('[data-ar-start]').disabled = true;
      let session;
      try {
        // requestSession is called before the first await, inside the tap.
        const requested = navigator.xr.requestSession('immersive-ar', {requiredFeatures: ['hit-test', 'dom-overlay'],optionalFeatures: ['plane-detection'],domOverlay: {root}});
        session = await requested;
        if (!active()) {await session.end();return;}
        xr = session;
        const THREE = await import('/vendor/three-0.170.0.module.min.js');
        if (!active() || xr !== session) {await session.end().catch(() => {});return;}
        canvas.hidden = false;renderer = new THREE.WebGLRenderer({canvas,alpha: true,antialias: true});
        renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));renderer.setSize(root.clientWidth || innerWidth, root.clientHeight || innerHeight, false);
        renderer.xr.enabled = true;renderer.xr.setReferenceSpaceType('local');await renderer.xr.setSession(session);
        const reference = renderer.xr.getReferenceSpace(), viewer = await session.requestReferenceSpace('viewer');
        hitSource = await session.requestHitTestSource({space: viewer});
        const scene = new THREE.Scene(), camera = new THREE.PerspectiveCamera(), planes = new Map(), sessionRenderer = renderer;
        let lastPointCount = -1;
        const reticle = new THREE.Mesh(new THREE.RingGeometry(0.035, 0.045, 32).rotateX(-Math.PI / 2),new THREE.MeshBasicMaterial({color: 0xc9ffdf,side: THREE.DoubleSide}));
        reticle.matrixAutoUpdate = false;reticle.visible = false;scene.add(reticle);
        const line = new THREE.LineSegments(new THREE.BufferGeometry(),new THREE.LineBasicMaterial({color: 0xffffff}));scene.add(line);
        const pointMarks = new THREE.Points(new THREE.BufferGeometry(),new THREE.PointsMaterial({color: 0xffffff,size: 0.035}));scene.add(pointMarks);
        dimensions = [];points = [];updateDimensions();document.body.classList.add('ar-scanning');
        $('[data-ar-start]').hidden = true;$('[data-ar-point]').hidden = false;state('Ищу поверхности');
        // Overlay buttons should not also produce an XR select/tap.
        session.addEventListener('end', () => {hit = null;hitSource?.cancel();hitSource = null;if (xr === session) xr = null;sessionRenderer.setAnimationLoop(null);for (const mesh of planes.values()) {mesh.geometry.dispose();mesh.material.dispose();}reticle.geometry.dispose();reticle.material.dispose();line.geometry.dispose();line.material.dispose();pointMarks.geometry.dispose();pointMarks.material.dispose();sessionRenderer.dispose();if (renderer === sessionRenderer) renderer = null;if (active()) {document.body.classList.remove('ar-scanning');canvas.hidden = true;$('[data-ar-point]').hidden = true;$('[data-ar-undo]').hidden = true;$('[data-ar-start]').disabled = false;if (!document.hidden && $('.ar-review').hidden) void openCamera();}}, {once: true});
        renderer.setAnimationLoop((time, frame) => {
          if (!active() || !frame || xr !== session) return;
          const matches = frame.getHitTestResults(hitSource), pose = matches[0]?.getPose(reference);
          hit = pose?.transform.position || null;reticle.visible = Boolean(pose);
          if (pose) reticle.matrix.fromArray(pose.transform.matrix);
          $('[data-ar-point]').disabled = !pose;
          const detected = frame.detectedPlanes;
          if (detected) {
            for (const [plane, mesh] of planes) if (!detected.has(plane)) {scene.remove(mesh);mesh.geometry.dispose();mesh.material.dispose();planes.delete(plane);}
            for (const plane of [...detected].slice(0, 32)) {
              const planePose = frame.getPose(plane.planeSpace, reference);if (!planePose) continue;
              let mesh = planes.get(plane);
              if (!mesh) {mesh = new THREE.Mesh(new THREE.BufferGeometry(),new THREE.MeshBasicMaterial({color: plane.orientation === 'vertical' ? 0xa9f5c7 : 0xffffff,opacity: plane.orientation === 'vertical' ? 0.25 : 0.1,transparent: true,side: THREE.DoubleSide,depthWrite: false}));mesh.matrixAutoUpdate = false;planes.set(plane,mesh);scene.add(mesh);}
              if (mesh.userData.updated !== plane.lastChangedTime) {
                const polygon = Array.from(plane.polygon).slice(0, 256), vertices = [], indices = [];
                for (const p of polygon) vertices.push(p.x,p.y,p.z);
                for (let i = 1; i + 1 < polygon.length; i++) indices.push(0,i,i+1);
                mesh.geometry.dispose();mesh.geometry = new THREE.BufferGeometry();mesh.geometry.setAttribute('position',new THREE.Float32BufferAttribute(vertices,3));mesh.geometry.setIndex(indices);mesh.userData.updated = plane.lastChangedTime;
              }
              mesh.matrix.fromArray(planePose.transform.matrix);
            }
          }
          if (lastPointCount !== points.length) {
            lastPointCount = points.length;const vertices = points.flatMap(p => [p.x,p.y,p.z]);
            pointMarks.geometry.dispose();pointMarks.geometry = new THREE.BufferGeometry();pointMarks.geometry.setAttribute('position',new THREE.Float32BufferAttribute(vertices,3));
            line.geometry.dispose();line.geometry = new THREE.BufferGeometry();line.geometry.setAttribute('position',new THREE.Float32BufferAttribute(vertices.slice(0,Math.floor(points.length/2)*6),3));
          }
          state(pose ? 'Поверхность найдена' : 'Медленно поводите телефоном, чтобы найти поверхность');
          renderer.render(scene,camera);
        });
      } catch (error) {
        if (session) await session.end().catch(() => {});
        await endXR();if (!active()) return;
        canvas.hidden = true;$('[data-ar-start]').disabled = false;state(error?.name === 'NotAllowedError' ? 'Разрешите пространственный трекинг для AR.' : 'Браузер не смог запустить пространственный AR. Повторите запуск или введите размеры вручную.');
        $('[data-ar-start]').hidden = false;$('[data-ar-start]').textContent = 'Повторить AR-замер';$('[data-ar-start]').onclick = startWebXR;
      }
    }

    async function startNative() {
      if (!active() || nativeBusy) return;
      nativeBusy = true;state('Открываю AR-сканер приложения…');
      try {const result = await window.SmetraShell.call('ar.measure', {}, {timeout: 0});if (active() && result.rooms?.length) await showReview(result.rooms);}
      catch (error) {if (active()) state(error.code === 'cancelled' ? 'Замер закрыт. Можно начать заново.' : error.message || 'Не удалось запустить AR-замер.');}
      finally {nativeBusy = false;if (active()) {$('[data-ar-start]').hidden = false;$('[data-ar-start]').textContent = 'Открыть AR-сканер';$('[data-ar-start]').onclick = startNative;}}
    }
    function objectOptions() {
      if (!active()) return;
      $('[data-ar-object]').innerHTML = '<option value="">Выберите объект</option>' + objects.map(object => `<option value="${esc(object.id)}">${esc(object.name)}</option>`).join('') + '<option value="new">Новый объект</option>';
      if (objectCreated) $('[data-ar-object]').value = objectCreated;
    }
    async function loadObjects() {
      try {const data = await api('/construction/objects');if (active()) {objects = data.items || [];objectOptions();}}
      catch (error) {if (active()) {$('[data-ar-object]').innerHTML = '<option value="">Не удалось загрузить объекты</option>';$('[data-ar-save-status]').textContent = error.message;}}
    }
    async function showReview(values) {
      rooms = (values || []).slice(0,12).map((r, index) => ({name: String(r.name || 'Комната '+(index+1)),unit: 'м',length: r.length || '',width: r.width || '',height: r.height || '',openings_m2: r.openings_m2 || '0',source: r.source === 'manual' ? 'manual' : 'ar'}));
      $('.ar-review').hidden = false;stopCamera();await endXR();if (!active()) return;
      $('[data-ar-rooms]').innerHTML = rooms.map((room, index) => `<fieldset data-ar-room="${index}"><legend>Помещение ${index+1}${room.source === 'manual' ? ' · ручной обмер' : ' · AR-обмер'}</legend><label class="ar-label">Название<input name="name" maxlength="120" required value="${esc(room.name)}"></label><div class="ar-dimensions">${[['length','Длина, м'],['width','Ширина, м'],['height','Высота, м']].map(([key,label])=>`<label class="ar-label">${label}<input name="${key}" type="number" inputmode="decimal" min="0.5" max="100" step="0.01" required value="${esc(room[key])}"></label>`).join('')}</div><label class="ar-label">Окна и двери, м²<input name="openings_m2" type="number" inputmode="decimal" min="0" step="0.01" required value="${esc(room.openings_m2)}"></label></fieldset>`).join('');
      $('[data-ar-confirm]').checked = false;$('[data-ar-save-status]').textContent = '';$('[data-ar-save]').disabled = false;
      await loadObjects();
    }
    $('[data-ar-manual]').onclick = () => showReview([{name: 'Комната 1',source: 'manual'}]);
    root.addEventListener('beforexrselect', event => event.preventDefault());
    $('[data-ar-review-close]').onclick = () => {$('.ar-review').hidden = true;if (!nativeBusy) void openCamera();};
    $('[data-ar-object]').onchange = () => {const fresh = $('[data-ar-object]').value === 'new';$('[data-ar-new-object]').hidden = !fresh;$('[data-ar-object-name]').required = fresh;};
    $('[data-ar-open-object]').onclick = () => window.SmetraNavigateTo('construction');
    $('[data-ar-form]').onsubmit = async event => {
      event.preventDefault();if (saving || !active()) return;
      const selected = $('[data-ar-object]').value;if (!selected || !$('[data-ar-confirm]').checked) return;
      const measured = [...root.querySelectorAll('[data-ar-room]')].map((fieldset,index) => {const row = {...rooms[index]};for (const input of fieldset.querySelectorAll('input')) row[input.name] = input.value;return row;});
      saving = true;$('[data-ar-save]').disabled = true;$('[data-ar-save-status]').textContent = 'Проверяю размеры…';
      let importing = false;
      try {
        let objectId = selected;
        if (selected === 'new') {if (!objectCreated) {const result = await api('/construction/objects',{method: 'POST',body: JSON.stringify({name: $('[data-ar-object-name]').value.trim()})});objectCreated = result.object.id;}objectId = objectCreated;}
        if (!active()) return;
        await api('/construction/objects/'+encodeURIComponent(objectId)+'/scan/preview',{method: 'POST',body: JSON.stringify({rooms: measured})});
        if (!active()) return;
        importing = true;
        const result = await api('/construction/objects/'+encodeURIComponent(objectId)+'/scan/import',{method: 'POST',body: JSON.stringify({rooms: measured,review_confirmed: true})});
        if (!active()) return;
        $('[data-ar-save-status]').textContent = 'Добавлено помещений: '+result.zones.length+'.';$('[data-ar-open-object]').hidden = false;$('[data-ar-save]').hidden = true;
      } catch (error) {
        if (!active()) return;
        const uncertain = importing && !error.status;
        $('[data-ar-save-status]').textContent = uncertain ? 'Не удалось подтвердить сохранение. Проверьте помещения объекта перед повторным импортом.' : error.message;
        $('[data-ar-save]').disabled = uncertain;if (uncertain) $('[data-ar-open-object]').hidden = false;
      } finally {saving = false;if (active() && !importing) $('[data-ar-save]').disabled = false;}
    };
    if (window.SmetraShell?.available) {
      await window.SmetraShell.ready;if (!active()) return;
      try {const info = await window.SmetraShell.call('ar.status');if (!active()) return;if (info.status === 'supported') {void startNative();return;}} catch {}
    }
    await openCamera();
  }
  return {render,stop: () => dispose()};
})();
