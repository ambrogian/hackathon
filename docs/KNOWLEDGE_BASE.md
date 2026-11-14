# Polycarbonate (PC) solid sheet extrusion line: troubleshooting knowledge base

> Generic line layout. Zone IDs are referenced by every defect in defects.json. Replace typical values with your line's actual setpoints before using this on a real line.

## Line layout

| Zone | Section | Parts | Typical |
|---|---|---|---|
| Z1 | Resin drying and feeding | dehumidifying dryer, drying hopper, gravimetric dosing / blender, regrind feed | PC dried at about 120 °C for at least 4 h, dew point -40 °C or lower, target moisture below 0.02 % |
| Z2 | Main extruder | feed throat, barrel heating/cooling zones, screw, vacuum vent (degassing port) and vacuum pump, thermocouples | Melt temperature roughly 270-310 °C depending on grade |
| Z3 | Melt filtration | screen changer, screen pack, pressure transducers before/after screen | Watch the pressure difference across the screen; rising difference means the screen is loading up |
| Z4 | Gear pump (melt pump) | gear pump, inlet pressure control loop, outlet pressure transducer | Stable inlet pressure means stable output |
| Z5 | UV co-extruder and feedblock | co-extruder, co-extruder hopper / dosing, feedblock | Thin UV-protective cap layer on one or both surfaces |
| Z6 | Flat sheet die | die body heating zones, flexible lip and lip adjustment bolts, choker bar, die lips | Lip gap set slightly above final thickness; die zones balanced across width |
| Z7 | Polishing roll stack (3-roll calender) | roll 1/2/3, temperature control units (TCUs) per roll, nip gap and gap parallelism, roll drives, gearboxes, bearings, melt bank in the first nip | Roll temperatures roughly 100-140 °C (below PC glass transition, about 147 °C) |
| Z8 | Cooling conveyor (roller table) | idler rollers, ambient cooling / fans | Sheet must cool evenly top and bottom |
| Z9 | Edge trim | edge-trim knives, edge-trim chopper / granulator | PC is notch-sensitive; trim while the sheet is still warm enough |
| Z10 | Protective film laminator | film unwinds (top/bottom), film tension control, laminating nip rolls | Even tension and nip pressure across width |
| Z11 | Haul-off (pull rolls) | rubber-covered pull rolls, haul-off drive, speed ratio to roll stack | Small, stable speed ratio relative to the roll stack |
| Z12 | Cross-cut saw and stacker | cross-cut saw or guillotine, blade, stacker | Sharp blade, correct feed rate, sheet not too cold at cutting |

Diagram: images/candidates/km_sheetline_labeled-04.png + -05.png (KraussMaffei sheet line, labeled; PC lines add the dryer, gear pump and UV co-extruder)

## Safety

- Barrel, adapter and die run at about 300 °C and molten PC causes severe burns: heat-resistant gloves, sleeves and face shield for any work at Z2-Z6.
- Never reach into the roll stack nip (Z7), the laminator nip (Z10) or the haul-off (Z11) while running. These are crushing and draw-in points.
- Die lip cleaning while running only with brass tools, only if your plant procedure allows it, and only by trained operators. Never use steel tools on die lips or polishing rolls.
- Screen changes and any opening of the melt path follow the plant procedure: melt under pressure can spray.
- Saw (Z12) and edge-trim knives (Z9): lockout/tagout before touching blades.
- If in doubt, stop and call the shift lead or maintenance. The assistant gives guidance; it does not replace plant procedures.

## Triage by what you see

