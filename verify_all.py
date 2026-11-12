import os
import json
import subprocess
import hashlib

def verify():
    kit_input = "/home/hatch/workspace/makefun/pumpfun-kit/pumpfun-top5-forecast-01-kit/input"
    out_dir = "/home/hatch/workspace/makefun/repo-pumpfun-v1/out"
    os.makedirs(out_dir, exist_ok=True)
    out_file = os.path.join(out_dir, "forecast.json")

    # 1. Run main.py twice for determinism check
    env = {**os.environ, "MAKEFUN_INPUT_DIR": kit_input, "MAKEFUN_OUTPUT_DIR": out_dir}
    
    subprocess.run(["python3", "/home/hatch/workspace/makefun/repo-pumpfun-v1/main.py"], env=env, check=True)
    with open(out_file, "rb") as f:
        data1 = f.read()
    h1 = hashlib.sha256(data1).hexdigest()

    subprocess.run(["python3", "/home/hatch/workspace/makefun/repo-pumpfun-v1/main.py"], env=env, check=True)
    with open(out_file, "rb") as f:
        data2 = f.read()
    h2 = hashlib.sha256(data2).hexdigest()

    print(f"Determinism Check: hash1={h1}, hash2={h2}, match={h1 == h2}")
    assert h1 == h2, "Non-deterministic output!"

    # 2. File size check (< 1,048,576 bytes)
    size = len(data1)
    print(f"File Size: {size} bytes (Limit: 1,048,576 bytes)")
    assert size < 1_048_576, "File too large!"

    # 3. JSON structure and keys
    forecast = json.loads(data1.decode('utf-8'))
    expected_keys = {"probabilities", "top5", "sizes"}
    assert set(forecast.keys()) == expected_keys, f"Invalid keys: {forecast.keys()}"
    print("JSON keys verified:", list(forecast.keys()))

    # 4. Top5 check
    top5 = forecast["top5"]
    assert isinstance(top5, list) and len(top5) == 5 and len(set(top5)) == 5, f"Invalid top5: {top5}"
    print("Top5 verified: 5 distinct mints")

    # 5. Probability sums and size sums per place (<= 1.0)
    place_probs = {}
    for row in forecast["probabilities"]:
        pl = row["place"]
        place_probs[pl] = place_probs.get(pl, 0.0) + row["p"]
    
    for pl, total_p in place_probs.items():
        print(f"Place {pl} probability sum: {total_p:.4f}")
        assert total_p <= 1.000001, f"Place {pl} probability sum exceeds 1: {total_p}"

    place_sizes = {}
    for row in forecast["sizes"]:
        pl = row["place"]
        place_sizes[pl] = place_sizes.get(pl, 0.0) + row["p"]

    for pl, total_s in place_sizes.items():
        print(f"Place {pl} size sum: {total_s:.4f}")
        assert total_s <= 1.000001, f"Place {pl} size sum exceeds 1: {total_s}"

    # 6. Proxy score vs baseline
    subprocess.run(["python3", "/home/hatch/workspace/makefun/repo-pumpfun-v1/test_proxy.py"], env=env, check=True)

if __name__ == "__main__":
    verify()
