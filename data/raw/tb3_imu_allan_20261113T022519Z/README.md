# TurtleBot3 stationary IMU and Allan variance

This stationary run started on 2026-11-13 at 02:25 UTC. It contains 37,164
`/imu` messages at 20 Hz spanning 1,858.13 s with no detected timestamp
gaps. The session also records `/odom`, `/joint_states`, and
`/battery_state`. Wheel positions and odometry passed the stationarity
screen. `summary.json` records the counts, thresholds, timing, and hashes.

| File | Contents |
| --- | --- |
| `bag/bag_0.db3.gz` | Lossless gzip of the original ROS 2 Humble SQLite bag |
| `bag/metadata.yaml` | Original rosbag2 metadata |
| `imu_samples.csv.gz` | IMU header and bag receive timestamps (ns), angular velocity (rad/s), and linear acceleration (m/s^2), each on three axes |
| `allan_variance.csv` | Overlapping Allan variance, deviation, and sample support for 47 averaging times from 0.05 to 171.50 s |
| `allan_deviation.png` | Six-axis Allan deviation plot |
| `summary.json` | Validation and SHA-256 of the original rosbag and derived files |

To use the bag with ROS 2, restore the original filename alongside its metadata.

```sh
gzip -dc bag/bag_0.db3.gz > bag/bag_0.db3
ros2 bag info bag
```

`SHA256SUMS.txt` covers the distributed files. The uncompressed SQLite
file should also match the `bag/bag_0.db3` hash in `summary.json`.

The calculation uses the overlapping estimator in [NIST SP 1065, Eq. (10)](https://nvlpubs.nist.gov/nistpubs/Legacy/SP/nistspecialpublication1065.pdf).
This dataset characterizes the TB3 ROS `/imu` output. At least 99.5% of
samples on each gyroscope axis are exactly zero, so the record does not
establish raw gyroscope noise coefficients.
