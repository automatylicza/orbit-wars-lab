import math
from collections import defaultdict, namedtuple
from dataclasses import dataclass, field


# =============================================================================
# CONFIG
# =============================================================================

BOARD = 100.0
CENTER_X = 50.0
CENTER_Y = 50.0
SUN_R = 10.0
MAX_SPEED = 6.0
SUN_SAFETY = 1.5
ROTATION_LIMIT = 50.0
TOTAL_STEPS = 500
HORIZON = 110
LAUNCH_CLEARANCE = 0.1

EARLY_TURN_LIMIT = 40
OPENING_TURN_LIMIT = 80
LATE_REMAINING_TURNS = 60
VERY_LATE_REMAINING_TURNS = 25

SAFE_NEUTRAL_MARGIN = 2
CONTESTED_NEUTRAL_MARGIN = 2
INTERCEPT_TOLERANCE = 1

SAFE_OPENING_PROD_THRESHOLD = 4
SAFE_OPENING_TURN_LIMIT = 10
ROTATING_OPENING_MAX_TURNS = 13
ROTATING_OPENING_LOW_PROD = 2
FOUR_PLAYER_ROTATING_REACTION_GAP = 3
FOUR_PLAYER_ROTATING_SEND_RATIO = 0.62
FOUR_PLAYER_ROTATING_TURN_LIMIT = 10

COMET_MAX_CHASE_TURNS = 10

ATTACK_COST_TURN_WEIGHT = 0.55
SNIPE_COST_TURN_WEIGHT = 0.45
INDIRECT_VALUE_SCALE = 0.15
INDIRECT_FRIENDLY_WEIGHT = 0.35
INDIRECT_NEUTRAL_WEIGHT = 0.9
INDIRECT_ENEMY_WEIGHT = 1.25

STATIC_NEUTRAL_VALUE_MULT = 1.4
STATIC_HOSTILE_VALUE_MULT = 1.55
ROTATING_OPENING_VALUE_MULT = 0.9
HOSTILE_TARGET_VALUE_MULT = 1.85
OPENING_HOSTILE_TARGET_VALUE_MULT = 1.45
SAFE_NEUTRAL_VALUE_MULT = 1.2
CONTESTED_NEUTRAL_VALUE_MULT = 0.7
EARLY_NEUTRAL_VALUE_MULT = 1.2
COMET_VALUE_MULT = 0.65
SNIPE_VALUE_MULT = 1.12
SWARM_VALUE_MULT = 1.05
FINISHING_HOSTILE_VALUE_MULT = 1.15
BEHIND_ROTATING_NEUTRAL_VALUE_MULT = 0.92

NEUTRAL_MARGIN_BASE = 2
NEUTRAL_MARGIN_PROD_WEIGHT = 2
NEUTRAL_MARGIN_CAP = 8
HOSTILE_MARGIN_BASE = 3
HOSTILE_MARGIN_PROD_WEIGHT = 2
HOSTILE_MARGIN_CAP = 12
STATIC_TARGET_MARGIN = 4
CONTESTED_TARGET_MARGIN = 5
FOUR_PLAYER_TARGET_MARGIN = 3
LONG_TRAVEL_MARGIN_START = 18
LONG_TRAVEL_MARGIN_DIVISOR = 3
LONG_TRAVEL_MARGIN_CAP = 8
COMET_MARGIN_RELIEF = 6
FINISHING_HOSTILE_SEND_BONUS = 3

STATIC_TARGET_SCORE_MULT = 1.18
EARLY_STATIC_NEUTRAL_SCORE_MULT = 1.25
FOUR_PLAYER_ROTATING_NEUTRAL_SCORE_MULT = 0.84
DENSE_STATIC_NEUTRAL_COUNT = 4
DENSE_ROTATING_NEUTRAL_SCORE_MULT = 0.86
SNIPE_SCORE_MULT = 1.12
SWARM_SCORE_MULT = 1.06

FOLLOWUP_MIN_SHIPS = 8
LOW_VALUE_COMET_PRODUCTION = 1
LATE_CAPTURE_BUFFER = 5
VERY_LATE_CAPTURE_BUFFER = 3

REAR_SOURCE_MIN_SHIPS = 16
REAR_DISTANCE_RATIO = 1.25
REAR_STAGE_PROGRESS = 0.78
REAR_SEND_RATIO_TWO_PLAYER = 0.62
REAR_SEND_RATIO_FOUR_PLAYER = 0.7
REAR_SEND_MIN_SHIPS = 10
REAR_MAX_TRAVEL_TURNS = 40

PARTIAL_SOURCE_MIN_SHIPS = 6
MULTI_SOURCE_TOP_K = 5
MULTI_SOURCE_ETA_TOLERANCE = 2
MULTI_SOURCE_PLAN_PENALTY = 0.97

# v6: Tightened swarm timing on hostile finishes
HOSTILE_SWARM_ETA_TOLERANCE = 1

# v6: 3-source swarm
THREE_SOURCE_SWARM_ENABLED = True
THREE_SOURCE_MIN_TARGET_SHIPS = 20
THREE_SOURCE_ETA_TOLERANCE = 1
THREE_SOURCE_PLAN_PENALTY = 0.93

# v6: Reinforcement missions
REINFORCE_ENABLED = True
REINFORCE_MIN_PRODUCTION = 2
REINFORCE_MAX_TRAVEL_TURNS = 22
REINFORCE_SAFETY_MARGIN = 2
REINFORCE_VALUE_MULT = 1.35
REINFORCE_MAX_SOURCE_FRACTION = 0.75
REINFORCE_MIN_FUTURE_TURNS = 40

# v6: Multi-enemy proactive defense
MULTI_ENEMY_PROACTIVE_HORIZON = 14
MULTI_ENEMY_PROACTIVE_RATIO = 0.22
MULTI_ENEMY_STACK_WINDOW = 3

PROACTIVE_DEFENSE_HORIZON = 12
PROACTIVE_DEFENSE_RATIO = 0.18

LATE_IMMEDIATE_SHIP_VALUE = 0.6
WEAK_ENEMY_THRESHOLD = 45
ELIMINATION_BONUS = 18.0

BEHIND_DOMINATION = -0.20
AHEAD_DOMINATION = 0.18
FINISHING_DOMINATION = 0.35
FINISHING_PROD_RATIO = 1.25
AHEAD_ATTACK_MARGIN_BONUS = 0.08
BEHIND_ATTACK_MARGIN_PENALTY = 0.05
FINISHING_ATTACK_MARGIN_BONUS = 0.08

DOOMED_EVAC_TURN_LIMIT = 24
DOOMED_MIN_SHIPS = 8

# v6: Crash-exploit missions (4-player only)
CRASH_EXPLOIT_ENABLED = True
CRASH_EXPLOIT_MIN_TOTAL_SHIPS = 10
CRASH_EXPLOIT_ETA_WINDOW = 2
CRASH_EXPLOIT_POST_CRASH_DELAY = 1
CRASH_EXPLOIT_VALUE_MULT = 1.18


# =============================================================================
# TYPES
# =============================================================================

Planet = namedtuple(
    "Planet", ["id", "owner", "x", "y", "radius", "ships", "production"]
)
Fleet = namedtuple(
    "Fleet", ["id", "owner", "x", "y", "angle", "from_planet_id", "ships"]
)


@dataclass(frozen=True)
class ShotOption:
    score: float
    src_id: int
    target_id: int
    angle: float
    turns: int
    needed: int
    send_cap: int
    mission: str = "capture"


@dataclass
class Mission:
    kind: str
    score: float
    target_id: int
    turns: int
    options: list = field(default_factory=list)


# =============================================================================
# PHYSICS
# =============================================================================

def dist(ax, ay, bx, by):
    return math.hypot(ax - bx, ay - by)


def orbital_radius(planet):
    return dist(planet.x, planet.y, CENTER_X, CENTER_Y)


def is_static_planet(planet):
    return orbital_radius(planet) + planet.radius >= ROTATION_LIMIT


