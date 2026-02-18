# TRLC-DK1-Follower URDF

![Visual 3D Model of TRLC-DK1-Follower](https://github.com/andreaskoepf/trlc-dk1-follower-urdf/raw/main/assets/dk1_vsual_right.png)

This repository contains the URDF (Unified Robot Description Format) model of the **DK-1 Follower arm** developed by [The Robot Learning Company (TRLC)](https://www.robot-learning.co/), a German robotics startup based in Munich.

## About the TRLC DK-1

The TRLC DK-1 is an open-source robotic arm designed for robot learning and AI research. It uses a leader-follower configuration where this URDF represents the **follower arm** - the actuated arm that replicates movements from a passive leader arm during teleoperation and data collection for imitation learning.

### Key Specifications

| Specification | Value |
|---------------|-------|
| Reach | 700 mm |
| Payload | 1 kg |
| Degrees of Freedom | 6 (+ gripper) |
| Gripper Force | 114 N |
| Platform Support | Linux, macOS, Windows |
| Connectivity | USB-C, CAN bus |

### Joint Configuration

| Joint | Motor | Max Velocity | Range |
|-------|-------|--------------|-------|
| Joint 1 | DAMIAO DM4340 | 5.4 rad/s | ±120° |
| Joint 2 | DAMIAO DM4340 | 5.4 rad/s | 0° to 180° |
| Joint 3 | DAMIAO DM4340 | 5.4 rad/s | 0° to 270° |
| Joint 4 | DAMIAO DM4310 | 5.4 rad/s | ±90° |
| Joint 5 | DAMIAO DM4310 | 5.4 rad/s | ±90° |
| Joint 6 | DAMIAO DM4310 | 5.4 rad/s | ±180° |
| Gripper | DAMIAO DM4310 | 0.18 m/s | 45 mm stroke |

### Materials & Construction

- Carbon fiber reinforced filaments (PLA-CF, PAHT-CF)
- Precision ball bearings (6803ZZ)
- MGN9C linear rail gripper system

## Repository Contents

```
├── TRLC-DK1-Follower.urdf    # Robot description file
├── TRLC-DK1-Follower.srdf    # Semantic robot description (MoveIt)
├── collision_trlc-dk1.yml    # Simplified collision spheres
├── meshes/
│   ├── visual/               # GLB meshes for visualization
│   │   ├── base_link.glb
│   │   ├── link1-2.glb
│   │   ├── link2-3.glb
│   │   ├── link3-4.glb
│   │   ├── link4-5.glb
│   │   ├── link5-6.glb
│   │   ├── link6-7.glb
│   │   ├── finger_left.glb
│   │   └── finger_right.glb
│   └── collision/            # STL meshes for collision detection
│       └── [corresponding .stl files]
└── assets/                   # Images and documentation assets
```

### URDF Features

- Kinematic chain with joint limits and inertial properties
- Separate visual (GLB) and collision (STL) meshes
- Parallel gripper with left/right finger joints
- Tool center point (TCP) frame at `tool0`
- Wrist camera mount with 15° downward tilt
- SRDF file with joint groups, named poses (home, open, close), and self-collision exclusions
- Simplified collision sphere model (`collision_trlc-dk1.yml`) for use with simulation frameworks like [RoboTwin 2.0](https://robotwin-platform.github.io/)

### Development Tools

This URDF model was created using:

- [FreeCAD](https://www.freecad.org/) - Parametric 3D CAD modeling and URDF export
- [Blender](https://www.blender.org/) - Mesh optimization and GLB export
- [Online URDF Viewer](https://viewer.robotsfan.com/) - Web-based URDF visualization and validation

## Resources

- [TRLC Website](https://www.robot-learning.co/)
- [Hardware Documentation](https://docs.robot-learning.co/hardware)
- [TRLC-DK1 GitHub Repository](https://github.com/robot-learning-co/trlc-dk1)
- [Web URDF Viewer](https://viewer.robotsfan.com/)

## License

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.

