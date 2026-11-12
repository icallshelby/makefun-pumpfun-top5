import os
import json
import math

def erfcc(x):
    z = abs(x)
    t = 1.0 / (1.0 + 0.5 * z)
    r = t * math.exp(-z * z - 1.26551223 + t * (1.00002368 + t * (0.37409196 + t * (0.09678418 + t * (-0.18628806 + t * (0.27886807 + t * (-1.13520398 + t * (1.48851587 + t * (-0.82215223 + t * 0.17087277)))))))))
    return r if x >= 0 else 2.0 - r

def above(x, mean, sd):
    if x == -float('inf'):
        return 1.0
    if x == float('inf'):
        return 0.0
    sd = max(sd, 1e-5)
    return 0.5 * erfcc((x - mean) / (sd * math.sqrt(2.0)))

class LCG:
    def __init__(self, seed=1337):
        self.state = seed
    def next(self):
        self.state = (1103515245 * self.state + 12345) % 2**31
        return self.state / 2**31

def sample_normal(rng):
    u1 = max(1e-10, rng.next())
    u2 = rng.next()
    return math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)

def main():
    input_dir = os.environ.get("MAKEFUN_INPUT_DIR", "/input")
    output_dir = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")

    with open(os.path.join(input_dir, "task.json"), "r") as f:
        task = json.load(f)

    with open(os.path.join(input_dir, "history.ndjson"), "r") as f:
        lines = [json.loads(line) for line in f if line.strip()]

    valid_marks = [m for m in lines if m.get("ok") and m.get("rows")]
    if not valid_marks:
        raise RuntimeError("No valid marks in history")

    last_mark = valid_marks[-1]
    chart = sorted(last_mark["rows"], key=lambda r: r["rank"])

    places = task["places"]
    edges = task["size"]["edges"]

    if len(chart) < places:
        raise RuntimeError(f"Chart has {len(chart)} coins, fewer than {places} places")

    coin_history = {}
    for m_idx, m in enumerate(valid_marks):
        for r in m.get("rows", []):
            mint = r["mint"]
            if mint not in coin_history:
                coin_history[mint] = []
            coin_history[mint].append({
                "mark": m_idx,
                "rank": r["rank"],
                "cap": int(r["market_cap_lamports"]),
                "venue": r.get("venue", "curve")
            })

    candidates = []
    seen_mints = set()

    for r in chart[:40]:
        mint = r["mint"]
        if mint not in seen_mints:
            seen_mints.add(mint)
            candidates.append(mint)

    for mint, history in coin_history.items():
        if mint not in seen_mints:
            log_caps = [math.log10(h["cap"]) for h in history]
            vel = (log_caps[-1] - log_caps[0]) if len(log_caps) >= 2 else 0.0
            if vel > 0.02 or len(history) >= 2:
                seen_mints.add(mint)
                candidates.append(mint)

    for r in chart:
        if r["mint"] not in seen_mints:
            seen_mints.add(r["mint"])
            candidates.append(r["mint"])

    candidate_data = {}
    for mint in candidates:
        history = coin_history.get(mint, [{"cap": chart[0]["market_cap_lamports"], "venue": "curve"}])
        latest = history[-1]
        current_cap = latest["cap"]
        current_log_cap = math.log10(current_cap)
        venue = latest["venue"]

        log_caps = [math.log10(h["cap"]) for h in history]
        velocity = (log_caps[-1] - log_caps[0]) / (len(log_caps) - 1) if len(log_caps) >= 2 else 0.0

        if len(log_caps) >= 2:
            mean_lc = sum(log_caps) / len(log_caps)
            variance = sum((lc - mean_lc) ** 2 for lc in log_caps) / (len(log_caps) - 1)
            std_dev = math.sqrt(variance)
            sigma = max(0.15, min(0.6, std_dev * 1.2 + 0.18))
        else:
            sigma = 0.35

        shrink = 0.4
        venue_boost = 0.05 if venue == "pool" else 0.0
        projected_log_cap = current_log_cap + shrink * velocity + venue_boost

        candidate_data[mint] = {
            "mint": mint,
            "current_cap": current_cap,
            "current_log_cap": current_log_cap,
            "projected_log_cap": projected_log_cap,
            "sigma": sigma,
            "venue": venue,
            "velocity": velocity
        }

    rng = LCG(seed=1337)
    draws = 4000
    place_counts = {p: {} for p in range(1, places + 1)}

    cand_list = list(candidate_data.values())

    for _ in range(draws):
        simulated = []
        for c in cand_list:
            sim_val = c["projected_log_cap"] + sample_normal(rng) * c["sigma"]
            simulated.append((sim_val, c["mint"]))
        simulated.sort(key=lambda x: x[0], reverse=True)

        for place_idx in range(places):
            if place_idx < len(simulated):
                place = place_idx + 1
                mint = simulated[place_idx][1]
                place_counts[place][mint] = place_counts[place].get(mint, 0) + 1

    probabilities = []
    for place in range(1, places + 1):
        counts = place_counts[place]
        raw_place_probs = []
        for mint, cnt in counts.items():
            p = cnt / draws
            if p >= 0.01:
                p = min(0.35, p)
                raw_place_probs.append((mint, p))
        
        total_p = sum(p for _, p in raw_place_probs)
        if total_p > 0.55:
            scale = 0.50 / total_p
            raw_place_probs = [(m, p * scale) for m, p in raw_place_probs]

        for mint, p in raw_place_probs:
            probabilities.append({"mint": mint, "place": place, "p": round(p, 6)})

    sorted_by_proj = sorted(cand_list, key=lambda c: c["projected_log_cap"], reverse=True)
    top5 = []
    for c in sorted_by_proj:
        if c["mint"] not in top5:
            top5.append(c["mint"])
        if len(top5) == 5:
            break

    if len(top5) < places:
        for r in chart:
            if r["mint"] not in top5:
                top5.append(r["mint"])
            if len(top5) == places:
                break

    sizes = []
    for place in range(1, places + 1):
        target_mint = top5[place - 1] if place - 1 < len(top5) else chart[place - 1]["mint"]
        c_data = candidate_data.get(target_mint)
        if c_data:
            projected_log_cap = c_data["projected_log_cap"]
            sigma = c_data["sigma"]
        else:
            projected_log_cap = math.log10(chart[place - 1]["market_cap_lamports"])
            sigma = 0.35

        mean_log_cap_centered = projected_log_cap - 9.0
        micro = 1_000_000
        for bin_idx in range(len(edges) + 1):
            lo = -float('inf') if bin_idx == 0 else edges[bin_idx - 1]
            hi = float('inf') if bin_idx == len(edges) else edges[bin_idx]
            
            p_bin = above(lo, mean_log_cap_centered, sigma) - above(hi, mean_log_cap_centered, sigma)
            u = int(math.floor(p_bin * micro))
            if u > 0:
                p_val = round(u / micro, 6)
                sizes.append({"place": place, "bin": bin_idx, "p": p_val})

    if len(set(top5)) != 5:
        raise RuntimeError("Top 5 must contain exactly 5 distinct mints")

    output_data = {
        "probabilities": probabilities,
        "top5": top5,
        "sizes": sizes
    }

    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, task["output"])
    with open(out_path, "w") as f:
        json.dump(output_data, f, separators=(',', ':'))
        f.write("\n")

if __name__ == "__main__":
    main()