def fleet_speed(ships):
    if ships <= 1:
        return 1.0
    ratio = math.log(ships) / math.log(1000.0)
    ratio = max(0.0, min(1.0, ratio))
    return 1.0 + (MAX_SPEED - 1.0) * (ratio ** 1.5)


def point_to_segment_distance(px, py, x1, y1, x2, y2):
    dx = x2 - x1
    dy = y2 - y1
    seg_len_sq = dx * dx + dy * dy
    if seg_len_sq <= 1e-9:
        return dist(px, py, x1, y1)
    t = ((px - x1) * dx + (py - y1) * dy) / seg_len_sq
    t = max(0.0, min(1.0, t))
    proj_x = x1 + t * dx
    proj_y = y1 + t * dy
    return dist(px, py, proj_x, proj_y)


def segment_hits_sun(x1, y1, x2, y2, safety=SUN_SAFETY):
    return point_to_segment_distance(CENTER_X, CENTER_Y, x1, y1, x2, y2) < SUN_R + safety


def launch_point(sx, sy, sr, angle):
    clearance = sr + LAUNCH_CLEARANCE
    return sx + math.cos(angle) * clearance, sy + math.sin(angle) * clearance


def actual_path_geometry(sx, sy, sr, tx, ty, tr):
    angle = math.atan2(ty - sy, tx - sx)
    start_x, start_y = launch_point(sx, sy, sr, angle)
    hit_distance = max(0.0, dist(sx, sy, tx, ty) - (sr + LAUNCH_CLEARANCE) - tr)
    end_x = start_x + math.cos(angle) * hit_distance
    end_y = start_y + math.sin(angle) * hit_distance
    return angle, start_x, start_y, end_x, end_y, hit_distance


def safe_angle_and_distance(sx, sy, sr, tx, ty, tr):
    angle, start_x, start_y, end_x, end_y, hit_distance = actual_path_geometry(
        sx, sy, sr, tx, ty, tr,
    )
    if segment_hits_sun(start_x, start_y, end_x, end_y):
        return None
    return angle, hit_distance


def predict_planet_position(planet, initial_by_id, angular_velocity, turns):
    init = initial_by_id.get(planet.id)
    if init is None:
        return planet.x, planet.y
    r = dist(init.x, init.y, CENTER_X, CENTER_Y)
    if r + init.radius >= ROTATION_LIMIT:
        return planet.x, planet.y
    cur_ang = math.atan2(planet.y - CENTER_Y, planet.x - CENTER_X)
    new_ang = cur_ang + angular_velocity * turns
    return (
        CENTER_X + r * math.cos(new_ang),
        CENTER_Y + r * math.sin(new_ang),
    )


def predict_comet_position(planet_id, comets, turns):
    for group in comets:
        pids = group.get("planet_ids", [])
        if planet_id not in pids:
            continue
        idx = pids.index(planet_id)
        paths = group.get("paths", [])
        path_index = group.get("path_index", 0)
        if idx >= len(paths):
            return None
        path = paths[idx]
        future_idx = path_index + int(turns)
        if 0 <= future_idx < len(path):
            return path[future_idx][0], path[future_idx][1]
        return None
    return None


def comet_remaining_life(planet_id, comets):
    for group in comets:
        pids = group.get("planet_ids", [])
        if planet_id not in pids:
            continue
        idx = pids.index(planet_id)
        paths = group.get("paths", [])
        path_index = group.get("path_index", 0)
        if idx < len(paths):
            return max(0, len(paths[idx]) - path_index)
    return 0


def estimate_arrival(sx, sy, sr, tx, ty, tr, ships):
    safe = safe_angle_and_distance(sx, sy, sr, tx, ty, tr)
    if safe is None:
        return None
    angle, total_d = safe
    turns = max(1, int(math.ceil(total_d / fleet_speed(max(1, ships)))))
    return angle, turns


def travel_time(sx, sy, sr, tx, ty, tr, ships):
    est = estimate_arrival(sx, sy, sr, tx, ty, tr, ships)
    if est is None:
        return 10 ** 9
    return est[1]


def predict_target_position(target, turns, initial_by_id, ang_vel, comets, comet_ids):
    if target.id in comet_ids:
        return predict_comet_position(target.id, comets, turns)
    return predict_planet_position(target, initial_by_id, ang_vel, turns)


def search_safe_intercept(src, target, ships, initial_by_id, ang_vel, comets, comet_ids):
    best = None
    best_score = None
    max_turns = HORIZON
    if target.id in comet_ids:
        max_turns = min(max_turns, max(0, comet_remaining_life(target.id, comets) - 1))

    for candidate_turns in range(1, max_turns + 1):
        pos = predict_target_position(
            target, candidate_turns, initial_by_id, ang_vel, comets, comet_ids,
        )
        if pos is None:
            continue
        est = estimate_arrival(src.x, src.y, src.radius, pos[0], pos[1], target.radius, ships)
        if est is None:
            continue
        _, turns = est
        if abs(turns - candidate_turns) > INTERCEPT_TOLERANCE:
            continue

        actual_turns = max(turns, candidate_turns)
        actual_pos = predict_target_position(
            target, actual_turns, initial_by_id, ang_vel, comets, comet_ids,
        )
        if actual_pos is None:
            continue

        confirm = estimate_arrival(
            src.x, src.y, src.radius, actual_pos[0], actual_pos[1], target.radius, ships,
        )
        if confirm is None:
            continue

        delta = abs(confirm[1] - actual_turns)
        if delta > INTERCEPT_TOLERANCE:
            continue

        score = (delta, confirm[1], candidate_turns)
        if best is None or score < best_score:
            best_score = score
            best = (confirm[0], confirm[1], actual_pos[0], actual_pos[1])

    return best


def aim_with_prediction(src, target, ships, initial_by_id, ang_vel, comets, comet_ids):
    est = estimate_arrival(src.x, src.y, src.radius, target.x, target.y, target.radius, ships)
    if est is None:
        return search_safe_intercept(
            src, target, ships, initial_by_id, ang_vel, comets, comet_ids,
        )

    tx, ty = target.x, target.y
    for _ in range(5):
        _, turns = est
        pos = predict_target_position(target, turns, initial_by_id, ang_vel, comets, comet_ids)
        if pos is None:
            return None
        ntx, nty = pos
        next_est = estimate_arrival(src.x, src.y, src.radius, ntx, nty, target.radius, ships)
        if next_est is None:
            return search_safe_intercept(
                src, target, ships, initial_by_id, ang_vel, comets, comet_ids,
            )
        if (
            abs(ntx - tx) < 0.3
            and abs(nty - ty) < 0.3
            and abs(next_est[1] - turns) <= INTERCEPT_TOLERANCE
        ):
            return next_est[0], next_est[1], ntx, nty
        tx, ty = ntx, nty
        est = next_est

    final_est = estimate_arrival(src.x, src.y, src.radius, tx, ty, target.radius, ships)
    if final_est is None:
        return search_safe_intercept(
            src, target, ships, initial_by_id, ang_vel, comets, comet_ids,
        )
    return final_est[0], final_est[1], tx, ty


# =============================================================================
# WORLD MODEL
# =============================================================================

def fleet_target_planet(fleet, planets):
    best_planet = None
    best_time = 1e9
    dir_x = math.cos(fleet.angle)
    dir_y = math.sin(fleet.angle)
    speed = fleet_speed(fleet.ships)

    for planet in planets:
        dx = planet.x - fleet.x
        dy = planet.y - fleet.y
        proj = dx * dir_x + dy * dir_y
        if proj < 0:
            continue
        perp_sq = dx * dx + dy * dy - proj * proj
        radius_sq = planet.radius * planet.radius
        if perp_sq >= radius_sq:
            continue
        hit_d = max(0.0, proj - math.sqrt(max(0.0, radius_sq - perp_sq)))
        turns = hit_d / speed
        if turns <= HORIZON and turns < best_time:
            best_time = turns
            best_planet = planet

    if best_planet is None:
        return None, None
    return best_planet, int(math.ceil(best_time))


def build_arrival_ledger(fleets, planets):
    arrivals_by_planet = {planet.id: [] for planet in planets}
    for fleet in fleets:
        target, eta = fleet_target_planet(fleet, planets)
        if target is None:
            continue
        arrivals_by_planet[target.id].append((eta, fleet.owner, int(fleet.ships)))
    return arrivals_by_planet