| Pattern | Check these defects |
|---|---|
| no sheet in the roll stack: melt pouring off the die or rolls into the tray | melt_dumping_not_threaded |
| continuous straight lines along the sheet (machine direction), fixed position | die_lines, roll_scratches_marks |
| regular evenly spaced lines across the width (transverse) | chatter_marks, thickness_surging_md, sticking_to_rolls |
| random spots or particles in the sheet | moisture_bubbles_splay, black_specks, gels_unmelts_contamination |
| whole-surface color or appearance change | yellowing_degradation, dull_surface_orange_peel |
| wavy, V-shaped or irregular moving marks | flow_lines_bank_marks |
| sheet not flat | warp_bow_stress |
| thickness or optics differ across the width | thickness_variation_cd |
| damage at edges or at cut | edge_and_cut_cracks |
| problems with the masking film | protective_film_defects |
| not visible in a normal photo | uv_layer_defects |

## Defects

### Bubbles, voids and silver streaks (splay) (`moisture_bubbles_splay`)

**What it looks like:** Small round or elongated bubbles inside the sheet, spread across the whole width; silvery streaks running along the sheet. Sheet may look slightly hazy.

**Where it starts:** Z1 Resin drying and feeding, Z2 Main extruder  
**Severity:** scrap

**Likely causes (most likely first):**

- Resin not dry enough: dryer temperature low, dew point too high, or drying time too short for the current output
- Dryer fault: desiccant saturated, regeneration heater failed, air leak in dryer hoses
- Wet or poorly stored regrind added to the feed
- Vacuum vent not degassing: vent port blocked or vacuum pump off/weak

**Operator steps:**

1. Check the dryer panel: actual temperature at setpoint (typical PC about 120 °C) and dew point at -40 °C or lower. Note any dryer alarm.
2. Check drying time: hopper level must give at least about 4 h residence at current output. If the hopper is low, material is going through undried.
3. Check the vacuum gauge on the extruder vent: vacuum present, vent port not blocked with material.
4. Check regrind: stop or reduce wet or open-stored regrind.
5. If available, measure resin moisture (target below 0.02 %).
6. While the dryer recovers, reduce line output to increase drying time. Do not try to fix bubbles by raising melt temperature: it makes PC degrade faster.

**Fixed when:** Bubbles and streaks fade once properly dried material reaches the die. If the dryer was the cause this can take hours, because the hopper is full of wet material.  
**Escalate if:** Dryer alarm, dew point does not recover, or vacuum pump fault: call maintenance.
**Don't confuse with:** yellowing_degradation (gas bubbles from overheating come with yellowing); gels_unmelts_contamination

### Yellowing / thermal degradation (`yellowing_degradation`)

**What it looks like:** Yellow to brown tint across the sheet or in streaks. Compare against a good sample on a white background. Often comes with black specks or bubbles.

**Where it starts:** Z2 Main extruder, Z6 Flat sheet die, Z1 Resin drying and feeding  
**Severity:** scrap

**Likely causes (most likely first):**

- Melt temperature too high
- Material held too long in the extruder or die (output reduced a lot, long stop with heat on)
- One heating zone overshooting: failed thermocouple or controller
- Dryer running too hot or material dried far too long
- Wrong or degraded regrind

**Operator steps:**

1. Compare actual vs setpoint on every barrel, adapter and die zone. Look for one zone running hotter than set or a reading that does not change.
2. Lower melt temperature in steps of 5-10 °C and watch the color.
3. Check output: if it was reduced a lot, residence time went up. Restore output if possible.
4. Check the dryer temperature is not above setpoint.
5. Stop regrind if its color or source is doubtful.

**Fixed when:** Color returns to normal after the degraded material is purged through.  
**Escalate if:** A zone will not control, or a thermocouple reading is implausible: maintenance.
**Don't confuse with:** black_specks

### Black or brown specks (`black_specks`)

**What it looks like:** Small dark particles in the sheet, randomly placed, sometimes in bursts. Often after a restart or a temperature change.

**Where it starts:** Z2 Main extruder, Z3 Melt filtration, Z4 Gear pump (melt pump), Z6 Flat sheet die  
**Severity:** scrap

**Likely causes (most likely first):**

- Burnt material breaking loose from dead spots in screw, adapter, gear pump or die
- Screen pack torn or bypassed
- Contaminated regrind or dirty material handling

