import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { createHash } from 'node:crypto';
import { createRequire } from 'node:module';

const here = path.dirname(fileURLToPath(import.meta.url));
const viewer = path.resolve(here, '../viewer');
const original = path.resolve(process.argv[2] ?? 'E:/Dev/plane-3d-astra');
const require = createRequire(path.join(original, 'package.json'));
const ts = require('typescript');
const cache = path.join(viewer, 'node_modules/.cache/lake-city-aircraft');
await fs.mkdir(cache, { recursive: true });
const sha256 = data => createHash('sha256').update(data).digest('hex');
const sourceFiles = ['assets/AirplaneModel.ts', 'assets/MaterialLibrary.ts', 'game/types.ts'];
const runtimeFiles = ['assets/AirplaneModel.ts', 'assets/MaterialLibrary.ts', 'types.ts'];

async function loadModel(root, files, tag, webgpu) {
  const modules = new Map();
  for (const relative of files) {
    const source = await fs.readFile(path.join(root, relative), 'utf8');
    let code = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ES2022 } }).outputText;
    const three = webgpu ? path.join(viewer, 'node_modules/three') : path.join(original, 'node_modules/three');
    code = code.replaceAll("from 'three';", `from '${pathToFileURL(path.join(three, 'build/three.module.js'))}';`)
      .replaceAll("from 'three/webgpu';", `from '${pathToFileURL(path.join(three, 'build/three.webgpu.js'))}';`)
      .replaceAll("from 'three/tsl';", `from '${pathToFileURL(path.join(three, 'build/three.tsl.js'))}';`)
      .replaceAll("from 'three/addons/utils/BufferGeometryUtils.js';", `from '${pathToFileURL(path.join(three, 'examples/jsm/utils/BufferGeometryUtils.js'))}';`)
      .replaceAll("from './MaterialLibrary';", `from './${tag}-MaterialLibrary.mjs';`);
    const filename = `${tag}-${path.basename(relative, '.ts')}.mjs`;
    await fs.writeFile(path.join(cache, filename), code);
    modules.set(relative, { file: path.join(root, relative), sha256: sha256(Buffer.from(source)), bytes: Buffer.byteLength(source) });
  }
  const { AirplaneModel } = await import(pathToFileURL(path.join(cache, `${tag}-AirplaneModel.mjs`)).href);
  return { model: new AirplaneModel(), files: [...modules.values()] };
}

function geometrySignature(model) {
  model.root.updateMatrixWorld(true);
  const hash = createHash('sha256');
  const normalizedHash = createHash('sha256');
  let meshes = 0, vertices = 0, triangles = 0;
  const parts = [];
  model.root.traverse(object => {
    if (!object.isMesh) return;
    const geometry = object.geometry;
    meshes++;
    vertices += geometry.getAttribute('position').count;
    triangles += (geometry.index?.count ?? geometry.getAttribute('position').count) / 3;
    const descriptor = { name: object.name, matrix: object.matrixWorld.elements, visible: object.visible, parts: object.userData.parts ?? [], groups: geometry.groups };
    hash.update(JSON.stringify(descriptor));
    normalizedHash.update(JSON.stringify(descriptor));
    for (const name of Object.keys(geometry.attributes).sort()) {
      const attribute = geometry.attributes[name];
      const layout = JSON.stringify({ name, itemSize: attribute.itemSize, normalized: attribute.normalized, type: attribute.array.constructor.name });
      hash.update(layout); normalizedHash.update(layout);
      hash.update(Buffer.from(attribute.array.buffer, attribute.array.byteOffset, attribute.array.byteLength));
      const normalized = attribute.array.map(value => Math.abs(value) < 1e-12 ? 0 : value);
      normalizedHash.update(Buffer.from(normalized.buffer, normalized.byteOffset, normalized.byteLength));
    }
    if (geometry.index) {
      const indices = Buffer.from(geometry.index.array.buffer, geometry.index.array.byteOffset, geometry.index.array.byteLength);
      hash.update(indices); normalizedHash.update(indices);
    }
    parts.push(descriptor);
  });
  return { sha256: hash.digest('hex'), normalizedSha256: normalizedHash.digest('hex'), zeroRoundoffTolerance: 1e-12, meshes, vertices, triangles, parts };
}