def resolve_arrival_event(owner, garrison, arrivals):
    by_owner = {}
    for _, attacker_owner, ships in arrivals:
        by_owner[attacker_owner] = by_owner.get(attacker_owner, 0) + ships

    if not by_owner:
        return owner, max(0.0, garrison)

    sorted_players = sorted(by_owner.items(), key=lambda item: item[1], reverse=True)
    top_owner, top_ships = sorted_players[0]

    if len(sorted_players) > 1:
        second_ships = sorted_players[1][1]
        if top_ships == second_ships:
            survivor_owner = -1
            survivor_ships = 0
        else:
            survivor_owner = top_owner
            survivor_ships = top_ships - second_ships
    else:
        survivor_owner = top_owner
        survivor_ships = top_ships

    if survivor_ships <= 0:
        return owner, max(0.0, garrison)

    if owner == survivor_owner:
        return owner, garrison + survivor_ships

    garrison -= survivor_ships
    if garrison < 0:
        return survivor_owner, -garrison
    return owner, garrison


def normalize_arrivals(arrivals, horizon):
    events = []
    for turns, owner, ships in arrivals:
        if ships <= 0:
            continue
        eta = max(1, int(math.ceil(turns)))
        if eta > horizon:
            continue
        events.append((eta, owner, int(ships)))
    events.sort(key=lambda item: item[0])
    return events


def simulate_planet_timeline(planet, arrivals, player, horizon):
    horizon = max(0, int(math.ceil(horizon)))
    events = normalize_arrivals(arrivals, horizon)
    by_turn = defaultdict(list)
    for item in events:
        by_turn[item[0]].append(item)

    owner = planet.owner
    garrison = float(planet.ships)
    owner_at = {0: owner}
    ships_at = {0: max(0.0, garrison)}
    min_owned = garrison if owner == player else 0.0
    first_enemy = None
    fall_turn = None

    for turn in range(1, horizon + 1):
        if owner != -1:
            garrison += planet.production

        group = by_turn.get(turn, [])
        prev_owner = owner
        if group:
            if prev_owner == player and first_enemy is None:
                if any(item[1] not in (-1, player) for item in group):
                    first_enemy = turn
            owner, garrison = resolve_arrival_event(owner, garrison, group)
            if prev_owner == player and owner != player and fall_turn is None:
                fall_turn = turn

        owner_at[turn] = owner
        ships_at[turn] = max(0.0, garrison)
        if owner == player:
            min_owned = min(min_owned, garrison)

    keep_needed = 0
    holds_full = True

    if planet.owner == player:

        def survives_with_keep(keep):
            sim_owner = planet.owner
            sim_garrison = float(keep)
            for turn in range(1, horizon + 1):
                if sim_owner != -1:
                    sim_garrison += planet.production
                group = by_turn.get(turn, [])
                if group:
                    sim_owner, sim_garrison = resolve_arrival_event(sim_owner, sim_garrison, group)
                    if sim_owner != player:
                        return False
            return sim_owner == player

        if survives_with_keep(int(planet.ships)):
            lo, hi = 0, int(planet.ships)
            while lo < hi:
                mid = (lo + hi) // 2
                if survives_with_keep(mid):
                    hi = mid
                else:
                    lo = mid + 1
            keep_needed = lo
        else:
            holds_full = False
            keep_needed = int(planet.ships)

    return {
        "owner_at": owner_at,
        "ships_at": ships_at,
        "keep_needed": keep_needed,
        "min_owned": max(0, int(math.floor(min_owned))) if planet.owner == player else 0,
        "first_enemy": first_enemy,
        "fall_turn": fall_turn,
        "holds_full": holds_full,
        "horizon": horizon,
    }


def state_at_timeline(timeline, arrival_turn):
    turn = max(0, int(math.ceil(arrival_turn)))
    turn = min(turn, timeline["horizon"])
    owner = timeline["owner_at"].get(turn, timeline["owner_at"][timeline["horizon"]])
    ships = timeline["ships_at"].get(turn, timeline["ships_at"][timeline["horizon"]])
    return owner, max(0.0, ships)


def count_players(planets, fleets):
    owners = set()
    for planet in planets:
        if planet.owner != -1:
            owners.add(planet.owner)
    for fleet in fleets:
        owners.add(fleet.owner)
    return max(2, len(owners))


def nearest_distance_to_set(px, py, planets):
    if not planets:
        return 10 ** 9
    return min(dist(px, py, planet.x, planet.y) for planet in planets)


def indirect_wealth(planet, planets, player):
    wealth = 0.0
    for other in planets:
        if other.id == planet.id:
            continue
        d = dist(planet.x, planet.y, other.x, other.y)
        if d < 1:
            continue
        factor = other.production / (d + 12.0)
        if other.owner == player:
            wealth += factor * INDIRECT_FRIENDLY_WEIGHT
        elif other.owner == -1:
            wealth += factor * INDIRECT_NEUTRAL_WEIGHT
        else:
            wealth += factor * INDIRECT_ENEMY_WEIGHT
    return wealth


def detect_enemy_crashes(arrivals_by_planet, player, eta_window):
    crashes = []
    for target_id, arrivals in arrivals_by_planet.items():
        enemy_events = [
            (eta, owner, ships)
            for eta, owner, ships in arrivals
            if owner not in (-1, player) and ships > 0
        ]
        if len(enemy_events) < 2:
            continue

        by_owner = defaultdict(list)
        for eta, owner, ships in enemy_events:
            by_owner[owner].append((eta, ships))
        if len(by_owner) < 2:
            continue

        enemy_events.sort(key=lambda item: item[0])
        matched = False
        for i in range(len(enemy_events)):
            if matched:
                break
            for j in range(i + 1, len(enemy_events)):
                eta_a, owner_a, ships_a = enemy_events[i]
                eta_b, owner_b, ships_b = enemy_events[j]
                if owner_a == owner_b:
                    continue
                if abs(eta_a - eta_b) > eta_window:
                    continue
                total = ships_a + ships_b
                if total < CRASH_EXPLOIT_MIN_TOTAL_SHIPS:
                    continue
                crash_turn = max(eta_a, eta_b)
                crashes.append(
                    {
                        "target_id": target_id,
                        "crash_turn": crash_turn,
                        "total_enemy_ships": total,
                        "contributors": ((owner_a, ships_a), (owner_b, ships_b)),
                    }
                )
                matched = True
                break
    return crashes