**Operator steps:**

1. Check pressure before and after the screen changer. Change the screen if the difference is high, or if it is suddenly low (possible torn screen).
2. Stop regrind and check the hopper and conveying lines for dirt.
3. If specks started after a restart or temperature change, purge: they often clear by themselves within a few minutes to an hour.
4. If specks persist, plan a die and adapter cleaning at the next stop.

**Fixed when:** Speck count drops steadily after screen change or purge.  
**Escalate if:** Specks continue after screen change and purge: die/adapter cleaning needed, involve the process engineer.
**Don't confuse with:** gels_unmelts_contamination; yellowing_degradation

### Gels, unmelted particles, foreign material (`gels_unmelts_contamination`)

**What it looks like:** Clear or whitish specks or lumps ('fish eyes'), sometimes with a small tail; hazy spots from a foreign polymer.

**Where it starts:** Z1 Resin drying and feeding, Z2 Main extruder, Z3 Melt filtration  
**Severity:** scrap

**Likely causes (most likely first):**

- Unmelted pellets: feed and compression zone temperatures too low, or output too high for the screw
- Foreign polymer in the feed (other plastics in regrind, wrong material in hopper)
- Screen pack damaged

**Operator steps:**

1. Check the screen changer pressure difference and change the screen if needed.
2. Check the feed and compression zone temperatures are at setpoint.
3. Check the hopper, dosing and regrind for foreign material or wrong grade.
4. As a test, reduce output slightly: if the particles drop, they are unmelts.

**Fixed when:** Particles disappear after screen change or feed correction.  
**Escalate if:** Wrong material in the feed system: stop feeding and inform the shift lead.
**Don't confuse with:** black_specks; moisture_bubbles_splay

### Die lines (`die_lines`)

**What it looks like:** Thin straight lines running along the sheet (machine direction), at the same position across the width all the time. They do not move and are visible through the sheet, not only on one surface.

**Where it starts:** Z6 Flat sheet die  
**Severity:** quality

**Likely causes (most likely first):**

- Degraded material building up on the die lips
- Particle stuck in the die lip gap
- Nick or scratch on the die lip

**Operator steps:**

1. Measure the line's position from the sheet edge. That is where to look on the die lip.
2. Inspect the die lip at that position.
3. If plant procedure allows, clean the lip at that position with a brass tool, wearing full heat protection. Never use steel.
4. If lines keep coming back, a small increase in die lip temperature can slow build-up.
5. If the lip is damaged, it needs polishing at the next planned stop.

**Fixed when:** Line disappears right after cleaning.  
**Escalate if:** Lip damaged, or lines return within hours: process engineer / maintenance.
**Don't confuse with:** roll_scratches_marks (only on one surface, often sharper); flow_lines_bank_marks (these move and change)

### Thickness variation across the width (`thickness_variation_cd`)

**What it looks like:** Bands of optical distortion along the sheet, wavy look when viewed at an angle; thickness gauge profile not flat; one side thicker than the other.

**Where it starts:** Z6 Flat sheet die, Z7 Polishing roll stack (3-roll calender)  
**Severity:** quality

**Likely causes (most likely first):**

- Die lip gap uneven (lip bolts)
- Die heating zones out of balance across width
- Choker bar setting
- Roll stack gap not parallel (one side tighter)

**Operator steps:**

1. Read the thickness gauge profile, or measure at several points across the width.
2. Thick spot in one place: close the lip bolt(s) at that position by a small step; thin spot: open. Wait for the change to reach the gauge before the next step.
3. Check die zone temperatures across the width: actual vs set.
4. One whole side thick or thin: check roll stack gap on both sides (operator and drive side).

**Fixed when:** Gauge profile flattens within tolerance.  
**Escalate if:** Profile will not respond to bolt adjustments: process engineer.
**Don't confuse with:** thickness_surging_md

### Thickness pulsing along the length (surging) (`thickness_surging_md`)

