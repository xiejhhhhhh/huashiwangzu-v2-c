/**
 * Three.js addons re-export shim.
 *
 * Rolldown (Vite 8's default bundler) does not support Node.js wildcard subpath
 * exports (`package.json` `./examples/jsm/*` or `./addons/*` patterns) from
 * outside the project root. This barrel re-exports addons via direct relative
 * paths, which Vite can resolve without going through the package.json exports
 * field. The core THREE namespace uses the package name `'three'` so that Vite's
 * `resolve.dedupe` treats all `'three'` imports as the same module instance.
 */

export { OrbitControls } from '../../../../frontend/node_modules/three/examples/jsm/controls/OrbitControls.js'
export { EffectComposer } from '../../../../frontend/node_modules/three/examples/jsm/postprocessing/EffectComposer.js'
export { RenderPass } from '../../../../frontend/node_modules/three/examples/jsm/postprocessing/RenderPass.js'
export { UnrealBloomPass } from '../../../../frontend/node_modules/three/examples/jsm/postprocessing/UnrealBloomPass.js'
export { CSS2DRenderer, CSS2DObject } from '../../../../frontend/node_modules/three/examples/jsm/renderers/CSS2DRenderer.js'

// Use the package name so Vite's dedupe treats all `'three'` imports as one instance.
export * as THREE from 'three'
