/**
 * The city: the feeder rendered as a place, the grid hardware hung on it, and a fleet
 * of vehicles that drive it.
 *
 * Everything visible here is downstream of the solver. Lamps dim because the voltage
 * at their bus fell, conductors glow because that branch is carrying loss, and a car
 * charges slowly because the controller told its station to back off. Nothing is
 * animated to look right — if it looks wrong, the number behind it is wrong.
 */

import * as THREE from 'three';
import {
  WORLD, BAND_LO, COL, ROAD_W, POLE_H, SUB, place, buildings, solids, stationSpot,
  maxX, mat, PALETTE, vMag, branchLossKw, lampBrightness, clamp01, PV_SET, rng,
} from './core.js';

const WARM = new THREE.Color(PALETTE.warm);
const SICK = new THREE.Color(PALETTE.sick);
const COOL = new THREE.Color(PALETTE.cool);
const scratch = new THREE.Color();

const V3 = (x, y, z) => new THREE.Vector3(x, y, z);
const IDENT_Q = new THREE.Quaternion();
const ONE = V3(1, 1, 1);
const HIDDEN = new THREE.Matrix4().makeScale(1e-4, 1e-4, 1e-4);

/** Parent of each bus in the radial tree, for routing vehicles along real roads. */
const parentOf = new Map();
for (const b of WORLD.branches) parentOf.set(b.to, b.from);

/** The road centreline from the substation out to `bus`, as ground positions. */
function routeTo(bus) {
  const chain = [];
  for (let b = bus; b !== undefined; b = parentOf.get(b)) {
    chain.push(b);
    if (b === 1) break;
  }
  chain.reverse();
  return chain.map((b) => {
    const p = place.get(b);
    return { x: p.x, z: p.z };
  });
}