**What it looks like:** Thickness goes up and down along the sheet, giving bands across the full width that repeat every few seconds to minutes; may look like wide soft transverse waves.

**Where it starts:** Z1 Resin drying and feeding, Z2 Main extruder, Z4 Gear pump (melt pump), Z11 Haul-off (pull rolls)  
**Severity:** quality

**Likely causes (most likely first):**

- Uneven feeding: hopper level low, material bridging
- Melt pressure fluctuating before the gear pump
- Gear pump inlet pressure control not stable
- Roll stack or haul-off speed fluctuating

**Operator steps:**

1. Check the hopper level and material flow at the feed throat.
2. Look at the melt pressure trend before the gear pump: is it cycling at the same rate as the bands?
3. Check the gear pump inlet pressure control loop is stable (not hunting).
4. Check roll stack and haul-off speed readings for fluctuation.

**Fixed when:** Melt pressure trend flat; bands stop.  
**Escalate if:** Control loop hunting or drive speed unstable: maintenance / controls.
**Don't confuse with:** chatter_marks (much finer spacing)

### Chatter marks (`chatter_marks`)

**What it looks like:** Fine, evenly spaced lines across the width, repeating at a regular short interval (millimetres to a few centimetres).

**Where it starts:** Z7 Polishing roll stack (3-roll calender), Z11 Haul-off (pull rolls), Z6 Flat sheet die  
**Severity:** quality

**Likely causes (most likely first):**

- Vibration in the roll stack: drive, gearbox, coupling or bearing
- Haul-off speed not matched to roll stack
- Die too hot, causing stick-slip at the lips

**Operator steps:**

1. Measure the spacing between marks. Compare with roll circumference and drive parts: the matching spacing points to the component.
2. Listen and feel (from a safe position) for noise or vibration at roll drives and bearings.
3. Check die temperature is not above setpoint.
4. Check the speed ratio between roll stack and haul-off.

**Fixed when:** Marks stop after the cause is corrected.  
**Escalate if:** Bearing or gearbox noise: maintenance, before it fails.
**Don't confuse with:** thickness_surging_md; sticking_to_rolls

### Dull surface, haze, orange peel (`dull_surface_orange_peel`)

**What it looks like:** Low gloss or matte patches, uneven reflection, fine bumpy 'orange peel' texture when a light is reflected in the surface.

**Where it starts:** Z7 Polishing roll stack (3-roll calender)  
**Severity:** quality

**Likely causes (most likely first):**

- Polishing rolls too cold
- Melt bank too small, sheet not fully pressed against the roll
- Deposits (plate-out) or damage on the roll surface

**Operator steps:**

1. Check each roll's temperature control unit: actual vs setpoint.
2. Raise polishing roll temperature in small steps.
3. Check the melt bank in the first nip: it should be small and even across the width.
4. Inspect the roll surface for deposits or damage; clean per procedure with approved materials only.

**Fixed when:** Gloss returns within minutes of a roll temperature change.  
**Escalate if:** Roll surface damaged: roll needs re-chroming/polishing, maintenance.
**Don't confuse with:** moisture_bubbles_splay (haze from moisture)

### Flow lines, V-marks, bank marks (`flow_lines_bank_marks`)

**What it looks like:** Wavy, V-shaped or irregular lines that move and change, often near the center or edges.

**Where it starts:** Z7 Polishing roll stack (3-roll calender), Z6 Flat sheet die  
**Severity:** quality

**Likely causes (most likely first):**

- Melt bank in the first nip too big (excess melt rolls over itself)
- Melt bank too small or uneven across width
- Melt temperature too low

**Operator steps:**

1. Look at the melt bank between roll 1 and roll 2 from the safe viewing position.
2. Bank too big: increase roll speed slightly or reduce output. Bank too small: the opposite.
3. Bank uneven across width: adjust die profile (see thickness_variation_cd).
4. Check melt temperature is at setpoint.