class WorldModel:
    def __init__(self, player, step, planets, fleets, initial_by_id, ang_vel, comets, comet_ids):
        self.player = player
        self.step = step
        self.planets = planets
        self.fleets = fleets
        self.initial_by_id = initial_by_id
        self.ang_vel = ang_vel
        self.comets = comets
        self.comet_ids = set(comet_ids)

        self.planet_by_id = {planet.id: planet for planet in planets}
        self.my_planets = [planet for planet in planets if planet.owner == player]
        self.enemy_planets = [planet for planet in planets if planet.owner not in (-1, player)]
        self.neutral_planets = [planet for planet in planets if planet.owner == -1]
        self.static_neutral_planets = [
            planet for planet in self.neutral_planets if is_static_planet(planet)
        ]

        self.num_players = count_players(planets, fleets)
        self.remaining_steps = max(1, TOTAL_STEPS - step)
        self.is_early = step < EARLY_TURN_LIMIT
        self.is_opening = step < OPENING_TURN_LIMIT
        self.is_late = self.remaining_steps < LATE_REMAINING_TURNS
        self.is_very_late = self.remaining_steps < VERY_LATE_REMAINING_TURNS
        self.is_four_player = self.num_players >= 4

        self.owner_strength = defaultdict(int)
        self.owner_production = defaultdict(int)
        for planet in planets:
            if planet.owner != -1:
                self.owner_strength[planet.owner] += int(planet.ships)
                self.owner_production[planet.owner] += int(planet.production)
        for fleet in fleets:
            self.owner_strength[fleet.owner] += int(fleet.ships)

        self.my_total = self.owner_strength.get(player, 0)
        self.enemy_total = sum(
            strength for owner, strength in self.owner_strength.items() if owner != player
        )
        self.max_enemy_strength = max(
            (strength for owner, strength in self.owner_strength.items() if owner != player),
            default=0,
        )
        self.my_prod = self.owner_production.get(player, 0)
        self.enemy_prod = sum(
            production
            for owner, production in self.owner_production.items()
            if owner != player
        )

        self.arrivals_by_planet = build_arrival_ledger(fleets, planets)
        self.base_timeline = {
            planet.id: simulate_planet_timeline(
                planet,
                self.arrivals_by_planet[planet.id],
                player,
                HORIZON,
            )
            for planet in planets
        }
        self.indirect_wealth_map = {
            planet.id: indirect_wealth(planet, planets, player) for planet in planets
        }
        self.reaction_cache = {}
        self.base_need_cache = {}

        (
            self.reserve,
            self.available,
            self.doomed_candidates,
            self.threatened_candidates,
        ) = self._compute_defense_buffers()

        if CRASH_EXPLOIT_ENABLED and self.is_four_player:
            self.enemy_crashes = detect_enemy_crashes(
                self.arrivals_by_planet,
                player,
                CRASH_EXPLOIT_ETA_WINDOW,
            )
        else:
            self.enemy_crashes = []

    def _multi_enemy_proactive_keep(self, planet):
        if not self.enemy_planets:
            return 0

        threats = []
        for enemy in self.enemy_planets:
            eta = travel_time(
                enemy.x, enemy.y, enemy.radius,
                planet.x, planet.y, planet.radius,
                max(1, enemy.ships),
            )
            if eta > MULTI_ENEMY_PROACTIVE_HORIZON:
                continue
            threats.append((eta, int(enemy.ships)))
        if not threats:
            return 0

        threats.sort()
        best_stacked = 0
        left = 0
        running = 0
        for right in range(len(threats)):
            running += threats[right][1]
            while threats[right][0] - threats[left][0] > MULTI_ENEMY_STACK_WINDOW:
                running -= threats[left][1]
                left += 1
            best_stacked = max(best_stacked, running)

        proactive = int(best_stacked * MULTI_ENEMY_PROACTIVE_RATIO)

        legacy = 0
        for eta, ships in threats:
            if eta <= PROACTIVE_DEFENSE_HORIZON:
                legacy = max(legacy, int(ships * PROACTIVE_DEFENSE_RATIO))
        return max(proactive, legacy)

    def _compute_defense_buffers(self):
        reserve = {}
        available = {}
        doomed_candidates = set()
        threatened_candidates = {}

        for planet in self.my_planets:
            timeline = self.base_timeline[planet.id]
            exact_keep = timeline["keep_needed"]

            proactive_keep = self._multi_enemy_proactive_keep(planet)

            reserve[planet.id] = min(int(planet.ships), max(exact_keep, proactive_keep))
            available[planet.id] = max(0, int(planet.ships) - reserve[planet.id])

            if not timeline["holds_full"] and timeline["fall_turn"] is not None:
                fall_turn = timeline["fall_turn"]
                if fall_turn <= DOOMED_EVAC_TURN_LIMIT and planet.ships >= DOOMED_MIN_SHIPS:
                    doomed_candidates.add(planet.id)

                if (
                    REINFORCE_ENABLED
                    and planet.production >= REINFORCE_MIN_PRODUCTION
                    and self.remaining_steps >= REINFORCE_MIN_FUTURE_TURNS
                ):
                    ships_at = timeline["ships_at"]
                    owner_at = timeline["owner_at"]
                    deficit_hint = 0
                    for turn in range(1, fall_turn + 1):
                        if owner_at.get(turn) != self.player:
                            deficit_hint = max(deficit_hint, int(math.ceil(ships_at.get(turn, 0))) + 1)
                            break
                    threatened_candidates[planet.id] = {
                        "fall_turn": fall_turn,
                        "deficit_hint": max(1, deficit_hint),
                    }

        return reserve, available, doomed_candidates, threatened_candidates

    def is_static(self, planet_id):
        return is_static_planet(self.planet_by_id[planet_id])

    def comet_life(self, planet_id):
        return comet_remaining_life(planet_id, self.comets)

    def source_inventory_left(self, source_id, spent_total):
        return max(0, int(self.planet_by_id[source_id].ships) - spent_total[source_id])

    def source_attack_left(self, source_id, spent_total):
        return max(0, self.available.get(source_id, 0) - spent_total[source_id])

    def plan_shot(self, src_id, target_id, ships):
        src = self.planet_by_id[src_id]
        target = self.planet_by_id[target_id]
        return aim_with_prediction(
            src, target, ships,
            self.initial_by_id, self.ang_vel, self.comets, self.comet_ids,
        )

    def reaction_times(self, target_id):
        cached = self.reaction_cache.get(target_id)
        if cached is not None:
            return cached

        target = self.planet_by_id[target_id]
        my_t = min(
            (
                travel_time(
                    planet.x, planet.y, planet.radius,
                    target.x, target.y, target.radius,
                    max(1, planet.ships),
                )
                for planet in self.my_planets
            ),
            default=10 ** 9,
        )
        enemy_t = min(
            (
                travel_time(
                    planet.x, planet.y, planet.radius,
                    target.x, target.y, target.radius,
                    max(1, planet.ships),
                )
                for planet in self.enemy_planets
            ),
            default=10 ** 9,
        )
        cached = (my_t, enemy_t)
        self.reaction_cache[target_id] = cached
        return cached

    def projected_state(self, target_id, arrival_turn, planned_commitments=None, extra_arrivals=()):
        planned_commitments = planned_commitments or {}
        cutoff = max(1, int(math.ceil(arrival_turn)))
        if not planned_commitments.get(target_id) and not extra_arrivals:
            return state_at_timeline(self.base_timeline[target_id], cutoff)

        arrivals = [
            item for item in self.arrivals_by_planet.get(target_id, []) if item[0] <= cutoff
        ]
        arrivals.extend(
            item for item in planned_commitments.get(target_id, []) if item[0] <= cutoff
        )
        arrivals.extend(item for item in extra_arrivals if item[0] <= cutoff)

        target = self.planet_by_id[target_id]
        dyn = simulate_planet_timeline(target, arrivals, self.player, cutoff)
        return state_at_timeline(dyn, cutoff)

    def ships_needed_to_capture(self, target_id, arrival_turn, planned_commitments=None, extra_arrivals=()):
        planned_commitments = planned_commitments or {}
        cutoff = max(1, int(math.ceil(arrival_turn)))
        cache_key = None
        if not planned_commitments.get(target_id) and not extra_arrivals:
            cache_key = (target_id, cutoff)
            if cache_key in self.base_need_cache:
                return self.base_need_cache[cache_key]

        owner_t, ships_t = self.projected_state(
            target_id, cutoff,
            planned_commitments=planned_commitments,
            extra_arrivals=extra_arrivals,
        )
        if owner_t == self.player:
            need = 0
        else:
            need = int(math.ceil(ships_t)) + 1

        if cache_key is not None:
            self.base_need_cache[cache_key] = need
        return need

    def reinforcement_needed_for(self, planet_id, arrival_turn, planned_commitments=None):
        planned_commitments = planned_commitments or {}
        arrival_turn = max(1, int(math.ceil(arrival_turn)))
        planet = self.planet_by_id[planet_id]
        if planet.owner != self.player:
            return self.ships_needed_to_capture(planet_id, arrival_turn, planned_commitments)

        arrivals = list(self.arrivals_by_planet.get(planet_id, []))
        for item in planned_commitments.get(planet_id, []):
            arrivals.append(item)

        horizon = max(arrival_turn + 5, self.base_timeline[planet_id]["horizon"])
        timeline = simulate_planet_timeline(planet, arrivals, self.player, horizon)

        lookahead_end = min(horizon, arrival_turn + 20)
        worst_deficit = 0
        for turn in range(arrival_turn, lookahead_end + 1):
            owner = timeline["owner_at"].get(turn)
            ships = timeline["ships_at"].get(turn, 0)
            if owner != self.player:
                worst_deficit = max(worst_deficit, int(math.ceil(ships)) + 1)
        return worst_deficit


