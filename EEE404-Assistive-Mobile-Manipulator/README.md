# Intelligent Mobile Manipulation System for Daily Assistance of Visually Impaired Individuals

**Course:** EEE 404 — Robotics & Automation Laboratory (July 2025)
**Institution:** Department of EEE, Bangladesh University of Engineering and Technology (BUET)
**Section:** G2 | **Group:** 04
**Full report:** [`EEE404_Project_Report_Group_04.pdf`](EEE404_Project_Report_Group_04.pdf)

---

## What this project does

An autonomous mobile robot that finds an object on a table, drives to it, confirms it is the
right object, picks it up with a robotic arm, and delivers it to a fixed destination — with no
human input. It is built as a low-cost assistive device for visually impaired users, who
otherwise depend on others to locate and fetch everyday objects.

The complete task loop the robot runs:

1. Map the workspace from an overhead camera using four corner **ArUco markers**.
2. Locate itself and all candidate objects inside that coordinate frame.
3. Pick the nearest valid target and drive toward it.
4. Stop precisely at **32 cm** using an ultrasonic sonar.
5. Take a close-up photo with the front camera and **classify the object** (shape / colour).
6. If it matches, grasp it with the 6-DOF arm; if not, skip it and move to the next target.
7. Navigate to the destination marker, release the object, and return for the next task.

## Key idea: hybrid (dual-layer) perception

Instead of one sensing modality, the system splits perception into two cheap, complementary layers:

| Layer | Sensor | Job |
| --- | --- | --- |
| **Global** | Overhead USB camera + ArUco markers | Workspace mapping, robot localisation, object coordinates |
| **Local** | Front-facing Pi Camera | Close-range object verification before grasping |
| **Proximity** | HC-SR04 ultrasonic sonar | Precision stopping and collision avoidance |

This keeps the Raspberry Pi's computational load low while improving positioning reliability —
the central design trade-off of the project.

## Hardware

| Component | Role |
| --- | --- |
| Raspberry Pi 4B (8 GB) | Central controller — vision, ML inference, motion logic |
| 6-DOF robotic arm | Object grasping and placement |
| PCA9685 PWM driver | Servo control for the arm |
| Dual-motor chassis + L298N | Mobile navigation platform |
| Overhead USB camera | Global localisation via ArUco |
| Pi Camera (front) | Object classification |
| HC-SR04 ultrasonic sensor | Distance feedback (±1–2 cm) |
| 12 V rechargeable battery pack | Power for motors, servos, and regulated Pi supply |

## Software & methods

- **Coordinate geometry** — Euclidean distance for nearest-target selection and path planning.
- **Two ML models** — one for global object localisation (overhead view), one for close-range
  classification by shape and colour, both deployed on-device.
- **Threshold-based control** — sonar-triggered stopping logic with real-time motion feedback.
- **OpenCV** for image processing and ArUco marker detection.
- All processing runs **locally on the Pi** — no cloud dependency, which also protects user privacy.

## Results and known limits

The robot was validated on four functions: workspace mapping, target localisation, precision
stopping, and object manipulation — tested repeatedly in a bounded tabletop setup with scattered
coloured objects and a fixed destination marker.

Documented limitations:

- The Pi 4B struggles to run two real-time ML models simultaneously.
- Sonar readings vary with surface texture (±1–2 cm error).
- ArUco detection needs good, consistent lighting.
- Arm torque restricts handling to lightweight objects only.

## Using the prototype (short version)

Place the four corner markers and the destination marker, position the overhead camera so the
whole table is visible, power up the Pi and drivers, and run the main control program. The robot
handles everything from there. Operate only in a clear area and keep hands away from the arm
while it moves. The report contains the full 12-step user manual.

## Future work

SLAM-based navigation for larger indoor spaces, voice-command interaction, force/tactile
feedback for adaptive grasping, stronger recognition models robust to lighting, and cost and
portability reductions for real deployment.

## Team

Moshiur Rahman (2006099) · Md. Woahidur Rahman (2006102) · Sayed Mohammad Wasif (2006112) ·
Shahriar Rashid Khan Sifat (2006117) · Tanvir Arafat Fahim (2006118) · Md. Rifat Rahman (2006137)

**Course instructors:** Md. Jawad Ul Islam (Lecturer), Md Abu Sayed Chowdhury (Part-Time Lecturer)