**Fixed when:** Bank small and even, marks disappear.  
**Escalate if:** Marks persist with a good bank: process engineer.
**Don't confuse with:** die_lines

### Sheet sticking to rolls (`sticking_to_rolls`)

**What it looks like:** Sheet follows a roll past the normal release point; transverse release marks or tear marks on the surface; release line on the roll is uneven.

**Where it starts:** Z7 Polishing roll stack (3-roll calender)  
**Severity:** quality

**Likely causes (most likely first):**

- Roll temperature too high
- Melt temperature too high
- Speed ratio between rolls wrong

**Operator steps:**

1. Identify which roll the sheet sticks to.
2. Lower that roll's temperature in small steps.
3. Check melt temperature.
4. Check roll speed ratios.

**Fixed when:** Sheet releases cleanly at a straight line.  
**Escalate if:** Roll temperature will not control: maintenance (temperature control unit).
**Don't confuse with:** chatter_marks

### Warp, bow, built-in stress (`warp_bow_stress`)

**What it looks like:** Sheet not flat on the conveyor or stack: edges curling up or down, bowing, waviness. Optical distortion under polarized light.

**Where it starts:** Z7 Polishing roll stack (3-roll calender), Z8 Cooling conveyor (roller table), Z11 Haul-off (pull rolls)  
**Severity:** quality

**Likely causes (most likely first):**

- Top and bottom surfaces cooled unevenly (roll temperatures unbalanced)
- Uneven cooling across the width (drafts, one side hotter)
- Haul-off pulling too hard or too little
- Sheets stacked while still too hot

**Operator steps:**

1. Note which way the sheet curls (up or down) and whether it is edges or center.
2. The side that stays hotter longer shrinks more and ends up on the concave side. Adjust the roll temperatures to even out the two surfaces: make one small change and watch, because the right direction depends on your stack layout.
3. Check for drafts or fans hitting one side of the conveyor.
4. Check the haul-off speed ratio to the roll stack.
5. Check sheets are cool enough before stacking.

**Fixed when:** Sheet lies flat after cooling.  
**Escalate if:** Warp persists after balancing: process engineer.

### Cracked edges, cracks at the cut (`edge_and_cut_cracks`)

**What it looks like:** Cracks starting at the sheet edge or the cut line, chipped or whitened edges, rough cut faces.

**Where it starts:** Z9 Edge trim, Z12 Cross-cut saw and stacker  
**Severity:** scrap

**Likely causes (most likely first):**

- Edge trimming or cutting when the sheet is too cold (PC cracks easily from a notch)
- Dull or damaged trim knives or saw blade
- Wrong saw speed or feed rate

**Operator steps:**

1. Check trim knives and saw blade condition (lockout first). Replace if dull or chipped.
2. Check the sheet temperature at trim and saw positions; trim warmer if possible.
3. Check saw speed and feed rate settings.

**Fixed when:** Clean edges and cut faces.  
**Escalate if:** Blade or knife damage repeating: maintenance.

### Protective (masking) film defects (`protective_film_defects`)

**What it looks like:** Wrinkles or trapped air bubbles under the masking film, film not covering the edge, film lifting or misaligned.

**Where it starts:** Z10 Protective film laminator  
**Severity:** quality

**Likely causes (most likely first):**

- Film unwind tension too high or too low
- Laminating nip pressure too low or uneven
- Film roll misaligned
- Sheet too hot or too cold at the laminator

**Operator steps:**

1. Check film unwind tension; adjust in small steps.
2. Check laminating nip pressure on both sides.
3. Check film roll alignment to the sheet.
4. Check sheet temperature at the laminator.

**Fixed when:** Film lies flat with no trapped air.  
**Escalate if:** Tension control not working: maintenance.

### Roll scratches and repeating roll marks (`roll_scratches_marks`)

**What it looks like:** Sharp lines along the sheet on one surface only, or marks that repeat at a fixed distance along the sheet.

