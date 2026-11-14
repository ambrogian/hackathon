# Pitch run of show (5 minutes)

## Before going on stage

Open these in this order. All are local files, so no internet is needed.

1. `media/working_machine.mp4`
2. `media/failure.mp4` (set to loop, or pause on the frame)
3. `visuals/pc-extrusion-line.html`
4. `showcase/index.html`
5. `demo/index.html`

Rehearse once: press **Play the scenario** in the showcase and time it (about 20 seconds). Check that the video in the demo page plays.

## 1. Hook (0:00–0:30) · `media/working_machine.mp4`

> "This is a polycarbonate sheet line. It runs around the clock and puts out more than a tonne of sheet an hour. When something goes wrong, it keeps running, and every minute becomes scrap."

## 2. Problem (0:30–1:00) · `media/failure.mp4`

> "When a defect appears at 3 a.m., the operator has a manual of hundreds of pages and an expert who's asleep. Finding the cause takes 30 minutes or more."

## 3. The machine (1:00–1:45) · `visuals/pc-extrusion-line.html`

Scroll through the plant layout.

> "Twelve sections, from the resin dryer to the saw. A defect you see at the end can start anywhere along the line."

## 4. The assistant (1:45–3:30) · `showcase/index.html`

- Select **Bubbles**, press **Play the scenario**.
- At **Diagnose**, point at the pin on **Z1 Dryer**:
  > "The bubbles show up at the end of the line, but the cause is wet resin in the dryer, at the other end of the line. That's what the expert knows and the new operator doesn't."
- At **Fix**:
  > "Numbered steps from the line's own knowledge base, with the safety rule for that part of the machine."
- Click **Die lines** to show a different part of the line lighting up.
- Scroll to the calculator:
  > "Thirty minutes saved on a 1,180 kg/h line is 590 kg of polycarbonate per incident."

## 5. Predictive (3:30–4:15) · `demo/index.html`

> "The camera sees what's already wrong. The sensors see what's about to go wrong. Here the system catches a failing dryer heater hours before the first bubble appears."

## 6. How it runs (4:15–4:40) · `showcase/index.html`, "How it runs at the line"

> "It all runs offline on a Qualcomm device next to the machine. The AI recognises the problem, and the instructions always come from the line's own manual, so it never invents a step."

## 7. Close (4:40–5:00)

> "Faster fixes, less scrap, and the expert's knowledge on every shift."

State the ask, e.g. a pilot on one line.

## If judges ask

- **Are the videos real?** No, they're AI-generated illustrations.
- **Is the model running live?** The page shows scripted diagnoses from the knowledge base. The model runs locally; connecting it to the page is the next step (see `docs/ARCHITECTURE.md`).
- **How accurate is it?** The knowledge base is general polycarbonate practice. A plant's process engineer validates it against the real line.
