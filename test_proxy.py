import os
import json
import math
import subprocess

def score_forecast(forecast_path, task_path, history_path, eval_mark_idx=None):
    with open(task_path) as f:
        task = json.load(f)
    with open(history_path) as f:
        lines = [json.loads(line) for line in f if line.strip()]
    with open(forecast_path) as f:
        forecast = json.load(f)

    places = task["places"]
    edges = task["size"]["edges"]

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

    target_mark = lines[eval_mark_idx] if eval_mark_idx is not None else [m for m in lines if m.get("ok") and m.get("rows")][-1]
    chart = sorted(target_mark["rows"], key=lambda r: r["rank"])
    chart_mints = {r["mint"] for r in chart}

    floor_val = math.log(0.0001)

    prob_map = {}
    for row in forecast.get("probabilities", []):
        pl = row["place"]
        if pl not in prob_map:
            prob_map[pl] = {}
        prob_map[pl][row["mint"]] = row["p"]

    size_map = {}
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

        actual_bin = len(edges)
        for idx, edge in enumerate(edges):
            if actual_log_cap < edge:
                actual_bin = idx
                break

        p_dict = prob_map.get(place, {})
        named_sum = sum(p_dict.values())
        unnamed_share = max(0.0, 1.0 - named_sum)
        unnamed_coins = [m for m in chart_mints if m not in p_dict]
        unnamed_per_coin = unnamed_share / len(unnamed_coins) if unnamed_coins else 0.0

        p_assigned = p_dict.get(actual_mint, unnamed_per_coin)
        log_p_order = floor_val if p_assigned <= 0 else max(floor_val, math.log(p_assigned))
        order_score += log_p_order

        s_dict = size_map.get(place, {})
        size_named_sum = sum(s_dict.values())
        size_unnamed_share = max(0.0, 1.0 - size_named_sum)
        total_bins = len(edges) + 1
        size_unnamed_per_bin = size_unnamed_share / total_bins

        p_size = s_dict.get(actual_bin, size_unnamed_per_bin)
        log_p_size = floor_val if p_size <= 0 else max(floor_val, math.log(p_size))
        size_score += log_p_size

    total_score = order_score + size_score
    return order_score, size_score, total_score, prob_sums, size_sums

if __name__ == "__main__":
    kit_input = "/home/hatch/workspace/makefun/pumpfun-kit/pumpfun-top5-forecast-01-kit/input"
    out_dir = "/home/hatch/workspace/makefun/repo-pumpfun-v1/out"
    os.makedirs(out_dir, exist_ok=True)

    history_path = os.path.join(kit_input, "history.ndjson")
    with open(history_path) as f:
        all_lines = [json.loads(line) for line in f if line.strip()]

    # Truncate history to marks 0, 1, 2 (lines index 0, 1, 2, 3)
    # Line 0: mark 0 (0 rows)
    # Line 1: mark 1 (121 rows)
    # Line 2: mark 2 (200 rows)
    # Line 3: mark 3 (200 rows) -> wait, mark 2 in 0-indexed marks means lines up to index 3 (mark 0, mark 1, mark 2)
    truncated_lines = all_lines[:4] # lines 0, 1, 2, 3 (marks 0, 1, 2)

    temp_input_long = os.path.join(out_dir, "temp_input_long")
    os.makedirs(temp_input_long, exist_ok=True)
    with open(os.path.join(temp_input_long, "task.json"), "w") as f:
        with open(os.path.join(kit_input, "task.json")) as tf:
            f.write(tf.read())
    truncated_history_path = os.path.join(temp_input_long, "history.ndjson")
    with open(truncated_history_path, "w") as f:
        for l in truncated_lines:
            f.write(json.dumps(l) + "\n")

    # Run Baseline on truncated history
    baseline_long_out = os.path.join(out_dir, "baseline_long_forecast.json")
    subprocess.run(["npx", "tsx", "/home/hatch/workspace/makefun/pumpfun-kit/pumpfun-top5-forecast-01-kit/starter/main.ts"],
                   env={**os.environ, "MAKEFUN_INPUT_DIR": temp_input_long, "MAKEFUN_OUTPUT_DIR": out_dir}, check=True)
    subprocess.run(["mv", os.path.join(out_dir, "forecast.json"), baseline_long_out], check=True)

    # Run v2 on truncated history
    v2_long_out = os.path.join(out_dir, "v2_long_forecast.json")
    subprocess.run(["python3", "/home/hatch/workspace/makefun/repo-pumpfun-v1/main.py"],
                   env={**os.environ, "MAKEFUN_INPUT_DIR": temp_input_long, "MAKEFUN_OUTPUT_DIR": out_dir}, check=True)
    subprocess.run(["mv", os.path.join(out_dir, "forecast.json"), v2_long_out], check=True)

    # Score long proxy against mark 5 (line index 5 in all_lines)
    b_l_order, b_l_size, b_l_total, b_l_p_sums, b_l_s_sums = score_forecast(
        baseline_long_out, os.path.join(kit_input, "task.json"), history_path, eval_mark_idx=5)
    v2_l_order, v2_l_size, v2_l_total, v2_l_p_sums, v2_l_s_sums = score_forecast(
        v2_long_out, os.path.join(kit_input, "task.json"), history_path, eval_mark_idx=5)

    print("=== LONG-HORIZON PROXY (Train marks 0-2, Score mark 5) ===")
    print(f"Baseline Long: Total={b_l_total:.4f} (Order={b_l_order:.4f}, Sizes={b_l_size:.4f})")
    print(f"V2 Long:       Total={v2_l_total:.4f} (Order={v2_l_order:.4f}, Sizes={v2_l_size:.4f})")
    print("V2 Size sums per place:", v2_l_s_sums)
    print("V2 Prob sums per place:", v2_l_p_sums)

    # Sanity Check 10-min Proxy (Full history, eval against last mark)
    baseline_full_out = os.path.join(out_dir, "baseline_full_forecast.json")
    subprocess.run(["npx", "tsx", "/home/hatch/workspace/makefun/pumpfun-kit/pumpfun-top5-forecast-01-kit/starter/main.ts"],
                   env={**os.environ, "MAKEFUN_INPUT_DIR": kit_input, "MAKEFUN_OUTPUT_DIR": out_dir}, check=True)
    subprocess.run(["mv", os.path.join(out_dir, "forecast.json"), baseline_full_out], check=True)

    v2_full_out = os.path.join(out_dir, "v2_full_forecast.json")
    subprocess.run(["python3", "/home/hatch/workspace/makefun/repo-pumpfun-v1/main.py"],
                   env={**os.environ, "MAKEFUN_INPUT_DIR": kit_input, "MAKEFUN_OUTPUT_DIR": out_dir}, check=True)
    subprocess.run(["mv", os.path.join(out_dir, "forecast.json"), v2_full_out], check=True)

    b_f_order, b_f_size, b_f_total, _, _ = score_forecast(
        baseline_full_out, os.path.join(kit_input, "task.json"), history_path, eval_mark_idx=5)
    v2_f_order, v2_f_size, v2_f_total, _, _ = score_forecast(
        v2_full_out, os.path.join(kit_input, "task.json"), history_path, eval_mark_idx=5)

    print("\n=== 10-MIN SANITY PROXY ===")
    print(f"Baseline Full: Total={b_f_total:.4f} (Order={b_f_order:.4f}, Sizes={b_f_size:.4f})")
    print(f"V2 Full:       Total={v2_f_total:.4f} (Order={v2_f_order:.4f}, Sizes={v2_f_size:.4f})")
