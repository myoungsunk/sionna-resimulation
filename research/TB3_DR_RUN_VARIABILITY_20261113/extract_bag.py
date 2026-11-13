"""Extract /odom, /imu, /joint_states, /cmd_vel arrays from a ROS 2 Humble SQLite bag (rosbags package).

Usage: python -I extract_bag.py BAG_DIR OUT.npz
O: (t_header_s, odom_yaw_rad, x_m, y_m); I: (t_header_s, imu_wz_rad_s, imu_orientation_yaw_rad);
J: (t_header_s, wheel_left_rad, wheel_right_rad); C: (t_bag_s, cmd_wz_rad_s, cmd_vx_m_s)
"""
import math
import sys
from pathlib import Path

import numpy as np
from rosbags.highlevel import AnyReader
from rosbags.typesys import Stores, get_typestore


def yawq(q):
    return math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))


def main(bag_dir, out):
    ts = get_typestore(Stores.ROS2_HUMBLE)
    O, I, J, C = [], [], [], []
    with AnyReader([Path(bag_dir)], default_typestore=ts) as r:
        conns = [c for c in r.connections if c.topic in ("/odom", "/imu", "/joint_states", "/cmd_vel")]
        for c, t, raw in r.messages(connections=conns):
            m = r.deserialize(raw, c.msgtype)
            if c.topic == "/cmd_vel":
                C.append((t * 1e-9, m.angular.z, m.linear.x))
                continue
            st = m.header.stamp.sec + m.header.stamp.nanosec * 1e-9
            if c.topic == "/odom":
                O.append((st, yawq(m.pose.pose.orientation), m.pose.pose.position.x, m.pose.pose.position.y))
            elif c.topic == "/imu":
                I.append((st, m.angular_velocity.z, yawq(m.orientation)))
            else:
                nm = list(m.name)
                J.append((st, m.position[nm.index("wheel_left_joint")], m.position[nm.index("wheel_right_joint")]))
    np.savez(out, O=np.array(O), I=np.array(I), J=np.array(J), C=np.array(C))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