# =============================================================================
# STRATEGY
# =============================================================================

def planet_distance(first, second):
    return math.hypot(first.x - second.x, first.y - second.y)


def build_modes(world):
    domination = (world.my_total - world.enemy_total) / max(1, world.my_total + world.enemy_total)
    is_behind = domination < BEHIND_DOMINATION
    is_ahead = domination > AHEAD_DOMINATION
    is_dominating = is_ahead or (
        world.max_enemy_strength > 0 and world.my_total > world.max_enemy_strength * 1.25
    )
    is_finishing = (
        domination > FINISHING_DOMINATION
        and world.my_prod > world.enemy_prod * FINISHING_PROD_RATIO
        and world.step > 100
    )

    attack_margin_mult = 1.0
    if is_ahead:
        attack_margin_mult += AHEAD_ATTACK_MARGIN_BONUS
    if is_behind:
        attack_margin_mult -= BEHIND_ATTACK_MARGIN_PENALTY
    if is_finishing:
        attack_margin_mult += FINISHING_ATTACK_MARGIN_BONUS

    return {
        "domination": domination,
        "is_behind": is_behind,
        "is_ahead": is_ahead,
        "is_dominating": is_dominating,
        "is_finishing": is_finishing,
        "attack_margin_mult": attack_margin_mult,
    }


def is_safe_neutral(target, world):
    if target.owner != -1:
        return False
    my_t, enemy_t = world.reaction_times(target.id)
    return my_t <= enemy_t - SAFE_NEUTRAL_MARGIN


def is_contested_neutral(target, world):
    if target.owner != -1:
        return False
    my_t, enemy_t = world.reaction_times(target.id)
    return abs(my_t - enemy_t) <= CONTESTED_NEUTRAL_MARGIN


def opening_filter(target, arrival_turns, needed, src_available, world):
    if not world.is_opening or target.owner != -1:
        return False
    if target.id in world.comet_ids:
        return False
    if world.is_static(target.id):
        return False

    my_t, enemy_t = world.reaction_times(target.id)
    reaction_gap = enemy_t - my_t
    if (
        target.production >= SAFE_OPENING_PROD_THRESHOLD
        and arrival_turns <= SAFE_OPENING_TURN_LIMIT
        and reaction_gap >= SAFE_NEUTRAL_MARGIN
    ):
        return False

    if world.is_four_player:
        affordable = needed <= max(
            PARTIAL_SOURCE_MIN_SHIPS,
            int(src_available * FOUR_PLAYER_ROTATING_SEND_RATIO),
        )
        if (
            affordable
            and arrival_turns <= FOUR_PLAYER_ROTATING_TURN_LIMIT
            and reaction_gap >= FOUR_PLAYER_ROTATING_REACTION_GAP
        ):
            return False
        return True

    return arrival_turns > ROTATING_OPENING_MAX_TURNS or target.production <= ROTATING_OPENING_LOW_PROD


def target_value(target, arrival_turns, mission, world, modes):
    turns_profit = max(1, world.remaining_steps - arrival_turns)
    if target.id in world.comet_ids:
        life = world.comet_life(target.id)
        turns_profit = max(0, min(turns_profit, life - arrival_turns))
        if turns_profit <= 0:
            return -1.0

    value = target.production * turns_profit
    value += world.indirect_wealth_map[target.id] * turns_profit * INDIRECT_VALUE_SCALE

    if world.is_static(target.id):
        value *= STATIC_NEUTRAL_VALUE_MULT if target.owner == -1 else STATIC_HOSTILE_VALUE_MULT
    else:
        value *= ROTATING_OPENING_VALUE_MULT if world.is_opening else 1.0

    if target.owner not in (-1, world.player):
        value *= OPENING_HOSTILE_TARGET_VALUE_MULT if world.is_opening else HOSTILE_TARGET_VALUE_MULT

    if target.owner == -1:
        if is_safe_neutral(target, world):
            value *= SAFE_NEUTRAL_VALUE_MULT
        elif is_contested_neutral(target, world):
            value *= CONTESTED_NEUTRAL_VALUE_MULT
        if world.is_early:
            value *= EARLY_NEUTRAL_VALUE_MULT

    if target.id in world.comet_ids:
        value *= COMET_VALUE_MULT

    if mission == "snipe":
        value *= SNIPE_VALUE_MULT
    elif mission == "swarm":
        value *= SWARM_VALUE_MULT
    elif mission == "reinforce":
        value *= REINFORCE_VALUE_MULT
    elif mission == "crash_exploit":
        value *= CRASH_EXPLOIT_VALUE_MULT

    if world.is_late:
        value += max(0, target.ships) * LATE_IMMEDIATE_SHIP_VALUE
        if target.owner not in (-1, world.player):
            enemy_strength = world.owner_strength.get(target.owner, 0)
            if enemy_strength <= WEAK_ENEMY_THRESHOLD:
                value += ELIMINATION_BONUS

    if modes["is_finishing"] and target.owner not in (-1, world.player):
        value *= FINISHING_HOSTILE_VALUE_MULT
    if modes["is_behind"] and target.owner == -1 and not world.is_static(target.id):
        value *= BEHIND_ROTATING_NEUTRAL_VALUE_MULT
    if modes["is_behind"] and target.owner == -1 and is_safe_neutral(target, world):
        value *= 1.08
    if modes["is_dominating"] and target.owner == -1 and is_contested_neutral(target, world):
        value *= 0.92

    return value


