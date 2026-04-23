import math
from kaggle_environments.envs.orbit_wars.orbit_wars import Planet, Fleet

BOARD = 100.0
CENTER_X, CENTER_Y = 50.0, 50.0
SUN_R = 10.0
MAX_SPEED = 6.0
SUN_SAFETY = 1.5
ROTATION_LIMIT = 50.0
TOTAL_STEPS = 500


def dist(ax, ay, bx, by):
    return math.hypot(ax - bx, ay - by)


def fleet_speed(ships):
    if ships <= 1:
        return 1.0
    ratio = math.log(ships) / math.log(1000.0)
    ratio = max(0.0, min(1.0, ratio))
    return 1.0 + (MAX_SPEED - 1.0) * (ratio ** 1.5)


def segment_hits_sun(x1, y1, x2, y2, safety=SUN_SAFETY):
    r = SUN_R + safety
    dx, dy = x2 - x1, y2 - y1
    fx, fy = x1 - CENTER_X, y1 - CENTER_Y
    a = dx * dx + dy * dy
    if a < 1e-9:
        return dist(x1, y1, CENTER_X, CENTER_Y) < r
    b = 2 * (fx * dx + fy * dy)
    c = fx * fx + fy * fy - r * r
    disc = b * b - 4 * a * c
    if disc < 0:
        return False
    disc = math.sqrt(disc)
    t1 = (-b - disc) / (2 * a)
    t2 = (-b + disc) / (2 * a)
    return (0 <= t1 <= 1) or (0 <= t2 <= 1)


def safe_angle_and_distance(sx, sy, tx, ty):
    if not segment_hits_sun(sx, sy, tx, ty):
        return math.atan2(ty - sy, tx - sx), dist(sx, sy, tx, ty)
    vx, vy = tx - sx, ty - sy
    norm = math.hypot(vx, vy)
    if norm < 1e-9:
        return math.atan2(ty - sy, tx - sx), dist(sx, sy, tx, ty)
    nx, ny = -vy / norm, vx / norm
    best = None
    for sign in (1.0, -1.0):
        for mult in (2.0, 3.0, 4.0):
            wx = CENTER_X + sign * nx * (SUN_R * mult)
            wy = CENTER_Y + sign * ny * (SUN_R * mult)
            if segment_hits_sun(sx, sy, wx, wy) or segment_hits_sun(wx, wy, tx, ty):
                continue
            d = dist(sx, sy, wx, wy) + dist(wx, wy, tx, ty)
            if best is None or d < best[0]:
                best = (d, wx, wy)
            break
    if best is None:
        ang = math.atan2(ty - sy, tx - sx)
        return ang, dist(sx, sy, tx, ty) * 1.5
    _, wx, wy = best
    ang = math.atan2(wy - sy, wx - sx)
    return ang, best[0]


def predict_planet_position(planet, initial_by_id, angular_velocity, turns):
    init = initial_by_id.get(planet.id)
    if init is None:
        return planet.x, planet.y
    orbital_r = dist(init.x, init.y, CENTER_X, CENTER_Y)
    if orbital_r + init.radius >= ROTATION_LIMIT:
        return planet.x, planet.y
    cur_ang = math.atan2(planet.y - CENTER_Y, planet.x - CENTER_X)
    new_ang = cur_ang + angular_velocity * turns
    return (CENTER_X + orbital_r * math.cos(new_ang),
            CENTER_Y + orbital_r * math.sin(new_ang))


def predict_comet_position(planet_id, comets, turns):
    for g in comets:
        pids = g.get("planet_ids", [])
        if planet_id not in pids:
            continue
        idx = pids.index(planet_id)
        paths = g.get("paths", [])
        path_index = g.get("path_index", 0)
        if idx >= len(paths):
            return None
        path = paths[idx]
        future_idx = path_index + int(turns)
        if 0 <= future_idx < len(path):
            return path[future_idx][0], path[future_idx][1]
        return None
    return None


def comet_remaining_life(planet_id, comets):
    for g in comets:
        pids = g.get("planet_ids", [])
        if planet_id not in pids:
            continue
        idx = pids.index(planet_id)
        paths = g.get("paths", [])
        path_index = g.get("path_index", 0)
        if idx < len(paths):
            return max(0, len(paths[idx]) - path_index)
    return 0