export function buildCity(scene) {
  const lamps = [];
  const windows = [];

  /* ---------------------------------------------------------- ground */

  const groundMesh = new THREE.Mesh(new THREE.PlaneGeometry(2400, 1000), mat.ground);
  groundMesh.rotation.x = -Math.PI / 2;
  groundMesh.position.set(maxX / 2 - 40, 0, 8);
  groundMesh.receiveShadow = true;
  scene.add(groundMesh);

  /* ----------------------------------------------------------- roads */

  {
    const segs = [];
    for (const br of WORLD.branches) {
      const a = place.get(br.from), b = place.get(br.to);
      segs.push([a.x, a.z, b.x, b.z]);
    }
    // A stub past every dead end, so the road does not stop in mid-air at bus 18.
    for (const p of place.values()) {
      if (![...place.values()].some((q) => q.row === p.row && q.col === p.col + 1)) {
        segs.push([p.x, p.z, p.x + COL * 1.4, p.z]);
      }
    }
    // And a spur west from bus 1 to the control centre, which is where the day starts.
    segs.push([place.get(1).x, 0, -46, 0]);
    segs.push([-46, 0, -46, -14]);

    const road = new THREE.InstancedMesh(new THREE.BoxGeometry(1, 0.12, 1), mat.asphalt, segs.length);
    road.receiveShadow = true;
    const m = new THREE.Matrix4();
    const q = new THREE.Quaternion();
    segs.forEach(([ax, az, bx, bz], i) => {
      const len = Math.hypot(bx - ax, bz - az);
      q.setFromAxisAngle(V3(0, 1, 0), -Math.atan2(bz - az, bx - ax));
      m.compose(V3((ax + bx) / 2, 0.06, (az + bz) / 2), q, V3(len, 1, ROAD_W));
      road.setMatrixAt(i, m);
    });
    scene.add(road);
  }

  /* ------------------------------------------------------- buildings */

  const town = new THREE.InstancedMesh(new THREE.BoxGeometry(1, 1, 1), mat.wall, buildings.length);
  town.castShadow = town.receiveShadow = true;
  const roofs = new THREE.InstancedMesh(new THREE.BoxGeometry(1, 1, 1), mat.roof, buildings.length);
  roofs.castShadow = true;
  {
    const m = new THREE.Matrix4();
    buildings.forEach((b, i) => {
      m.compose(V3(b.x, b.h / 2, b.z), IDENT_Q, V3(b.w, b.h, b.d));
      town.setMatrixAt(i, m);
      m.compose(V3(b.x, b.h + 0.18, b.z), IDENT_Q, V3(b.w * 1.04, 0.36, b.d * 1.04));
      roofs.setMatrixAt(i, m);
    });
  }
  scene.add(town, roofs);

  for (const b of buildings) {
    const rows = Math.min(b.floors, 6);
    for (const face of [-1, 1]) {
      for (let r = 0; r < rows; r++) {
        for (let c = 0; c < 3; c++) {
          if (b.r() > 0.62) continue;
          windows.push({
            bus: b.bus,
            x: b.x + (c - 1) * (b.w / 3.4),
            y: 1.6 + (r + 0.5) * ((b.h - 2.2) / rows),
            z: b.z + face * (b.d / 2 + 0.06),
            face,
          });
        }
      }
    }
  }
  const winMesh = new THREE.InstancedMesh(
    new THREE.PlaneGeometry(1.5, 1.9),
    new THREE.MeshBasicMaterial({ toneMapped: false }),
    windows.length,
  );
  {
    const m = new THREE.Matrix4();
    const q = new THREE.Quaternion();
    windows.forEach((w, i) => {
      q.setFromAxisAngle(V3(0, 1, 0), w.face > 0 ? 0 : Math.PI);
      m.compose(V3(w.x, w.y, w.z), q, ONE);
      winMesh.setMatrixAt(i, m);
      winMesh.setColorAt(i, new THREE.Color(0x111820));
    });
  }
  scene.add(winMesh);

  /* -------------------------------------------------- poles and lamps */

  const poles = new THREE.InstancedMesh(new THREE.CylinderGeometry(0.16, 0.22, POLE_H, 8), mat.steel, place.size);
  poles.castShadow = true;
  const bulbs = new THREE.InstancedMesh(
    new THREE.SphereGeometry(0.42, 12, 10),
    new THREE.MeshBasicMaterial({ toneMapped: false }),
    place.size,
  );
  {
    const m = new THREE.Matrix4();
    let i = 0;
    for (const p of place.values()) {
      const px = p.x, pz = p.z - ROAD_W / 2 - 1.4;
      m.compose(V3(px, POLE_H / 2, pz), IDENT_Q, ONE);
      poles.setMatrixAt(i, m);
      m.compose(V3(px, POLE_H + 0.5, pz), IDENT_Q, ONE);
      bulbs.setMatrixAt(i, m);
      lamps.push({ bus: p.bus, index: i, pos: V3(px, POLE_H + 0.5, pz), flux: 1, colour: new THREE.Color() });
      i++;
    }
  }
  scene.add(poles, bulbs);

  /* ------------------------------------------------------ conductors */

  const conductors = WORLD.branches.map((br) => {
    const a = place.get(br.from), b = place.get(br.to);
    const p1 = V3(a.x, POLE_H, a.z - ROAD_W / 2 - 1.4);
    const p2 = V3(b.x, POLE_H, b.z - ROAD_W / 2 - 1.4);
    const mid = p1.clone().lerp(p2, 0.5);
    // Span sag: a real conductor hangs, and the sag grows with span length.
    mid.y -= 1.1 + p1.distanceTo(p2) * 0.012;
    const curve = new THREE.CatmullRomCurve3([p1, mid, p2]);
    const material = new THREE.MeshStandardMaterial({ color: 0x2b3540, roughness: 0.6, emissive: new THREE.Color(0x000000) });
    const mesh = new THREE.Mesh(new THREE.TubeGeometry(curve, 10, 0.07, 5, false), material);
    scene.add(mesh);
    return mesh;
  });

  /* -------------------------------------------- grid hardware on the poles */

  // Pole-top distribution transformers: one wherever a lateral leaves the trunk or a
  // bus carries more than a couple of houses. They are the visible reason a street has
  // low voltage at all — the drop happens between here and the substation.
  const xfmrBuses = [...place.values()].filter((p) => p.kw >= 90 || p.row !== 0).map((p) => p.bus);
  const xfmrs = new THREE.InstancedMesh(new THREE.CylinderGeometry(0.62, 0.62, 1.5, 10), mat.steel, xfmrBuses.length);
  xfmrs.castShadow = true;
  {
    const m = new THREE.Matrix4();
    xfmrBuses.forEach((bus, i) => {
      const p = place.get(bus);
      m.compose(V3(p.x + 0.95, POLE_H - 3.1, p.z - ROAD_W / 2 - 1.4), IDENT_Q, ONE);
      xfmrs.setMatrixAt(i, m);
    });
  }
  scene.add(xfmrs);

  // Reclosers at the three lateral heads. These are the switches that would island a
  // faulted branch; here they are landmarks that tell you the feeder has structure.
  const reclosers = [];
  for (const bus of [2, 3, 6]) {
    const p = place.get(bus);
    const g = new THREE.Group();
    const box = new THREE.Mesh(new THREE.BoxGeometry(1.1, 1.5, 0.9), mat.cabinet);
    box.position.set(p.x - 1.1, POLE_H - 5.4, p.z - ROAD_W / 2 - 1.4);
    box.castShadow = true;
    g.add(box);
    const led = new THREE.Mesh(
      new THREE.SphereGeometry(0.13, 8, 6),
      new THREE.MeshBasicMaterial({ color: PALETTE.cool, toneMapped: false }),
    );
    led.position.set(p.x - 1.1, POLE_H - 4.8, p.z - ROAD_W / 2 - 1.9);
    g.add(led);
    scene.add(g);
    reclosers.push({ bus, led });
  }

  // Capacitor bank at bus 6, where the trunk splits and the reactive load piles up.
  {
    const p = place.get(6);
    const g = new THREE.Group();
    for (const dx of [-0.8, 0, 0.8]) {
      const can = new THREE.Mesh(new THREE.CylinderGeometry(0.34, 0.34, 1.3, 8), mat.steel);
      can.position.set(p.x + dx, POLE_H - 6.6, p.z - ROAD_W / 2 - 1.4);
      g.add(can);
    }
    const frame = new THREE.Mesh(new THREE.BoxGeometry(2.6, 0.14, 0.8), mat.steel);
    frame.position.set(p.x, POLE_H - 7.4, p.z - ROAD_W / 2 - 1.4);
    g.add(frame);
    scene.add(g);
  }

  // Rooftop PV on the three PV buses. Dark at night, which is exactly the point the
  // day makes when the evening peak arrives and the arrays have nothing left to give.
  const pvPanels = [];
  {
    const targets = buildings.filter((b) => PV_SET.has(b.bus));
    const panelMat = new THREE.MeshStandardMaterial({ color: 0x1b2836, roughness: 0.25, metalness: 0.55 });
    const pv = new THREE.InstancedMesh(new THREE.BoxGeometry(1, 0.12, 1), panelMat, targets.length);
    const m = new THREE.Matrix4();
    const q = new THREE.Quaternion();
    targets.forEach((b, i) => {
      q.setFromAxisAngle(V3(1, 0, 0), -0.28);
      m.compose(V3(b.x, b.h + 0.7, b.z), q, V3(b.w * 0.7, 1, b.d * 0.6));
      pv.setMatrixAt(i, m);
      pvPanels.push({ bus: b.bus, index: i });
    });
    pv.castShadow = true;
    scene.add(pv);
  }

  // Battery container beside the substation — the thing the town would buy if it
  // wanted to stop arguing about charging schedules.
  {
    const g = new THREE.Group();
    const box = new THREE.Mesh(new THREE.BoxGeometry(12, 3.2, 3.4), mat.cabinet);
    box.position.set(SUB.x + 26, 1.6, SUB.z + 4);
    box.castShadow = box.receiveShadow = true;
    g.add(box);
    const strip = new THREE.Mesh(
      new THREE.BoxGeometry(11, 0.16, 0.1),
      new THREE.MeshBasicMaterial({ color: PALETTE.cool, toneMapped: false }),
    );
    strip.position.set(SUB.x + 26, 2.6, SUB.z + 2.28);
    g.add(strip);
    scene.add(g);
    solids.push({ x: SUB.x + 26, z: SUB.z + 4, w: 12, d: 3.4 });
  }

  /* ------------------------------------------------------- substation */

  {
    const g = new THREE.Group();
    const fence = (x, z, w, d) => {
      const mm = new THREE.Mesh(new THREE.BoxGeometry(w, 3.2, d), mat.steel);
      mm.position.set(x, 1.6, z);
      mm.castShadow = mm.receiveShadow = true;
      g.add(mm);
    };
    fence(SUB.x, SUB.z - 13, 42, 0.5);
    fence(SUB.x, SUB.z + 13, 42, 0.5);
    fence(SUB.x - 21, SUB.z, 0.5, 26);
    fence(SUB.x + 21, SUB.z, 0.5, 26);

    const tank = new THREE.Mesh(new THREE.BoxGeometry(11, 7.5, 9), mat.steel);
    tank.position.set(SUB.x - 8, 3.75, SUB.z - 2);
    tank.castShadow = true;
    g.add(tank);
    const tank2 = new THREE.Mesh(new THREE.CylinderGeometry(3.4, 3.4, 6, 14), mat.steel);
    tank2.position.set(SUB.x + 8, 3, SUB.z - 1);
    tank2.castShadow = true;
    g.add(tank2);
    for (const dx of [-6, 4]) {
      const post = new THREE.Mesh(new THREE.BoxGeometry(0.9, 15, 0.9), mat.steel);
      post.position.set(SUB.x + dx, 7.5, SUB.z + 7);
      post.castShadow = true;
      g.add(post);
    }
    const beam = new THREE.Mesh(new THREE.BoxGeometry(12, 0.6, 0.6), mat.steel);
    beam.position.set(SUB.x - 1, 14.7, SUB.z + 7);
    g.add(beam);

    // Yard floodlights are fed from the grid side and do not sag with the town, so
    // they stay the one constant light in the scene while the streets brown out.
    for (const dx of [-15, 15]) {
      const mast = new THREE.Mesh(new THREE.CylinderGeometry(0.14, 0.2, 12, 8), mat.steel);
      mast.position.set(SUB.x + dx, 6, SUB.z + 9);
      g.add(mast);
      const head = new THREE.Mesh(
        new THREE.SphereGeometry(0.5, 10, 8),
        new THREE.MeshBasicMaterial({ color: PALETTE.ice, toneMapped: false }),
      );
      head.position.set(SUB.x + dx, 12.4, SUB.z + 9);
      g.add(head);
      const l = new THREE.PointLight(PALETTE.ice, 2400, 110, 2);
      l.position.set(SUB.x + dx, 12.4, SUB.z + 9);
      g.add(l);
    }
    scene.add(g);
  }

  /* --------------------------------------------------------- stations */

  const stations = WORLD.stations.map((bus, si) => {
    const s = stationSpot(bus);
    const g = new THREE.Group();
    const canopy = new THREE.Mesh(new THREE.BoxGeometry(22, 0.7, 12), mat.steel);
    canopy.position.set(s.x, 6.6, s.z);
    canopy.castShadow = true;
    g.add(canopy);
    const strip = new THREE.Mesh(
      new THREE.BoxGeometry(21, 0.22, 11),
      new THREE.MeshBasicMaterial({ color: PALETTE.cool, toneMapped: false }),
    );
    strip.position.set(s.x, 6.18, s.z);
    g.add(strip);
    for (const dx of [-9, 9]) {
      const post = new THREE.Mesh(new THREE.BoxGeometry(0.8, 6.6, 0.8), mat.steel);
      post.position.set(s.x + dx, 3.3, s.z);
      post.castShadow = true;
      g.add(post);
    }
    // Six chargers, one per bay, so the parked cars have something to be plugged into.
    const bays = [];
    for (let i = 0; i < 6; i++) {
      const bx = s.x - 7 + (i % 3) * 7;
      const bz = s.z - 3 + Math.floor(i / 3) * 6;
      const post = new THREE.Mesh(new THREE.BoxGeometry(0.45, 1.5, 0.35), mat.cabinet);
      post.position.set(bx + 1.8, 0.75, bz);
      g.add(post);
      bays.push({ x: bx, z: bz });
    }
    const deskBox = new THREE.Mesh(new THREE.BoxGeometry(1.2, 1.3, 2.1), mat.cabinet);
    deskBox.position.set(s.x - 12.5, 0.65, s.z - 4);
    g.add(deskBox);
    const light = new THREE.PointLight(PALETTE.cool, 700, 52, 2);
    light.position.set(s.x, 6, s.z);
    g.add(light);
    scene.add(g);
    return { bus, si, spot: s, bays, strip, light };
  });

  /* --------------------------------------------------------- vehicles */

  const FLEET = 30;
  const carMesh = new THREE.InstancedMesh(new THREE.BoxGeometry(2.4, 1.45, 4.4), mat.car, FLEET);
  carMesh.castShadow = true;
  const socMesh = new THREE.InstancedMesh(
    new THREE.PlaneGeometry(1, 0.28),
    new THREE.MeshBasicMaterial({ toneMapped: false, side: THREE.DoubleSide }),
    FLEET,
  );
  const headMesh = new THREE.InstancedMesh(
    new THREE.SphereGeometry(0.17, 6, 5),
    new THREE.MeshBasicMaterial({ color: 0xf2ead6, toneMapped: false }),
    FLEET * 2,
  );
  scene.add(carMesh, socMesh, headMesh);

  const routes = new Map();
  for (const bus of WORLD.stations) routes.set(bus, routeTo(bus));

  const fleet = Array.from({ length: FLEET }, (_, i) => ({
    si: i % 4,
    state: 'inbound',
    leg: 0,
    t: Math.random(),
    soc: 0.15 + Math.random() * 0.3,
    bay: -1,
    x: -60, z: 0, yaw: 0,
  }));

  /** Position along a route polyline at leg + fraction, with a lane offset. */
  function alongRoute(route, leg, t, lane) {
    const a = route[Math.min(leg, route.length - 1)];
    const b = route[Math.min(leg + 1, route.length - 1)];
    const x = a.x + (b.x - a.x) * t;
    const z = a.z + (b.z - a.z) * t;
    const yaw = Math.atan2(b.z - a.z, b.x - a.x);
    // Offset to the right of travel so the two directions do not drive through each other.
    return { x: x + Math.sin(yaw) * lane, z: z - Math.cos(yaw) * lane, yaw };
  }

  const SPEED = 11;

  // Seed the fleet mid-evening rather than at the depot gate. Bus 18 is 510 m from the
  // substation, so a fleet that all starts at leg zero leaves every station empty for
  // the first minute — which is not what an evening peak looks like.
  {
    const perStation = [[], [], [], []];
    for (const car of fleet) perStation[car.si].push(car);
    perStation.forEach((cars, si) => {
      const route = routes.get(WORLD.stations[si]);
      cars.forEach((car, k) => {
        if (k < 4) {
          car.state = 'charging';
          car.bay = k;
          car.x = stations[si].bays[k].x;
          car.z = stations[si].bays[k].z;
          car.yaw = 0;
        } else {
          car.leg = Math.floor(Math.random() * (route.length - 1));
          const p = alongRoute(route, car.leg, car.t, 3.4);
          car.x = p.x; car.z = p.z; car.yaw = p.yaw;
        }
      });
    });
  }

  function updateVehicles(dt, ctx) {
    const { plugged, stationKw, running } = ctx;
    const m = new THREE.Matrix4();
    const q = new THREE.Quaternion();
    let head = 0;

    // How many bays each station should have filled, scaled from the recorded count.
    const want = plugged.map((n) => Math.min(6, Math.ceil(n / 7)));
    const filled = [0, 0, 0, 0];
    for (const c of fleet) if (c.state === 'charging') filled[c.si]++;

    fleet.forEach((car, i) => {
      const route = routes.get(WORLD.stations[car.si]);
      const st = stations[car.si];

      if (car.state === 'inbound') {
        car.t += (SPEED * dt) / Math.max(1, segLength(route, car.leg));
        while (car.t >= 1 && car.leg < route.length - 2) { car.t -= 1; car.leg++; }
        if (car.leg >= route.length - 2 && car.t >= 1) {
          if (filled[car.si] < want[car.si] && car.bay < 0) {
            const taken = new Set(fleet.filter((o) => o.state === 'charging' && o.si === car.si).map((o) => o.bay));
            const free = st.bays.findIndex((_, bi) => !taken.has(bi));
            if (free >= 0) {
              car.bay = free; car.state = 'charging'; filled[car.si]++;
              car.x = st.bays[free].x; car.z = st.bays[free].z; car.yaw = 0;
            }
          }
          car.t = 1;
        }
        if (car.state === 'inbound') {
          const p = alongRoute(route, car.leg, Math.min(1, car.t), 3.4);
          car.x = p.x; car.z = p.z; car.yaw = p.yaw;
        }
      } else if (car.state === 'charging') {
        // The station's commanded power is shared across every vehicle actually
        // plugged in — all 38 of them, not the six bays drawn under the canopy. Divide
        // by the visible bays instead and each car gets 139 kW, fills in a quarter of
        // a second, and the bar tells you nothing.
        const draw = Math.max(0, -stationKw[car.si]) / Math.max(1, plugged[car.si]);
        // 60 kWh pack. A simulated day passes in about 16 seconds of wall clock, so
        // one second here is 1.5 hours there — which is the rate soc has to rise at.
        car.soc = Math.min(1, car.soc + (running ? (draw / 60) * dt * 1.52 : 0));
        if (car.soc >= 0.995 || filled[car.si] > want[car.si]) {
          car.state = 'outbound';
          car.leg = route.length - 2;
          car.t = 0;
          filled[car.si]--;
          car.bay = -1;
        }
      } else {
        car.t += (SPEED * dt) / Math.max(1, segLength(route, car.leg));
        while (car.t >= 1 && car.leg > 0) { car.t -= 1; car.leg--; }
        const p = alongRoute(route, car.leg, 1 - Math.min(1, car.t), -3.4);
        car.x = p.x; car.z = p.z; car.yaw = p.yaw + Math.PI;
        // A car that drove all the way back to the substation before turning round
        // would be gone for the better part of a minute, and the station it left would
        // sit empty. It rejoins the traffic a few blocks out instead.
        if (car.leg <= Math.max(0, route.length - 9)) {
          car.state = 'inbound';
          car.si = Math.floor(Math.random() * 4);
          const next = routes.get(WORLD.stations[car.si]);
          car.leg = Math.max(0, Math.min(car.leg, next.length - 2));
          car.t = 0;
          car.soc = 0.12 + Math.random() * 0.28;
        }
      }

      q.setFromAxisAngle(V3(0, 1, 0), -car.yaw);
      m.compose(V3(car.x, 0.75, car.z), q, ONE);
      carMesh.setMatrixAt(i, m);

      // State of charge, drawn as a bar on the roof: teal while it fills, amber when full.
      m.compose(V3(car.x, 1.56, car.z), new THREE.Quaternion().setFromEuler(new THREE.Euler(-Math.PI / 2, 0, -car.yaw)), V3(1.7 * car.soc, 1, 1));
      socMesh.setMatrixAt(i, m);
      socMesh.setColorAt(i, scratch.copy(car.soc > 0.98 ? WARM : COOL).multiplyScalar(1.7));

      if (car.state !== 'charging') {
        for (const side of [-0.75, 0.75]) {
          const hx = car.x + Math.cos(car.yaw) * 2.1 - Math.sin(car.yaw) * side;
          const hz = car.z + Math.sin(car.yaw) * 2.1 + Math.cos(car.yaw) * side;
          m.compose(V3(hx, 0.72, hz), IDENT_Q, ONE);
          headMesh.setMatrixAt(head++, m);
        }
      }
    });

    for (let i = head; i < FLEET * 2; i++) headMesh.setMatrixAt(i, HIDDEN);
    carMesh.instanceMatrix.needsUpdate = true;
    socMesh.instanceMatrix.needsUpdate = true;
    socMesh.instanceColor.needsUpdate = true;
    headMesh.instanceMatrix.needsUpdate = true;
  }

  function segLength(route, leg) {
    const a = route[Math.min(leg, route.length - 1)];
    const b = route[Math.min(leg + 1, route.length - 1)];
    return Math.hypot(b.x - a.x, b.z - a.z);
  }

  /* -------------------------------------------------- voltage -> light */

  function applyVoltages(stationKw, manual) {
    for (const lamp of lamps) {
      const v = vMag[lamp.bus];
      const b = lampBrightness(v);
      const health = clamp01((v - 0.84) / 0.11);
      lamp.flux = 0.1 + 0.9 * b;
      lamp.colour.copy(v >= BAND_LO ? WARM : scratch.copy(SICK).lerp(WARM, health));
      bulbs.setColorAt(lamp.index, scratch.copy(lamp.colour).multiplyScalar(0.35 + 2.6 * lamp.flux));
    }
    bulbs.instanceColor.needsUpdate = true;

    windows.forEach((w, i) => {
      const v = vMag[w.bus];
      const b = lampBrightness(v);
      const health = clamp01((v - 0.84) / 0.11);
      // Mixed up from a dark base, so a sagging bus reads as dim rather than lurid.
      scratch.copy(v >= BAND_LO ? WARM : SICK.clone().lerp(WARM, health)).multiplyScalar(0.16 + 1.5 * b);
      winMesh.setColorAt(i, scratch);
    });
    winMesh.instanceColor.needsUpdate = true;

    conductors.forEach((mesh, i) => {
      const heat = Math.min(1, branchLossKw[i + 1] / 4);
      mesh.material.emissive.setRGB(heat * 0.85, heat * 0.24, heat * 0.2);
    });

    // A recloser shows amber when the branch below it has a bus outside the band.
    for (const r of reclosers) {
      const p = place.get(r.bus);
      const sick = [...place.values()].some((q) => q.col >= p.col && vMag[q.bus] < BAND_LO);
      r.led.material.color.copy(sick ? SICK : COOL);
    }

    stations.forEach((s, i) => {
      const kw = stationKw[i];
      const taken = manual[i] !== null;
      const c = taken || kw > 1 ? WARM : COOL;
      s.strip.material.color.copy(c);
      s.light.color.copy(c);
      s.light.intensity = 420 + Math.min(1, Math.abs(kw) / 700) * 900;
    });
  }

  return { lamps, stations, applyVoltages, updateVehicles, fleet };
}
