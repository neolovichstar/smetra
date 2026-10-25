markdown-it 15.0.2, MIT, https://github.com/markdown-it/markdown-it

Browser build and license copied from the pinned npm release, after checking the
registry SHA-512 integrity of the complete tarball. No runtime CDN dependency.

`markdown-it-15.0.2.min.js` SHA-256:
`635972b985228e8af9f0143647c68616b7a3bb09f6946e7e4a52e43dcf5e7be5`

Smetra disables raw HTML, permits only HTTP(S) links, and renders image alt text
without fetching remote images. The adapter lives in `../chat-markdown.js`.

three.js 0.170.0, MIT, https://github.com/mrdoob/three.js

Copied from the pinned npm tarball after checking the registry SHA-512 integrity
(`FQK+LEpYc0fBD+J8g6oSEyyNzjp+Q7Ks1C568WWaoMRLW+TkNNWmenWeGgJjV105Gd+p/2ql1ZcjYvNiPZBhuQ==`).
`three-0.170.0.module.min.js` is `build/three.module.min.js` (SHA-256
`08fd7545d13d2c7fb65ab691530a802dafefd638596501854f267d0fb13c39e7`).
`three-rounded-box-0.170.0.js` and `three-room-environment-0.170.0.js` are
`examples/jsm/geometries/RoundedBoxGeometry.js` and
`examples/jsm/environments/RoomEnvironment.js` with the bare `'three'` import
rewritten to the local file (no import map, so the CSP needs no inline script).
Used only by the landing hero (`../room3d.js`), loaded after the page is idle.
