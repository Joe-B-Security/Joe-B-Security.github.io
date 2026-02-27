(function() {
  if (window.location.pathname !== '/') return;

  var canvas = document.createElement('canvas');
  canvas.style.position = 'fixed';
  canvas.style.top = '0';
  canvas.style.left = '0';
  // No CSS width/height — pixel dimensions drive size so there's no
  // vw/vh vs innerWidth/Height mismatch on mobile Safari
  canvas.style.zIndex = '1';
  canvas.style.pointerEvents = 'none';
  document.body.appendChild(canvas);

  // Raise page content above canvas — no background color hacking needed
  document.body.classList.add('threebody-active');

  // Hide canvas immediately on link click so it doesn't flash during
  // page transition (fixes Android Firefox rendering glitch)
  document.addEventListener('click', function(e) {
    var link = e.target.closest('a');
    if (link && link.href && link.href.indexOf('#') !== 0) {
      canvas.style.display = 'none';
      document.body.classList.remove('threebody-active');
    }
  });

  // Clean up when leaving the page (bfcache)
  window.addEventListener('pagehide', function() {
    canvas.style.display = 'none';
    document.body.classList.remove('threebody-active');
  });
  window.addEventListener('pageshow', function(e) {
    if (e.persisted) {
      canvas.style.display = '';
      document.body.classList.add('threebody-active');
    }
  });

  var ctx = canvas.getContext('2d');
  var width, height, scale;
  var bodies = [];

  function resetBodies() {
    var x1 = 0.97000436, y1 = -0.24308753;
    var vx3 = -0.93240737, vy3 = -0.86473146;
    bodies = [
      { x: x1, y: y1, vx: -vx3/2, vy: -vy3/2, color: '#555555', trail: [] },
      { x: -x1, y: -y1, vx: -vx3/2, vy: -vy3/2, color: '#888888', trail: [] },
      { x: 0, y: 0, vx: vx3, vy: vy3, color: '#aaaaaa', trail: [] }
    ];
  }

  function resize() {
    width = window.innerWidth;
    height = window.innerHeight;
    canvas.width = width;
    canvas.height = height;
    scale = Math.min(width, height) * 0.55;
  }

  // visualViewport fires on iOS when address bar shows/hides; fallback to resize
  if (window.visualViewport) {
    window.visualViewport.addEventListener('resize', resize);
  } else {
    window.addEventListener('resize', resize);
  }
  resize();
  resetBodies();

  var lastTime = 0;
  var frameInterval = 1000 / 60;

  function loop(timestamp) {
    requestAnimationFrame(loop);
    var delta = timestamp - lastTime;
    if (delta < frameInterval) return;
    lastTime = timestamp - (delta % frameInterval);

    var G = 1, dt = 0.002, softening = 0.01, subSteps = 4;

    for (var step = 0; step < subSteps; step++) {
      var ax = [0, 0, 0], ay = [0, 0, 0];
      for (var i = 0; i < 3; i++) {
        for (var j = i + 1; j < 3; j++) {
          var dx = bodies[j].x - bodies[i].x;
          var dy = bodies[j].y - bodies[i].y;
          var distSq = dx*dx + dy*dy + softening;
          var dist = Math.sqrt(distSq);
          var f = G / distSq;
          ax[i] += f * dx / dist; ay[i] += f * dy / dist;
          ax[j] -= f * dx / dist; ay[j] -= f * dy / dist;
        }
      }
      for (var i = 0; i < 3; i++) {
        bodies[i].vx += ax[i] * dt; bodies[i].vy += ay[i] * dt;
        bodies[i].x += bodies[i].vx * dt; bodies[i].y += bodies[i].vy * dt;
      }
    }

    for (var i = 0; i < 3; i++) {
      bodies[i].trail.push({ x: bodies[i].x, y: bodies[i].y });
      if (bodies[i].trail.length > 80) bodies[i].trail.shift();
    }

    ctx.imageSmoothingEnabled = false;
    ctx.clearRect(0, 0, width, height);

    var colors = [[85,85,85],[136,136,136],[170,170,170]];
    for (var i = 0; i < 3; i++) {
      var body = bodies[i], c = colors[i];
      for (var t = 0; t < body.trail.length; t++) {
        var pos = body.trail[t];
        var opacity = (t + 1) / body.trail.length;
        ctx.fillStyle = 'rgba(' + c[0] + ',' + c[1] + ',' + c[2] + ',' + opacity + ')';
        var sx = Math.round((width/2 + pos.x * scale) / 4) * 4;
        var sy = Math.round((height/2 + pos.y * scale) / 4) * 4;
        ctx.fillRect(sx - 1, sy - 1, 3, 3);
      }
    }

    for (var i = 0; i < 3; i++) {
      var body = bodies[i];
      ctx.fillStyle = body.color;
      var sx = Math.round((width/2 + body.x * scale) / 4) * 4;
      var sy = Math.round((height/2 + body.y * scale) / 4) * 4;
      ctx.fillRect(sx - 2, sy - 2, 4, 4);
      ctx.fillRect(sx - 2, sy - 6, 4, 4);
      ctx.fillRect(sx - 2, sy + 2, 4, 4);
      ctx.fillRect(sx - 6, sy - 2, 4, 4);
      ctx.fillRect(sx + 2, sy - 2, 4, 4);
    }
  }

  requestAnimationFrame(loop);
})();