def estimate_arrival(sx, sy, tx, ty, ships):
    angle, d = safe_angle_and_distance(sx, sy, tx, ty)
    return angle, max(1, int(math.ceil(d / fleet_speed(ships))))


def aim_with_prediction(src, target, ships, initial_by_id, ang_vel, comets, comet_ids):
    tx, ty = target.x, target.y
    for _ in range(4):
        angle, turns = estimate_arrival(src.x, src.y, tx, ty, ships)
        if target.id in comet_ids:
            pos = predict_comet_position(target.id, comets, turns)
            if pos is None:
                return None
            ntx, nty = pos
        else:
            ntx, nty = predict_planet_position(target, initial_by_id, ang_vel, turns)
        if abs(ntx - tx) < 0.5 and abs(nty - ty) < 0.5:
            tx, ty = ntx, nty
            break
        tx, ty = ntx, nty
    angle, turns = estimate_arrival(src.x, src.y, tx, ty, ships)
    return angle, turns, tx, ty


def fleet_target_planet(fleet, planets):
    best_p, best_t = None, 1e9
    fvx, fvy = math.cos(fleet.angle), math.sin(fleet.angle)
    sp = fleet_speed(fleet.ships)
    for p in planets:
        dx, dy = p.x - fleet.x, p.y - fleet.y
        proj = dx * fvx + dy * fvy
        if proj <= 0:
            continue
        perp = abs(dx * fvy - dy * fvx)
        if perp > p.radius + 1.2:
            continue
        t = proj / sp
        if t < best_t and t <= 80:
            best_t = t
            best_p = p
    return best_p, int(math.ceil(best_t)) if best_p else (None, None)


def incoming_to_planet(planet, fleets):
    arrivals = []
    fvx_cache = {}
    for f in fleets:
        fvx, fvy = math.cos(f.angle), math.sin(f.angle)
        dx, dy = planet.x - f.x, planet.y - f.y
        proj = dx * fvx + dy * fvy
        if proj <= 0:
            continue
        perp = abs(dx * fvy - dy * fvx)
        if perp > planet.radius + 1.5:
            continue
        t = proj / fleet_speed(f.ships)
        if t > 80:
            continue
        arrivals.append((int(math.ceil(t)), f.owner, int(f.ships)))
    return arrivals


def simulate_planet_outcome(planet, arrivals, player, horizon):
    if not arrivals:
        return planet.ships + (planet.production * horizon if planet.owner == player else 0), planet.owner
    events = sorted(arrivals, key=lambda a: a[0])
    garrison = planet.ships
    owner = planet.owner
    last_t = 0
    i = 0
    max_deficit = 0
    while i < len(events):
        t = events[i][0]
        if owner != -1:
            if owner == player:
                garrison += (t - last_t) * planet.production
            else:
                garrison += (t - last_t) * planet.production
        group = []
        while i < len(events) and events[i][0] == t:
            group.append(events[i])
            i += 1
        by_owner = {}
        for _, o, s in group:
            by_owner[o] = by_owner.get(o, 0) + s
        attackers = [(o, s) for o, s in by_owner.items() if o != owner]
        defender_reinforce = sum(s for o, s in by_owner.items() if o == owner)
        garrison += defender_reinforce
        if attackers:
            attackers.sort(key=lambda x: -x[1])
            if len(attackers) >= 2 and attackers[0][1] == attackers[1][1]:
                pass
            else:
                top_owner, top_ships = attackers[0]
                second = attackers[1][1] if len(attackers) > 1 else 0
                surviving = top_ships - second
                if surviving > 0:
                    garrison -= surviving
                    if garrison < 0:
                        if owner == player:
                            max_deficit = max(max_deficit, -garrison + 1)
                        garrison = -garrison
                        owner = top_owner
        last_t = t
    if owner != -1:
        garrison += (horizon - last_t) * planet.production
    return garrison, owner


