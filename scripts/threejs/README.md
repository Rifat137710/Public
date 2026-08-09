# The Three.js build

A GPU version of the walkable town, for comparison against the hand-written
canvas rasteriser in `docs/feeder33-walk.html`. Same geometry, same exported
data, same backward/forward sweep — the difference is that every lamp is a real
photometric light instead of a painted ellipse.

## Building it

Three.js is bundled into the page rather than fetched, because the published
artifact runs under a CSP that blocks external hosts.

```sh
npm install three                 # r185
npx esbuild scene.js --bundle --format=iife --minify \
    --target=es2020 --loader:.json=json --outfile=bundle.js
# then substitute bundle.js for the /*BUNDLE*/ marker in shell.html
```

`scene.js` imports `world.json`, which comes from `scripts/world-data.ts`.

## Notes for anyone picking this up

- **Lights are physical.** Intensity is candela and illuminance falls as 1/d².
  A street lamp needs thousands, not hundreds; the first attempt at 300 rendered
  a black town.
- **`setColorAt` writes `instanceColor`,** which is not `vertexColors`. Setting
  `vertexColors: true` on a material with no such geometry attribute makes the
  shader read black.
- **Only one light casts shadows.** A shadow-casting point light is six render
  passes; thirty-three of them is not something a browser will do.
- **Frame cost here is fragments, not draw calls or lights.** Halving the render
  size roughly triples the frame rate; emptying the light pool changes nothing.
  That is why the quality ladder ends in resolution.
- **No volumetric cones.** An additively-blended cone mesh reads as a hard
  silhouette. A convincing shaft needs raymarching through the light's falloff.
