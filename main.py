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

    probabilities = []
    sizes = []

    for place in range(1, places + 1):
        target_coin = chart[place - 1]
        mint = target_coin["mint"]
        venue = target_coin.get("venue", "curve")
        current_cap = int(target_coin["market_cap_lamports"])
        current_log_cap = math.log10(current_cap)

        history = coin_history.get(mint, [])
        
        velocity = 0.0
        log_caps = [math.log10(h["cap"]) for h in history]
        if len(history) >= 2:
            velocity = log_caps[-1] - log_caps[0]

        # Size sigma from trajectory variance (floor 0.15, cap 0.6)
        if len(log_caps) >= 2:
            mean_lc = sum(log_caps) / len(log_caps)
            variance = sum((lc - mean_lc) ** 2 for lc in log_caps) / (len(log_caps) - 1)
            std_dev = math.sqrt(variance)
            sigma = max(0.15, min(0.6, std_dev * 1.2 + 0.18))
        else:
            sigma = 0.35

        # Project cap 1-2h forward
        proj_growth = velocity * 0.5 + (0.10 if venue == "pool" else 0.03)
        projected_log_cap = current_log_cap + proj_growth

        # Order model: balance persistence with sensible unnamed share for rank churn at 1-2h
        venue_bonus = 0.08 if venue == "pool" else 0.02
        velocity_bonus = min(0.04, max(-0.02, velocity * 0.02))
        p_stay = min(0.48, round(0.35 + venue_bonus + velocity_bonus, 6))

        place_probs = []
        place_probs.append({"mint": mint, "place": place, "p": p_stay})
        current_sum = p_stay

        if place > 1:
            prev_coin = chart[place - 2]
            p_prev = 0.10 if prev_coin.get("venue") == "pool" else 0.07
            if current_sum + p_prev <= 0.99:
                place_probs.append({"mint": prev_coin["mint"], "place": place, "p": p_prev})
                current_sum += p_prev

        if place < len(chart):
            next_coin = chart[place]
            p_next = 0.10 if next_coin.get("venue") == "pool" else 0.07
            if current_sum + p_next <= 0.99:
                place_probs.append({"mint": next_coin["mint"], "place": place, "p": p_next})
                current_sum += p_next

        probabilities.extend(place_probs)

        # Size distribution
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

    top5 = [r["mint"] for r in chart[:places]]
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