const source = await loadModel(path.join(original, 'src'), sourceFiles, 'source', false);
const runtime = await loadModel(path.join(viewer, 'src/flight'), runtimeFiles, 'runtime', true);
const sourceGeometry = geometrySignature(source.model);
const runtimeGeometry = geometrySignature(runtime.model);
let differences = [];
if (sourceGeometry.sha256 !== runtimeGeometry.sha256) {
  const a = [], b = [];
  source.model.root.traverse(object => { if (object.isMesh) a.push(object); });
  runtime.model.root.traverse(object => { if (object.isMesh) b.push(object); });
  differences = a.map((object, i) => {
    const next = b[i];
    const attributes = Object.keys(object.geometry.attributes).map(name => {
      const first = object.geometry.attributes[name].array, second = next.geometry.attributes[name].array;
      let maxDifference = 0, changed = 0;
      if (first.length !== second.length) return { name, countA: first.length, countB: second.length };
      for (let j = 0; j < first.length; j++) if (first[j] !== second[j]) { maxDifference = Math.max(maxDifference, Math.abs(first[j] - second[j])); changed++; }
      return { name, changed, maxDifference };
    }).filter(attribute => attribute.changed || attribute.countA);
    return { name: object.name, attributes, indicesEqual: JSON.stringify(object.geometry.index?.array) === JSON.stringify(next.geometry.index?.array), descriptorEqual: JSON.stringify(sourceGeometry.parts[i]) === JSON.stringify(runtimeGeometry.parts[i]) };
  }).filter(row => row.attributes.length || !row.indicesEqual || !row.descriptorEqual);
  if (sourceGeometry.normalizedSha256 !== runtimeGeometry.normalizedSha256) throw new Error('Aircraft geometry changed beyond primitive near-zero roundoff during integration');
}

// Node provides Blob; GLTFExporter also needs the browser FileReader interface.
globalThis.FileReader = class FileReader {
  result = null;
  onloadend = null;
  readAsArrayBuffer(blob) { blob.arrayBuffer().then(result => { this.result = result; this.onloadend?.(); }); }
  readAsDataURL(blob) { blob.arrayBuffer().then(result => { this.result = `data:${blob.type};base64,${Buffer.from(result).toString('base64')}`; this.onloadend?.(); }); }
};
const { GLTFExporter } = await import(pathToFileURL(path.join(viewer, 'node_modules/three/examples/jsm/exporters/GLTFExporter.js')).href);
// Export the source PBR materials, whose values match the runtime. Blender's
// still asset stores the source shader expression as provenance on the disc.
source.model.root.traverse(object => {
  if (object.name === 'Propeller additive motion blur') {
    object.userData.runtimeVisibleAboveRpm = 200;
    object.userData.runtimeOpacity = 'opacity * smoothstep(0.25, 0.39, r) * (1 - smoothstep(0.66, 1, r)) * (0.15 + 0.23 * (0.5 + 0.5 * sin(atan(y, x) * 9 + r * 25)))';
  }
});
source.model.root.userData.provenance = 'plane-3d-astra/src/assets/AirplaneModel.ts';
source.model.root.userData.geometrySha256 = sourceGeometry.sha256;
source.model.root.userData.unit = 'meter';
const glb = await new GLTFExporter().parseAsync(source.model.root, { binary: true, onlyVisible: false, trs: true });
await fs.writeFile(path.join(here, 'Cropper_Seven.glb'), Buffer.from(glb));
const report = {
  sourceProject: original, sourceRevision: '48662bf', runtimeThree: '0.186.1', sourceThree: '0.184.0',
  sourceFiles: source.files, runtimeFiles: runtime.files,
  sourceGeometry, runtimeGeometry, authoredGeometryUnchanged: true, geometryEqualWithinZeroRoundoff: true, floatingPointDifferences: differences,
  diagnostics: runtime.model.diagnostics,
  adaptations: ['Three.js WebGPU imports', 'Equivalent TSL propeller opacity expression', 'Lake City scoped paint storage key'],
  glb: { file: 'Cropper_Seven.glb', sha256: sha256(Buffer.from(glb)), bytes: glb.byteLength },
};
await fs.writeFile(path.join(here, 'aircraft_provenance.json'), JSON.stringify(report, null, 2) + '\n');
console.log(JSON.stringify({ authoredGeometryUnchanged: true, geometryEqualWithinZeroRoundoff: true, normalizedGeometrySha256: sourceGeometry.normalizedSha256, meshes: runtimeGeometry.meshes, vertices: runtimeGeometry.vertices, triangles: runtimeGeometry.triangles, glbBytes: glb.byteLength, dimensions: runtime.model.diagnostics.bounds }));
source.model.dispose(); runtime.model.dispose();
