import os
import json
import math
import subprocess

def score_forecast(forecast_path, task_path, history_path):
    with open(task_path) as f:
        task = json.load(f)
    with open(history_path) as f:
        lines = [json.loads(line) for line in f if line.strip()]
    with open(forecast_path) as f:
        forecast = json.load(f)

    places = task["places"]
    edges = task["size"]["edges"]

    # Shape validation: Check per-place probability sums and size sums <= 1.0
    prob_sums = {}
    for row in forecast.get("probabilities", []):
        pl = row["place"]
        prob_sums[pl] = prob_sums.get(pl, 0.0) + row["p"]

    size_sums = {}
    for row in forecast.get("sizes", []):
        pl = row["place"]
        size_sums[pl] = size_sums.get(pl, 0.0) + row["p"]

    eps = 1e-6
    for place in range(1, places + 1):
        p_sum = prob_sums.get(place, 0.0)
        s_sum = size_sums.get(place, 0.0)
        if p_sum > 1.0 + eps:
            raise RuntimeError(f"Shape validation failed: place {place} probability sum {p_sum:.6f} exceeds 1.0")
        if s_sum > 1.0 + eps:
            raise RuntimeError(f"Shape validation failed: place {place} size sum {s_sum:.6f} exceeds 1.0")

    valid_marks = [m for m in lines if m.get("ok") and m.get("rows")]
    last_mark = valid_marks[-1]
    chart = sorted(last_mark["rows"], key=lambda r: r["rank"])
    chart_mints = {r["mint"] for r in chart}

    # Floor log score value
    floor_val = math.log(0.0001) # -9.210340...

    # Map forecast probabilities by place
    prob_map = {} # place -> {mint: p}
    for row in forecast.get("probabilities", []):
        pl = row["place"]
        if pl not in prob_map:
            prob_map[pl] = {}
        prob_map[pl][row["mint"]] = row["p"]

    # Map forecast sizes by place
    size_map = {} # place -> {bin: p}
    for row in forecast.get("sizes", []):
        pl = row["place"]
        if pl not in size_map:
            size_map[pl] = {}
        size_map[pl][row["bin"]] = row["p"]

    order_score = 0.0
    size_score = 0.0

    for place in range(1, places + 1):
        actual_coin = chart[place - 1]
        actual_mint = actual_coin["mint"]
        actual_cap = int(actual_coin["market_cap_lamports"])
        actual_log_cap = math.log10(actual_cap) - 9.0

        # Determine actual bin
        actual_bin = len(edges)
        for idx, edge in enumerate(edges):
            if actual_log_cap < edge:
                actual_bin = idx
                break

        # Order score
        p_dict = prob_map.get(place, {})
        named_sum = sum(p_dict.values())
        unnamed_share = max(0.0, 1.0 - named_sum)
        
        unnamed_coins = [m for m in chart_mints if m not in p_dict]
        unnamed_per_coin = unnamed_share / len(unnamed_coins) if unnamed_coins else 0.0

        p_assigned = p_dict.get(actual_mint, unnamed_per_coin)
        if p_assigned <= 0:
            log_p_order = floor_val
        else:
            log_p_order = max(floor_val, math.log(p_assigned))
        order_score += log_p_order

        # Size score
        s_dict = size_map.get(place, {})
        size_named_sum = sum(s_dict.values())
        size_unnamed_share = max(0.0, 1.0 - size_named_sum)
        total_bins = len(edges) + 1
        size_unnamed_per_bin = size_unnamed_share / total_bins

        p_size = s_dict.get(actual_bin, size_unnamed_per_bin)
        if p_size <= 0:
            log_p_size = floor_val
        else:
            log_p_size = max(floor_val, math.log(p_size))
        size_score += log_p_size

    total_score = order_score + size_score
    return order_score, size_score, total_score

if __name__ == "__main__":
    kit_input = "/home/hatch/workspace/makefun/pumpfun-kit/pumpfun-top5-forecast-01-kit/input"
    out_dir = "/home/hatch/workspace/makefun/repo-pumpfun-v1/out"
    os.makedirs(out_dir, exist_ok=True)

    # 1. Run starter baseline
    baseline_out = os.path.join(out_dir, "baseline_forecast.json")
    subprocess.run(["npx", "tsx", "/home/hatch/workspace/makefun/pumpfun-kit/pumpfun-top5-forecast-01-kit/starter/main.ts"], 
                   env={**os.environ, "MAKEFUN_INPUT_DIR": kit_input, "MAKEFUN_OUTPUT_DIR": out_dir}, check=True)
    subprocess.run(["mv", os.path.join(out_dir, "forecast.json"), baseline_out], check=True)

    # 2. Run our main.py
    my_out = os.path.join(out_dir, "my_forecast.json")
    subprocess.run(["python3", "/home/hatch/workspace/makefun/repo-pumpfun-v1/main.py"], 
                   env={**os.environ, "MAKEFUN_INPUT_DIR": kit_input, "MAKEFUN_OUTPUT_DIR": out_dir}, check=True)
    subprocess.run(["mv", os.path.join(out_dir, "forecast.json"), my_out], check=True)

    # 3. Score both
    b_order, b_size, b_total = score_forecast(baseline_out, os.path.join(kit_input, "task.json"), os.path.join(kit_input, "history.ndjson"))
    m_order, m_size, m_total = score_forecast(my_out, os.path.join(kit_input, "task.json"), os.path.join(kit_input, "history.ndjson"))

    print(f"Baseline Score: Total={b_total:.4f} (Order={b_order:.4f}, Sizes={b_size:.4f})")
    print(f"My Model V1:    Total={m_total:.4f} (Order={m_order:.4f}, Sizes={m_size:.4f})")
