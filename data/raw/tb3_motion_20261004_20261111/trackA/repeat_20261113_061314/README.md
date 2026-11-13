# trackA REPEAT on 2026-11-13

TurtleBot3 Sweep r2.1.0 completed P001–P018 along the original 7.65 m trackA TEACH route with headings −60°, −30°, 0°, +30° and +60° at each station. The reference TEACH used Sweep r1.3.1 and is in [../teach](../teach). Recording ran from 06:13:00 to 06:46:16 UTC.

- `scans/`, `repeat.json`, `summary.csv`, and the run logs contain the original 234 station scans, odom poses, ICP results and station summaries. Pi source `/mnt/experiment/tb3_experiments/data/tb3_sweep_data/trackA/repeat_20261113_061314/`.
- `bag/` is the complete ROS 2 SQLite bag from the same run. It includes 20,061 `/scan` messages and 39,843 each for `/odom`, `/imu` and `/joint_states`, plus `/battery_state`, `/tf`, `/tf_static` and `/cmd_vel`. Pi source `/mnt/experiment/TRACKA_REPEAT_CAPTURE_20261113T061300Z/bag/`.
- `capture/` contains the original recorder and REPEAT commands, timestamps, logs and exit status.
- `SHA256SUMS.txt` covers all 249 files copied from the Pi. The original DB3, NPZ scans and JSONL journal use Git LFS.

The `/imu` angular velocity fields contain the OpenCR values published by the ROS driver. This recording covers that processed angular-rate stream. The sensor-register `gyroRaw` values are unavailable in the bag.