def net_defense_needed(planet, arrivals, player):
    if not arrivals:
        return 0
    events = sorted(arrivals, key=lambda a: a[0])
    garrison = planet.ships
    prod = planet.production if planet.owner == player else 0
    last_t = 0
    deficit = 0
    i = 0
    while i < len(events):
        t = events[i][0]
        garrison += (t - last_t) * prod
        group = []
        while i < len(events) and events[i][0] == t:
            group.append(events[i])
            i += 1
        friendly = sum(s for tt, o, s in group if o == player)
        enemy = sum(s for tt, o, s in group if o != player)
        garrison += friendly
        garrison -= enemy
        if garrison < 0:
            deficit = max(deficit, -garrison)
        last_t = t
    return deficit


def agent(obs):
    if isinstance(obs, dict):
        get = obs.get
    else:
        get = lambda k, d=None: getattr(obs, k, d)

    player = get("player", 0)
    step = get("step", 0) or 0
    raw_planets = get("planets", []) or []
    raw_fleets = get("fleets", []) or []
    ang_vel = get("angular_velocity", 0.0) or 0.0
    raw_init = get("initial_planets", []) or []
    comets = get("comets", []) or []
    comet_ids = set(get("comet_planet_ids", []) or [])

    planets = [Planet(*p) for p in raw_planets]
    fleets = [Fleet(*f) for f in raw_fleets]
    initial_by_id = {Planet(*p).id: Planet(*p) for p in raw_init}
    planet_by_id = {p.id: p for p in planets}

    my_planets = [p for p in planets if p.owner == player]
    if not my_planets:
        return []

    remaining_steps = max(1, TOTAL_STEPS - step)
    is_early = step < 40
    is_late = remaining_steps < 60

    reserve = {p.id: 0 for p in my_planets}
    for p in my_planets:
        arrivals = incoming_to_planet(p, fleets)
        need = net_defense_needed(p, arrivals, player)
        reserve[p.id] = min(p.ships, need)

    available = {p.id: max(0, p.ships - reserve[p.id]) for p in my_planets}

    inbound_friendly = {}
    inbound_enemy = {}
    fleet_eta = {}
    for f in fleets:
        tgt, eta = fleet_target_planet(f, planets)
        if tgt is None:
            continue
        fleet_eta[(f.id, tgt.id)] = eta
        if f.owner == player:
            inbound_friendly[tgt.id] = inbound_friendly.get(tgt.id, 0) + int(f.ships)
        else:
            inbound_enemy[tgt.id] = inbound_enemy.get(tgt.id, 0) + int(f.ships)

    enemy_planets = [p for p in planets if p.owner != player and p.owner != -1]
    enemy_total = sum(p.ships for p in enemy_planets) + sum(int(f.ships) for f in fleets if f.owner != player)

    moves = []

    def target_value(tgt, arrival_turns):
        prod = tgt.production
        turns_to_profit = max(1, remaining_steps - arrival_turns)
        if tgt.id in comet_ids:
            life = comet_remaining_life(tgt.id, comets)
            turns_to_profit = max(0, min(turns_to_profit, life - arrival_turns))
        value = prod * turns_to_profit
        if tgt.owner != player and tgt.owner != -1:
            value *= 1.8
        if is_early and tgt.owner == -1:
            value *= 1.3
        return value

    def compute_needed(tgt, arrival_turns):
        if tgt.owner == -1:
            defender = tgt.ships
        else:
            defender = tgt.ships + tgt.production * arrival_turns
        defender -= inbound_friendly.get(tgt.id, 0)
        defender = max(0, defender)
        return defender + 1

    candidates = []
    for src in my_planets:
        if available[src.id] <= 0:
            continue
        for tgt in planets:
            if tgt.id == src.id or tgt.owner == player:
                continue
            d0 = dist(src.x, src.y, tgt.x, tgt.y)
            if d0 > 140:
                continue
            _, turns0 = estimate_arrival(src.x, src.y, tgt.x, tgt.y, max(10, available[src.id]))
            if is_late and turns0 > remaining_steps - 5:
                continue
            if tgt.id in comet_ids and turns0 >= comet_remaining_life(tgt.id, comets):
                continue

            est_needed = compute_needed(tgt, turns0)
            if est_needed > available[src.id]:
                continue

            aim = aim_with_prediction(src, tgt, est_needed, initial_by_id, ang_vel, comets, comet_ids)
            if aim is None:
                continue
            angle, turns, _, _ = aim

            ships_needed = compute_needed(tgt, turns)
            if ships_needed > available[src.id]:
                continue

            if segment_hits_sun(src.x, src.y,
                                src.x + math.cos(angle) * 3,
                                src.y + math.sin(angle) * 3, safety=0.3):
                continue

            value = target_value(tgt, turns)
            if value <= 0:
                continue
            cost = ships_needed + turns * 0.6
            score = value / (cost + 1.0)
            if is_early and tgt.owner == -1 and ships_needed <= 15:
                score *= 1.5
            candidates.append((score, src.id, tgt.id, angle, ships_needed, turns))

    candidates.sort(key=lambda x: -x[0])
    taken_targets = set()
    for score, sid, tid, angle, ships, turns in candidates:
        if tid in taken_targets:
            continue
        if available[sid] < ships:
            continue
        moves.append([sid, float(angle), int(ships)])
        available[sid] -= ships
        taken_targets.add(tid)
        inbound_friendly[tid] = inbound_friendly.get(tid, 0) + ships

    if not is_late and enemy_planets:
        remaining_sources = [p for p in my_planets if available[p.id] >= 20]
        for src in remaining_sources:
            best = None
            for tgt in planets:
                if tgt.id == src.id or tgt.owner == player:
                    continue
                if tgt.id in taken_targets:
                    continue
                d0 = dist(src.x, src.y, tgt.x, tgt.y)
                if d0 > 140:
                    continue
                _, turns0 = estimate_arrival(src.x, src.y, tgt.x, tgt.y, available[src.id])
                if is_late and turns0 > remaining_steps - 5:
                    continue
                if tgt.id in comet_ids and turns0 >= comet_remaining_life(tgt.id, comets):
                    continue
                needed = compute_needed(tgt, turns0)
                if needed > available[src.id] * 1.5:
                    continue
                contrib_needed = max(0, needed - inbound_friendly.get(tgt.id, 0))
                if contrib_needed <= 0:
                    continue
                if contrib_needed > available[src.id]:
                    continue
                value = target_value(tgt, turns0)
                if value <= 0:
                    continue
                score = value / (contrib_needed + turns0 * 0.6 + 1.0)
                if best is None or score > best[0]:
                    best = (score, tgt, contrib_needed, turns0)
            if best is None:
                continue
            score, tgt, ships, turns0 = best
            aim = aim_with_prediction(src, tgt, ships, initial_by_id, ang_vel, comets, comet_ids)
            if aim is None:
                continue
            angle, turns, _, _ = aim
            if segment_hits_sun(src.x, src.y,
                                src.x + math.cos(angle) * 3,
                                src.y + math.sin(angle) * 3, safety=0.3):
                continue
            moves.append([src.id, float(angle), int(ships)])
            available[src.id] -= ships
            inbound_friendly[tgt.id] = inbound_friendly.get(tgt.id, 0) + ships

    if enemy_planets and len(my_planets) > 1 and not is_late:
        front_dist = {mp.id: min(dist(mp.x, mp.y, e.x, e.y) for e in enemy_planets) for mp in my_planets}
        front = min(my_planets, key=lambda p: front_dist[p.id])
        for r in my_planets:
            if r.id == front.id:
                continue
            if front_dist[r.id] < front_dist[front.id] * 1.3:
                continue
            if available[r.id] < 20:
                continue
            send = int(available[r.id] * 0.7)
            if send < 12:
                continue
            aim = aim_with_prediction(r, front, send, initial_by_id, ang_vel, comets, comet_ids)
            if aim is None:
                continue
            angle, turns, _, _ = aim
            if turns > 35:
                continue
            if segment_hits_sun(r.x, r.y,
                                r.x + math.cos(angle) * 3,
                                r.y + math.sin(angle) * 3, safety=0.3):
                continue
            moves.append([r.id, float(angle), int(send)])
            available[r.id] -= send

    return moves
