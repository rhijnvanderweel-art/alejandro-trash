"""Headless renderer: draws manifold3d solids with three.js in Chromium (Playwright).

Usage (from python):
    render(parts: dict[name -> (Manifold, hexcolor)], out_png, views=[...])

Needs a copy of three.min.js; set THREE_JS env var or pass three_js=...
(`npm install three@0.160.0` and point to node_modules/three/build/three.min.js).
"""
import json
import os
import tempfile
import subprocess

import numpy as np


def _mesh_payload(m, color, opacity=1.0):
    mesh = m.to_mesh()
    v = np.asarray(mesh.vert_properties)[:, :3].astype(np.float32)
    t = np.asarray(mesh.tri_verts).astype(np.int32)
    # flat shading: un-index
    pos = v[t.reshape(-1)]
    return {"pos": pos.round(3).reshape(-1).tolist(), "color": color, "opacity": opacity}


HTML = """<!doctype html><html><head><meta charset=utf-8>
<style>html,body{margin:0;background:#fff}</style></head><body>
<script src="THREEJS"></script>
<script>
const data = DATA;
const W = data.w, H = data.h;
const renderer = new THREE.WebGLRenderer({antialias:true, preserveDrawingBuffer:true});
renderer.setSize(W, H); renderer.setClearColor(0xffffff);
document.body.appendChild(renderer.domElement);
const scene = new THREE.Scene();
scene.add(new THREE.AmbientLight(0xffffff, 0.55));
const d1 = new THREE.DirectionalLight(0xffffff, 0.75); d1.position.set(1,-1.5,2.5); scene.add(d1);
const d2 = new THREE.DirectionalLight(0xffffff, 0.30); d2.position.set(-2,1,1); scene.add(d2);
const group = new THREE.Group();
for (const p of data.parts) {
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(p.pos, 3));
  g.computeVertexNormals();
  const mat = new THREE.MeshPhongMaterial({color: p.color, flatShading:true, shininess:25,
      transparent: p.opacity < 1, opacity: p.opacity, side: THREE.DoubleSide});
  group.add(new THREE.Mesh(g, mat));
  const e = new THREE.EdgesGeometry(g, 35);
  group.add(new THREE.LineSegments(e, new THREE.LineBasicMaterial({color:0x333333, transparent:true, opacity:0.35})));
}
scene.add(group);
const cam = data.ortho ? new THREE.OrthographicCamera(-1,1,1,-1,0.1,5000)
                       : new THREE.PerspectiveCamera(data.fov, W/H, 1, 5000);
cam.up.set(...data.up);
cam.position.set(...data.eye); cam.lookAt(...data.target);
if (data.ortho) { const s = data.ortho; cam.left=-s*W/H; cam.right=s*W/H; cam.top=s; cam.bottom=-s; cam.updateProjectionMatrix(); }
renderer.render(scene, cam);
window.done = true;
</script></body></html>"""


def render(parts, out_png, eye, target, w=1400, h=1000, fov=30, ortho=None, three_js=None, up=(0, 0, 1)):
    three_js = three_js or os.environ.get("THREE_JS")
    payload = {"parts": [_mesh_payload(m, c, *rest) for (m, c, *rest) in parts.values()],
               "eye": list(eye), "target": list(target), "w": w, "h": h, "fov": fov,
               "ortho": ortho, "up": list(up)}
    html = HTML.replace("THREEJS", "file://" + os.path.abspath(three_js)).replace("DATA", json.dumps(payload))
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as f:
        f.write(html)
        path = f.name
    js = ("const {chromium}=require('playwright');(async()=>{const b=await chromium.launch({args:['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']});"
          "const p=await b.newPage({viewport:{width:%d,height:%d}});await p.goto('file://%s');"
          "await p.waitForFunction('window.done===true',null,{timeout:120000});await p.screenshot({path:'%s'});await b.close();})();"
          % (w, h, path, os.path.abspath(out_png)))
    subprocess.run(["node", "-e", js], check=True)
    os.unlink(path)
