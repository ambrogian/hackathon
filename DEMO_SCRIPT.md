1. 0:00 - The problem and hardware
[Point to the Qualcomm Dragonwing IQ-9075 board]
SAYS: On a plant floor with no connectivity, an extrusion line operator spots a defect and needs to know where to intervene right away. Everything here runs offline on the Qualcomm Dragonwing IQ-9075 and its Hexagon NPU.

2. 0:15 - Prove it is offline
[In the serial console, run: sudo nmcli radio wifi off, then: nmcli -p device]
SAYS: First, let's prove there is no network by turning the board's Wi-Fi off right here from the serial console.

3. 0:30 - Press Monitor and dual NPU models
[Press Monitor on the dashboard; good stills cycle by, then a failure appears]
SAYS: I'll press Monitor. Both models are running on the Hexagon NPU at the same time: Liquid d1-2B on the ZETIC Ixian runtime and Liquid LFM3-Omni-2B on llama.cpp.

4. 0:45 - Sub-second d1 decision
[Point to the d1 scores: 0.88-0.98 on good stills, then 0.07 on the failure]
SAYS: Each still hits d1 first—good frames score 0.88 to 0.98, and it makes that good-versus-bad decision in 0.47 seconds. There's the failure at 0.07.

5. 1:00 - Red box, explanation, and KB step
[Approximate red bounding box, Omni's inspection sentence, and the matched knowledge-base step appear]
SAYS: That triggers Omni, which outputs an inspection sentence and an approximate red bounding box in about 8 seconds, matched to our offline 16-defect extrusion knowledge base for the operator step.

6. 1:20 - Push-to-talk and NPU numbers
[Use the speakerphone mute button as push-to-talk to ask a question; the spoken answer plays]
SAYS: The speakerphone mute button is push-to-talk for follow-ups. On the NPU, Omni's first text on an image plus question arrives in 0.8 seconds versus 3.5 seconds on the CPU, and spoken answers start about 0.3 seconds after synthesis begins.

7. 1:40 - Why not a cloud API call?
SAYS: Why not a cloud API call? There is no connectivity on the plant floor, and the line needs a sub-second local decision.

8. 1:50 - What's next
SAYS: Next, we'll replace the general values in our 16-defect knowledge base with a real line's setpoints reviewed by a process engineer.
