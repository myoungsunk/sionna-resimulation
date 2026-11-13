# TurtleBot3 motion measurements

| Files | Contents and origin |
| --- | --- |
| trackA/teach/ | TB3 Sweep TEACH capture, 2026-10-04. 18 stations, 158 NPZ scan files, teach.json with odom poses, and events.log. Pi source: /mnt/experiment/tb3_experiments/data/tb3_sweep_data/trackA/teach/ |
| corridor_5p07m/bag/ | 2026-11-11 straight corridor run, 5.06972 m along the odom start axis. ROS 2 SQLite bag with 680 /scan, 1,339 /odom, 2,138 /tf and 2 /tf_static messages. Pi source: /mnt/experiment/CORRIDOR_MAPS/full-corridor/partial_20261111T082144573916Z/bag/ |
| corridor_5p07m/receipt.json | Run receipt from SLAM_bot/artifacts/CORRIDOR_MAP_FULL_CORRIDOR_PARTIAL_20261111T082144573916Z/. |
| corridor_5p07m/replay.json | Offline wall-based replay from SLAM_bot/artifacts/CORRIDOR_WALL_GUIDANCE_REPLAY_20261111/. |
| distance_scale/teach.json | Configuration snapshot from SLAM_bot/artifacts/MODE6_TEACH_MAP_MOCK_20261111T063118Z/. |

## Measurement scope

The TB3 Sweep release notes report a rotation scale fit using onboard LiDAR scan registration and odom for trackA. The fit uses 36 clockwise and 72 counterclockwise moves, with scale factors 1.0076 and 0.9981 and residual RMS 0.18 deg. The configuration snapshot records both factors and odom_scale=0.96756. The Sweep distance calibration method compares tape distance with odom. The snapshot records the configured distance scale.

At the end of the corridor run, the replay estimated a wall-relative lateral displacement of -0.07926 m from the start. The drive receipt records a peak absolute odom cross-track displacement of 0.00595 m relative to the odom start axis. The two quantities use their respective references.

The LiDAR observations provide an onboard relative reference. These records do not provide independent external ground truth, separate left/right wheel encoder streams, or estimates of effective wheelbase, wheel radius asymmetry, or slip rate.

## Integrity

SHA256SUMS.txt covers the 165 evidence files. The 162 files copied from the Pi were checked byte-for-byte by SHA-256. Git LFS stores the NPZ files.