def preferred_send(target, base_needed, arrival_turns, src_available, world, modes):
    send = max(base_needed, int(math.ceil(base_needed * modes["attack_margin_mult"])))
    margin = 0
    if target.owner == -1:
        margin += min(
            NEUTRAL_MARGIN_CAP,
            NEUTRAL_MARGIN_BASE + target.production * NEUTRAL_MARGIN_PROD_WEIGHT,
        )
    else:
        margin += min(
            HOSTILE_MARGIN_CAP,
            HOSTILE_MARGIN_BASE + target.production * HOSTILE_MARGIN_PROD_WEIGHT,
        )
    if world.is_static(target.id):
        margin += STATIC_TARGET_MARGIN
    if is_contested_neutral(target, world):
        margin += CONTESTED_TARGET_MARGIN
    if world.is_four_player:
        margin += FOUR_PLAYER_TARGET_MARGIN
    if arrival_turns > LONG_TRAVEL_MARGIN_START:
        margin += min(LONG_TRAVEL_MARGIN_CAP, arrival_turns // LONG_TRAVEL_MARGIN_DIVISOR)
    if target.id in world.comet_ids:
        margin = max(0, margin - COMET_MARGIN_RELIEF)
    if modes["is_finishing"] and target.owner not in (-1, world.player):
        margin += FINISHING_HOSTILE_SEND_BONUS
    return min(src_available, send + margin)


def apply_score_modifiers(base_score, target, mission, world):
    score = base_score
    if world.is_static(target.id):
        score *= STATIC_TARGET_SCORE_MULT
    if world.is_early and target.owner == -1 and world.is_static(target.id):
        score *= EARLY_STATIC_NEUTRAL_SCORE_MULT
    if world.is_four_player and target.owner == -1 and not world.is_static(target.id):
        score *= FOUR_PLAYER_ROTATING_NEUTRAL_SCORE_MULT
    if (
        len(world.static_neutral_planets) >= DENSE_STATIC_NEUTRAL_COUNT
        and target.owner == -1
        and not world.is_static(target.id)
    ):
        score *= DENSE_ROTATING_NEUTRAL_SCORE_MULT
    if mission == "snipe":
        score *= SNIPE_SCORE_MULT
    elif mission == "swarm":
        score *= SWARM_SCORE_MULT
    return score


def build_snipe_mission(src, target, src_available, world, planned_commitments, modes):
    if target.owner != -1:
        return None

    enemy_etas = sorted(
        {
            int(math.ceil(eta))
            for eta, owner, ships in world.arrivals_by_planet.get(target.id, [])
            if owner not in (-1, world.player) and ships > 0
        }
    )
    if not enemy_etas:
        return None

    probe = min(src_available, max(PARTIAL_SOURCE_MIN_SHIPS, int(target.ships) + 8))
    rough = world.plan_shot(src.id, target.id, probe)
    if rough is None:
        return None

    for enemy_eta in enemy_etas[:3]:
        if abs(rough[1] - enemy_eta) > 1:
            continue

        sync_turn = max(rough[1], enemy_eta)
        if target.id in world.comet_ids:
            life = world.comet_life(target.id)
            if sync_turn >= life or sync_turn > COMET_MAX_CHASE_TURNS:
                continue

        need = world.ships_needed_to_capture(target.id, sync_turn, planned_commitments)
        if need <= 0 or need > src_available:
            continue

        final = world.plan_shot(src.id, target.id, need)
        if final is None:
            continue

        angle, turns, _, _ = final
        if abs(turns - enemy_eta) > 1:
            continue

        sync_turn = max(turns, enemy_eta)
        need = world.ships_needed_to_capture(target.id, sync_turn, planned_commitments)
        if need <= 0 or need > src_available:
            continue

        value = target_value(target, sync_turn, "snipe", world, modes)
        if value <= 0:
            continue

        score = apply_score_modifiers(
            value / (need + sync_turn * SNIPE_COST_TURN_WEIGHT + 1.0),
            target, "snipe", world,
        )
        option = ShotOption(
            score=score,
            src_id=src.id,
            target_id=target.id,
            angle=angle,
            turns=turns,
            needed=need,
            send_cap=need,
            mission="snipe",
        )
        return Mission(
            kind="snipe", score=score, target_id=target.id,
            turns=sync_turn, options=[option],
        )

    return None


def build_reinforcement_missions(world, planned_commitments, modes, source_budget_fn):
    if not REINFORCE_ENABLED or not world.threatened_candidates:
        return []

    missions = []
    for target_id, info in world.threatened_candidates.items():
        target = world.planet_by_id[target_id]
        fall_turn = info["fall_turn"]
        if fall_turn is None or fall_turn > REINFORCE_MAX_TRAVEL_TURNS + 5:
            continue

        best_mission = None
        for src in world.my_planets:
            if src.id == target_id:
                continue
            budget = source_budget_fn(src.id)
            if budget <= 0:
                continue
            source_cap = min(budget, int(src.ships * REINFORCE_MAX_SOURCE_FRACTION))
            if source_cap <= 0:
                continue

            probe_ships = max(PARTIAL_SOURCE_MIN_SHIPS, int(info["deficit_hint"]) + REINFORCE_SAFETY_MARGIN)
            probe_ships = min(probe_ships, source_cap)
            if probe_ships <= 0:
                continue

            aim = world.plan_shot(src.id, target.id, probe_ships)
            if aim is None:
                continue
            angle, turns, _, _ = aim
            if turns > REINFORCE_MAX_TRAVEL_TURNS:
                continue
            if turns > fall_turn:
                continue

            need = world.reinforcement_needed_for(target_id, turns, planned_commitments)
            if need <= 0:
                continue
            send = min(source_cap, need + REINFORCE_SAFETY_MARGIN)
            if send < need:
                continue

            final = world.plan_shot(src.id, target.id, send)
            if final is None:
                continue
            angle, turns, _, _ = final
            if turns > fall_turn:
                continue

            value = target_value(target, turns, "reinforce", world, modes)
            if value <= 0:
                continue
            score = value / (send + turns * 0.35 + 1.0)

            option = ShotOption(
                score=score,
                src_id=src.id, target_id=target_id,
                angle=angle, turns=turns,
                needed=need, send_cap=send,
                mission="reinforce",
            )
            mission = Mission(
                kind="reinforce", score=score, target_id=target_id,
                turns=turns, options=[option],
            )
            if best_mission is None or mission.score > best_mission.score:
                best_mission = mission

        if best_mission is not None:
            missions.append(best_mission)

    return missions


def build_crash_exploit_missions(world, planned_commitments, modes):
    if not CRASH_EXPLOIT_ENABLED or not world.enemy_crashes:
        return []

    missions = []
    for crash in world.enemy_crashes:
        target_id = crash["target_id"]
        target = world.planet_by_id[target_id]
        if target.owner == world.player:
            continue
        crash_turn = crash["crash_turn"]
        desired_arrival = crash_turn + CRASH_EXPLOIT_POST_CRASH_DELAY

        best = None
        for src in world.my_planets:
            probe = max(PARTIAL_SOURCE_MIN_SHIPS, 12)
            probe = min(probe, int(src.ships))
            if probe <= 0:
                continue
            aim = world.plan_shot(src.id, target_id, probe)
            if aim is None:
                continue
            _, turns, _, _ = aim
            if abs(turns - desired_arrival) > 2:
                continue

            need = world.ships_needed_to_capture(target_id, turns, planned_commitments)
            if need <= 0 or need > int(src.ships):
                continue
            final = world.plan_shot(src.id, target_id, need)
            if final is None:
                continue
            angle, turns, _, _ = final
            if abs(turns - desired_arrival) > 2:
                continue
            need = world.ships_needed_to_capture(target_id, turns, planned_commitments)
            if need <= 0:
                continue

            value = target_value(target, turns, "crash_exploit", world, modes)
            if value <= 0:
                continue
            score = value / (need + turns * SNIPE_COST_TURN_WEIGHT + 1.0)
            option = ShotOption(
                score=score,
                src_id=src.id, target_id=target_id,
                angle=angle, turns=turns,
                needed=need, send_cap=need,
                mission="crash_exploit",
            )
            mission = Mission(
                kind="crash_exploit", score=score, target_id=target_id,
                turns=turns, options=[option],
            )
            if best is None or mission.score > best.score:
                best = mission
        if best is not None:
            missions.append(best)
    return missions


def plan_moves(world):
    modes = build_modes(world)
    planned_commitments = defaultdict(list)
    source_options_by_target = defaultdict(list)
    missions = []
    moves = []
    spent_total = defaultdict(int)

    def source_inventory_left(source_id):
        return world.source_inventory_left(source_id, spent_total)

    def source_attack_left(source_id):
        return world.source_attack_left(source_id, spent_total)

    def append_move(src_id, angle, ships):
        send = min(int(ships), source_inventory_left(src_id))
        if send < 1:
            return 0
        moves.append([src_id, float(angle), int(send)])
        spent_total[src_id] += send
        return send

    # v6: Reinforcement missions first (competes on score with captures)
    reinforce_missions = build_reinforcement_missions(
        world, planned_commitments, modes, source_inventory_left,
    )
    missions.extend(reinforce_missions)

    for src in world.my_planets:
        src_available = source_attack_left(src.id)
        if src_available <= 0:
            continue

        for target in world.planets:
            if target.id == src.id or target.owner == world.player:
                continue

            rough_ships = max(
                1,
                min(src_available, max(PARTIAL_SOURCE_MIN_SHIPS, int(target.ships) + 1)),
            )
            rough_aim = world.plan_shot(src.id, target.id, rough_ships)
            if rough_aim is None:
                continue

            rough_turns = rough_aim[1]
            if world.is_very_late and rough_turns > world.remaining_steps - VERY_LATE_CAPTURE_BUFFER:
                continue
            if target.id in world.comet_ids:
                life = world.comet_life(target.id)
                if rough_turns >= life or rough_turns > COMET_MAX_CHASE_TURNS:
                    continue

            rough_needed = world.ships_needed_to_capture(target.id, rough_turns, planned_commitments)
            if rough_needed <= 0:
                continue
            if opening_filter(target, rough_turns, rough_needed, src_available, world):
                continue

            send_guess = preferred_send(target, rough_needed, rough_turns, src_available, world, modes)
            aim = world.plan_shot(src.id, target.id, max(1, send_guess))
            if aim is None:
                continue

            angle, turns, _, _ = aim
            if world.is_very_late and turns > world.remaining_steps - VERY_LATE_CAPTURE_BUFFER:
                continue
            if target.id in world.comet_ids:
                life = world.comet_life(target.id)
                if turns >= life or turns > COMET_MAX_CHASE_TURNS:
                    continue

            needed = world.ships_needed_to_capture(target.id, turns, planned_commitments)
            if needed <= 0:
                continue
            if opening_filter(target, turns, needed, src_available, world):
                continue

            send_cap = min(src_available, preferred_send(target, needed, turns, src_available, world, modes))
            if send_cap < 1:
                continue
            if send_cap < needed and send_cap < PARTIAL_SOURCE_MIN_SHIPS:
                continue

            value = target_value(target, turns, "capture", world, modes)
            if value <= 0:
                continue

            expected_send = max(
                needed,
                min(send_cap, preferred_send(target, needed, turns, send_cap, world, modes)),
            )
            score = apply_score_modifiers(
                value / (expected_send + turns * ATTACK_COST_TURN_WEIGHT + 1.0),
                target, "capture", world,
            )

            option = ShotOption(
                score=score, src_id=src.id, target_id=target.id,
                angle=angle, turns=turns,
                needed=needed, send_cap=send_cap,
                mission="capture",
            )
            source_options_by_target[target.id].append(option)

            if send_cap >= needed:
                missions.append(
                    Mission(kind="single", score=score, target_id=target.id,
                            turns=turns, options=[option])
                )

            snipe = build_snipe_mission(src, target, src_available, world, planned_commitments, modes)
            if snipe is not None:
                missions.append(snipe)

    # Multi-source swarm assembly
    for target_id, options in source_options_by_target.items():
        if len(options) < 2:
            continue

        target = world.planet_by_id[target_id]
        top_options = sorted(options, key=lambda item: -item.score)[:MULTI_SOURCE_TOP_K]

        hostile_target = target.owner not in (-1, world.player)
        # v6: tighter tolerance on hostile finishes
        eta_tolerance_2 = (
            HOSTILE_SWARM_ETA_TOLERANCE if hostile_target else MULTI_SOURCE_ETA_TOLERANCE
        )

        for i in range(len(top_options)):
            for j in range(i + 1, len(top_options)):
                first = top_options[i]
                second = top_options[j]
                if first.src_id == second.src_id:
                    continue
                if abs(first.turns - second.turns) > eta_tolerance_2:
                    continue

                joint_turn = max(first.turns, second.turns)
                need = world.ships_needed_to_capture(target_id, joint_turn, planned_commitments)
                if need <= 0:
                    continue
                if first.send_cap >= need or second.send_cap >= need:
                    continue

                total_cap = first.send_cap + second.send_cap
                if total_cap < need:
                    continue

                value = target_value(target, joint_turn, "swarm", world, modes)
                if value <= 0:
                    continue

                pair_score = apply_score_modifiers(
                    value / (need + joint_turn * ATTACK_COST_TURN_WEIGHT + 1.0),
                    target, "swarm", world,
                )
                pair_score *= MULTI_SOURCE_PLAN_PENALTY
                missions.append(
                    Mission(kind="swarm", score=pair_score, target_id=target_id,
                            turns=joint_turn, options=[first, second])
                )

        # v6: 3-source swarm for heavy hostile finishes
        if (
            THREE_SOURCE_SWARM_ENABLED
            and hostile_target
            and int(target.ships) >= THREE_SOURCE_MIN_TARGET_SHIPS
            and len(top_options) >= 3
        ):
            for i in range(len(top_options)):
                for j in range(i + 1, len(top_options)):
                    for k in range(j + 1, len(top_options)):
                        trio = [top_options[i], top_options[j], top_options[k]]
                        src_ids = {opt.src_id for opt in trio}
                        if len(src_ids) < 3:
                            continue
                        eta_spread = max(opt.turns for opt in trio) - min(opt.turns for opt in trio)
                        if eta_spread > THREE_SOURCE_ETA_TOLERANCE:
                            continue

                        joint_turn = max(opt.turns for opt in trio)
                        need = world.ships_needed_to_capture(target_id, joint_turn, planned_commitments)
                        if need <= 0:
                            continue
                        total_cap = sum(opt.send_cap for opt in trio)
                        if total_cap < need:
                            continue
                        if any(
                            trio[a].send_cap + trio[b].send_cap >= need
                            for a in range(3) for b in range(a + 1, 3)
                        ):
                            continue

                        value = target_value(target, joint_turn, "swarm", world, modes)
                        if value <= 0:
                            continue
                        trio_score = apply_score_modifiers(
                            value / (need + joint_turn * ATTACK_COST_TURN_WEIGHT + 1.0),
                            target, "swarm", world,
                        )
                        trio_score *= THREE_SOURCE_PLAN_PENALTY
                        missions.append(
                            Mission(kind="swarm", score=trio_score, target_id=target_id,
                                    turns=joint_turn, options=trio)
                        )

    # v6: Crash-exploit missions
    crash_missions = build_crash_exploit_missions(world, planned_commitments, modes)
    missions.extend(crash_missions)

    missions.sort(key=lambda item: -item.score)

    for mission in missions:
        target = world.planet_by_id[mission.target_id]

        if mission.kind in ("single", "snipe", "reinforce", "crash_exploit"):
            option = mission.options[0]

            if mission.kind == "reinforce":
                left = source_inventory_left(option.src_id)
            else:
                left = source_attack_left(option.src_id)
            if left <= 0:
                continue

            arrival_turn = option.turns

            if mission.kind == "reinforce":
                missing = world.reinforcement_needed_for(option.target_id, arrival_turn, planned_commitments)
            else:
                missing = world.ships_needed_to_capture(target.id, arrival_turn, planned_commitments)
            if missing <= 0:
                continue

            send_limit = min(left, option.send_cap)
            if send_limit < missing:
                continue

            if mission.kind in ("snipe", "crash_exploit"):
                send = missing
            elif mission.kind == "reinforce":
                send = min(send_limit, missing + REINFORCE_SAFETY_MARGIN)
            else:
                send = min(
                    send_limit,
                    max(missing, preferred_send(target, missing, arrival_turn, send_limit, world, modes)),
                )
            if send < missing:
                continue

            sent = append_move(option.src_id, option.angle, send)
            if sent < missing:
                continue
            planned_commitments[target.id].append((arrival_turn, world.player, int(sent)))
            continue

        limits = []
        for option in mission.options:
            left = source_attack_left(option.src_id)
            limits.append(min(left, option.send_cap))
        if min(limits) <= 0:
            continue

        missing = world.ships_needed_to_capture(target.id, mission.turns, planned_commitments)
        if missing <= 0:
            continue
        if sum(limits) < missing:
            continue

        ordered = sorted(
            zip(mission.options, limits),
            key=lambda item: (item[0].turns, -item[1], item[0].src_id),
        )
        remaining = missing
        sends = {}
        for idx, (option, limit) in enumerate(ordered):
            remaining_other = sum(other_limit for _, other_limit in ordered[idx + 1:])
            send = min(limit, max(0, remaining - remaining_other))
            sends[option.src_id] = send
            remaining -= send
        if remaining > 0:
            continue

        committed = []
        for option, _ in ordered:
            send = sends.get(option.src_id, 0)
            if send <= 0:
                continue
            actual = append_move(option.src_id, option.angle, send)
            if actual <= 0:
                continue
            committed.append((option.turns, world.player, int(actual)))
        if sum(item[2] for item in committed) < missing:
            continue
        planned_commitments[target.id].extend(committed)

    # Follow-up attack pass
    if not world.is_very_late:
        for src in world.my_planets:
            src_left = source_attack_left(src.id)
            if src_left < FOLLOWUP_MIN_SHIPS:
                continue

            best = None
            for target in world.planets:
                if target.id == src.id or target.owner == world.player:
                    continue
                if target.id in world.comet_ids and target.production <= LOW_VALUE_COMET_PRODUCTION:
                    continue

                rough_ships = max(
                    1,
                    min(src_left, max(PARTIAL_SOURCE_MIN_SHIPS, int(target.ships) + 1)),
                )
                rough_aim = world.plan_shot(src.id, target.id, rough_ships)
                if rough_aim is None:
                    continue

                est_turns = rough_aim[1]
                if world.is_late and est_turns > world.remaining_steps - LATE_CAPTURE_BUFFER:
                    continue

                rough_needed = world.ships_needed_to_capture(target.id, est_turns, planned_commitments)
                if rough_needed <= 0:
                    continue
                if opening_filter(target, est_turns, rough_needed, src_left, world):
                    continue

                send = preferred_send(target, rough_needed, est_turns, src_left, world, modes)
                if send < rough_needed:
                    continue

                value = target_value(target, est_turns, "capture", world, modes)
                if value <= 0:
                    continue

                score = apply_score_modifiers(
                    value / (send + est_turns * ATTACK_COST_TURN_WEIGHT + 1.0),
                    target, "capture", world,
                )
                if best is None or score > best[0]:
                    best = (score, target, send)

            if best is None:
                continue

            _, target, send = best
            aim = world.plan_shot(src.id, target.id, send)
            if aim is None:
                continue

            angle, turns, _, _ = aim
            missing = world.ships_needed_to_capture(target.id, turns, planned_commitments)
            if missing <= 0:
                continue

            src_left = source_attack_left(src.id)
            send = min(
                src_left,
                max(missing, preferred_send(target, missing, turns, src_left, world, modes)),
            )
            if send < missing:
                continue

            actual = append_move(src.id, angle, send)
            if actual < missing:
                continue
            planned_commitments[target.id].append((turns, world.player, int(actual)))

    # Doomed salvage
    if world.doomed_candidates:
        frontier_targets = (
            world.enemy_planets
            if world.enemy_planets
            else (world.static_neutral_planets or world.neutral_planets)
        )
        if frontier_targets:
            frontier_distance = {
                planet.id: nearest_distance_to_set(planet.x, planet.y, frontier_targets)
                for planet in world.my_planets
            }
        else:
            frontier_distance = {planet.id: 10 ** 9 for planet in world.my_planets}

        for planet in world.my_planets:
            if planet.id not in world.doomed_candidates:
                continue

            # v6: skip if reinforcement already committed to this planet
            if planned_commitments.get(planet.id):
                incoming = sum(
                    ships for _, owner, ships in planned_commitments[planet.id] if owner == world.player
                )
                if incoming > 0:
                    continue

            available_now = source_inventory_left(planet.id)
            if available_now < world.reserve.get(planet.id, 0):
                continue

            best_capture = None
            for target in world.planets:
                if target.id == planet.id or target.owner == world.player:
                    continue
                probe_aim = world.plan_shot(planet.id, target.id, available_now)
                if probe_aim is None:
                    continue
                probe_turns = probe_aim[1]
                if probe_turns > world.remaining_steps - 2:
                    continue
                need = world.ships_needed_to_capture(target.id, probe_turns, planned_commitments)
                if need <= 0 or need > available_now:
                    continue
                final_aim = world.plan_shot(planet.id, target.id, need)
                if final_aim is None:
                    continue
                angle, turns, _, _ = final_aim
                score = target_value(target, turns, "capture", world, modes) / (need + turns + 1.0)
                if target.owner not in (-1, world.player):
                    score *= 1.05
                if best_capture is None or score > best_capture[0]:
                    best_capture = (score, target.id, angle, turns, need)

            if best_capture is not None:
                _, target_id, angle, turns, need = best_capture
                actual = append_move(planet.id, angle, need)
                if actual >= 1:
                    planned_commitments[target_id].append((turns, world.player, int(actual)))
                continue

            safe_allies = [
                ally for ally in world.my_planets
                if ally.id != planet.id and ally.id not in world.doomed_candidates
            ]
            if not safe_allies:
                continue

            retreat_target = min(
                safe_allies,
                key=lambda ally: (
                    frontier_distance.get(ally.id, 10 ** 9),
                    planet_distance(planet, ally),
                ),
            )
            aim = world.plan_shot(planet.id, retreat_target.id, available_now)
            if aim is None:
                continue
            angle, _, _, _ = aim
            append_move(planet.id, angle, available_now)

    # Rear-to-front logistics funnel
    if (world.enemy_planets or world.neutral_planets) and len(world.my_planets) > 1 and not world.is_late:
        frontier_targets = (
            world.enemy_planets
            if world.enemy_planets
            else (world.static_neutral_planets or world.neutral_planets)
        )
        frontier_distance = {
            planet.id: nearest_distance_to_set(planet.x, planet.y, frontier_targets)
            for planet in world.my_planets
        }
        safe_fronts = [planet for planet in world.my_planets if planet.id not in world.doomed_candidates]
        if safe_fronts:
            front_anchor = min(safe_fronts, key=lambda planet: frontier_distance[planet.id])
            send_ratio = (
                REAR_SEND_RATIO_FOUR_PLAYER if world.is_four_player else REAR_SEND_RATIO_TWO_PLAYER
            )
            if modes["is_finishing"]:
                send_ratio = max(send_ratio, REAR_SEND_RATIO_FOUR_PLAYER)

            for rear in sorted(world.my_planets, key=lambda planet: -frontier_distance[planet.id]):
                if rear.id == front_anchor.id or rear.id in world.doomed_candidates:
                    continue
                if source_attack_left(rear.id) < REAR_SOURCE_MIN_SHIPS:
                    continue
                if frontier_distance[rear.id] < frontier_distance[front_anchor.id] * REAR_DISTANCE_RATIO:
                    continue

                stage_candidates = [
                    planet for planet in safe_fronts
                    if planet.id != rear.id
                    and frontier_distance[planet.id] < frontier_distance[rear.id] * REAR_STAGE_PROGRESS
                ]
                if stage_candidates:
                    front = min(stage_candidates, key=lambda planet: planet_distance(rear, planet))
                else:
                    objective = min(frontier_targets, key=lambda target: planet_distance(rear, target))
                    remaining_fronts = [planet for planet in safe_fronts if planet.id != rear.id]
                    if not remaining_fronts:
                        continue
                    front = min(remaining_fronts, key=lambda planet: planet_distance(planet, objective))

                if front.id == rear.id:
                    continue

                send = int(source_attack_left(rear.id) * send_ratio)
                if send < REAR_SEND_MIN_SHIPS:
                    continue

                aim = world.plan_shot(rear.id, front.id, send)
                if aim is None:
                    continue

                angle, turns, _, _ = aim
                if turns > REAR_MAX_TRAVEL_TURNS:
                    continue
                append_move(rear.id, angle, send)

    # Clamp by inventory without merging launches (merging changes fleet speed/ETA)
    final_moves = []
    used_final = defaultdict(int)
    for src_id, angle, ships in moves:
        source = world.planet_by_id[src_id]
        max_allowed = int(source.ships) - used_final[src_id]
        send = min(int(ships), max_allowed)
        if send >= 1:
            final_moves.append([src_id, float(angle), int(send)])
            used_final[src_id] += send

    return final_moves


# =============================================================================
# AGENT ENTRY POINT
# =============================================================================

def _read(obs, key, default=None):
    if isinstance(obs, dict):
        return obs.get(key, default)
    return getattr(obs, key, default)


def build_world(obs):
    player = _read(obs, "player", 0)
    step = _read(obs, "step", 0) or 0
    raw_planets = _read(obs, "planets", []) or []
    raw_fleets = _read(obs, "fleets", []) or []
    ang_vel = _read(obs, "angular_velocity", 0.0) or 0.0
    raw_init = _read(obs, "initial_planets", []) or []
    comets = _read(obs, "comets", []) or []
    comet_ids = set(_read(obs, "comet_planet_ids", []) or [])

    planets = [Planet(*planet) for planet in raw_planets]
    fleets = [Fleet(*fleet) for fleet in raw_fleets]
    initial_planets = [Planet(*planet) for planet in raw_init]
    initial_by_id = {planet.id: planet for planet in initial_planets}

    return WorldModel(
        player=player,
        step=step,
        planets=planets,
        fleets=fleets,
        initial_by_id=initial_by_id,
        ang_vel=ang_vel,
        comets=comets,
        comet_ids=comet_ids,
    )


def agent(obs):
    world = build_world(obs)
    if not world.my_planets:
        return []
    return plan_moves(world)


__all__ = ["agent", "build_world"]
