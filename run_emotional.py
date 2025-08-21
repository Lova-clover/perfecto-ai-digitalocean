#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse, yaml
from runner import load_personas, run_job  # 기존 runner.py 재사용

def main():
    ap = argparse.ArgumentParser(description="감성 텍스트 전용 러너")
    ap.add_argument("-c", "--config", default="job_config.yaml")
    ap.add_argument("--personas-file", default=None)
    ap.add_argument("--personas-group", default=None)
    args = ap.parse_args()

    with open(args.config, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    default_personas_file = args.personas_file or cfg.get("personas_file", "personas.yaml")
    default_personas_group = args.personas_group or cfg.get("personas_group")

    jobs = cfg.get("jobs", [])
    if not jobs:
        raise SystemExit("No jobs in config")

    results = []
    for job in jobs:
        # 잡별로 그룹/파일 오버라이드 허용
        pfile = job.get("personas_file", default_personas_file)
        pgroup = job.get("personas_group", default_personas_group)
        personas = load_personas(pfile, group=pgroup)

        job = dict(job)  # copy
        job["style"] = "emotional"
        job["include_voice"] = False
        res = run_job(job, personas)
        results.append(res)

    print("\n=== SUMMARY ===")
    for i, r in enumerate(results, 1):
        print(f"[{i}] {r['title']} -> {r['video_path']}")

if __name__ == "__main__":
    main()