**Where it starts:** Z7 Polishing roll stack (3-roll calender), Z8 Cooling conveyor (roller table), Z11 Haul-off (pull rolls)  
**Severity:** quality

**Likely causes (most likely first):**

- Damage or deposit on a polishing roll
- Debris on a conveyor roller or haul-off roll
- A roller not turning and the sheet sliding over it

**Operator steps:**

1. Measure the distance between repeating marks and compare it with roll circumferences to find the roll.
2. Check which surface (top or bottom) has the mark to narrow down which rolls touch it.
3. Check conveyor rollers turn freely and are clean.
4. Inspect the identified roll surface.

**Fixed when:** Marks stop after cleaning or fixing the roll.  
**Escalate if:** Polishing roll damaged: maintenance.
**Don't confuse with:** die_lines (visible through the sheet, fixed position)

### UV layer missing or uneven (`uv_layer_defects`)

**What it looks like:** Not visible in a normal photo. Under a UV lamp the protected surface looks different; gaps show as bright or dark areas.

**Where it starts:** Z5 UV co-extruder and feedblock  
**Severity:** scrap

**Likely causes (most likely first):**

- Co-extruder hopper empty or dosing stopped
- Co-extruder stopped or running at wrong speed
- Feedblock settings, or viscosity mismatch between layers

**Operator steps:**

1. Check the co-extruder is running and its hopper has material.
2. Check the UV layer across the width with a UV lamp.
3. Check co-extruder speed and feedblock settings against the recipe.

**Fixed when:** UV lamp check shows even coverage.  
**Escalate if:** Coverage uneven with co-extruder running correctly: process engineer.

### Melt dumping / sheet not threaded into roll stack (`melt_dumping_not_threaded`)

**What it looks like:** The melt curtain leaving the flat sheet die (Z6) is not entering the first nip of the polishing roll stack (Z7), or the sheet has broken at the rolls. Molten polycarbonate is pouring or piling off the die lips or rolls into the catch tray below.

**Where it starts:** Z6 Flat sheet die, Z7 Polishing roll stack (3-roll calender)  
**Severity:** line_stop

**Likely causes (most likely first):**

- Line is in startup and the melt curtain has not yet been threaded into the polishing roll stack (Z7)
- Sheet break at the roll stack (Z7) or downstream at the haul-off (Z11) caused by a speed mismatch, roll drive trip, or cold/stuck wrap on roll 1/2/3
- Roll stack (Z7) retracted or nip gap opened too wide, letting the melt curtain drop straight through
- Sudden melt viscosity drop or pressure surge from the gear pump (Z4) / extruder (Z2) tearing the curtain before it reaches the first nip

**Operator steps:**

1. Keep hands and tools completely clear of the roll stack nip (Z7) and die lips (Z6). Never reach into a running nip or touch the hot die (around 300 °C) to guide molten plastic.
2. Wear heat-resistant gloves, sleeves, and a face shield before approaching Z6-Z7.
3. Call the shift lead immediately to coordinate a safe line slowdown, stop, or re-threading.
4. Follow the plant's threading procedure: reduce extruder/gear pump (Z4) output or put the line in safe standby/purge as instructed, and retract the roll stack (Z7) if required by procedure.
5. Check roll stack (Z7) drives, nip gap, and roll temperatures (TCUs) to confirm why the sheet broke or failed to feed before attempting to re-thread.
6. Allow purged molten PC in the catch tray to cool safely per plant procedure before clearing, and re-thread only with trained crew using the approved threading tools and procedure.

**Fixed when:** The melt curtain feeds cleanly into the first nip of the polishing roll stack (Z7), forms a stable melt bank across the width, and the sheet travels smoothly through the roll stack and haul-off (Z11) with no material dropping into the catch tray.  
**Escalate if:** Roll drives, gearboxes, or TCUs at Z7 fault or will not hold speed/gap, or if the curtain repeatedly tears during threading: keep the line in safe standby and call maintenance and the shift lead.
**Don't confuse with:** sticking_to_rolls
